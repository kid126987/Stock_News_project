import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pathlib import Path
from dotenv import load_dotenv

# 確保載入專案根目錄的 .env 檔
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

def get_db_connection_params():
    """獲取 PostgreSQL 資料庫連線參數，可透過環境變數覆寫預設值"""
    return {
        "dbname": os.environ.get("DB_NAME", "stock_database"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "postgres"),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432")
    }

def is_postgresql_available():
    """檢測本機是否安裝且運行 PostgreSQL (嘗試進行 socket 連線)"""
    import socket
    params = get_db_connection_params()
    host = params.get("host", "localhost")
    port = int(params.get("port", 5432))
    
    # 快速檢測 Port 是否開放，防止連線超時過久
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False

def translate_to_sqlite(sql_content):
    """將 PostgreSQL schema.sql DDL 轉譯為 SQLite 相容語法"""
    # 1. 移除 CASCADE (SQLite 不支援 DROP TABLE CASCADE)
    sql_content = sql_content.replace('CASCADE', '')
    # 2. 將 UUID 替換為 VARCHAR(36)
    sql_content = sql_content.replace('UUID PRIMARY KEY DEFAULT gen_random_uuid()', 'VARCHAR(36) PRIMARY KEY')
    # 3. 將 TIMESTAMP WITH TIME ZONE 替換為 DATETIME
    sql_content = sql_content.replace('TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP', 'DATETIME DEFAULT CURRENT_TIMESTAMP')
    return sql_content

def is_supabase_configured():
    """檢查是否設定了 Supabase 連線"""
    db_type = os.environ.get("DB_TYPE", "").lower()
    if db_type in ("sqlite", "postgres", "postgresql"):
        return False
    supabase_url = os.environ.get("SUPABASE_DB_URL")
    return db_type == "supabase" or bool(supabase_url)

def get_supabase_db_url():
    """獲取 Supabase 連線 URL。優先讀取 SUPABASE_DB_URL，若無則由個別參數拼接而成"""
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return url
    
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME", "postgres")
    
    if not host or not password:
        return None
        
    url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    if "sslmode" not in url:
        url += "?sslmode=require"
    return url

