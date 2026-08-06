import pandas as pd
import yfinance as yf
import requests
import json
import time

def get_all_taiwan_stocks():
    """抓取全台灣上市與上櫃的股票清單"""
    stocks = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. 上市股票清單
    try:
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        df_twse = pd.read_html(url_twse)[0]
        df_twse.columns = df_twse.iloc[0]
        df_twse = df_twse.iloc[1:]
        for item in df_twse['有價證券代號及名稱'].dropna():
            parts = str(item).split('\u3000')
            if len(parts) == 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4 and code.isdigit():
                    stocks.append({'symbol': f"{code}.TW", 'code': code, 'name': name, 'market': '上市'})
    except Exception as e:
        print(f"抓取上市清單失敗: {e}")

    # 2. 上櫃股票清單
    try:
        url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        df_tpex = pd.read_html(url_tpex)[0]
        df_tpex.columns = df_tpex.iloc[0]
        df_tpex = df_tpex.iloc[1:]
        for item in df_tpex['有價證券代號及名稱'].dropna():
            parts = str(item).split('\u3000')
            if len(parts) == 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4 and code.isdigit():
                    stocks.append({'symbol': f"{code}.TWO", 'code': code, 'name': name, 'market': '上櫃'})
    except Exception as e:
        print(f"抓取上櫃清單失敗: {e}")

    return stocks

print("1. 開始取得全台股上市與上櫃股票清單...")
all_stocks = get_all_taiwan_stocks()
print(f"成功取得 {len(all_stocks)} 檔台灣股票，準備進行 4 大條件篩選...")

filtered_results = []

# 為了確保 GitHub Actions 執行速度，批量掃描全台股
for idx, item in enumerate(all_stocks):
    symbol = item['symbol']
    code = item['code']
    name = item['name']
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # 抓取篩選所需欄位
        price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
        pe = info.get('trailingPE', 0) or 0
        div_yield = info.get('dividendYield', 0) or 0
        div_yield_pct = div_yield * 100 if div_yield else 0.0
        market_cap = info.get('marketCap', 0) or 0
        
        # 計算 20 日平均成交金額 (20日均量 * 股價)
        avg_volume_20d = info.get('averageVolume10days') or info.get('averageVolume') or 0
        avg_turnover_20d = avg_volume_20d * price

        # -----------------------------------------------------
        # 嚴格 4 大篩選條件判斷
        # -----------------------------------------------------
        # 1. 20日平均成交金額 >= 30,000,000 TWD (3000萬)
        cond1 = avg_turnover_20d >= 30000000
        
        # 2. 本益比 (P/E) < 18 且 > 0
        cond2 = 0 < pe < 18
        
        # 3. 現金殖利率 >= 4.5%
        cond3 = div_yield_pct >= 4.5
        
        # 4. 總市值 < 200,000,000,000 TWD (2000億)
        cond4 = market_cap < 200000000000

        # 通過所有 4 個門檻才加入最終清單
        if cond1 and cond2 and cond3 and cond4:
            # 製作好理解的標籤
            tags = ["💰 高配息", "🏷️ 價格甜甜", "🔥 交易熱絡"]
            
            # 計算綜合分數
            score = round(70 + (div_yield_pct * 3) + ((18 - pe) * 1.5), 1)
            score = min(score, 99.0)

            filtered_results.append({
                "code": code,
                "name": name,
                "market": item['market'],
                "price": f"${round(price, 1)}",
                "pe": f"{round(pe, 1)} 倍",
                "yield": f"{round(div_yield_pct, 2)}%",
                "turnover": f"{round(avg_turnover_20d / 1000000, 1)} 百萬",
                "market_cap": f"{round(market_cap / 100000000, 1)} 億",
                "score": score,
                "tags": tags
            })
            print(f"  [符合標的] {code} {name} - 殖利率:{round(div_yield_pct,2)}%, 本益比:{round(pe,1)}")

    except Exception:
        continue

# 依綜合推薦分數從高到低排序
filtered_results.sort(key=lambda x: x['score'], reverse=True)

print(f"\n全市場掃描完成！共篩選出 {len(filtered_results)} 檔符合條件的優質標的。")

# 寫入 stocks.json 供前端讀取
with open('stocks.json', 'w', encoding='utf-8') as f:
    json.dump(filtered_results, f, ensure_ascii=False, indent=2)
