import pandas as pd
from datetime import datetime
from sqlalchemy import text

def calculate_and_save_warnings(stock_code, engine, thresholds=None):
    """
    計算指定個股的財務防雷指標，並將結果 UPSERT 寫入資料庫
    :param stock_code: 股票代號 (例如 '2330')
    :param engine: SQLAlchemy Database Engine
    :param thresholds: 可選的自訂閥值字典，若無則從資料庫 CompanyWarningThresholds 讀取
    :return: True 代表成功，False 代表失敗或無資料
    """
    try:
        # 1. 取得閥值
        if thresholds is None:
            with engine.connect() as conn:
                t_row = conn.execute(
                    text('SELECT "MinEarningsQualityRatio", "MaxReceivableTurnoverDays", "MaxInventoryTurnoverDays", "MaxDebtRatio", "MinInterestCoverage" FROM "CompanyWarningThresholds" WHERE "StockCode" = :stock_id'),
                    {"stock_id": stock_code}
                ).fetchone()
                
            if t_row:
                min_eq = float(t_row[0] if t_row[0] is not None else 80.00)
                max_recv = float(t_row[1] if t_row[1] is not None else 120.00)
                max_inv = float(t_row[2] if t_row[2] is not None else 150.00)
                max_debt = float(t_row[3] if t_row[3] is not None else 60.00)
                min_int = float(t_row[4] if t_row[4] is not None else 3.00)
            else:
                # 預設安全值
                min_eq, max_recv, max_inv, max_debt, min_int = 80.00, 120.00, 150.00, 60.00, 3.00
        else:
            min_eq = float(thresholds.get("MinEarningsQualityRatio", 80.00))
            max_recv = float(thresholds.get("MaxReceivableTurnoverDays", 120.00))
            max_inv = float(thresholds.get("MaxInventoryTurnoverDays", 150.00))
            max_debt = float(thresholds.get("MaxDebtRatio", 60.00))
            min_int = float(thresholds.get("MinInterestCoverage", 3.00))

        # 2. 撈取該股的季度財務原始資料 (以 Balance Sheet 與 Cash Flow 進行比率計算)
        query = text("""
            WITH AllDates AS (
                SELECT "StockCode", "DateInfo" FROM "StockBalance" WHERE "StockCode" = :stock_id
                UNION
                SELECT "StockCode", "DateInfo" FROM "StockFinancial" WHERE "StockCode" = :stock_id
                UNION
                SELECT "StockCode", "DateInfo" FROM "StockCashflow" WHERE "StockCode" = :stock_id
            )
            SELECT 
                ad."DateInfo",
                MAX(CASE WHEN c."Types" IN ('CashFlowsFromOperatingActivities', 'NetCashInflowFromOperatingActivities') OR c."OriginName" IN ('營業活動之淨現金流入（流出）', '營業活動之淨現金流入') THEN c."DataValue" END) as ocf,
                MAX(CASE WHEN f."Types" IN ('IncomeAfterTaxes', 'IncomeAfterTax') OR f."OriginName" IN ('本期淨利（淨損）', '本期稅後淨利（淨損）') THEN f."DataValue" END) as ni,
                MAX(CASE WHEN (b."Types" = 'Liabilities' OR b."OriginName" = '負債總額') AND b."Types" NOT LIKE '%_per' THEN b."DataValue" END) as debt,
                MAX(CASE WHEN (b."Types" = 'TotalAssets' OR b."OriginName" = '資產總額') AND b."Types" NOT LIKE '%_per' THEN b."DataValue" END) as assets,
                MAX(CASE WHEN f."Types" = 'OperatingIncome' OR f."OriginName" = '營業利益（損失）' THEN f."DataValue" END) as op_inc,
                MAX(CASE WHEN c."Types" IN ('InterestExpense', 'PayTheInterest') OR c."OriginName" IN ('利息費用', '支付之利息') THEN c."DataValue" END) as int_exp,
                MAX(CASE WHEN b."Types" IN ('AccountsReceivable', 'NotesAndAccountsReceivable') OR b."OriginName" IN ('應收帳款', '應收帳款合計', '應收票據及帳款') THEN b."DataValue" END) as ar,
                MAX(CASE WHEN b."Types" IN ('Inventories', 'Inventory') OR b."OriginName" IN ('存貨', '存貨合計') THEN b."DataValue" END) as inv,
                MAX(CASE WHEN f."Types" IN ('Revenue', 'OperatingRevenue') OR f."OriginName" IN ('營業收入合計', '營業收入', '營業收入淨額') THEN f."DataValue" END) as revenue,
                MAX(CASE WHEN f."Types" IN ('OperatingCosts', 'CostOfGoodsSold') OR f."OriginName" IN ('營業成本合計', '營業成本') THEN f."DataValue" END) as cost
            FROM AllDates ad
            LEFT JOIN "StockBalance" b ON ad."StockCode" = b."StockCode" AND ad."DateInfo" = b."DateInfo"
            LEFT JOIN "StockFinancial" f ON ad."StockCode" = f."StockCode" AND ad."DateInfo" = f."DateInfo"
            LEFT JOIN "StockCashflow" c ON ad."StockCode" = c."StockCode" AND ad."DateInfo" = c."DateInfo"
            GROUP BY ad."DateInfo"
            ORDER BY ad."DateInfo" DESC
        """)
        
        df = pd.read_sql(query, con=engine, params={"stock_id": stock_code}).fillna(0)
        if df.empty:
            return False

        with engine.connect() as conn:
            for idx, r in df.iterrows():
                d = r['DateInfo']
                dt = datetime.strptime(d, '%Y-%m-%d') if isinstance(d, str) else d
                year = int(dt.year)
                quarter = int((dt.month - 1) // 3 + 1)
                
                # 1. 盈餘品質 (ocf / ni * 100)
                ni_val = float(r['ni'])
                ocf_val = float(r['ocf'])
                eq_ratio = (ocf_val / ni_val * 100) if ni_val > 0 else (100.0 if ocf_val >= 0 else -100.0)
                
                # 2. 負債比率 (debt / assets * 100)
                assets_val = float(r['assets'])
                debt_val = float(r['debt'])
                debt_ratio = (debt_val / assets_val * 100) if assets_val > 0 else 0.0
                
                # 3. 利息保障倍數 (op_inc / int_exp)
                int_val = float(r['int_exp'])
                op_val = float(r['op_inc'])
                int_coverage = (op_val / int_val) if int_val > 0 else (999.0 if op_val >= 0 else -999.0)
                
                # 4. 應收帳款與存貨週轉天數 (真實公式計算)
                ar_val = float(r.get('ar') or 0.0)
                inv_val = float(r.get('inv') or 0.0)
                rev_val = float(r.get('revenue') or 0.0)
                cost_val = float(r.get('cost') or 0.0)
                
                # 年化應收帳款週轉率 = 季度營收 * 4
                if rev_val > 0:
                    recv_days = (ar_val / (rev_val * 4 / 365))
                else:
                    recv_days = 65.0
                    
                # 年化存貨週轉率 = 季度營業成本 * 4
                if cost_val > 0:
                    inv_days = (inv_val / (cost_val * 4 / 365))
                else:
                    inv_days = 85.0

                is_cf_warn = 1 if eq_ratio < min_eq else 0
                is_debt_warn = 1 if debt_ratio > max_debt else 0
                is_recv_warn = 1 if recv_days > max_recv else 0
                is_inv_warn = 1 if inv_days > max_inv else 0

                # UPSERT 警告結果
                update_warn = text("""
                    INSERT INTO "FinancialWarningIndicators"
                    ("StockCode", "Year", "Quarter", "EarningsQualityRatio", "ReceivableTurnoverDays", "InventoryTurnoverDays", "DebtToEquityRatio", "InterestCoverageRatio",
                     "IsReceivableWarning", "IsInventoryWarning", "IsCashFlowWarning", "IsDebtWarning")
                    VALUES (:stock_id, :year, :quarter, :eq_ratio, :recv_days, :inv_days, :debt_ratio, :int_coverage,
                            :is_recv_warn, :is_inv_warn, :is_cf_warn, :is_debt_warn)
                    ON CONFLICT ("StockCode", "Year", "Quarter") DO UPDATE SET
                        "EarningsQualityRatio" = EXCLUDED."EarningsQualityRatio",
                        "ReceivableTurnoverDays" = EXCLUDED."ReceivableTurnoverDays",
                        "InventoryTurnoverDays" = EXCLUDED."InventoryTurnoverDays",
                        "DebtToEquityRatio" = EXCLUDED."DebtToEquityRatio",
                        "InterestCoverageRatio" = EXCLUDED."InterestCoverageRatio",
                        "IsReceivableWarning" = EXCLUDED."IsReceivableWarning",
                        "IsInventoryWarning" = EXCLUDED."IsInventoryWarning",
                        "IsCashFlowWarning" = EXCLUDED."IsCashFlowWarning",
                        "IsDebtWarning" = EXCLUDED."IsDebtWarning"
                """)
                conn.execute(update_warn, {
                    "stock_id": stock_code,
                    "year": year,
                    "quarter": quarter,
                    "eq_ratio": round(eq_ratio, 2),
                    "recv_days": round(recv_days, 2),
                    "inv_days": round(inv_days, 2),
                    "debt_ratio": round(debt_ratio, 2),
                    "int_coverage": round(int_coverage, 2),
                    "is_recv_warn": is_recv_warn,
                    "is_inv_warn": is_inv_warn,
                    "is_cf_warn": is_cf_warn,
                    "is_debt_warn": is_debt_warn
                })
            conn.commit()
        return True
    except Exception as e:
        print(f"計算或儲存 {stock_code} 防雷警報時出錯: {e}")
        return False
