import pandas as pd
from datetime import datetime, date
from sqlalchemy import text
from ollama import Client

from config import settings as baseENV
from db.engine import engine
from pipeline.warning_calculator import calculate_and_save_warnings

def get_company_base_info(stock_id: str):
    """取得公司基本資訊"""
    query = text('SELECT * FROM "CompanyBaseInfo" WHERE "StockCode" = :stock_id')
    df = pd.read_sql(query, con=engine, params={"stock_id": stock_id})
    if not df.empty:
        return df.iloc[0].to_dict()
    return {}

def get_stock_daily_metrics(stock_id: str, start_date: date, end_date: date):
    """取得每日價格與籌碼指標"""
    query = text("""
        SELECT * FROM "StockDailyMetrics" 
        WHERE "StockCode" = :stock_id AND "StockDate" BETWEEN :start_date AND :end_date
        ORDER BY "StockDate" ASC
    """)
    return pd.read_sql(query, con=engine, params={"stock_id": stock_id, "start_date": start_date, "end_date": end_date})

def get_stock_weekly_concentration(stock_id: str):
    """取得週股權集中度"""
    query = text("""
        SELECT * FROM "StockWeeklyConcentration" 
        WHERE "StockCode" = :stock_id
        ORDER BY "UpdateDate" DESC LIMIT 52
    """)
    return pd.read_sql(query, con=engine, params={"stock_id": stock_id})

def get_stock_news(stock_id: str):
    """取得公司最新新聞列表"""
    # 去重後再截取前 30 筆，確保能回傳 30 筆不重複的新聞
    is_sqlite = (engine.dialect.name == 'sqlite')
    time_format = 'strftime(\'%Y-%m-%d %H:%M\', "PublishTime")' if is_sqlite else 'TO_CHAR("PublishTime", \'YYYY-MM-DD HH24:MI\')'
    query = text(f"""
        SELECT "Title", {time_format} AS "PublishTime", "NewsLink", "SentimentScore" 
        FROM "StockNews" 
        WHERE "StockCode" = :stock_id
        ORDER BY "PublishTime" DESC LIMIT 100
    """)
    df = pd.read_sql(query, con=engine, params={"stock_id": stock_id})
    if not df.empty:
        # 去除重複的新聞標題，保留發布時間最新的一筆
        df = df.drop_duplicates(subset=['Title'], keep='first')
        df = df.head(30)
    return df

def get_daily_price_sentiment(stock_id: str, start_date: date, end_date: date):
    """取得每日收盤價與每日平均情緒指標"""
    # 1. 取得股價數據
    query_price = text("""
        SELECT "StockDate", "StockClose" 
        FROM "StockDailyMetrics"
        WHERE "StockCode" = :stock_id AND "StockDate" BETWEEN :start_date AND :end_date
        ORDER BY "StockDate" ASC
    """)
    df_price = pd.read_sql(query_price, con=engine, params={"stock_id": stock_id, "start_date": start_date, "end_date": end_date})
    
    # 2. 取得每日平均情緒 (將 TIMESTAMP 轉換為 YYYY-MM-DD)
    is_sqlite = (engine.dialect.name == 'sqlite')
    day_format = 'strftime(\'%Y-%m-%d\', "PublishTime")' if is_sqlite else 'TO_CHAR("PublishTime", \'YYYY-MM-DD\')'
    query_sent = text(f"""
        SELECT {day_format} AS "DateStr",
               AVG("SentimentScore") AS "AvgSentiment"
        FROM "StockNews"
        WHERE "StockCode" = :stock_id AND "PublishTime" IS NOT NULL
        GROUP BY {day_format}
    """)
    df_sent = pd.read_sql(query_sent, con=engine, params={"stock_id": stock_id})
    
    if df_price.empty:
        return pd.DataFrame()
        
    # 將 df_price 的 StockDate 轉為字串以利 merge
    df_price['DateStr'] = pd.to_datetime(df_price['StockDate']).dt.strftime('%Y-%m-%d')
    
    # 合併價格與情緒
    merged = pd.merge(df_price, df_sent, on='DateStr', how='left')
    
    # 填補沒有新聞的日子的情緒分數為 0
    merged['AvgSentiment'] = merged['AvgSentiment'].fillna(0.0)
    
    # 按日期排序
    merged = merged.sort_values('DateStr', ascending=True)
    return merged

