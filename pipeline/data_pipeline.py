import logging
import os
import pandas as pd
import numpy as np
import requests
from datetime import datetime, date
import pyarrow.parquet as pq
from sqlalchemy import text

from scrapers.stock_scraper import FinMindData, GoogleNewsData
from db.engine import engine
from pipeline.warning_calculator import calculate_and_save_warnings
from pipeline.indicators import compute_indicators

# 引入已重構拆分的各子模組
from config.settings import STOCK_LIST
from pipeline.db_writer import get_last_date, idempotent_to_sql
from pipeline.sentiment import get_finbert_sentiment
from pipeline.tdcc_scraper import download_tdcc_weekly_shares, aggregate_weekly_holding

# 設定日誌格式並輸出到專案根目錄的 log 檔案與主控台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("history.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

FD = FinMindData()
GD = GoogleNewsData()

# 使用統一管理的股票清單
stockbasedata = pd.DataFrame({
   'StockCode' : STOCK_LIST
})

def update_daily_metrics(today_str):
    """抓取並更新 StockDailyMetrics & StockWeeklyConcentration"""
    for stock_code in stockbasedata['StockCode']:
        logging.info(f"--- 處理個股 {stock_code} ---")
        
        last_daily = get_last_date(stock_code, 'StockDailyMetrics', 'StockDate', default_years=1)
        logging.info(f"日K與籌碼起始時間: {last_daily} -> {today_str}")
        
        # 1. 抓取日量價與日籌碼
        price_df = FD.stock_price_info(stock_code, last_daily, today_str)
        investor_df = FD.stock_investors_buy_info(stock_code, last_daily, today_str)
        margin_df = FD.stock_margin_info(stock_code, last_daily, today_str)
        
        if price_df.empty:
            logging.warning(f"股票 {stock_code} 無價格資料，跳過")
            continue
            
        # 格式化日期與代碼
        price_df['StockDate'] = pd.to_datetime(price_df['date']).dt.date
        price_df = price_df.rename(columns={'stock_id': 'StockCode', 'close': 'StockClose', 'Trading_Volume': 'TradingVolume', 'Trading_money': 'TradingMoney'})
        price_df = price_df[['StockCode', 'StockDate', 'StockClose', 'TradingVolume', 'TradingMoney']]
        
        # 處理三大法人買賣超
        daily_investor = []
        if not investor_df.empty:
            investor_df['StockDate'] = pd.to_datetime(investor_df['date']).dt.date
            investor_df['NetBuy'] = investor_df['buy'] - investor_df['sell']
            
            # 按日期分組
            for d, group in investor_df.groupby('StockDate'):
                foreign = group[group['name'].str.contains('Foreign|外資', na=True, case=False)]['NetBuy'].sum()
                trust = group[group['name'].str.contains('Trust|投信', na=True, case=False)]['NetBuy'].sum()
                dealer = group[group['name'].str.contains('Dealer|自營商', na=True, case=False)]['NetBuy'].sum()
                daily_investor.append({
                    'StockDate': d,
                    'ForeignNetBuy': foreign,
                    'TrustNetBuy': trust,
                    'DealerNetBuy': dealer
                })
        investor_summary = pd.DataFrame(daily_investor) if daily_investor else pd.DataFrame(columns=['StockDate', 'ForeignNetBuy', 'TrustNetBuy', 'DealerNetBuy'])
        
        # 處理融資券
        if not margin_df.empty:
            margin_df['StockDate'] = pd.to_datetime(margin_df['date']).dt.date
            margin_df = margin_df.rename(columns={'MarginPurchaseTodayBalance': 'MarginBalance', 'ShortSaleTodayBalance': 'ShortBalance'})
            margin_df = margin_df[['StockDate', 'MarginBalance', 'ShortBalance']]
        else:
            margin_df = pd.DataFrame(columns=['StockDate', 'MarginBalance', 'ShortBalance'])
            
        # 整合每日數據
        daily_metrics = price_df.copy()
        if not investor_summary.empty:
            daily_metrics = pd.merge(daily_metrics, investor_summary, on='StockDate', how='left')
        else:
            daily_metrics['ForeignNetBuy'] = 0
            daily_metrics['TrustNetBuy'] = 0
            daily_metrics['DealerNetBuy'] = 0
            
        if not margin_df.empty:
            daily_metrics = pd.merge(daily_metrics, margin_df, on='StockDate', how='left')
        else:
            daily_metrics['MarginBalance'] = 0
            daily_metrics['ShortBalance'] = 0
            
        daily_metrics = daily_metrics.fillna(0)
        
        # 2. 計算技術指標
        try:
            hist_query = text('SELECT "StockCode", "StockDate", "StockClose", "TradingVolume", "TradingMoney", "ForeignNetBuy", "TrustNetBuy", "DealerNetBuy", "MarginBalance", "ShortBalance" FROM "StockDailyMetrics" WHERE "StockCode" = :stock_id ORDER BY "StockDate" DESC LIMIT 65')
            hist_df = pd.read_sql(hist_query, con=engine, params={"stock_id": stock_code})
            if not hist_df.empty:
                hist_df['StockDate'] = pd.to_datetime(hist_df['StockDate']).dt.date
                combined = pd.concat([hist_df, daily_metrics]).drop_duplicates(subset=['StockDate']).sort_values('StockDate').reset_index(drop=True)
                combined = compute_indicators(combined)
                new_dates = set(daily_metrics['StockDate'])
                daily_metrics_processed = combined[combined['StockDate'].isin(new_dates)]
            else:
                daily_metrics_processed = compute_indicators(daily_metrics)
        except Exception as e:
            logging.error(f"計算指標歷史拼接錯誤: {e}", exc_info=True)
            daily_metrics_processed = compute_indicators(daily_metrics)
            
        # 3. 寫入每日時序表
        idempotent_to_sql(daily_metrics_processed, 'StockDailyMetrics', ['StockCode', 'StockDate'])
        
        # 4. 抓取股權集中度 (週頻率)
        last_weekly = get_last_date(stock_code, 'StockWeeklyConcentration', 'UpdateDate', default_years=1)
        logging.info(f"週大戶比例起始時間: {last_weekly} -> {today_str}")
        weekly_raw = FD.stock_holding_shares_info(stock_code, last_weekly, today_str)
        if not weekly_raw.empty:
            weekly_clean = aggregate_weekly_holding(weekly_raw, stock_code)
            idempotent_to_sql(weekly_clean, 'StockWeeklyConcentration', ['StockCode', 'UpdateDate'])
        else:
            logging.warning(f"FinMind API 未回傳個股 {stock_code} 的週股權集中度資料 (回傳空值)，嘗試自集保結算所 (TDCC) 開放資料下載...")
            weekly_raw = download_tdcc_weekly_shares(stock_code)
            if not weekly_raw.empty:
                weekly_clean = aggregate_weekly_holding(weekly_raw, stock_code)
                idempotent_to_sql(weekly_clean, 'StockWeeklyConcentration', ['StockCode', 'UpdateDate'])

