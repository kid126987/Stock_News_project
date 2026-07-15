import requests
import pandas as pd
import feedparser
from config.settings import get_login_data, data_url

class FinMindData:
    def __init__(self):
        self.token = get_login_data().get('token', '')

    def stock_price_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            df = pd.DataFrame(res["data"])
            df = df[['date', 'stock_id', 'close', 'Trading_Volume', 'Trading_money']]
            return df
        return pd.DataFrame()

    def stock_revenue_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            df = pd.DataFrame(res["data"])
            return df[['stock_id', 'revenue', 'revenue_month', 'revenue_year', 'date']]
        return pd.DataFrame()

    def stock_dividend_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockDividend",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            df = pd.DataFrame(res["data"])
            # Ensure required columns exist
            cols = ['stock_id', 'year', 'StockEarningsDistribution', 'StockStatutorySurplus',
                    'CashEarningsDistribution', 'CashStatutorySurplus',
                    'CashExDividendTradingDate', 'CashDividendPaymentDate']
            for c in cols:
                if c not in df.columns:
                    df[c] = ''
            return df[cols]
        return pd.DataFrame()

    def stock_per_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockPER",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            return pd.DataFrame(res["data"])[['date', 'stock_id', 'dividend_yield', 'PER', 'PBR']]
        return pd.DataFrame()

    def stock_financial_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            return pd.DataFrame(res["data"])[['date', 'stock_id', 'type', 'value', 'origin_name']]
        return pd.DataFrame()

    def stock_balance_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockBalanceSheet",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            return pd.DataFrame(res["data"])[['date', 'stock_id', 'type', 'value', 'origin_name']]
        return pd.DataFrame()

    def stock_cashflow_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockCashFlowsStatement",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            return pd.DataFrame(res["data"])[['date', 'stock_id', 'type', 'value', 'origin_name']]
        return pd.DataFrame()

    def stock_investors_buy_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            return pd.DataFrame(res["data"])[['date', 'stock_id', 'buy', 'name', 'sell']]
        return pd.DataFrame()

    def stock_margin_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockMarginPurchaseShortSale",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        if res.get("data"):
            df = pd.DataFrame(res["data"])
            # Required fields: date, stock_id, MarginPurchaseTodayBalance, ShortSaleTodayBalance
            required_cols = ['date', 'stock_id', 'MarginPurchaseTodayBalance', 'ShortSaleTodayBalance']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = 0
            return df[required_cols]
        return pd.DataFrame()

    def stock_holding_shares_info(self, stock_id: str, start_date: str, end_date: str):
        params = {
            "dataset": "TaiwanStockHoldingSharesPer",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token
        }
        res = requests.get(data_url, params=params).json()
        import logging
        if not res.get("data"):
            logging.warning(f"FinMind TaiwanStockHoldingSharesPer API raw response for {stock_id}: {res}")
        if res.get("data"):
            return pd.DataFrame(res["data"])
        return pd.DataFrame()

class GoogleNewsData:
    def __init__(self):
        pass

    def google_news_search(self, kw: str, country: str, startdate: str, enddate: str):
        from urllib.parse import quote
        import ssl
        from datetime import datetime, timedelta
        try:
            ssl._create_default_https_context = ssl._create_unverified_context
        except Exception:
            pass
            
        # 計算 before 參數 (加一天以包含 enddate 當天的完整新聞)
        try:
            end_dt = datetime.strptime(enddate, '%Y-%m-%d')
            enddate_query = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        except Exception:
            enddate_query = enddate
            
        # 限制新聞來源：Anue 鉅亨網 (cnyes.com), MoneyDJ 理財網 (moneydj.com), Yahoo 奇摩股市 (yahoo.com), CMoney (cmoney.tw)
        full_query = kw
        encoded_kw = quote(full_query)
        url = f'https://news.google.com/rss/search?q=intitle:{encoded_kw}+after:{startdate}+before:{enddate_query}&hl=zh-TW&gl={country}'
        res = feedparser.parse(url)
        if not res.get('entries'):
            return pd.DataFrame()
        
        df = pd.json_normalize(res['entries'])
        
        if df.empty:
            return pd.DataFrame()
            
        # 參考 global_news_tool-main 提取來源名稱的邏輯 (優先從 source.title 拿，若空則從 title 的 " - " 後方切割)
        if 'source.title' in df.columns:
            df['source_name'] = df['source.title'].fillna('')
        else:
            df['source_name'] = ''
            
        if 'title' in df.columns:
            def clean_title_and_extract_source(row):
                title = row.get('title', '')
                source = row.get('source_name', '')
                if not source and isinstance(title, str) and " - " in title:
                    parts = title.split(" - ")
                    source = parts[-1].strip()
                    title = " - ".join(parts[:-1]).strip()
                return pd.Series({'title': title, 'source_name': source})
            
            df[['title', 'source_name']] = df.apply(clean_title_and_extract_source, axis=1)
            
        # 確保必要欄位存在
        cols_needed = ['title', 'published', 'link', 'source_name']
        for col in cols_needed:
            if col not in df.columns:
                df[col] = 'nodata'
                
        # 透過資料來源進行新聞來源限制：Anue 鉅亨網、MoneyDJ 理財網、Yahoo 奇摩股市、CMoney
        def is_allowed_source(source_name):
            if not source_name:
                return False
            name_lower = source_name.lower()
            allowed_keywords = ["鉅亨", "cnyes", "moneydj", "yahoo股市", "奇摩", "cmoney"]
            return any(kw in name_lower for kw in allowed_keywords)
            
        df = df[df['source_name'].apply(is_allowed_source)]
        
        if df.empty:
            return pd.DataFrame()
            
        return df[['title', 'published', 'link']]
