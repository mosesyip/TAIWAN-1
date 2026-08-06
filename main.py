import json
import requests
from datetime import datetime, timezone, timedelta

def fetch_data():
    # 1. 設定台灣時區 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    update_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")

    stocks_map = {}

    # 2. 抓取上市股票本益比與殖利率 (BWIBBU_ALL)
    try:
        url_bw = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res_bw = requests.get(url_bw, timeout=10).json()
        for row in res_bw:
            code = row.get("Code")
            name = row.get("Name")
            try:
                pe = float(row.get("PEratio", 0)) if row.get("PEratio") else 0
                dividend_yield = float(row.get("DividendYield", 0)) if row.get("DividendYield") else 0
            except ValueError:
                continue
            
            if code and name:
                stocks_map[code] = {
                    "code": code,
                    "name": name,
                    "pe": pe,
                    "yield_rate": dividend_yield,
                    "turnover_wan": 0,
                    "price": 0.0
                }
    except Exception as e:
        print(f"Error fetching TWSE BWIBBU: {e}")

    # 3. 抓取上市股票價格與成交金額 (STOCK_DAY_ALL)
    try:
        url_day = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res_day = requests.get(url_day, timeout=10).json()
        for row in res_day:
            code = row.get("Code")
            if code in stocks_map:
                try:
                    price = float(row.get("ClosingPrice", 0)) if row.get("ClosingPrice") else 0
                    turnover = float(row.get("TradeValue", 0)) if row.get("TradeValue") else 0
                    turnover_wan = round(turnover / 10000)
                    stocks_map[code]["price"] = price
                    stocks_map[code]["turnover_wan"] = turnover_wan
                except ValueError:
                    continue
    except Exception as e:
        print(f"Error fetching TWSE STOCK_DAY: {e}")

    # 4. 抓取上櫃股票數據 (TPEx)
    try:
        url_tpex_per = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratios"
        res_tpex_per = requests.get(url_tpex_per, timeout=10).json()
        for row in res_tpex_per:
            code = row.get("SecuritiesCompanyCode")
            name = row.get("CompanyName")
            try:
                pe = float(row.get("PERatio", 0)) if row.get("PERatio") else 0
                dividend_yield = float(row.get("YieldRatio", 0)) if row.get("YieldRatio") else 0
            except ValueError:
                continue

            if code and name and code not in stocks_map:
                stocks_map[code] = {
                    "code": code,
                    "name": name,
                    "pe": pe,
                    "yield_rate": dividend_yield,
                    "turnover_wan": 0,
                    "price": 0.0
                }

        url_tpex_quotes = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res_tpex_quotes = requests.get(url_tpex_quotes, timeout=10).json()
        for row in res_tpex_quotes:
            code = row.get("SecuritiesCompanyCode")
            if code in stocks_map:
                try:
                    price = float(row.get("Close", 0)) if row.get("Close") else 0
                    turnover = float(row.get("Amount", 0)) if row.get("Amount") else 0
                    turnover_wan = round(turnover / 10000)
                    stocks_map[code]["price"] = price
                    stocks_map[code]["turnover_wan"] = turnover_wan
                except ValueError:
                    continue
    except Exception as e:
        print(f"Error fetching TPEx data: {e}")

    # 5. 量化篩選與 CP 分數計算
    filtered_list = []
    for code, stock in stocks_map.items():
        pe = stock["pe"]
        yield_rate = stock["yield_rate"]
        turnover_wan = stock["turnover_wan"]
        price = stock["price"]
        name = stock["name"]

        # 篩選條件：0 < 本益比 < 20、殖利率 >= 2.5%、日成交金額 >= 1,500萬、有股價數據
        if 0 < pe < 20 and yield_rate >= 2.5 and turnover_wan >= 1500 and price > 0:
            # 量化權重評分公式 (總分約 100 分)
            pe_score = max(0, (20 - pe) * 2.5)       # 最高 50 分
            yield_score = min(40, yield_rate * 5)     # 最高 40 分
            turnover_score = min(10, (turnover_wan / 10000) * 1) # 最高 10 分
            cp_score = round(pe_score + yield_score + turnover_score, 2)

            # 金額格式化（大於 1 億自動轉為 "X.XX 億"）
            if turnover_wan >= 10000:
                turnover_formatted = f"{turnover_wan / 10000:.2f} 億"
            else:
                turnover_formatted = f"{turnover_wan:,.0f} 萬"

            # 生成智慧評語標籤 (非重複數據)
            if pe < 10 and yield_rate >= 6.0:
                highlight = "🔥 極低估值 + 超高殖利率雙優標的"
            elif pe < 10:
                highlight = "💡 低估值潛力股：本益比遠低於市場平均"
            elif yield_rate >= 6.0:
                highlight = "💰 高息防守首選：具備強勁現金殖利率"
            elif turnover_wan >= 50000:
                highlight = "⚡ 市場熱門交投：流動性極佳且基本面穩健"
            else:
                highlight = "✨ 穩健價值股：估值與殖利率兼備"

            filtered_list.append({
                "code": code,
                "name": name,
                "price": price,
                "pe": pe,
                "yield_rate": yield_rate,
                "turnover_wan": turnover_wan,
                "turnover_formatted": turnover_formatted,
                "cp_score": cp_score,
                "highlight": highlight,
                "link": f"https://tw.stock.yahoo.com/quote/{code}"
            })

    # 6. 排序並取 Top 20
    filtered_list.sort(key=lambda x: x["cp_score"], reverse=True)
    top20 = filtered_list[:20]
    for idx, item in enumerate(top20, start=1):
        item["rank"] = idx

    output_data = {
        "update_time": update_time,
        "stocks": top20
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated data.json at {update_time}")

if __name__ == "__main__":
    fetch_data()