def update_fundamentals(today_str):
    """更新三大基本面報表、營收、股息"""
    for stock_code in stockbasedata['StockCode']:
        last_revenue = get_last_date(stock_code, 'StockRevenue', 'RevenueYear', default_years=1)
        # 月營收
        rev_raw = FD.stock_revenue_info(stock_code, f"{last_revenue.split('-')[0]}-01-01", today_str)
        if not rev_raw.empty:
            rev_raw = rev_raw.rename(columns={'stock_id': 'StockCode', 'revenue_year': 'RevenueYear', 'revenue_month': 'RevenueMonth', 'revenue': 'TotalRevenue'})
            rev_raw = rev_raw[['StockCode', 'RevenueYear', 'RevenueMonth', 'TotalRevenue']].drop_duplicates()
            idempotent_to_sql(rev_raw, 'StockRevenue', ['StockCode', 'RevenueYear', 'RevenueMonth'])
            
        # 股利
        div_raw = FD.stock_dividend_info(stock_code, "2020-01-01", today_str)
        if not div_raw.empty:
            div_raw = div_raw.rename(columns={'stock_id': 'StockCode', 'year': 'DateInfo',
                                              'CashExDividendTradingDate': 'ExDividendDate',
                                              'CashDividendPaymentDate': 'CashDividendDate'})
            div_raw['CashDividends'] = pd.to_numeric(div_raw['StockEarningsDistribution'], errors='coerce').fillna(0) + pd.to_numeric(div_raw['StockStatutorySurplus'], errors='coerce').fillna(0)
            div_raw['StockDividend'] = pd.to_numeric(div_raw['CashEarningsDistribution'], errors='coerce').fillna(0) + pd.to_numeric(div_raw['CashStatutorySurplus'], errors='coerce').fillna(0)
            div_clean = div_raw[['StockCode', 'DateInfo', 'CashDividends', 'StockDividend', 'ExDividendDate', 'CashDividendDate']].dropna(subset=['ExDividendDate', 'CashDividendDate'])
            div_clean = div_clean[(div_clean['ExDividendDate'] != '') & (div_clean['CashDividendDate'] != '')]
            idempotent_to_sql(div_clean, 'StockDividend', ['StockCode', 'DateInfo'])

        # 財務三表
        for table, fetch_fn in [('StockFinancial', FD.stock_financial_info), 
                                ('StockBalance', FD.stock_balance_info), 
                                ('StockCashflow', FD.stock_cashflow_info)]:
            last_date = get_last_date(stock_code, table, 'DateInfo', default_years=2)
            raw = fetch_fn(stock_code, last_date, today_str)
            if not raw.empty:
                raw['DateInfo'] = pd.to_datetime(raw['date']).dt.date
                raw = raw.rename(columns={'stock_id': 'StockCode', 'type': 'Types', 'value': 'DataValue', 'origin_name': 'OriginName'})
                raw = raw[['StockCode', 'DateInfo', 'Types', 'DataValue', 'OriginName']].drop_duplicates()
                idempotent_to_sql(raw, table, ['StockCode', 'DateInfo', 'Types'])