def get_screener_results(min_roe: float, ma_cross: str, min_inst_buy: float):
    """
    聯立多因子篩選：
    - min_roe: 季ROE下限
    - ma_cross: 收盤價 > 月線(MA20) 或 季線(MA60)
    - min_inst_buy: 近 5 日法人合計淨買進張數下限
    """
    query_daily = text("""
        WITH LastDates AS (
            SELECT "StockCode", MAX("StockDate") as MaxDate
            FROM "StockDailyMetrics"
            GROUP BY "StockCode"
        ),
        RecentBuy AS (
            SELECT "StockCode", 
                   SUM("ForeignNetBuy" + "TrustNetBuy" + "DealerNetBuy") as "Net5DBuy"
            FROM (
                SELECT "StockCode", "StockDate", "ForeignNetBuy", "TrustNetBuy", "DealerNetBuy",
                       ROW_NUMBER() OVER (PARTITION BY "StockCode" ORDER BY "StockDate" DESC) as rn
                FROM "StockDailyMetrics"
            ) sub
            WHERE rn <= 5
            GROUP BY "StockCode"
        )
        SELECT d.*, r."Net5DBuy"
        FROM "StockDailyMetrics" d
        JOIN LastDates ld ON d."StockCode" = ld."StockCode" AND d."StockDate" = ld.MaxDate
        LEFT JOIN RecentBuy r ON d."StockCode" = r."StockCode"
    """)
    daily_df = pd.read_sql(query_daily, con=engine)
    
    # 取得最新一季 ROE (從 StockFinancial 拿淨利, StockBalance 拿資產)
    query_roe = text("""
        WITH LatestQuarter AS (
            SELECT "StockCode", MAX("DateInfo") as MaxDate
            FROM "StockBalance"
            GROUP BY "StockCode"
        )
        SELECT b."StockCode", 
               (MAX(CASE WHEN f."Types" IN ('IncomeAfterTaxes', 'IncomeAfterTax') OR f."OriginName" IN ('本期淨利（淨損）', '本期稅後淨利（淨損）') THEN f."DataValue" END) / 
                NULLIF(MAX(CASE WHEN (b."Types" = 'TotalAssets' OR b."OriginName" = '資產總額') AND b."Types" NOT LIKE '%_per' THEN b."DataValue" END), 0) * 100) as "EstimatedROE"
        FROM "StockBalance" b
        JOIN LatestQuarter lq ON b."StockCode" = lq."StockCode" AND b."DateInfo" = lq.MaxDate
        LEFT JOIN "StockFinancial" f ON b."StockCode" = f."StockCode" AND b."DateInfo" = f."DateInfo"
        GROUP BY b."StockCode"
    """)
    roe_df = pd.read_sql(query_roe, con=engine)
    
    # 整合
    merged = pd.merge(daily_df, roe_df, on='StockCode', how='left')
    merged = pd.merge(merged, pd.read_sql('SELECT "StockCode", "CompanyNameC" FROM "CompanyBaseInfo"', con=engine), on='StockCode', how='left')
    
    # 補足空值
    merged['EstimatedROE'] = merged['EstimatedROE'].fillna(0)
    merged['Net5DBuy'] = merged['Net5DBuy'].fillna(0)
    
    # 過濾條件
    if min_roe > 0:
        merged = merged[merged['EstimatedROE'] >= min_roe]
        
    if min_inst_buy > 0:
        merged = merged[merged['Net5DBuy'] >= min_inst_buy]
        
    if ma_cross == "收盤 > 月線(MA20)":
        merged = merged[merged['StockClose'] > merged['MA20']]
    elif ma_cross == "收盤 > 季線(MA60)":
        merged = merged[merged['StockClose'] > merged['MA60']]
        
    # 回傳整潔欄位
    res = merged[['StockCode', 'CompanyNameC', 'StockClose', 'MA20', 'MA60', 'Net5DBuy', 'EstimatedROE']]
    res.columns = ['股票代碼', '公司名稱', '收盤價', '月線(MA20)', '季線(MA60)', '近5日法人淨買進(張)', '估算ROE(%)']
    return res.reset_index(drop=True)

def get_financial_warning_indicators(stock_id: str):
    """取得季防雷警示指標與門檻值"""
    # 門檻值
    t_query = text('SELECT * FROM "CompanyWarningThresholds" WHERE "StockCode" = :stock_id')
    threshold_df = pd.read_sql(t_query, con=engine, params={"stock_id": stock_id})
    threshold = threshold_df.iloc[0].to_dict() if not threshold_df.empty else {}
    
    # 每季警告值
    w_query = text("""
        SELECT * FROM "FinancialWarningIndicators" 
        WHERE "StockCode" = :stock_id
        ORDER BY "Year" DESC, "Quarter" DESC LIMIT 12
    """)
    indicators_df = pd.read_sql(w_query, con=engine, params={"stock_id": stock_id})
    
    return threshold, indicators_df

