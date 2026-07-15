import logging
import io
import urllib3
import warnings
import requests
import pandas as pd
from datetime import datetime

# 全域快取，避免每檔股票重複下載 40MB 的集保股權分散 CSV
_tdcc_df_cache = None

def download_tdcc_weekly_shares(stock_id):
    """自集保結算所開放資料下載最新一週的股權分散表 (具有全域記憶體快取以避免重複下載)"""
    global _tdcc_df_cache
    url = 'https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5'
    
    if _tdcc_df_cache is None:
        logging.info("正在從集保結算所下載最新的週股權分散開放資料 CSV (此步驟大約需數秒)...")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, verify=False)
            res.raise_for_status()
            res.encoding = 'utf-8'
            
            df = pd.read_csv(io.StringIO(res.text))
            df.columns = [c.strip() for c in df.columns]
            _tdcc_df_cache = df
            logging.info("集保週股權分散資料下載成功且已載入快取。")
        except Exception as e:
            logging.error(f"下載集保 Open Data 發生錯誤: {e}")
            return pd.DataFrame()
            
    df = _tdcc_df_cache
    # 動態尋找包含特定關鍵字的欄位名稱以相容 占/佔 等繁簡或格式異同
    date_col = next((c for c in df.columns if '日期' in c), '資料日期')
    code_col = next((c for c in df.columns if '代號' in c), '證券代號')
    level_col = next((c for c in df.columns if '分級' in c), '持股分級')
    people_col = next((c for c in df.columns if '人數' in c), '人數')
    percent_col = next((c for c in df.columns if any(x in c for x in ['比例', '占', '佔'])), '佔總股數比例')
    
    df_filtered = df[df[code_col].astype(str).str.strip() == stock_id].copy()
    if df_filtered.empty:
        return pd.DataFrame()
        
    def format_date(val):
        val_str = str(val).strip()
        if len(val_str) == 8:
            return f"{val_str[:4]}-{val_str[4:6]}-{val_str[6:]}"
        return val_str
        
    df_filtered['date'] = df_filtered[date_col].apply(format_date)
    df_filtered['HoldingSharesLevel'] = df_filtered[level_col]
    df_filtered['people'] = df_filtered[people_col]
    df_filtered['percent'] = df_filtered[percent_col]
    
    return df_filtered[['date', 'HoldingSharesLevel', 'people', 'percent']]

def aggregate_weekly_holding(df_raw, stock_id):
    """將股權分級原始資料轉換為週頻率的大戶與散戶持股比例"""
    if df_raw.empty:
        return pd.DataFrame()
    
    df = df_raw.copy()
    df['HoldingSharesLevel'] = pd.to_numeric(df['HoldingSharesLevel'], errors='coerce')
    
    # 依照日期分組彙總
    dates = df['date'].unique()
    rows = []
    
    for d in dates:
        day_df = df[df['date'] == d]
        if day_df.empty:
            continue
            
        # 散戶 (Level <= 3)
        retail_10 = day_df[day_df['HoldingSharesLevel'] <= 3]['percent'].sum()
        # 400張大戶 (Level >= 12)
        large_400 = day_df[day_df['HoldingSharesLevel'] >= 12]['percent'].sum()
        # 1000張大戶 (Level >= 15)
        large_1000 = day_df[day_df['HoldingSharesLevel'] >= 15]['percent'].sum()
        # 總人數
        total_people = day_df['people'].sum()
        
        rows.append({
            'StockCode': stock_id,
            'UpdateDate': datetime.strptime(d, '%Y-%m-%d').date(),
            'LargeHoldersRatio400': large_400,
            'LargeHoldersRatio1000': large_1000,
            'RetailHoldersRatio10': retail_10,
            'TotalShareholders': int(total_people)
        })
        
    return pd.DataFrame(rows)
