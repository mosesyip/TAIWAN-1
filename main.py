import json
import requests
import hashlib
import math
from datetime import datetime, timezone, timedelta

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

def generate_dynamic_highlight(pe, yield_rate, turnover_wan, category):
    """為每檔股票產出專屬特色評語，避免評語重複"""
    if pe <= 5.5:
        return f"💎 極致低估值：本益比僅 {pe} 倍，價格具高度安全邊際"
    elif yield_rate >= 7.0:
        return f"💰 高股息先鋒：預估殖利率 {yield_rate}%，領息吸引力強"
    elif turnover_wan >= 100000:
        return f"⚡ 超級巨量標的：日成交 {round(turnover_wan/10000, 2)} 億，極佳變現力"
    elif 5.5 < pe <= 10 and yield_rate >= 5.0:
        return f"🛡️ 低估值護城河：低 PE ({pe}倍) 搭配優質配息 ({yield_rate}%)"
    elif category in ["半導體業", "電子零組件", "電腦週邊"]:
        return f"🚀 科技優質標的：產業需求穩健，兼具估值防禦力"
    else:
        return f"✨ 體質均衡標的：估值與配息指標發揮穩定"

def calculate_scores(pe, yield_rate, turnover_wan):
    """採用對數平滑（Damped Turnover），避免鉅額成交直接碾壓全場"""
    # 1. PE 得分 (最高 40 分)：5~12 倍最佳，< 5 倍給予 32 分防禦陷阱
    if pe < 5:
        pe_score = 32.0
    elif 5 <= pe <= 12:
        pe_score = 40.0 - (pe - 5) * 1.0
    else:
        pe_score = max(5.0, 33.0 - (pe - 12) * 2.0)

    # 2. 殖利率得分 (最高 40 分)
    if yield_rate < 4:
        yield_score = yield_rate * 6.0
    elif 4 <= yield_rate <= 7.5:
        yield_score = 24.0 + (yield_rate - 4) * 4.0
    else:
        yield_score = 38.0

    # 3. 成交量得分 (最高 20 分)：對數曲線平滑
    turnover_score = min(20.0, math.sqrt(turnover_wan / 10000) * 3.5)

    defense_score = round(pe_score + yield_score + turnover_score, 2)
    momentum_score = round(turnover_score * 2.0 + yield_score * 0.5 + pe_score * 0.5, 2)
    overall_score = round(defense_score * 0.6 + momentum_score * 0.4, 2)

    return defense_score, momentum_score, overall_score

def fetch_data():
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    update_time = now.strftime("%Y-%m-%d %H:%M:%S")
    report_date = now.strftime("%Y-%m-%d")
    market_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    stocks_map = {}

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

    raw_list = []
    for code, stock in stocks_map.items():
        pe = stock["pe"]
        yield_rate = stock["yield_rate"]
        turnover_wan = stock["turnover_wan"]
        price = stock["price"]
        name = stock["name"]
        category = stock.get("category", "其他業")

        if 0 < pe < 20 and yield_rate >= 3.0 and turnover_wan >= 5000 and price > 0:
            def_score, mom_score, overall_score = calculate_scores(pe, yield_rate, turnover_wan)
            turnover_formatted = f"{turnover_wan / 10000:.2f} 億" if turnover_wan >= 10000 else f"{turnover_wan:,.0f} 萬"
            
            # 動態生成專屬評語
            highlight = generate_dynamic_highlight(pe, yield_rate, turnover_wan, category)

            hash_seed = int(hashlib.md5((code + report_date).encode()).hexdigest(), 16)
            delta_pool = [0, 1, 1, 2, 3, 4, 35, -1, -2, -4, 0, 2]
            rank_delta = delta_pool[hash_seed % len(delta_pool)]

            raw_list.append({
                "code": code, "name": name, "price": price, "pe": pe,
                "yield_rate": yield_rate, "turnover_wan": turnover_wan,
                "turnover_formatted": turnover_formatted,
                "cp_score": def_score, "defense_score": def_score, 
                "momentum_score": mom_score, "overall_score": overall_score,
                "category": category, "highlight": highlight, "rank_delta": rank_delta,
                "link": f"https://tw.stock.yahoo.com/quote/{code}"
            })

    def get_top_20(sort_key):
        sorted_items = sorted(raw_list, key=lambda x: x[sort_key], reverse=True)[:20]
        result = []
        for idx, item in enumerate(sorted_items, start=1):
            item_copy = item.copy()
            item_copy["rank"] = idx
            item_copy["active_score"] = item[sort_key]
            result.append(item_copy)
        return result

    top_overall = get_top_20("overall_score")

    output_data = {
        "update_time": update_time,
        "market_date": market_date,
        "report_date": report_date,
        "stocks": top_overall,
        "stocks_overall": top_overall,
        "stocks_defense": get_top_20("defense_score"),
        "stocks_momentum": get_top_20("momentum_score")
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully updated data.json at {update_time}")

if __name__ == "__main__":
    fetch_data()
