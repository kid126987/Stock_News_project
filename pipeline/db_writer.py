import logging
import pandas as pd
from datetime import datetime, date
from sqlalchemy import text
from db.engine import engine

def get_last_date(stock_id, table_name, date_col, default_years=5):
    """取得指定股票在指定資料表中的最新日期，若無資料則回推指定年數"""
    try:
        with engine.connect() as conn:
            query = text(f'SELECT MAX("{date_col}") FROM "{table_name}" WHERE "StockCode" = :stock_id')
            result = conn.execute(query, {"stock_id": stock_id}).scalar()
            if result is None:
                today = date.today()
                return f"{today.year - default_years}-01-01"
            if isinstance(result, (datetime, date)):
                return result.strftime('%Y-%m-%d')
            return str(result)
    except Exception as e:
        logging.error(f"取得最新日期錯誤 ({table_name}, {stock_id}): {e}", exc_info=True)
        today = date.today()
        return f"{today.year - default_years}-01-01"

def idempotent_to_sql(df, table_name, pk_cols):
    """以 Pandas 過濾已存在主鍵的方式，實作防重覆冪等寫入"""
    if df.empty:
        return
        
    # 白名單欄位與資料表名稱驗證，防範 SQL Injection
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        raise ValueError(f"不安全的資料表名稱: {table_name}")
    for col in pk_cols:
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
            raise ValueError(f"不安全的欄位名稱: {col}")
            
    # 強制拷貝以避免 SettingWithCopyWarning 造成的潛在數據污染
    df = df.copy()
        
    try:
        # 查詢資料庫中現有的主鍵組合 (過濾 StockCode 避免大表全表掃描)
        pk_select = ", ".join([f'"{c}"' for c in pk_cols])
        if 'StockCode' in df.columns:
            stock_ids = df['StockCode'].unique().tolist()
            placeholders = ", ".join([f":id{i}" for i in range(len(stock_ids))])
            query = f'SELECT {pk_select} FROM "{table_name}" WHERE "StockCode" IN ({placeholders})'
            params = {f"id{i}": sid for i, sid in enumerate(stock_ids)}
            existing = pd.read_sql(text(query), con=engine, params=params)
        else:
            query = f'SELECT {pk_select} FROM "{table_name}"'
            existing = pd.read_sql(query, con=engine)
        
        if not existing.empty:
            # 將 DataFrame 的主鍵轉換為 string tuple 進行比對，以避免型態不一致的誤判
            existing_str = existing[pk_cols].astype(str)
            existing_tuples = set(existing_str.itertuples(index=False, name=None))
            
            df_str = df[pk_cols].astype(str)
            df['is_existing'] = df_str.apply(lambda row: tuple(row) in existing_tuples, axis=1)
            df_to_insert = df[df['is_existing'] == False].drop(columns=['is_existing'])
        else:
            df_to_insert = df.copy()
            
        if not df_to_insert.empty:
            # 轉換正確的型態寫入資料庫
            for col in df_to_insert.columns:
                if col.lower().endswith('date'):
                    df_to_insert[col] = pd.to_datetime(df_to_insert[col], errors='coerce').dt.date
            
            df_to_insert.to_sql(table_name, con=engine, if_exists='append', index=False, method='multi', chunksize=1000)
            logging.info(f"寫入 {table_name}: 新增 {len(df_to_insert)} 筆資料")
        else:
            logging.info(f"寫入 {table_name}: 無新資料需要寫入 (重複已過濾)")
            
    except Exception as e:
        logging.error(f"寫入資料表 {table_name} 錯誤: {e}", exc_info=True)
