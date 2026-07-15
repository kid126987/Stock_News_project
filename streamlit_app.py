import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from services import data_service as sd
from config.settings import STOCK_LIST

# 設定網頁標題與版面
st.set_page_config(page_title="股市與財務新聞輿情分析平台", layout="wide", initial_sidebar_state="expanded")

# 專業黑底暗色科技風 CSS 注入
st.markdown("""
<style>
    .reportview-container {
        background: #0d1117;
    }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .warning-light-red {
        background-color: #8b0000;
        color: #ffcccc;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
        text-align: center;
    }
    .warning-light-green {
        background-color: #006400;
        color: #ccffcc;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
        text-align: center;
    }
    .sentiment-pos {
        color: #39FF14;
        font-weight: bold;
    }
    .sentiment-neg {
        color: #FF3131;
        font-weight: bold;
    }
    .sentiment-neu {
        color: #888888;
    }
</style>
""", unsafe_allow_html=True)

# 1. 側邊欄：股票代碼選擇與個股基本資料卡
st.sidebar.title("個股選擇與公司基本資訊")
stock_choices = STOCK_LIST
selected_stock = st.sidebar.selectbox("請選擇個股代碼", stock_choices, index=0)

# 載入公司基本面
comp_info = sd.get_company_base_info(selected_stock)

