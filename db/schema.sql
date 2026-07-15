-- Drop tables if they exist
DROP TABLE IF EXISTS "FinancialWarningIndicators" CASCADE;
DROP TABLE IF EXISTS "CompanyWarningThresholds" CASCADE;
DROP TABLE IF EXISTS "StockWeeklyConcentration" CASCADE;
DROP TABLE IF EXISTS "StockDailyMetrics" CASCADE;
DROP TABLE IF EXISTS "StockNews" CASCADE;
DROP TABLE IF EXISTS "StockInvestorsBuy" CASCADE;
DROP TABLE IF EXISTS "StockCashflow" CASCADE;
DROP TABLE IF EXISTS "StockBalance" CASCADE;
DROP TABLE IF EXISTS "StockFinancial" CASCADE;
DROP TABLE IF EXISTS "StockDividend" CASCADE;
DROP TABLE IF EXISTS "StockRevenue" CASCADE;
DROP TABLE IF EXISTS "StockPriceInfo" CASCADE;
DROP TABLE IF EXISTS "CompanyBaseInfo" CASCADE;

-- 1. 公司基本資訊表
CREATE TABLE "CompanyBaseInfo"(
    "StockCode" VARCHAR(10) PRIMARY KEY, -- 股票代號
    "CompanyNameC" VARCHAR(50),          -- 中文名稱
    "CompanyNameAbbr" VARCHAR(50),       -- 公司簡稱
    "CompanyNameE" VARCHAR(100),         -- 英文名稱
    "ChairmanName" VARCHAR(50),          -- 董事長
    "EstablishmentDate" Date,            -- 成立時間
    "ListingDate" Date,                  -- 掛牌日期
    "CompanyClass" VARCHAR(50),          -- 產業類別
    "Webside" VARCHAR(200),               -- 公司網站
    "CompanyEmail" VARCHAR(100),         -- 電子郵件
    "GeneralManager" VARCHAR(50),        -- 總經理
    "CompanyAddress" VARCHAR(200),       -- 公司地址
    "MarketClass" VARCHAR(20),           -- 市場別 (上市/上櫃)
    "MainBusinessActivities" TEXT        -- 主要業務說明
);

-- 2. 每日技術與籌碼綜合時序表
CREATE TABLE "StockDailyMetrics" (
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "StockDate" DATE NOT NULL,
    -- 價格量價數據
    "StockClose" DECIMAL(10, 2) NOT NULL,
    "TradingVolume" DECIMAL(18, 2),
    "TradingMoney" DECIMAL(18, 2),
    -- 技術面指標 (由系統運算引擎動態計算並更新)
    "MA20" DECIMAL(10, 2),
    "MA60" DECIMAL(10, 2),
    "KValue" DECIMAL(6, 2),
    "DValue" DECIMAL(6, 2),
    "RSI14" DECIMAL(6, 2),
    "MACD_Hist" DECIMAL(10, 2),
    -- 籌碼面指標 (日頻率)
    "ForeignNetBuy" DECIMAL(18, 2),  -- 外資買賣超張數
    "TrustNetBuy" DECIMAL(18, 2),    -- 投信買賣超張數
    "DealerNetBuy" DECIMAL(18, 2),   -- 自營商買賣超張數
    "MarginBalance" DECIMAL(18, 2),  -- 融資餘額張數
    "ShortBalance" DECIMAL(18, 2),   -- 融券餘額張數
    PRIMARY KEY ("StockCode", "StockDate")
);

-- 建立索引以優化篩選與圖表加載性能
CREATE INDEX idx_daily_metrics_date ON "StockDailyMetrics" ("StockDate" DESC, "StockCode");

-- 3. 週頻率股權集中度時序表
CREATE TABLE "StockWeeklyConcentration" (
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "UpdateDate" DATE NOT NULL,
    "LargeHoldersRatio400" DECIMAL(5, 2) NOT NULL,   -- 400張以上大戶持股比例
    "LargeHoldersRatio1000" DECIMAL(5, 2) NOT NULL,  -- 1000張以上大戶持股比例
    "RetailHoldersRatio10" DECIMAL(5, 2) NOT NULL,   -- 10張以下散戶持股比例
    "TotalShareholders" INT NOT NULL,                -- 總股東人數
    PRIMARY KEY ("StockCode", "UpdateDate")
);

CREATE INDEX idx_weekly_chip_date ON "StockWeeklyConcentration" ("UpdateDate" DESC, "StockCode");

