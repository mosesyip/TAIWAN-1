import json
import pandas as pd
import yfinance as yf

def get_stock_list():
    url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    stocks = []
    for url, suffix in [(url_twse, ".TW"), (url_tpex, ".TWO")]:
        try:
            res = pd.read_html(url)[0]
            res.columns = res.iloc[0]
            df = res.iloc[1:]
            df_stocks = df[df['CFICode'] == 'ESVUFR']['有價證券代號及名稱'].str.split(' ').str[0]
            for s in df_stocks:
                stocks.append(f"{s}{suffix}")
        except Exception:
            pass
    return stocks

def generate_dashboard_data():
    all_stocks = get_stock_list()
    # 測試先掃描前 100 檔驗證功能
    target_stocks = all_stocks[:100] if all_stocks else ["2330.TW", "2317.TW", "3556.TWO"]
    
    results = []
    for symbol in target_stocks:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1mo")
            if df.empty or len(df) < 15:
                continue
            
            close = df['Close'].iloc[-1]
            avg_vol = df['Volume'].mean()
            avg_amt = avg_vol * close
            
            info = ticker.info
            market_cap = info.get("marketCap", 0) / 1e8
            pe = info.get("trailingPE", None)
            div_yield = (info.get("dividendYield") or 0) * 100
            
            # 篩選邏輯：日均額 >= 3000萬、PE < 18、殖利率 >= 4.5%、市值 < 200億
            if (avg_amt >= 30000000) and (pe and 0 < pe < 18) and (div_yield >= 4.5) and (market_cap < 200):
                code = symbol.replace(".TW", "").replace(".TWO", "")
                results.append({
                    "rank": len(results) + 1,
                    "delta": "NEW",
                    "code": code,
                    "name": info.get("shortName", f"股票{code}"),
                    "industry": info.get("industry", "半導體/電子"),
                    "total_score": round(95.0 - (len(results) * 2), 1),
                    "momentum": 50,
                    "quality": 30,
                    "val_flow": 20,
                    "rev_3m": f"{round(close, 1)} 元",
                    "profit_growth": f"{round(pe, 1)} 倍",
                    "cash_conv": f"{round(div_yield, 1)}%"
                })
        except Exception:
            continue

    with open("stocks.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    generate_dashboard_data()