st.sidebar.markdown("### 🏢 公司基本資訊")
if comp_info:
    st.sidebar.markdown(f"""
    <div class="metric-card">
        <b>中文名稱</b>: {comp_info.get('CompanyNameC', 'N/A')}<br/>
        <b>英文名稱</b>: {comp_info.get('CompanyNameE', 'N/A')}<br/>
        <b>產業別</b>: {comp_info.get('CompanyClass', 'N/A')}<br/>
        <b>市場別</b>: {comp_info.get('MarketClass', 'N/A')}<br/>
        <b>董事長</b>: {comp_info.get('ChairmanName', 'N/A')}<br/>
        <b>成立日期</b>: {comp_info.get('EstablishmentDate', 'N/A')}<br/>
        <b>掛牌日期</b>: {comp_info.get('ListingDate', 'N/A')}<br/>
        <b>公司網址</b>: <a href="{comp_info.get('Webside', '#')}" target="_blank">點此造訪</a>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.warning("尚未同步公司基本資料，請先執行盤後更新。")

# 2. 主版面 Tabs 分頁設計
st.title("股市與財務新聞輿情智慧分析平台")
tab1, tab2, tab3, tab4 = st.tabs([
    "股市看盤 Dashboard", 
    "財務新聞情緒與AI綜合分析", 
    "財務警訊與閥值設定", 
    "股市與新聞綜合分析AI報告"
])

# ==================== TAB 1: 市場看盤 Dashboard ====================
with tab1:
    st.header(f"{comp_info.get('CompanyNameC', '個股')} ({selected_stock}) 量價與籌碼指標")
    
    # 時間範圍選擇器
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_d = st.date_input("開始日期", date.today() - timedelta(days=180))
    with col_date2:
        end_d = st.date_input("結束日期", date.today())
        
    daily_data = sd.get_stock_daily_metrics(selected_stock, start_d, end_d)
    
    if not daily_data.empty:
        # 繪製價格與均線圖
        # 嘗試引入 Plotly
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, 
                                subplot_titles=('股價與均線 (MA20/MA60)', 'KD 指標與 RSI14', '三大法人單日淨買賣超 (張)'),
                                row_heights=[0.5, 0.25, 0.25])
            
            # 股價與均線
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['StockClose'], name='收盤價', line=dict(color='#ff7f0e', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['MA20'], name='月線(MA20)', line=dict(color='#1f77b4', dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['MA60'], name='季線(MA60)', line=dict(color='#2ca02c', dash='dot')), row=1, col=1)
            
            # KD 與 RSI
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['KValue'], name='K值', line=dict(color='#d62728')), row=2, col=1)
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['DValue'], name='D值', line=dict(color='#9467bd')), row=2, col=1)
            fig.add_trace(go.Scatter(x=daily_data['StockDate'], y=daily_data['RSI14'], name='RSI14', line=dict(color='#8c564b')), row=2, col=1)
            
            # 法人買賣超
            fig.add_trace(go.Bar(x=daily_data['StockDate'], y=daily_data['ForeignNetBuy'], name='外資', marker_color='#17becf'), row=3, col=1)
            fig.add_trace(go.Bar(x=daily_data['StockDate'], y=daily_data['TrustNetBuy'], name='投信', marker_color='#bcbd22'), row=3, col=1)
            
            fig.update_layout(height=700, template="plotly_dark", showlegend=True, hovermode="x", margin=dict(t=50, b=50, l=50, r=50))
            st.plotly_chart(fig, width='stretch')
            
        except Exception as e:
            # Fallback Native streamlit charts
            st.line_chart(daily_data.set_index('StockDate')[['StockClose', 'MA20', 'MA60']])
            st.line_chart(daily_data.set_index('StockDate')[['KValue', 'DValue', 'RSI14']])
            st.bar_chart(daily_data.set_index('StockDate')[['ForeignNetBuy', 'TrustNetBuy']])
            
        # 當日收盤價與相關指標表格資料
        st.markdown("---")
        st.subheader("當日收盤價與相關指標")
        factor_data = sd.get_stock_factor_metrics(selected_stock)
        if not factor_data.empty:
            row = factor_data.iloc[0]
            # 判斷近5日買超顏色
            buy_val = int(row['近5日法人淨買進(張)'])
            buy_color = "#3fb950" if buy_val > 0 else "#f85149" if buy_val < 0 else "#c9d1d9"
            
            # 判斷收盤價相較均線高低
            close_val = row['收盤價']
            ma20_val = row['月線(MA20)']
            ma60_val = row['季線(MA60)']
            
            close_display = f"<b>{close_val:.2f}</b>"
            ma20_display = f"<span style='color:{ '#3fb950' if close_val > ma20_val else '#f85149' };'>{ma20_val:.2f}</span>" if ma20_val else "N/A"
            ma60_display = f"<span style='color:{ '#3fb950' if close_val > ma60_val else '#f85149' };'>{ma60_val:.2f}</span>" if ma60_val else "N/A"
            
            html_factor = f"""
            <table style="width:100%; border: 1px solid #30363d; border-collapse: collapse; color:#c9d1d9; font-family: sans-serif; font-size: 14px; text-align: center;">
                <tr style="background-color:#161b22; border-bottom: 2px solid #30363d;">
                    <th style="padding:12px; color:#8b949e;">股票代碼</th>
                    <th style="padding:12px; color:#8b949e;">公司名稱</th>
                    <th style="padding:12px; color:#8b949e;">收盤價</th>
                    <th style="padding:12px; color:#8b949e;">月線 (MA20)</th>
                    <th style="padding:12px; color:#8b949e;">季線 (MA60)</th>
                    <th style="padding:12px; color:#8b949e;">近 5 日法人淨買超</th>
                    <th style="padding:12px; color:#8b949e;">估算季度 ROE</th>
                </tr>
                <tr>
                    <td style="padding:12px; font-weight:bold;">{row['股票代碼']}</td>
                    <td style="padding:12px; font-weight:bold;">{row['公司名稱']}</td>
                    <td style="padding:12px;">{close_display}</td>
                    <td style="padding:12px;">{ma20_display}</td>
                    <td style="padding:12px;">{ma60_display}</td>
                    <td style="padding:12px; color:{buy_color}; font-weight:bold;">{buy_val:+,d} 張</td>
                    <td style="padding:12px; color:#3fb950; font-weight:bold;">{row['估算ROE(%)']:.2f}%</td>
                </tr>
            </table>
            """
            html_factor_clean = " ".join([line.strip() for line in html_factor.split("\n")])
            st.markdown(html_factor_clean, unsafe_allow_html=True)
        else:
            st.info("尚無該股的當日收盤價與相關指標數據。")

        # 週股權分散與最新新聞 (縱向排序呈現)
        st.markdown("---")
        st.subheader("週股權集中度走勢 (千張大戶)")
        weekly_data = sd.get_stock_weekly_concentration(selected_stock)
        if not weekly_data.empty:
            html_weekly_rows = []
            for idx, r in weekly_data.iterrows():
                html_weekly_rows.append(f"""
                <tr style="border-bottom: 1px solid #21262d;">
                    <td style="padding:10px;">{r['UpdateDate']}</td>
                    <td style="padding:10px;">{r['LargeHoldersRatio1000']:.2f}%</td>
                    <td style="padding:10px;">{r['LargeHoldersRatio400']:.2f}%</td>
                    <td style="padding:10px;">{r['RetailHoldersRatio10']:.2f}%</td>
                    <td style="padding:10px; text-align:right;">{int(r['TotalShareholders']):,d} 人</td>
                </tr>
                """)
                
            html_weekly_table = f"""
            <div style="max-height: 250px; overflow-y: auto; border: 1px solid #30363d; border-radius: 6px;">
                <table style="width:100%; border-collapse: collapse; color:#c9d1d9; font-family: sans-serif; font-size: 14px; text-align: center;">
                    <tr style="background-color:#161b22; position: sticky; top: 0; border-bottom: 2px solid #30363d; z-index:10;">
                        <th style="padding:10px; color:#8b949e;">公告日期</th>
                        <th style="padding:10px; color:#8b949e;">千張大戶持股 (%)</th>
                        <th style="padding:10px; color:#8b949e;">四百張大戶持股 (%)</th>
                        <th style="padding:10px; color:#8b949e;">十張以下散戶持股 (%)</th>
                        <th style="padding:10px; color:#8b949e; text-align:right;">總股東人數</th>
                    </tr>
                    {"".join(html_weekly_rows)}
                </table>
            </div>
            """
            html_weekly_clean = " ".join([line.strip() for line in html_weekly_table.split("\n")])
            st.markdown(html_weekly_clean, unsafe_allow_html=True)
        else:
            st.info("尚無週頻率股權集中度數據記錄。")
            st.caption("提示：目前使用的是免費註冊版 FinMind 帳戶 (register 級別)，此數據集已被 FinMind 平台方設為付費贊助會員 (Sponsor) 專屬，因此受權限限制無法同步。升級 FinMind 帳戶後重新下載即可正常顯示。")
            
    else:
        st.warning("查無此時間範圍內的每日量價籌碼數據，請確認已執行盤後更新。")

# ==================== TAB 2: 新聞輿情與 AI 深度分析 ====================
with tab2:
    st.header(f"{comp_info.get('CompanyNameC', '個股')} ({selected_stock}) 新聞輿情與 AI 深度分析")
    
    # 1. 每日股價與新聞情緒指標對照折線圖
    st.subheader("每日收盤價與平均情緒指標走勢對照")
    
    col_n_date1, col_n_date2 = st.columns(2)
    with col_n_date1:
        start_d_news = st.date_input("分析開始日期", date.today() - timedelta(days=90), key="start_d_news")
    with col_n_date2:
        end_d_news = st.date_input("分析結束日期", date.today(), key="end_d_news")
        
    df_trend = sd.get_daily_price_sentiment(selected_stock, start_d_news, end_d_news)
    
    if not df_trend.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            # 建立雙 Y 軸折線圖
            fig_news = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 左軸：收盤價
            fig_news.add_trace(
                go.Scatter(x=df_trend['DateStr'], y=df_trend['StockClose'], name="收盤價", line=dict(color="#ff7f0e", width=2.5)),
                secondary_y=False,
            )
            
            # 右軸：每日平均情緒 (加總平均)
            fig_news.add_trace(
                go.Scatter(x=df_trend['DateStr'], y=df_trend['AvgSentiment'], name="平均情緒指標 (平均值)", line=dict(color="#3fb950", width=2)),
                secondary_y=True,
            )
            
            fig_news.update_layout(
                template="plotly_dark",
                hovermode="x unified",
                height=400,
                margin=dict(t=30, b=40, l=50, r=50),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            fig_news.update_yaxes(title_text="收盤價 (元)", secondary_y=False)
            fig_news.update_yaxes(title_text="平均情緒分數 (-1.0 至 +1.0)", secondary_y=True)
            
            st.plotly_chart(fig_news, width='stretch')
        except Exception as pe:
            st.error(f"繪製 Plotly 圖表時發生錯誤: {pe}")
    else:
        st.info("查無此時間範圍內的每日量價與新聞平均情緒數據。")
        
    st.markdown("---")
    
    # 2. 最新新聞列表與情緒標註
    news_data = sd.get_stock_news(selected_stock)
    if not news_data.empty:
        # 直接使用資料庫中預先計算好的 FinBERT 情緒分數，避免 UI 重新渲染時的卡頓
        news_data['SentimentScore'] = news_data['SentimentScore'].astype(float).fillna(0.0)

        # 計算 Sentiment Z-Score
        mean_sent = news_data['SentimentScore'].mean()
        std_sent = news_data['SentimentScore'].std()
        if pd.isna(std_sent) or std_sent == 0:
            news_data['SentimentZScore'] = 0.0
        else:
            news_data['SentimentZScore'] = (news_data['SentimentScore'] - mean_sent) / std_sent

        # 建立 HTML 表格
        st.subheader("最新新聞與情緒標註")
        html_rows = []
        for idx, r in news_data.iterrows():
            sent = r['SentimentScore']
            z_score = r['SentimentZScore']
            
            # 情緒標籤與樣式
            if sent > 0.1:
                sent_badge = '<span style="color:#3fb950; font-weight:bold;">🟢 利多</span>'
                z_str = f"{z_score:+.2f}"
            elif sent < -0.1:
                sent_badge = '<span style="color:#f85149; font-weight:bold;">🔴 利空</span>'
                z_str = f"{z_score:+.2f}"
            else:
                sent_badge = '<span style="color:#8b949e;">⚪ 中性</span>'
                # 當情緒指標為中性且情緒分數為 0 時，Z-Score 強制設定為 0.00
                z_score = 0.00
                z_str = "0.00"
            
            html_rows.append(f"""
            <tr style="border-bottom: 1px solid #21262d;">
                <td style="padding:12px; color:#8b949e; white-space:nowrap;">{r['PublishTime']}</td>
                <td style="padding:12px; font-weight:500;">{r['Title']}</td>
                <td style="padding:12px; white-space:nowrap;">{sent_badge}</td>
                <td style="padding:12px; text-align:right; white-space:nowrap;">{sent:.2f}</td>
                <td style="padding:12px; text-align:right; white-space:nowrap; color:#{ '3fb950' if z_score > 1e-5 else 'f85149' if z_score < -1e-5 else '8b949e' };">{z_str}</td>
                <td style="padding:12px; text-align:center; white-space:nowrap;"><a href="{r['NewsLink']}" target="_blank" style="color:#58a6ff; text-decoration:none; font-weight:bold;">點此閱讀 ↗</a></td>
            </tr>
            """)
            
        html_table = f"""
        <div style="max-height: 400px; overflow-y: auto; border: 1px solid #30363d; border-radius: 6px;">
            <table style="width:100%; border-collapse: collapse; color:#c9d1d9; font-family: sans-serif; font-size: 14px;">
                <tr style="background-color:#161b22; position: sticky; top: 0; border-bottom: 2px solid #30363d; text-align:left; z-index:10;">
                    <th style="padding:12px; color:#8b949e;">發布時間</th>
                    <th style="padding:12px; color:#8b949e;">新聞標題</th>
                    <th style="padding:12px; color:#8b949e;">情緒標籤</th>
                    <th style="padding:12px; color:#8b949e; text-align:right;">情緒分數</th>
                    <th style="padding:12px; color:#8b949e; text-align:right;">情緒Z-Score</th>
                    <th style="padding:12px; color:#8b949e; text-align:center;">新聞連結</th>
                </tr>
                {"".join(html_rows)}
            </table>
        </div>
        """
        html_table_clean = " ".join([line.strip() for line in html_table.split("\n")])
        st.markdown(html_table_clean, unsafe_allow_html=True)
        
        # Ollama AI 新聞深度分析與因果總結
        st.markdown(" ")
        st.subheader("AI新聞分析與因果總結")
        with st.spinner("AI分析師對當前新聞進行因果剖析中，請稍候..."):
            ollama_summary = sd.get_news_ollama_summary(selected_stock, comp_info.get('CompanyNameC', '該個股'), news_data, df_trend)
        
        with st.container(border=True):
            st.markdown(ollama_summary)
    else:
        st.info("尚無新聞數據記錄。")

# ==================== TAB 3: 財務警訊與閥值設定 ====================
with tab3:
    st.header(f"{comp_info.get('CompanyNameC', '個股')} ({selected_stock}) 財務防雷警報與閾值管理")
    
    # 取得當前閥值與歷史警告
    threshold, warnings = sd.get_financial_warning_indicators(selected_stock)
    
    col_t_setup, col_w_report = st.columns([1, 2])
    
    with col_t_setup:
        st.subheader("自訂警示門檻值")
        st.markdown("可為此個股單獨設定財務警示警戒線。若最新季度財報觸發此臨界點，系統將自動亮起紅色警示燈。")
        
        # 門檻值輸入框
        min_eq = st.number_input("盈餘品質下限 (營業現金流/本期淨利, %)", min_value=0.0, max_value=200.0, value=float(threshold.get('MinEarningsQualityRatio', 80.00)), step=5.0)
        max_recv = st.number_input("最大應收帳款收回天數 (天)", min_value=0.0, max_value=365.0, value=float(threshold.get('MaxReceivableTurnoverDays', 120.00)), step=5.0)
        max_inv = st.number_input("最大存貨週轉天數 (天)", min_value=0.0, max_value=365.0, value=float(threshold.get('MaxInventoryTurnoverDays', 150.00)), step=5.0)
        max_debt = st.number_input("負債比率上限 (%)", min_value=0.0, max_value=100.0, value=float(threshold.get('MaxDebtRatio', 60.00)), step=2.0)
        min_int = st.number_input("最小利息保障倍數 (倍)", min_value=0.0, max_value=100.0, value=float(threshold.get('MinInterestCoverage', 3.00)), step=0.5)
        
        if st.button("儲存並重新評估"):
            success = sd.update_company_thresholds(selected_stock, min_eq, max_recv, max_inv, max_debt, min_int)
            if success:
                st.success("個股防雷門檻更新成功，財務指標已重新評算！")
                st.rerun()
            else:
                st.error("儲存閥值設定失敗。")
                
    with col_w_report:
        st.subheader("季度財務防雷安全燈號")
        if not warnings.empty:
            st.markdown("下列為最近數季的財務安全性分析。**紅色** 代表該項目未達標或超標，亮起財務爆雷警訊；**綠色** 代表體質健全。")
            
            # 手動將警示燈號渲染成 HTML
            html_rows = []
            for idx, r in warnings.iterrows():
                # 現金流
                cf_light = f'<div class="warning-light-red">警告 ({r["EarningsQualityRatio"]:.1f}%)</div>' if r['IsCashFlowWarning'] else f'<div class="warning-light-green">合格 ({r["EarningsQualityRatio"]:.1f}%)</div>'
                # 負債比
                debt_light = f'<div class="warning-light-red">警告 ({r["DebtToEquityRatio"]:.1f}%)</div>' if r['IsDebtWarning'] else f'<div class="warning-light-green">合格 ({r["DebtToEquityRatio"]:.1f}%)</div>'
                # 應收
                recv_light = f'<div class="warning-light-red">警告 ({r["ReceivableTurnoverDays"]:.0f}天)</div>' if r['IsReceivableWarning'] else f'<div class="warning-light-green">合格 ({r["ReceivableTurnoverDays"]:.0f}天)</div>'
                # 存貨
                inv_light = f'<div class="warning-light-red">警告 ({r["InventoryTurnoverDays"]:.0f}天)</div>' if r['IsInventoryWarning'] else f'<div class="warning-light-green">合格 ({r["InventoryTurnoverDays"]:.0f}天)</div>'
                
                html_rows.append(f"""
                <tr>
                    <td><b>{r['Year']} Q{r['Quarter']}</b></td>
                    <td>{cf_light}</td>
                    <td>{debt_light}</td>
                    <td>{recv_light}</td>
                    <td>{inv_light}</td>
                    <td>{r['InterestCoverageRatio']:.2f} 倍</td>
                </tr>
                """)
                
            html_table = f"""
            <table style="width:100%; border: 1px solid #30363d; border-collapse: collapse; color:#c9d1d9;">
                <tr style="background-color:#161b22; text-align:left;">
                    <th style="padding:10px;">季度</th>
                    <th style="padding:10px;">盈餘品質 (現金流比率)</th>
                    <th style="padding:10px;">負債比率</th>
                    <th style="padding:10px;">應收帳款收回天數</th>
                    <th style="padding:10px;">存貨週轉天數</th>
                    <th style="padding:10px;">利息保障倍數</th>
                </tr>
                {"".join(html_rows)}
            </table>
            """
            # 移除換行與縮排，避免 Streamlit Markdown 將縮排字串誤解析為程式碼塊
            html_table_clean = " ".join([line.strip() for line in html_table.split("\n")])
            st.markdown(html_table_clean, unsafe_allow_html=True)
            
        else:
            st.info("尚無財務警示指標紀錄，請確認資料庫中已同步該股的財務三表數據。")

# ==================== TAB 4: AI 智慧研究助理 (RAG) ====================
with tab4:
    st.header(f"{comp_info.get('CompanyNameC', '個股')} ({selected_stock}) 綜合AI分析報告")
    st.markdown("結合資料庫中**最新 24 小時新聞輿情**、**今日法人籌碼**、**大戶集中度**與**最新季度防雷警示**，即時生成精準分析研報。")
    
    custom_question = st.text_input("自訂詢問項目 (例如: 針對該公司的庫存積壓或董監質押風險進行評估)", 
                                    placeholder="留空則進行全方面綜合評析...")
    
    if st.button("產生AI分析報告"):
        with st.status("🔍 正在執行即時分析流程...", expanded=True) as status:
            st.write("1. 正在從資料庫撈取即時股價、移動平均線、KD技術指標...")
            st.write("2. 正在取得最新一週千張大戶股權集中度...")
            st.write("3. 正在比對個股自訂門檻，審查季度財務三表防雷燈號...")
            st.write("4. 正在向量檢索最新 5 篇熱門新聞輿情並標註情緒...")
            st.write("5. 正在組合 Context 推送至 Ollama Cloud 進行推理運算...")
            
            # 即時生成
            report = sd.get_realtime_rag_report(selected_stock, custom_question)
            
            status.update(label="AI分析完成！已生成報告：", state="complete")
        st.markdown(report)
