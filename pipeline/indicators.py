import pandas as pd
import numpy as np

def compute_indicators(df):
    """計算技術面指標：MA20, MA60, KD, RSI14, MACD_Hist"""
    if df.empty or len(df) < 5:
        df['MA20'] = None
        df['MA60'] = None
        df['KValue'] = 50.0
        df['DValue'] = 50.0
        df['RSI14'] = None
        df['MACD_Hist'] = None
        return df

    df = df.sort_values('StockDate').reset_index(drop=True)
    
    # 均線
    df['MA20'] = df['StockClose'].rolling(window=20).mean()
    df['MA60'] = df['StockClose'].rolling(window=60).mean()

    # KD指標
    low_9 = df['StockClose'].rolling(window=9).min() # 用收盤價替代最低價作簡化
    high_9 = df['StockClose'].rolling(window=9).max() # 用收盤價替代最高價作簡化
    
    # 防止分母為零
    denom = high_9 - low_9
    rsv = ((df['StockClose'] - low_9) / denom.replace(0, np.nan) * 100).fillna(50)
    
    k_vals = []
    d_vals = []
    current_k = 50.0
    current_d = 50.0
    for r in rsv:
        current_k = r / 3.0 + current_k * 2.0 / 3.0
        current_d = current_k / 3.0 + current_d * 2.0 / 3.0
        k_vals.append(current_k)
        d_vals.append(current_d)
    df['KValue'] = k_vals
    df['DValue'] = d_vals

    # RSI14
    delta = df['StockClose'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI14'] = 100 - (100 / (1 + rs).fillna(1))

    # MACD
    ema12 = df['StockClose'].ewm(span=12, adjust=False).mean()
    ema26 = df['StockClose'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    macd_signal = dif.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = dif - macd_signal

    return df
