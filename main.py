import subprocess
import sys
import os

# 優先將本地目錄加入 path，防止庫名遮蔽衝突
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_requirements(packages):
    """檢查依賴套件是否已安裝，若缺失則提示使用者手動安裝 (P1-7)"""
    missing = []
    for pkg in packages:
        # 特殊名稱映射
        import_name = pkg
        if pkg == 'psycopg2-binary':
            import_name = 'psycopg2'
        elif pkg == 'python-dotenv':
            import_name = 'dotenv'
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
            
    if missing:
        print("⚠️  偵測到以下缺失的 Python 依賴套件：")
        for m in missing:
            print(f"   - {m}")
        print("\n請在終端機執行以下指令進行安裝：")
        print("   pip install -r requirements.txt\n")
        sys.exit(1)

if __name__ == "__main__":
    # 檢查並驗證依賴套件
    check_requirements([
        'requests',
        'pandas',
        'sqlalchemy',
        'streamlit',
        'pyarrow',
        'fastparquet',
        'feedparser',
        'ollama',
        'psycopg2-binary',
        'plotly',
        'transformers',
        'torch',
        'torchvision',
        'python-dotenv'
    ])
    
    # 1. 設置與初始化資料庫
    print("--- 1. 資料庫初始化檢查 ---")
    from db.setup import check_and_create_database
    db_success = check_and_create_database()
    if not db_success:
        print("資料庫建置失敗，請確認 PostgreSQL 是否已啟動且帳密正確。")
        sys.exit(1)
        
    # 2. 進行增量資料更新與籌碼技術指標特徵工程
    print("--- 2. 開始執行日週籌碼、量價與財務防雷指標爬取管道 ---")
    from pipeline.data_pipeline import update_data
        
    try:
        update_data()
    except Exception as e:
        print(f"執行盤後資料更新時出錯，先啟動網頁以供檢視: {e}")
        
    # 3. 啟動 Streamlit 前端應用程式
    print("--- 3. 啟動 Streamlit 分析師看板 ---")
    app_path = os.path.join(os.path.dirname(__file__), "streamlit_app.py")
    try:
        # 使用當前 Python 執行環境的 streamlit 模組直接啟動
        subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])
    except KeyboardInterrupt:
        print("系統已關閉。")
