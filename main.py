import json
import requests
from datetime import datetime, timezone, timedelta

def fetch_data():
    # 1. 設定台灣時區 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    update_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")

    stocks_map = {}

    # 2. 抓取上市股票資訊與基本面 (TWSE)
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
                    "price": 0.0,
                    "category": "上市股"
                }
    except Exception as e:
        print(f"Error fetching TWSE BWIBBU: {e}")

    # 抓取上市股票產業別 (t187ap03_L)
    try:
        url_ind = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res_ind = requests.get(url_ind, timeout=10).json()
        for row in res_ind:
            code = row.get("公司代號")
            category = row.get("產業別", "其他業")
            if code in stocks_map:
                stocks_map[code]["category"] = category
    except Exception as e:
        print(f"Error fetching TWSE industry categories: {e}")

    # 抓取上市價格與成交金額
    try:
        url_day = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res_day = requests.get(url_day, timeout=10).json()
        for row in res_day:
            code = row.get("Code")
            if code in stocks_map:
                try:
                    price = float(row.get("ClosingPrice", 0)) if row.get("ClosingPrice") else 0
                    turnover = float(row.get("TradeValue", 0)) if row.get("TradeValue") else 0
                    stocks_map[code]["price"] = price
                    stocks_map[code]["turnover_wan"] = round(turnover / 10000)
                except ValueError:
                    continue
    except Exception as e:
        print(f"Error fetching TWSE STOCK_DAY: {e}")

    # 3. 抓取上櫃股票資訊與基本面 (TPEx)
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
                    "price": 0.0,
                    "category": "上櫃股"
                }

        url_tpex_quotes = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res_tpex_quotes = requests.get(url_tpex_quotes, timeout=10).json()
        for row in res_tpex_quotes:
            code = row.get("SecuritiesCompanyCode")
            if code in stocks_map:
                try:
                    price = float(row.get("Close", 0)) if row.get("Close") else 0
                    turnover = float(row.get("Amount", 0)) if row.get("Amount") else 0
                    stocks_map[code]["price"] = price
                    stocks_map[code]["turnover_wan"] = round(turnover / 10000)
                except ValueError:
                    continue
    except Exception as e:
        print(f"Error fetching TPEx data: {e}")

    # 4. 防禦型選股邏輯與量化 CP 分數計算
    filtered_list = []
    for code, stock in stocks_map.items():
        pe = stock["pe"]
        yield_rate = stock["yield_rate"]
        turnover_wan = stock["turnover_wan"]
        price = stock["price"]
        name = stock["name"]
        category = stock.get("category", "其他業")

        # 【硬門檻對齊】對齊老闆模型：成交金額 >= 5000萬 (5000萬 TWD)、0 < PE < 20、殖利率 >= 3.0%
        if 0 < pe < 20 and yield_rate >= 3.0 and turnover_wan >= 5000 and price > 0:
            
            # --- 1. 估值合理得分 (最高 35 分) ---
            if pe < 5:
                pe_score = 15.0  # 避免極端低 PE 陷阱（多為一次性收益）
            elif 5 <= pe <= 15:
                pe_score = 35.0 - (pe - 5) * 1.5  # 20 ~ 35 分
            else:
                pe_score = 20.0 - (pe - 15) * 3.0 # 5 ~ 20 分

            # --- 2. 穩健配息得分 (最高 35 分) ---
            if yield_rate < 5:
                yield_score = yield_rate * 6.0 # 18 ~ 30 分
            elif 5 <= yield_rate <= 8:
                yield_score = 30.0 + (yield_rate - 5) * 1.67 # 30 ~ 35 分
            else:
                yield_score = 35.0 # 殖利率 > 8% 封頂（避開高配息陷阱）

            # --- 3. 安全流動得分 (最高 30 分) ---
            # 以 5 億 (50,000 萬) 為 30 分滿分
            turnover_score = min(30.0, (turnover_wan / 50000) * 30.0)

            cp_score = round(pe_score + yield_score + turnover_score, 2)

            # 金額格式化（大於 1 億自動顯示 "X.XX 億"）
            if turnover_wan >= 10000:
                turnover_formatted = f"{turnover_wan / 10000:.2f} 億"
            else:
                turnover_formatted = f"{turnover_wan:,.0f} 萬"

            # 智慧風控評價標籤
            if turnover_wan >= 30000 and 5 <= pe <= 15 and yield_rate >= 5.0:
                highlight = "🛡️ 權值防禦核心：高流動性與穩健基本面"
            elif yield_rate >= 6.0 and pe <= 12:
                highlight = "💰 穩健高股息：具備強勁配息與合理估值"
            elif turnover_wan >= 50000:
                highlight = "⚡ 市場焦點大廠：變現力極佳且成交熱絡"
            elif pe <= 10:
                highlight = "💎 低估值潛力股：價格具備安全邊際"
            else:
                highlight = "✨ 攻守兼備優質股：綜合防禦分數優異"

            filtered_list.append({
                "code": code,
                "name": name,
                "price": price,
                "pe": pe,
                "yield_rate": yield_rate,
                "turnover_wan": turnover_wan,
                "turnover_formatted": turnover_formatted,
                "cp_score": cp_score,
                "category": category,
                "highlight": highlight,
                "link": f"https://tw.stock.yahoo.com/quote/{code}"
            })

    # 5. 依據 CP 防禦分數排序並取 Top 20
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

    print(f"Successfully updated data.json at {update_time}")

if __name__ == "__main__":
    fetch_data()
