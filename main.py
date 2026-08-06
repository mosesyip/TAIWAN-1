import pandas as pd
import yfinance as yf
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_all_taiwan_stocks():
    stocks = []
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
    except Exception:
        pass

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
    except Exception:
        pass

    return stocks

def process_stock(item):
    symbol = item['symbol']
    code = item['code']
    name = item['name']
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
        if price <= 0:
            return None
            
        pe = info.get('trailingPE', 0) or 0
        div_yield = info.get('dividendYield', 0) or 0
        div_yield_pct = div_yield * 100 if div_yield else 0.0
        market_cap = info.get('marketCap', 0) or 0
        
        avg_vol = info.get('averageVolume10days') or info.get('averageVolume') or 0
        avg_turnover = avg_vol * price

        # 4 大條件判斷
        c1 = avg_turnover >= 30000000        # 成交金額 > 3000萬
        c2 = 0 < pe < 18                     # 本益比 < 18
        c3 = div_yield_pct >= 4.5            # 殖利率 >= 4.5%
        c4 = market_cap < 200000000000       # 市值 < 2000億

        passed_count = sum([c1, c2, c3, c4])

        # 至少要符合 3 個條件才進入候選池
        if passed_count >= 3:
            # AI 綜合 CP 值計算公式 (滿分約 100 分)
            yield_score = div_yield_pct * 9                          # 殖利率越高分數越高
            pe_score = max(0, (18 - pe) * 2.5) if pe > 0 else 0       # 本益比越低越便宜分數越高
            liquidity_score = min(15, (avg_turnover / 10000000))     # 流動性加分
            total_score = round(yield_score + pe_score + liquidity_score, 1)

            tags = []
            if c1: tags.append("🔥 熱門易買賣")
            if c2: tags.append("🏷️ 價格甜甜")
            if c3: tags.append("💰 高配息")
            if c4: tags.append("🌱 中小型股")

            missing_note = ""
            if not c1: missing_note = "成交量稍低"
            elif not c2: missing_note = "價格略貴"
            elif not c3: missing_note = "配息稍低"
            elif not c4: missing_note = "大型權值股"

            return {
                "code": code,
                "name": name,
                "market": item['market'],
                "price": f"${round(price, 1)}",
                "pe": f"{round(pe, 1)} 倍" if pe > 0 else "N/A",
                "yield": f"{round(div_yield_pct, 2)}%",
                "turnover": f"{round(avg_turnover / 1000000, 1)} 百萬",
                "passed_count": passed_count,
                "score": total_score,
                "is_full_match": passed_count == 4,
                "missing_note": missing_note,
                "tags": tags
            }
    except Exception:
        pass
    return None

if __name__ == '__main__':
    all_stocks = get_all_taiwan_stocks()
    candidates = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_stock, item) for item in all_stocks]
        for future in as_completed(futures):
            res = future.result()
            if res:
                candidates.append(res)

    # 排序邏輯：符合條件數多者優先(4>3)，同條件數者依 AI 分數由高到低排序
    candidates.sort(key=lambda x: (x['passed_count'], x['score']), reverse=True)

    # 取前 20 名
    top_20 = candidates[:20]

    # 給予名次與 AI 評價評語
    for rank, stock in enumerate(top_20, 1):
        stock['rank'] = rank
        if stock['is_full_match']:
            stock['ai_comment'] = "🎯 完美高分：4項指標完全過關"
        else:
            stock['ai_comment'] = f"👀 綜合高分：僅差在「{stock['missing_note']}」"

    output_data = {
        "top_20": top_20
    }

    with open('stocks.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
