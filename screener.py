import pandas as pd
import yfinance as yf

# 設定要篩選的台股清單（可自行擴充或自 TWSE 抓取全股市清單）
stock_list = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "3293.TWO"]

selected_stocks = []

for symbol in stock_list:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3m")
        if df.empty or len(df) < 60:
            continue
        
        # 計算技術指標
        close = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        avg_volume = df['Volume'].tail(5).mean()

        # 篩選條件：站上 20日/60日均線 且 5日均量 > 1000張
        if close > ma20 and ma20 > ma60 and avg_volume > 1000000:
            info = ticker.info
            selected_stocks.append({
                "代號": symbol,
                "收盤價": round(close, 2),
                "本益比": info.get("trailingPE", "N/A"),
                "殖利率(%)": round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else "N/A"
            })
    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# 輸出篩選結果
result_df = pd.DataFrame(selected_stocks)
print(result_df)
