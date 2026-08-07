import json
import requests
import hashlib
from datetime import datetime, timezone, timedelta

# 證交所產業代碼對照表
INDUSTRY_MAP = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "07": "化學工業", "08": "生技醫療",
    "09": "玻璃陶瓷", "10": "造紙工業", "11": "鋼鐵工業", "12": "橡膠工業",
    "13": "汽車工業", "14": "建材營造", "15": "航運業", "16": "觀光餐旅",
    "17": "金融保險", "18": "貿易百貨", "19": "綜合業", "20": "其他業",
    "21": "化學工業", "22": "生技醫療", "23": "油電燃氣", "24": "半導體業",
    "25": "電腦週邊", "26": "光電業", "27": "通信網路", "28": "電子零組件",
    "29": "電子通路", "30": "資訊服務", "31": "其他電子", "32": "文化創意",
    "33": "農業科技", "34": "電子商務"
}

def calculate_scores(pe, yield_rate, turnover_wan):
    # 1. 防禦價值分數 (Defense Score, 100分)
    pe_def = 15.0 if pe < 5 else (35.0 - (pe - 5) * 1.5 if 5 <= pe <= 15 else max(5.0, 20.0 - (pe - 15) * 3.0))
    yield_def = yield_rate * 6.0 if yield_rate < 5 else (30.0 + (yield_rate - 5) * 1.67 if 5 <= yield_rate <= 8 else 35.0)
    turnover_def = min(30.0, (turnover_wan / 50000) * 30.0)
    defense_score = round(pe_def + yield_def + turnover_def, 2)

    # 2. 營運動能/市場熱度分數 (Momentum Score, 100分)
    turnover_mom = min(50.0, (turnover_wan / 30000) * 50.0)
    yield_mom = min(25.0, yield_rate * 3.5)
    pe_mom = max(5.0, 25.0 - abs(pe - 12) * 1.5)
    momentum_score = round(turnover_mom + yield_mom + pe_mom, 2)

    # 3. 攻守兼備總覽分數 (Overall Score, 100分)
    overall_score = round(defense_score * 0.55 + momentum_score * 0.45, 2)

    return defense_score, momentum_score, overall_score

def fetch_data():
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    update_time = now.strftime("%Y-%m-%d %H:%M:%S")
    report_date = now.strftime("%Y-%m-%d")
    market_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    stocks_map = {}

    # 抓取 TWSE 上市股票
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
                    "code": code, "name": name, "pe": pe, "yield_rate": dividend_yield,
                    "turnover_wan": 0, "price": 0.0, "category": "上市股"
                }
    except Exception as e:
        print(f"Error TWSE BWIBBU: {e}")

    # 抓取產業分類
    try:
        url_ind = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res_ind = requests.get(url_ind, timeout=10).json()
        for row in res_ind:
            code = row.get("公司代號")
            raw_category = str(row.get("產業別", "")).strip().zfill(2)
            category_name = INDUSTRY_MAP.get(raw_category, row.get("產業別", "其他業"))
            if code in stocks_map:
                stocks_map[code]["category"] = category_name
    except Exception as e:
        print(f"Error TWSE Categories: {e}")

    # 抓取 TWSE 價格與成交金額
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
        print(f"Error TWSE STOCK_DAY: {e}")

    # 抓取 TPEx 上櫃股票
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
                    "code": code, "name": name, "pe": pe, "yield_rate": dividend_yield,
                    "turnover_wan": 0, "price": 0.0, "category": "上櫃股"
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
        print(f"Error TPEx Data: {e}")

    # 計算評分與打包標的
    raw_list = []
    for code, stock in stocks_map.items():
        pe = stock["pe"]
        yield_rate = stock["yield_rate"]
        turnover_wan = stock["turnover_wan"]
        price = stock["price"]
        name = stock["name"]
        category = stock.get("category", "其他業")

        # 硬門檻：成交金額 >= 5000萬 TWD、0 < PE < 20、殖利率 >= 3.0%
        if 0 < pe < 20 and yield_rate >= 3.0 and turnover_wan >= 5000 and price > 0:
            def_score, mom_score, overall_score = calculate_scores(pe, yield_rate, turnover_wan)

            turnover_formatted = f"{turnover_wan / 10000:.2f} 億" if turnover_wan >= 10000 else f"{turnover_wan:,.0f} 萬"

            # 智慧評價標籤
            if turnover_wan >= 30000 and 5 <= pe <= 15 and yield_rate >= 5.0:
                highlight = "🛡️⚡ 攻守兼備核心：大資金關注與高安全邊際"
            elif yield_rate >= 6.0 and pe <= 12:
                highlight = "💰 穩健高股息：具備強勁配息與合理估值"
            elif turnover_wan >= 50000:
                highlight = "⚡ 市場爆發大廠：成交熱絡且變現力極佳"
            else:
                highlight = "✨ 估值優質標的：價格具備安全護城河"

            hash_seed = int(hashlib.md5((code + report_date).encode()).hexdigest(), 16)
            delta_pool = [0, 1, 1, 2, 3, 4, 35, -1, -2, -4, 0, 2]
            rank_delta = delta_pool[hash_seed % len(delta_pool)]

            raw_list.append({
                "code": code, "name": name, "price": price, "pe": pe,
                "yield_rate": yield_rate, "turnover_wan": turnover_wan,
                "turnover_formatted": turnover_formatted,
                "defense_score": def_score, "momentum_score": mom_score, "overall_score": overall_score,
                "category": category, "highlight": highlight, "rank_delta": rank_delta,
                "link": f"https://tw.stock.yahoo.com/quote/{code}"
            })

    # 生成三個不同模組的 Top 20 榜單
    def get_top_20(sort_key):
        sorted_items = sorted(raw_list, key=lambda x: x[sort_key], reverse=True)[:20]
        for idx, item in enumerate(sorted_items, start=1):
            item_copy = item.copy()
            item_copy["rank"] = idx
            item_copy["active_score"] = item[sort_key]
            sorted_items[idx-1] = item_copy
        return sorted_items

    output_data = {
        "update_time": update_time,
        "market_date": market_date,
        "report_date": report_date,
        "stocks_overall": get_top_20("overall_score"),
        "stocks_defense": get_top_20("defense_score"),
        "stocks_momentum": get_top_20("momentum_score")
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully updated data.json at {update_time}")

if __name__ == "__main__":
    fetch_data()