def update_news(today_str):
    """抓取 Google 新聞，分析情緒並寫入"""
    try:
        with engine.connect() as conn:
            companydata = pd.read_sql(text('SELECT "StockCode", "CompanyNameAbbr", "CompanyNameC" FROM "CompanyBaseInfo"'), con=engine)
    except Exception as e:
        logging.warning(f"從資料庫載入公司基本資訊錯誤: {e}。使用預設名稱與簡稱對照。")
        companydata = pd.DataFrame({
            'StockCode': STOCK_LIST,
            'CompanyNameAbbr': ['台積電', '鴻海', '聯發科', '台達電', '廣達', '中信金', '富邦金', '日月光投控', '國泰金', '中華電'],
            'CompanyNameC': ['台灣積體電路製造股份有限公司', '鴻海精密工業股份有限公司', '聯發科技股份有限公司', '台達電子工業股份有限公司', '廣達電腦股份有限公司', '中國信託金融控股股份有限公司', '富邦金融控股股份有限公司', '日月光投資控股股份有限公司', '國泰金融控股股份有限公司', '中華電信股份有限公司']
        })
        
    for idx, row in companydata.iterrows():
        stock_code = row['StockCode']
        kw = row.get('CompanyNameAbbr')
        if not kw or pd.isna(kw):
            kw = row.get('CompanyNameC')
        if not kw or pd.isna(kw):
            kw = stock_code
        
        # 取得該股新聞資料的最新時間 (MAX) 作為新聞起始日期以進行增量更新，若無則回推 90 天
        try:
            with engine.connect() as conn:
                max_date_val = conn.execute(
                    text('SELECT MAX("PublishTime") FROM "StockNews" WHERE "StockCode" = :stock_id'),
                    {"stock_id": stock_code}
                ).scalar()
            if max_date_val is not None:
                if isinstance(max_date_val, (datetime, date)):
                    start_date = max_date_val.strftime('%Y-%m-%d')
                else:
                    start_date = str(max_date_val)[:10]
            else:
                start_date = (date.today() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
        except Exception as e:
            logging.error(f"查詢最新新聞日期錯誤: {e}", exc_info=True)
            start_date = (date.today() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
        
        logging.info(f"抓取 {kw} ({stock_code}) 新聞 (增量更新起始時間: {start_date} -> {today_str})...")
        
        news_df_hist = GD.google_news_search(kw, "TW", start_date, today_str)
        recent_start = (date.today() - pd.Timedelta(days=7)).strftime('%Y-%m-%d')
        news_df_recent = GD.google_news_search(kw, "TW", recent_start, today_str)
        
        # 合併與去重
        if news_df_hist.empty and news_df_recent.empty:
            news_df = pd.DataFrame()
        elif news_df_hist.empty:
            news_df = news_df_recent
        elif news_df_recent.empty:
            news_df = news_df_hist
        else:
            news_df = pd.concat([news_df_recent, news_df_hist]).drop_duplicates(subset=['link'])
            
        if not news_df.empty:
            news_df['StockCode'] = stock_code
            news_df = news_df.rename(columns={'published': 'PublishTime', 'link': 'NewsLink', 'title': 'Title'})
            
            # 格式化 PublishTime 為 Timestamp 物件
            def safe_format_time(val):
                try:
                    return pd.to_datetime(val)
                except Exception:
                    return pd.NaT
            news_df['PublishTime'] = news_df['PublishTime'].apply(safe_format_time)
            
            import uuid
            news_df['NewsId'] = [str(uuid.uuid4()) for _ in range(len(news_df))]
            news_df['Content'] = ""
            news_df['SentimentScore'] = news_df['Title'].apply(get_finbert_sentiment)
            news_df = news_df[['NewsId', 'StockCode', 'Title', 'Content', 'PublishTime', 'NewsLink', 'SentimentScore']].drop_duplicates(subset=['NewsLink'])
            
            idempotent_to_sql(news_df, 'StockNews', ['StockCode', 'NewsLink'])

def init_warning_thresholds():
    """初始化 CompanyWarningThresholds 閥值表"""
    logging.info("--- 初始化財務防雷閾值 ---")
    for stock_code in stockbasedata['StockCode']:
        try:
            with engine.connect() as conn:
                check = conn.execute(text('SELECT 1 FROM "CompanyWarningThresholds" WHERE "StockCode" = :stock_id'), {"stock_id": stock_code}).fetchone()
                if check:
                    logging.info(f"個股 {stock_code} 的閥值已存在，跳過初始化。")
                    continue
                
                default_thresholds = {
                    "StockCode": stock_code,
                    "MinEarningsQualityRatio": 80.00,
                    "MaxReceivableTurnoverDays": 120.00,
                    "MaxInventoryTurnoverDays": 150.00,
                    "MaxDebtRatio": 60.00,
                    "MinInterestCoverage": 3.00
                }
                
                try:
                    debt_query = text("""
                        SELECT a."DateInfo", 
                               MAX(CASE WHEN (a."Types" = 'Liabilities' OR a."OriginName" = '負債總額') AND a."Types" NOT LIKE '%_per' THEN a."DataValue" END) as debt,
                               MAX(CASE WHEN (a."Types" = 'TotalAssets' OR a."OriginName" = '資產總額') AND a."Types" NOT LIKE '%_per' THEN a."DataValue" END) as assets
                        FROM "StockBalance" a
                        WHERE a."StockCode" = :stock_id
                        GROUP BY a."DateInfo"
                        HAVING MAX(CASE WHEN (a."Types" = 'TotalAssets' OR a."OriginName" = '資產總額') AND a."Types" NOT LIKE '%_per' THEN a."DataValue" END) > 0
                        ORDER BY a."DateInfo" DESC LIMIT 12
                    """)
                    debts = pd.read_sql(debt_query, con=engine, params={"stock_id": stock_code})
                    if not debts.empty:
                        ratios = debts['debt'] / debts['assets'] * 100
                        median_debt = ratios.median()
                        std_debt = ratios.std()
                        default_thresholds["MaxDebtRatio"] = float(round(max(median_debt + 1.5 * (std_debt if not pd.isna(std_debt) else 5), 60.00), 2))
                except Exception as e:
                    logging.error(f"計算個股 {stock_code} 負債比率歷史中位數失敗，使用預設值: {e}")
                    
                insert_query = text("""
                    INSERT INTO "CompanyWarningThresholds" 
                    ("StockCode", "MinEarningsQualityRatio", "MaxReceivableTurnoverDays", "MaxInventoryTurnoverDays", "MaxDebtRatio", "MinInterestCoverage")
                    VALUES (:StockCode, :MinEarningsQualityRatio, :MaxReceivableTurnoverDays, :MaxInventoryTurnoverDays, :MaxDebtRatio, :MinInterestCoverage)
                """)
                conn.execute(insert_query, default_thresholds)
                conn.commit()
                logging.info(f"個股 {stock_code} 防雷閥值初始化成功: {default_thresholds}")
                
        except Exception as e:
            logging.error(f"初始化個股 {stock_code} 閥值出錯: {e}", exc_info=True)

def update_warning_indicators():
    """計算並更新季度財務警示指標"""
    logging.info("--- 計算季度財務防雷指標與警報標記 ---")
    for stock_code in stockbasedata['StockCode']:
        success = calculate_and_save_warnings(stock_code, engine)
        if success:
            logging.info(f"個股 {stock_code} 季度防雷指標更新成功。")
        else:
            logging.warning(f"個股 {stock_code} 季度防雷指標更新失敗。")

def update_company_base_info():
    """從 TWSE Open API 下載並同步公司基本資料 (P1-1、P1-2、P1-3)"""
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    logging.info("開始自 TWSE OpenAPI 下載公司基本資料...")
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        raw_data = res.json()
        
        # 篩選特定公司代號
        filtered_data = [item for item in raw_data if str(item.get("公司代號", "")).strip() in STOCK_LIST]
        
        if not filtered_data:
            logging.warning("TWSE API 回傳的公司基本資料中無符合 STOCK_LIST 的個股。")
            return
            
        # 標準 TWSE 產業別代號對照 (對應 CompanyClass)
        industry_map = {
            "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
            "05": "電機機械", "06": "電器電纜", "07": "化學工業", "08": "玻璃陶瓷",
            "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業",
            "13": "電子工業", "14": "建材營造", "15": "航運業", "16": "觀光餐旅",
            "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他",
            "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
            "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業", "28": "電子零組件業",
            "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業", "32": "文化創意業",
            "33": "農業科技業", "34": "電子商務", "35": "綠能環保", "36": "數位雲端",
            "37": "運動休閒", "38": "居家生活"
        }
        
        rows = []
        for item in filtered_data:
            # 轉換日期格式 YYYYMMDD -> YYYY-MM-DD
            def parse_date(date_str):
                if not date_str:
                    return None
                date_str = str(date_str).strip()
                try:
                    return pd.to_datetime(date_str, format='%Y%m%d').date()
                except Exception:
                    return None
                    
            est_date = parse_date(item.get("成立日期"))
            lst_date = parse_date(item.get("上市日期"))
            
            industry_code = str(item.get("產業別", "")).strip()
            industry_name = industry_map.get(industry_code, "其他")
            
            rows.append({
                "StockCode": str(item.get("公司代號", "")).strip(),
                "CompanyNameC": str(item.get("公司名稱", "")).strip(),
                "CompanyNameAbbr": str(item.get("公司簡稱", "")).strip(),
                "CompanyNameE": str(item.get("英文簡稱", "")).strip(),
                "ChairmanName": str(item.get("董事長", "")).strip(),
                "EstablishmentDate": est_date,
                "ListingDate": lst_date,
                "CompanyClass": industry_name,
                "Webside": str(item.get("網址", "")).strip(),
                "CompanyEmail": str(item.get("電子郵件信箱", "")).strip(),
                "GeneralManager": str(item.get("總經理", "")).strip(),
                "CompanyAddress": str(item.get("住址", "")).strip(),
                "MarketClass": "上市",
                "MainBusinessActivities": "主要業務詳見公司官網"
            })
            
        company_df = pd.DataFrame(rows)
        idempotent_to_sql(company_df, 'CompanyBaseInfo', ['StockCode'])
        logging.info("TWSE 公司基本資訊下載與同步完成！")
        
    except Exception as e:
        logging.error(f"從 TWSE OpenAPI 下載或同步公司基本資訊失敗: {e}", exc_info=True)
        # 降級備用機制：若 API 失敗，嘗試讀取 Parquet
        logging.info("嘗試使用本地備用 parquet 檔案同步公司基本資訊...")
        try:
            companydata = pq.read_table(os.getenv('COMPANY_PARQUET_PATH', 'company_baseinfo.parquet')).to_pandas()
            companydata = companydata.rename(columns={'ListingDate': 'ListingDateTemp', 'EstablishmentDate': 'EstablishmentDateTemp'})
            companydata['ListingDate'] = pd.to_datetime(companydata['ListingDateTemp']).dt.date
            companydata['EstablishmentDate'] = pd.to_datetime(companydata['EstablishmentDateTemp']).dt.date
            companydata = companydata.drop(columns=['ListingDateTemp', 'EstablishmentDateTemp', 'Dataid'], errors='ignore')
            if 'CompanyNameAbbr' not in companydata.columns:
                companydata['CompanyNameAbbr'] = companydata['CompanyNameC']
            idempotent_to_sql(companydata, 'CompanyBaseInfo', ['StockCode'])
            logging.info("本地備用公司基本資訊同步完成。")
        except Exception as pe:
            logging.error(f"本地備用公司基本資訊同步亦失敗: {pe}", exc_info=True)

def update_data():
    todayinfo = date.today().strftime('%Y-%m-%d')
    logging.info(f"====== 開始盤後資料更新管線: {todayinfo} ======")
    
    # 檢測資料庫當中是否已經有包含當天資料 (P1-8 自選股增量優化)
    today_date = date.today()
    try:
        with engine.connect() as conn:
            # 檢查是否所有在 STOCK_LIST 中的股票都已經有當日的量價資料
            all_updated = True
            for s_code in STOCK_LIST:
                cnt = conn.execute(
                    text('SELECT COUNT(*) FROM "StockDailyMetrics" WHERE "StockCode" = :s_code AND "StockDate" >= :today'),
                    {"s_code": s_code, "today": today_date}
                ).scalar()
                if cnt == 0:
                    all_updated = False
                    break
                    
            # 取得整體資料的最新日期 (僅用於日誌說明)
            max_date = conn.execute(text('SELECT MAX("StockDate") FROM "StockDailyMetrics"')).scalar()
            if max_date is not None:
                if isinstance(max_date, str):
                    max_date_obj = datetime.strptime(max_date, '%Y-%m-%d').date()
                else:
                    max_date_obj = max_date
            else:
                max_date_obj = date.min
            
            with engine.connect() as conn:
                weekly_cnt = conn.execute(text('SELECT COUNT(*) FROM "StockWeeklyConcentration"')).scalar()
                
        if all_updated and weekly_cnt > 0:
            logging.info("自選股清單中的所有股票皆已包含今日資料，跳過股價與基本面更新。")
            logging.info("--- 執行今日新聞增量更新 ---")
            try:
                update_news(todayinfo)
            except Exception as ne:
                logging.error(f"更新今日新聞失敗: {ne}", exc_info=True)
            logging.info("====== 盤後資料更新已跳過！ ======")
            return
        else:
            logging.info(f"資料庫中有未更新的自選股，將繼續執行更新 (資料庫最新日期為 {max_date_obj.strftime('%Y-%m-%d') if max_date_obj != date.min else '無資料'})")
    except Exception as e:
        logging.error(f"檢測資料庫今日資料狀態時出錯，將繼續完整更新: {e}", exc_info=True)
    
    # 0. 同步公司基本資訊
    update_company_base_info()
        
    # 1. 更新日量價與日週籌碼
    update_daily_metrics(todayinfo)
    
    # 2. 更新財報基本面
    update_fundamentals(todayinfo)
    
    # 3. 更新新聞與情緒
    update_news(todayinfo)
    
    # 4. 初始化自訂防雷閥值表
    init_warning_thresholds()
    
    # 5. 計算警訊指標
    update_warning_indicators()
    
    logging.info("====== 盤後資料更新完成！ ======")

if __name__ == "__main__":
    update_data()
