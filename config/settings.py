import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# 確保載入專案根目錄的 .env 檔
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

data_url = "https://api.finmindtrade.com/api/v4/data"

# 統一管理的監控股票清單
STOCK_LIST = ['2330', '2317', '2454', '2308', '2382', '2891', '2881', '3711', '2882', '2412','1225']

# Ollama cloud API key
ollamaapikey = os.getenv("OLLAMA_API_KEY", "")

_login_data_cache = None

def get_login_data():
    """取得 FinMind 登入資訊 (延遲載入並進行快取以提升效能與穩定性)"""
    global _login_data_cache
    if _login_data_cache is None:
        login_url = "https://api.finmindtrade.com/api/v4/login"
        payload = {
            "user_id": os.getenv("FINMIND_USER"),
            "password": os.getenv("FINMIND_PASSWORD"),
        }
        try:
            res = requests.post(login_url, data=payload, timeout=15)
            res.raise_for_status()
            _login_data_cache = res.json()
        except Exception as e:
            import logging
            logging.error(f"FinMind API 登入失敗: {e}")
            _login_data_cache = {}
    return _login_data_cache