-- 4. 財務收益表 (月營收)
CREATE TABLE "StockRevenue"(
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "RevenueYear" INT NOT NULL,
    "RevenueMonth" INT NOT NULL,
    "TotalRevenue" DECIMAL(18, 2), -- 月營收額
    PRIMARY KEY ("StockCode", "RevenueYear", "RevenueMonth")
);

-- 5. 股票股息表
CREATE TABLE "StockDividend"(
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "DateInfo" VARCHAR(20) NOT NULL,       -- 年度與季度
    "CashDividends" DECIMAL(10, 2),        -- 現金股息
    "StockDividend" DECIMAL(10, 2),        -- 股票股息
    "ExDividendDate" DATE,                 -- 除息交易日
    "CashDividendDate" DATE,               -- 股息發放日
    PRIMARY KEY ("StockCode", "DateInfo")
);

-- 6. 損益表 (按季度/年度申報)
CREATE TABLE "StockFinancial"(
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "DateInfo" DATE NOT NULL,
    "Types" VARCHAR(300) NOT NULL,
    "DataValue" DECIMAL(18, 2),
    "OriginName" VARCHAR(300),
    PRIMARY KEY ("StockCode", "DateInfo", "Types")
);

-- 7. 資產負債表
CREATE TABLE "StockBalance"(
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "DateInfo" DATE NOT NULL,
    "Types" VARCHAR(300) NOT NULL,
    "DataValue" DECIMAL(18, 2),
    "OriginName" VARCHAR(300),
    PRIMARY KEY ("StockCode", "DateInfo", "Types")
);

-- 8. 現金流量表
CREATE TABLE "StockCashflow"(
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "DateInfo" DATE NOT NULL,
    "Types" VARCHAR(300) NOT NULL,
    "DataValue" DECIMAL(18, 2),
    "OriginName" VARCHAR(300),
    PRIMARY KEY ("StockCode", "DateInfo", "Types")
);

-- 9. 新聞與輿情情緒表
CREATE TABLE "StockNews"(
    "NewsId" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "Title" TEXT NOT NULL,
    "Content" TEXT,
    "PublishTime" TIMESTAMP,
    "NewsLink" TEXT,
    "SentimentScore" DECIMAL(4, 2) DEFAULT 0.00 -- 情緒分數 (-1.00 至 +1.00)
);

CREATE INDEX idx_news_stock_code ON "StockNews" ("StockCode", "PublishTime" DESC);
CREATE UNIQUE INDEX idx_news_unique_link ON "StockNews" ("StockCode", "NewsLink");

-- 10. 個股客製化財務防雷閥值設定表
CREATE TABLE "CompanyWarningThresholds" (
    "StockCode" VARCHAR(10) PRIMARY KEY REFERENCES "CompanyBaseInfo"("StockCode"),
    "MinEarningsQualityRatio" DECIMAL(5, 2) DEFAULT 80.00,       -- 營業現金流/稅後淨利比 (應 > 80%)
    "MaxReceivableTurnoverDays" DECIMAL(6, 2) DEFAULT 120.00,     -- 應收帳款週轉天數上限 (天)
    "MaxInventoryTurnoverDays" DECIMAL(6, 2) DEFAULT 150.00,      -- 存貨週轉天數上限 (天)
    "MaxDebtRatio" DECIMAL(5, 2) DEFAULT 60.00,                  -- 負債比率上限 (%)
    "MinInterestCoverage" DECIMAL(6, 2) DEFAULT 3.00,            -- 利息保障倍數下限 (倍)
    "LastUpdated" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 11. 財務防雷警告評估結果表 (每季計算結果)
CREATE TABLE "FinancialWarningIndicators" (
    "StockCode" VARCHAR(10) NOT NULL REFERENCES "CompanyBaseInfo"("StockCode"),
    "Year" INT NOT NULL,
    "Quarter" INT NOT NULL,
    "EarningsQualityRatio" DECIMAL(8, 2),
    "ReceivableTurnoverDays" DECIMAL(8, 2),
    "InventoryTurnoverDays" DECIMAL(8, 2),
    "DebtToEquityRatio" DECIMAL(8, 2),
    "InterestCoverageRatio" DECIMAL(8, 2),
    -- 警訊標誌 (0: 正常合格, 1: 觸發警告)
    "IsReceivableWarning" SMALLINT DEFAULT 0,
    "IsInventoryWarning" SMALLINT DEFAULT 0,
    "IsCashFlowWarning" SMALLINT DEFAULT 0,
    "IsDebtWarning" SMALLINT DEFAULT 0,
    PRIMARY KEY ("StockCode", "Year", "Quarter")
);
