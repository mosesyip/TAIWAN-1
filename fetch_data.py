"""Build data.json for the Taiwan Stock Quant Dashboard.

Only official TWSE/TPEx OpenAPI values are used.  A metric is ``null`` when an
official endpoint does not provide it; this script never estimates it.
"""

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


TW_TZ = timezone(timedelta(hours=8))
TWSE_API = "https://openapi.twse.com.tw/v1"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
MIN_TURNOVER_10K = 5_000  # TWD 50 million
MAX_PE = 25
MIN_DIVIDEND_YIELD = 2.0
TOP_WATCHLIST = 100
TOP_ELITE = 20

session = requests.Session()
session.headers.update({
    "User-Agent": "taiwan-stock-quant/2.0 (+GitHub Actions)",
    "Accept": "application/json",
})


def fetch_json(endpoint):
    """Fetch and validate a list response from an official API endpoint."""
    url = endpoint if endpoint.startswith("https://") else f"{TWSE_API}{endpoint}"
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("API response must be a JSON list")
            return data
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"API request failed: {url} / {last_error}")


def safe_float(value, default=None):
    """Convert API number formats safely; unavailable values remain None."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "--", "-", "N/A"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def number(row, *keys):
    for key in keys:
        value = safe_float(row.get(key))
        if value is not None:
            return value
    return None


def text(row, *keys):
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def rounded(value, digits=2):
    return round(value, digits) if value is not None and math.isfinite(value) else None


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def weighted_score(parts):
    """Weighted average of available components; unavailable is never treated as 0."""
    available = [(weight, value) for weight, value in parts if value is not None]
    if not available:
        return None
    total_weight = sum(weight for weight, _ in available)
    return rounded(sum(weight * value for weight, value in available) / total_weight)


def value_score(pe):
    if pe is None or pe <= 0:
        return None
    if pe < 4:
        return 55.0
    if pe < 6:
        return 75.0
    if pe <= 10:
        return 100.0 - abs(pe - 8) * 3
    if pe <= 12:
        return 90.0 - (pe - 10) * 5
    if pe <= 18:
        return 80.0 - (pe - 12) * 5
    return max(20.0, 50.0 - (pe - 18) * 6)


def dividend_score(yield_rate):
    if yield_rate is None or yield_rate <= 0:
        return None
    if yield_rate < 2:
        return yield_rate * 25
    if yield_rate <= 4:
        return 50 + (yield_rate - 2) * 12
    if yield_rate <= 6:
        return 74 + (yield_rate - 4) * 10
    if yield_rate <= 8:
        return 94 + (yield_rate - 6) * 3
    return 100.0


def liquidity_score(turnover_10k):
    if not turnover_10k or turnover_10k <= 0:
        return None
    return rounded(min(100, math.log10(turnover_10k) * 25))


def growth_score(eps_yoy, revenue_yoy):
    """Use actual EPS YoY first, supplemented by official revenue YoY only."""
    eps_part = clamp(50 + eps_yoy) if eps_yoy is not None else None
    revenue_part = clamp(50 + revenue_yoy) if revenue_yoy is not None else None
    return weighted_score(((0.7, eps_part), (0.3, revenue_part)))


def quality_score(roe, debt_ratio, gross_margin, operating_margin):
    return weighted_score((
        (0.35, clamp(roe * 5) if roe is not None else None),
        (0.25, 100 - clamp(debt_ratio) if debt_ratio is not None else None),
        (0.20, clamp(gross_margin * 2.5) if gross_margin is not None else None),
        (0.20, clamp(operating_margin * 4) if operating_margin is not None else None),
    ))


def default_stock(code, name, market):
    return {
        "code": code, "name": name, "market": market, "category": "其他業",
        "price": None, "pe": None, "yield_rate": None, "turnover_10k": 0,
        "eps": None, "eps_yoy": None, "revenue_yoy": None, "revenue_mom": None,
        "gross_margin": None, "operating_margin": None, "roe": None,
        "debt_ratio": None, "free_cash_flow": None, "fair_pe": None,
        "fair_value": None, "upside": None,
    }


def load_market_valuation(stocks):
    sources = (
        ("/exchangeReport/BWIBBU_ALL", "上市股", "Code", "Name", "PEratio", "DividendYield"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratios", "上櫃股", "SecuritiesCompanyCode", "CompanyName", "PERatio", "YieldRatio"),
    )
    for endpoint, market, code_key, name_key, pe_key, yield_key in sources:
        try:
            for row in fetch_json(endpoint):
                code, name = text(row, code_key), text(row, name_key)
                if code and name:
                    stocks[code].update(default_stock(code, name, market))
                    stocks[code]["pe"] = number(row, pe_key)
                    stocks[code]["yield_rate"] = number(row, yield_key)
        except RuntimeError as exc:
            print(f"[valuation] {exc}")


def load_quotes(stocks):
    sources = (
        ("/exchangeReport/STOCK_DAY_ALL", "Code", "ClosingPrice", "TradeValue"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", "SecuritiesCompanyCode", "Close", "Amount"),
    )
    for endpoint, code_key, price_key, turnover_key in sources:
        try:
            for row in fetch_json(endpoint):
                code = text(row, code_key)
                if code in stocks:
                    stocks[code]["price"] = number(row, price_key)
                    turnover = number(row, turnover_key)
                    stocks[code]["turnover_10k"] = rounded((turnover or 0) / 10_000, 0)
        except RuntimeError as exc:
            print(f"[quotes] {exc}")


def load_industries(stocks):
    try:
        for row in fetch_json("/opendata/t187ap03_L"):
            code = text(row, "公司代號")
            if code in stocks:
                stocks[code]["category"] = text(row, "產業別名稱", "產業別") or "其他業"
    except RuntimeError as exc:
        print(f"[industry] {exc}")


def load_monthly_revenue(stocks):
    """The listed-company source exposes official monthly YoY/MoM values."""
    try:
        rows = fetch_json("/opendata/t187ap05_L")
    except RuntimeError as exc:
        print(f"[monthly revenue] {exc}")
        return
    for row in rows:
        code = text(row, "公司代號")
        if code in stocks:
            stocks[code]["revenue_yoy"] = number(row, "營業收入-去年同月增減(%)", "去年同月增減(%)")
            stocks[code]["revenue_mom"] = number(row, "營業收入-上月比較增減(%)", "上月比較增減(%)")


def load_financials(stocks):
    """Add only disclosed general-industry values; unavailable categories stay null."""
    try:
        income_rows = fetch_json("/opendata/t187ap06_L_ci")
        balance_rows = fetch_json("/opendata/t187ap07_L_ci")
    except RuntimeError as exc:
        print(f"[financial statements] {exc}")
        return
    for row in income_rows:
        code = text(row, "公司代號")
        if code not in stocks:
            continue
        revenue = number(row, "營業收入", "收入")
        gross_profit = number(row, "營業毛利（毛損）", "營業毛利(毛損)", "營業毛利")
        operating_income = number(row, "營業利益（損失）", "營業利益(損失)", "營業利益")
        stocks[code]["eps"] = number(row, "基本每股盈餘", "基本每股盈餘(元)")
        if revenue:
            stocks[code]["gross_margin"] = rounded(gross_profit / revenue * 100) if gross_profit is not None else None
            stocks[code]["operating_margin"] = rounded(operating_income / revenue * 100) if operating_income is not None else None
    for row in balance_rows:
        code = text(row, "公司代號")
        if code not in stocks:
            continue
        assets = number(row, "資產總額")
        liabilities = number(row, "負債總額")
        if assets and liabilities is not None:
            stocks[code]["debt_ratio"] = rounded(liabilities / assets * 100)


def add_scores(stock):
    stock["value_score"] = rounded(value_score(stock["pe"]))
    stock["growth_score"] = growth_score(stock["eps_yoy"], stock["revenue_yoy"])
    stock["quality_score"] = quality_score(stock["roe"], stock["debt_ratio"], stock["gross_margin"], stock["operating_margin"])
    stock["dividend_score"] = rounded(dividend_score(stock["yield_rate"]))
    stock["liquidity_score"] = liquidity_score(stock["turnover_10k"])
    stock["overall_score"] = weighted_score((
        (0.25, stock["value_score"]), (0.30, stock["growth_score"]),
        (0.20, stock["quality_score"]), (0.15, stock["dividend_score"]),
        (0.10, stock["liquidity_score"]),
    ))
    stock["cp_score"] = stock["overall_score"]
    stock["defense_score"] = weighted_score(((0.45, stock["value_score"]), (0.35, stock["dividend_score"]), (0.20, stock["liquidity_score"])))
    stock["momentum_score"] = weighted_score(((0.60, stock["growth_score"]), (0.20, stock["liquidity_score"]), (0.20, stock["value_score"])))
    stock["turnover_wan"] = stock["turnover_10k"]
    stock["turnover_formatted"] = f"{stock['turnover_10k'] / 10_000:.2f} 億"
    stock["highlight"] = make_highlight(stock)
    stock["link"] = f"https://tw.stock.yahoo.com/quote/{stock['code']}"


def make_highlight(stock):
    if stock["growth_score"] is not None and stock["growth_score"] >= 80:
        return "成長指標表現突出，仍須留意基本面持續性"
    if stock["value_score"] is not None and stock["value_score"] >= 85 and (stock["yield_rate"] or 0) >= 4:
        return "合理估值搭配股息條件，偏向防禦價值"
    if stock["liquidity_score"] is not None and stock["liquidity_score"] >= 90:
        return "流動性條件佳，請搭配基本面評估"
    return "符合目前篩選條件，請自行評估投資風險"


def ranked(stocks, score_key, limit):
    ordered = sorted(stocks, key=lambda item: (item.get(score_key) is not None, item.get(score_key) or -1), reverse=True)
    result = []
    for rank, stock in enumerate(ordered[:limit], 1):
        item = stock.copy()
        item["rank"] = rank
        item["active_score"] = item.get(score_key)
        result.append(item)
    return result


def fetch_data():
    stocks = defaultdict(dict)
    load_market_valuation(stocks)
    load_quotes(stocks)
    load_industries(stocks)
    load_monthly_revenue(stocks)
    load_financials(stocks)

    passed = []
    for stock in stocks.values():
        if not stock.get("price") or not stock.get("pe") or not 0 < stock["pe"] < MAX_PE:
            continue
        if (stock.get("yield_rate") or 0) < MIN_DIVIDEND_YIELD or stock.get("turnover_10k", 0) < MIN_TURNOVER_10K:
            continue
        add_scores(stock)
        passed.append(stock)

    overall = ranked(passed, "overall_score", TOP_ELITE)
    now = datetime.now(TW_TZ)
    output = {
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"), "market_date": now.strftime("%Y-%m-%d"),
        "report_date": now.strftime("%Y-%m-%d"), "model_version": "Quant V2", "all_passed_count": len(passed),
        "stocks": overall, "stocks_overall": overall,
        "stocks_defense": ranked(passed, "defense_score", TOP_ELITE),
        "stocks_momentum": ranked(passed, "momentum_score", TOP_ELITE),
        "watchlist_100": ranked(passed, "overall_score", TOP_WATCHLIST), "elite_20": overall,
    }
    Path("data.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully updated data.json at {output['update_time']}. Total passed: {len(passed)}")


if __name__ == "__main__":
    fetch_data()