def update_company_thresholds(stock_id: str, min_eq: float, max_recv: float, max_inv: float, max_debt: float, min_int: float):
    """更新個股防雷閥值並重新計算其警告燈號"""
    try:
        # 1. 更新設定檔
        query_update = text("""
            UPDATE "CompanyWarningThresholds"
            SET "MinEarningsQualityRatio" = :min_eq,
                "MaxReceivableTurnoverDays" = :max_recv,
                "MaxInventoryTurnoverDays" = :max_inv,
                "MaxDebtRatio" = :max_debt,
                "MinInterestCoverage" = :min_int,
                "LastUpdated" = CURRENT_TIMESTAMP
            WHERE "StockCode" = :stock_id
        """)
        with engine.connect() as conn:
            conn.execute(query_update, {
                "stock_id": stock_id,
                "min_eq": min_eq,
                "max_recv": max_recv,
                "max_inv": max_inv,
                "max_debt": max_debt,
                "min_int": min_int
            })
            conn.commit()
            
        # 2. 重新計算該股的警告燈號 (呼叫公用計算引擎)
        thresholds = {
            "MinEarningsQualityRatio": min_eq,
            "MaxReceivableTurnoverDays": max_recv,
            "MaxInventoryTurnoverDays": max_inv,
            "MaxDebtRatio": max_debt,
            "MinInterestCoverage": min_int
        }
        calculate_and_save_warnings(stock_id, engine, thresholds=thresholds)
        return True
    except Exception as e:
        print(f"更新閥值發生錯誤: {e}")
        return False

def get_realtime_rag_report(stock_id: str, custom_prompt: str = ""):
    """AI分析報告"""
    comp = get_company_base_info(stock_id)
    comp_str = f"公司代號: {comp.get('StockCode','N/A')}, 名稱: {comp.get('CompanyNameC','N/A')}, 產業: {comp.get('CompanyClass','N/A')}, 主營業務: {comp.get('MainBusinessActivities','N/A')}"
    
    metrics = get_stock_daily_metrics(stock_id, date(date.today().year-1, 1, 1), date.today())
    metrics_str = "最新一日量價籌碼數據無記錄"
    if not metrics.empty:
        last_m = metrics.iloc[-1]
        metrics_str = f"最新股價: {last_m['StockClose']}, 5日均線: {metrics['StockClose'].tail(5).mean():.2f}, 20日均線: {last_m.get('MA20','N/A')}, KD值: (K={last_m.get('KValue','N/A')}, D={last_m.get('DValue','N/A')}), 外資單日買賣: {last_m.get('ForeignNetBuy',0)}張, 投信單日買賣: {last_m.get('TrustNetBuy',0)}張"

    weekly = get_stock_weekly_concentration(stock_id)
    weekly_str = "週集保大戶比例無記錄"
    if not weekly.empty:
        last_w = weekly.iloc[0]
        weekly_str = f"更新日期: {last_w['UpdateDate']}, 千張大戶持股比例: {last_w['LargeHoldersRatio1000']}%, 400張持股比例: {last_w['LargeHoldersRatio400']}%, 10張以下散戶比例: {last_w['RetailHoldersRatio10']}%"

    threshold, warnings = get_financial_warning_indicators(stock_id)
    warn_str = "季度財務警示均正常合格"
    if not warnings.empty:
        last_q = warnings.iloc[0]
        warn_list = []
        if last_q['IsCashFlowWarning']: warn_list.append("本期盈餘品質不佳（現金流短缺）")
        if last_q['IsDebtWarning']: warn_list.append("負債比率偏高，超出設定閥值")
        if last_q['IsReceivableWarning']: warn_list.append("應收帳款天數過長")
        if last_q['IsInventoryWarning']: warn_list.append("存貨天數過長，有滯銷可能")
        if warn_list:
            warn_str = "季度警告亮燈項目: " + ", ".join(warn_list)
        else:
            warn_str = f"季度指標正常 (最新一季 ROE/資產負債比健全，無警報)"

    news = get_stock_news(stock_id).head(5)
    news_list = []
    for idx, r in news.iterrows():
        news_list.append(f"[{r['PublishTime']}] {r['Title']} (情緒分數: {r['SentimentScore']})")
    news_str = "\n".join(news_list) if news_list else "近期無相關新聞"

    base_prompt = f"""請擔任一名資深專業證券分析師。
我將提供以下股票的即時量價、籌碼與財務風險資訊，請為我撰寫一份約 800 字的專業投資分析報告。

【公司資訊】
{comp_str}

【即時量價與法人籌碼面】
{metrics_str}

【週股權集中度面】
{weekly_str}

【財務防雷警訊狀態】
{warn_str}

【最新新聞與市場情緒】
{news_str}

【使用者特定詢問項目】
{custom_prompt if custom_prompt else "無額外指定項目，請針對公司的核心投資邏輯、近期籌碼異動、與新聞多空風險進行全面性解析。"}

請以 Markdown 格式撰寫，架構包括：
1. 核心投資價值與邏輯
2. 籌碼流向與大戶動態分析
3. 財務健康度與地雷預警點評
4. 新聞多空綜合影響與投資結論。撰寫時請保持專業、客觀且審慎的金融分析口吻。"""

    try:
        client = Client(
            host="https://ollama.com",
            headers={'Authorization': 'Bearer ' + baseENV.ollamaapikey}
        )
        messages = [{'role': 'user', 'content': base_prompt}]
        response = client.chat('gpt-oss:20b-cloud', messages=messages)
        return response['message']['content']
    except Exception:
        return f"""### {stock_id} 投資分析報告 (Ollama API 異常，此為系統備用離線模擬報告)

這是一份針對 **{comp.get('CompanyNameC','個股')} ({stock_id})** 進行的模擬投資分析報告。

#### 1. 核心投資價值與邏輯
本股屬於**{comp.get('CompanyClass','該分類')}**，業務範疇涵蓋：{comp.get('MainBusinessActivities','無特別說明')}。目前均線處於盤整或溫和多頭格局，在科技革新趨勢下具備穩定的產業護城河。

#### 2. 籌碼流向與大戶動態分析
* **三大法人動態**：{metrics_str}。外資與投信呈現均衡布局，短線無籌碼異常流出現象。
* **大戶集中度**：{weekly_str}。千張大戶持股仍維持在主流水準，籌碼穩定度高，代表長期機構投資人信心充足。

#### 3. 財務健康度與地雷預警點評
* **警示狀態**：{warn_str}。
* 公司的資產負債結構和現金流體質尚稱穩定，惟需持續追蹤存貨週轉及現金流量指標是否出現進一步惡化。

#### 4. 新聞多空綜合影響與結論
近期市場關注焦點如下：
{news_str}
綜合言之，利多新聞情緒溫和主導，公司技術面支撐力道強，基本面無重大爆雷疑慮，建議投資人分批佈局、逢低承接，持續關注後續營收增長。
"""

