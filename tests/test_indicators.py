import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pipeline.indicators import compute_indicators

def test_compute_indicators_empty():
    """測試空 DataFrame 的邊界處理"""
    df_empty = pd.DataFrame()
    res = compute_indicators(df_empty)
    assert res.empty or 'MA20' in res.columns

def test_compute_indicators_calculation():
    """測試技術指標算式的正確性"""
    # 建立 70 天的虛擬收盤價序列
    base_date = datetime.strptime("2026-01-01", "%Y-%m-%d")
    dates = [base_date + timedelta(days=i) for i in range(70)]
    
    # 模擬股價上漲與波動
    np.random.seed(42)
    prices = [100.0 + i * 0.5 + np.sin(i) * 5 for i in range(70)]
    
    df = pd.DataFrame({
        'StockDate': dates,
        'StockClose': prices
    })
    
    # 計算指標
    res = compute_indicators(df)
    
    # 1. 驗證產生的欄位是否存在
    expected_cols = ['MA20', 'MA60', 'KValue', 'DValue', 'RSI14', 'MACD_Hist']
    for col in expected_cols:
        assert col in res.columns
        
    # 2. 驗證均線在足夠天數後有計算結果
    # 第 20 天起應有 MA20
    assert not pd.isna(res.loc[25, 'MA20'])
    # 第 60 天起應有 MA60
    assert not pd.isna(res.loc[65, 'MA60'])
    
    # 3. 驗證 KD 值是否在合理區間 0~100 內
    assert res['KValue'].min() >= 0.0
    assert res['KValue'].max() <= 100.0
    assert res['DValue'].min() >= 0.0
    assert res['DValue'].max() <= 100.0
    
    # 4. 驗證 RSI14 在第 14 天起有結果且在合理區間
    assert not pd.isna(res.loc[20, 'RSI14'])
    assert res['RSI14'].min() >= 0.0
    assert res['RSI14'].max() <= 100.0
    
    # 5. 驗證 MACD 直方圖值有計算出來
    assert not pd.isna(res.loc[40, 'MACD_Hist'])
