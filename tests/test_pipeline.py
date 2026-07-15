import pytest
import pandas as pd
from datetime import date
from sqlalchemy import create_engine, text
import pipeline.db_writer
from pipeline.sentiment import rule_based_sentiment
from pipeline.tdcc_scraper import aggregate_weekly_holding

# 建立獨立的測試用記憶體 SQLite 資料庫以隔離測試環境
test_engine = create_engine("sqlite:///:memory:")

# 測試用 schema 設置
@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    # 覆寫 db_writer 的 engine 為記憶體測試引擎
    monkeypatch.setattr(pipeline.db_writer, "engine", test_engine)
    
    with test_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS "TestTable" (
                "StockCode" VARCHAR(10),
                "StockDate" DATE,
                "Value" INTEGER,
                PRIMARY KEY ("StockCode", "StockDate")
            );
        """))
        conn.execute(text('DELETE FROM "TestTable";'))
        conn.commit()

def test_idempotent_to_sql():
    """測試 idempotent_to_sql 冪等防重複寫入邏輯"""
    df1 = pd.DataFrame([
        {"StockCode": "2330", "StockDate": "2026-07-01", "Value": 100},
        {"StockCode": "2330", "StockDate": "2026-07-02", "Value": 200}
    ])
    
    # 第一次寫入兩筆
    pipeline.db_writer.idempotent_to_sql(df1, "TestTable", ["StockCode", "StockDate"])
    
    df_read = pd.read_sql('SELECT * FROM "TestTable" ORDER BY "StockDate"', con=test_engine)
    assert len(df_read) == 2
    assert df_read.loc[0, "Value"] == 100
    
    # 第二次寫入重複的一筆 + 新增一筆
    df2 = pd.DataFrame([
        {"StockCode": "2330", "StockDate": "2026-07-02", "Value": 999}, # 重重複
        {"StockCode": "2330", "StockDate": "2026-07-03", "Value": 300}  # 新增
    ])
    
    pipeline.db_writer.idempotent_to_sql(df2, "TestTable", ["StockCode", "StockDate"])
    
    df_read_final = pd.read_sql('SELECT * FROM "TestTable" ORDER BY "StockDate"', con=test_engine)
    # 重複的那筆應該被過濾不被覆蓋，且新增了一筆，總數應為 3 筆
    assert len(df_read_final) == 3
    assert df_read_final.loc[1, "Value"] == 200  # 原本的 200 未被覆蓋
    assert df_read_final.loc[2, "Value"] == 300  # 新增的 300 寫入成功

def test_idempotent_to_sql_injection():
    """測試 SQL 注入攔截驗證"""
    df = pd.DataFrame([{"StockCode": "2330", "StockDate": "2026-07-01", "Value": 100}])
    
    with pytest.raises(ValueError, match="不安全的資料表名稱"):
        pipeline.db_writer.idempotent_to_sql(df, "TestTable\"; DROP TABLE \"TestTable\";--", ["StockCode"])
        
    with pytest.raises(ValueError, match="不安全的欄位名稱"):
        pipeline.db_writer.idempotent_to_sql(df, "TestTable", ["StockCode\";--"])

def test_rule_based_sentiment():
    """測試新聞情緒關鍵字比對"""
    assert rule_based_sentiment("台積電營收創高") > 0.0
    assert rule_based_sentiment("聯發科獲利衰退") < 0.0
    assert rule_based_sentiment("中華電信今日召開董事會") == 0.0

def test_aggregate_weekly_holding():
    """測試集保週分散級彙總轉換邏輯"""
    raw_df = pd.DataFrame([
        # 散戶區 (持股分級 1~3)
        {"date": "2026-07-01", "HoldingSharesLevel": 1, "people": 100, "percent": 5.0},
        {"date": "2026-07-01", "HoldingSharesLevel": 3, "people": 50, "percent": 10.0},
        # 400張大戶區 (持股分級 12~14)
        {"date": "2026-07-01", "HoldingSharesLevel": 12, "people": 5, "percent": 25.0},
        # 1000張大戶區 (持股分級 15)
        {"date": "2026-07-01", "HoldingSharesLevel": 15, "people": 2, "percent": 45.0},
    ])
    
    res = aggregate_weekly_holding(raw_df, "2330")
    assert not res.empty
    row = res.iloc[0]
    assert row["StockCode"] == "2330"
    assert row["RetailHoldersRatio10"] == 15.0      # 5 + 10
    assert row["LargeHoldersRatio400"] == 70.0      # 25 + 45 (1000張也算400張以上大戶)
    assert row["LargeHoldersRatio1000"] == 45.0     # 45
    assert row["TotalShareholders"] == 157          # 100 + 50 + 5 + 2
