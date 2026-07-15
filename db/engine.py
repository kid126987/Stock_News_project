"""
共用 SQLAlchemy Engine 單例模組
所有需要資料庫連線的模組統一從此處 import engine，避免重複建構連線。
此模組支援動態切換：若偵測到 PostgreSQL 則連線 PG，否則連線本地 SQLite。
"""
from sqlalchemy import create_engine
from db.setup import get_db_connection_params, is_postgresql_available, is_supabase_configured, get_supabase_db_url

import os
use_sqlite = os.environ.get("DB_TYPE", "").lower() == "sqlite"

if is_supabase_configured():
    db_url = get_supabase_db_url()
    # Supabase PostgreSQL 連線
    engine = create_engine(db_url, echo=False)
elif not use_sqlite and is_postgresql_available():
    db_params = get_db_connection_params()
    db_url = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}:{db_params['port']}/{db_params['dbname']}"
    # PostgreSQL 連線
    engine = create_engine(db_url, echo=False)
else:
    # SQLite 降級連線 (開啟 check_same_thread=False 供 Streamlit 多線程查詢)
    db_url = "sqlite:///stock_database.db"
    engine = create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)