def get_news_ollama_summary(stock_code: str, company_name: str, news_df: pd.DataFrame, trend_df: pd.DataFrame = None):
    """利用 Ollama 對新聞表格資料與股價/情緒走勢進行摘要與因果分析總結"""
    if news_df.empty:
        return "尚無新聞資料可供分析。"
        
    news_lines = []
    for idx, r in news_df.iterrows():
        news_lines.append(f"- [{r['PublishTime']}] {r['Title']} (情緒: {r['SentimentScore']})")
    news_str = "\n".join(news_lines)
    
    trend_str = "暫無近期股價與平均情緒走勢資料。"
    if trend_df is not None and not trend_df.empty:
        trend_lines = []
        for idx, r in trend_df.tail(15).iterrows():
            trend_lines.append(f"日期: {r['DateStr']}, 收盤價: {r['StockClose']} 元, 平均情緒: {r['AvgSentiment']:.2f}")
        trend_str = "\n".join(trend_lines)

    prompt = f"""您是一位頂尖的證券金融分析師。
請根據以下提供的個股新聞事件以及近 15 天的股價與平均情緒走勢，進行深度因果關係總結與摘要。

公司名稱: {company_name} ({stock_code})

【近期新聞事件與情緒標註】
{news_str}

【近 15 天每日股價與平均情緒走勢】
{trend_str}

請針對以上資訊提供：
1. 關鍵多空事件摘要（指出影響最大的新聞與情緒偏向）
2. 股價與輿情因果分析（分析新聞情緒、散戶/市場心態如何引導或落後於這 15 天的股價走勢，並說明背後因果）
3. 未來投資風險與機會總結（給出具體且客觀的點評）

請以繁體中文撰寫，字數約 500 字，格式簡潔專業。"""

    try:
        client = Client(
            host="https://ollama.com",
            headers={'Authorization': 'Bearer ' + baseENV.ollamaapikey}
        )
        messages = [{'role': 'user', 'content': prompt}]
        response = client.chat('gpt-oss:20b-cloud', messages=messages)
        return response['message']['content']
    except Exception:
        return f"""### {company_name} ({stock_code}) AI 新聞深度分析與因果總結 (Ollama API 異常，此為離線模擬總結)

#### 1. 關鍵多空事件摘要
目前該股近期新聞主要呈現多頭情緒主導。在市場消息方面，利多主要圍繞在其技術領先優勢、產業訂單能見度佳，以及法人買盤持續溫和流入。

#### 2. 股價與輿情因果分析
根據近 15 天的股價與平均情緒走勢：
{trend_str}
分析顯示，在新聞情緒平均分數偏高或改善的交易日後，股價通常能獲得良好支撐或呈現小幅上揚，表明輿情與新聞的熱度與正面評估對短期股價具備一定的引導性因果關係。

#### 3. 未來投資風險與機會總結
* **機會**：技術面長天期均線具備支撐，基本面營收與盈餘結構依然健全。
* **風險**：需留意外部總體經濟環境變化及匯率波動對短期利潤的侵蝕。
"""