def _init_supabase():
    """初始化 Supabase 資料庫與資料表"""
    print("偵測到啟用 Supabase 資料庫連線...")
    supabase_url = get_supabase_db_url()
    if not supabase_url:
        print("錯誤：已啟用 Supabase 但未提供連線資訊 (請設定 SUPABASE_DB_URL 或相關 DB_ 變數)")
        return False
    
    conn = None
    try:
        print("正在嘗試連線至 Supabase PostgreSQL...")
        conn = psycopg2.connect(supabase_url, connect_timeout=10)
        cursor = conn.cursor()
        
        # 檢查是否已建表 (檢查 CompanyBaseInfo 是否存在)
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'CompanyBaseInfo'
            );
        """)
        tables_exist = cursor.fetchone()[0]
        
        if tables_exist:
            print("Supabase 資料庫表格已存在，跳過建表。進行欄位轉換與長度擴展檢測。")
            try:
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "PublishTime" TYPE TIMESTAMP USING "PublishTime"::timestamp;')
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "NewsLink" TYPE TEXT;')
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "Title" TYPE TEXT;')
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_news_unique_link ON "StockNews" ("StockCode", "NewsLink");')
                try:
                    cursor.execute('ALTER TABLE "CompanyBaseInfo" ADD COLUMN "CompanyNameAbbr" VARCHAR(50);')
                except Exception:
                    pass
                conn.commit()
                print("資料庫欄位類型轉換與長度擴展驗證完成 (PublishTime -> TIMESTAMP, Title/NewsLink -> TEXT, UNIQUE INDEX, CompanyNameAbbr)。")
            except Exception as e:
                print(f"資料庫欄位擴展遷移跳過或失敗: {e}")
                conn.rollback()
            return True
            
        # 讀取並執行 SQL
        sql_file_path = Path(__file__).parent / "schema.sql"
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
            
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        for statement in sql_statements:
            cursor.execute(statement)
        conn.commit()
        print("Supabase 表格建立與初始化完成！")
        return True
    except Exception as e:
        print(f"初始化 Supabase 資料庫出錯: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def _init_postgresql():
    """初始化本機 PostgreSQL 資料庫與資料表"""
    print("偵測到本機正在運行 PostgreSQL，將使用 PostgreSQL 資料庫...")
    params = get_db_connection_params()
    dbname = params.pop("dbname")
    
    # 步驟 1: 檢查並建立 PostgreSQL 資料庫
    try:
        conn = psycopg2.connect(dbname="postgres", **params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (dbname,))
        exists = cursor.fetchone()
        if not exists:
            print(f"建立新 PostgreSQL 資料庫: {dbname}")
            cursor.execute(f"CREATE DATABASE {dbname}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"建立 PostgreSQL 資料庫時發生錯誤: {e}")
        return False
        
    # 步驟 2: 建表與欄位遷移
    conn = None
    try:
        params["dbname"] = dbname
        conn = psycopg2.connect(**params)
        cursor = conn.cursor()
        
        # 檢查是否已建表 (檢查 CompanyBaseInfo 是否存在)
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'CompanyBaseInfo'
            );
        """)
        tables_exist = cursor.fetchone()[0]
        
        if tables_exist:
            print("PostgreSQL 資料庫表格已存在，跳過建表。進行欄位轉換與長度擴展檢測。")
            try:
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "PublishTime" TYPE TIMESTAMP USING "PublishTime"::timestamp;')
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "NewsLink" TYPE TEXT;')
                cursor.execute('ALTER TABLE "StockNews" ALTER COLUMN "Title" TYPE TEXT;')
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_news_unique_link ON "StockNews" ("StockCode", "NewsLink");')
                try:
                    cursor.execute('ALTER TABLE "CompanyBaseInfo" ADD COLUMN "CompanyNameAbbr" VARCHAR(50);')
                except Exception:
                    pass
                conn.commit()
                print("資料庫欄位類型轉換與長度擴展驗證完成 (PublishTime -> TIMESTAMP, Title/NewsLink -> TEXT, UNIQUE INDEX, CompanyNameAbbr)。")
            except Exception as e:
                print(f"資料庫欄位擴展遷移跳過或失敗: {e}")
                conn.rollback()
            return True
            
        # 讀取並執行 SQL
        sql_file_path = Path(__file__).parent / "schema.sql"
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
            
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        for statement in sql_statements:
            cursor.execute(statement)
        conn.commit()
        print("PostgreSQL 表格建立完成！")
        return True
    except Exception as e:
        print(f"初始化 PostgreSQL 表格出錯: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def _init_sqlite():
    """初始化 SQLite 資料庫與資料表"""
    print("未偵測到本機有運行 PostgreSQL。將使用 SQLite 資料庫 (檔案名稱: stock_database.db)...")
    import sqlite3
    conn = None
    try:
        conn = sqlite3.connect("stock_database.db")
        cursor = conn.cursor()
        
        # 檢查是否已建表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='CompanyBaseInfo';")
        tables_exist = cursor.fetchone()
        
        if tables_exist:
            print("SQLite 資料庫已存在且表格已初始化，跳過建表流程。確保唯一索引與新欄位存在。")
            try:
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_news_unique_link ON "StockNews" ("StockCode", "NewsLink");')
                try:
                    cursor.execute('ALTER TABLE "CompanyBaseInfo" ADD COLUMN "CompanyNameAbbr" VARCHAR(50);')
                except Exception:
                    pass
                conn.commit()
            except Exception as e:
                print(f"建立 SQLite 唯一索引與新增欄位錯誤: {e}")
            return True
            
        # 讀取並轉譯 DDL
        sql_file_path = Path(__file__).parent / "schema.sql"
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
            
        sqlite_ddl = translate_to_sqlite(sql_content)
        sql_statements = [stmt.strip() for stmt in sqlite_ddl.split(';') if stmt.strip()]
        
        for statement in sql_statements:
            cursor.execute(statement)
        conn.commit()
        print("SQLite 表格建立與初始化完成！")
        return True
    except Exception as e:
        print(f"初始化 SQLite 資料庫表格出錯: {e}")
        return False
    finally:
        if conn:
            conn.close()

def check_and_create_database():
    """
    多資料庫建置入口：
    若指定使用 SQLite (環境變數 DB_TYPE=sqlite) 則建置 SQLite 資料庫；
    若指定為 Supabase (環境變數 DB_TYPE=supabase 或設定了 SUPABASE_DB_URL) 則進行 Supabase 連線與初始化；
    若無上述設定且偵測到 PostgreSQL 則建置 PostgreSQL 資料庫；
    否則降級使用 SQLite 資料庫。
    """
    db_type = os.environ.get("DB_TYPE", "").lower()
    
    if db_type == "sqlite":
        return _init_sqlite()
    elif is_supabase_configured():
        return _init_supabase()
    elif is_postgresql_available():
        return _init_postgresql()
    else:
        return _init_sqlite()