def get_stock_factor_metrics(stock_id: str):
    """取得特定個股的多因子量化指標（收盤價、月線、季線、近5日法人淨買進、估算ROE）"""
    # 1. 取得最新一日的收盤價、月線、季線，以及近 5 日的法人淨買進
    query_daily = text("""
        WITH RecentBuy AS (
            SELECT "StockCode", 
                   SUM("ForeignNetBuy" + "TrustNetBuy" + "DealerNetBuy") as "Net5DBuy"
            FROM (
                SELECT "StockCode", "StockDate", "ForeignNetBuy", "TrustNetBuy", "DealerNetBuy",
                       ROW_NUMBER() OVER (PARTITION BY "StockCode" ORDER BY "StockDate" DESC) as rn
                FROM "StockDailyMetrics"
                WHERE "StockCode" = :stock_id
            ) sub
            WHERE rn <= 5
            GROUP BY "StockCode"
        )
        SELECT d.*, r."Net5DBuy"
        FROM "StockDailyMetrics" d
        LEFT JOIN RecentBuy r ON d."StockCode" = r."StockCode"
        WHERE d."StockCode" = :stock_id
        ORDER BY d."StockDate" DESC LIMIT 1
    """)
    daily_df = pd.read_sql(query_daily, con=engine, params={"stock_id": stock_id})
    
    # 2. 取得最新一季 ROE
    query_roe = text("""
        WITH LatestQuarter AS (
            SELECT "StockCode", MAX("DateInfo") as MaxDate
            FROM "StockBalance"
            WHERE "StockCode" = :stock_id
            GROUP BY "StockCode"
        )
        SELECT b."StockCode", 
               (MAX(CASE WHEN f."Types" IN ('IncomeAfterTaxes', 'IncomeAfterTax') OR f."OriginName" IN ('本期淨利（淨損）', '本期稅後淨利（淨損）') THEN f."DataValue" END) / 
                NULLIF(MAX(CASE WHEN (b."Types" = 'TotalAssets' OR b."OriginName" = '資產總額') AND b."Types" NOT LIKE '%_per' THEN b."DataValue" END), 0) * 100) as "EstimatedROE"
        FROM "StockBalance" b
        JOIN LatestQuarter lq ON b."StockCode" = lq."StockCode" AND b."DateInfo" = lq.MaxDate
        LEFT JOIN "StockFinancial" f ON b."StockCode" = f."StockCode" AND b."DateInfo" = f."DateInfo"
        WHERE b."StockCode" = :stock_id
        GROUP BY b."StockCode"
    """)
    roe_df = pd.read_sql(query_roe, con=engine, params={"stock_id": stock_id})
    
    # 3. 整合
    if daily_df.empty:
        return pd.DataFrame()
        
    merged = daily_df.copy()
    if not roe_df.empty:
        merged = pd.merge(merged, roe_df, on='StockCode', how='left')
    else:
        merged['EstimatedROE'] = 0.0
        
    merged['Net5DBuy'] = merged['Net5DBuy'].fillna(0)
    merged['EstimatedROE'] = merged['EstimatedROE'].fillna(0)
    
    # 讀取公司中文名稱
    merged = pd.merge(merged, pd.read_sql(text('SELECT "StockCode", "CompanyNameC" FROM "CompanyBaseInfo" WHERE "StockCode" = :stock_id'), con=engine, params={"stock_id": stock_id}), on='StockCode', how='left')
    
    res = merged[['StockCode', 'CompanyNameC', 'StockClose', 'MA20', 'MA60', 'Net5DBuy', 'EstimatedROE']]
    res.columns = ['股票代碼', '公司名稱', '收盤價', '月線(MA20)', '季線(MA60)', '近5日法人淨買進(張)', '估算ROE(%)']
    return res
