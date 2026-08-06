import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
import re
import requests
import yfinance as yf


def get_taiwan_stock_list():
  """抓取全台灣上市 (TWSE) 與上櫃 (TPEx) 股票代碼列表"""
  stocks = []
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      )
  }

  modes = [('2', '.TW'), ('4', '.TWO')]

  for mode, suffix in modes:
    try:
      url = f'https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}'
      res = requests.get(url, headers=headers, timeout=10)
      res.encoding = 'big5'

      matches = re.findall(r'(\d{4})\s+([^\s<]+)', res.text)
      for code, name in matches:
        if len(code) == 4 and code.isdigit():
          stocks.append({
              'symbol': f'{code}{suffix}',
              'code': code,
              'name': name.strip(),
          })
    except Exception as e:
      print(f'抓取股票清單失敗 (Mode {mode}): {e}')

  unique_stocks = {s['symbol']: s for s in stocks}.values()
  return list(unique_stocks)


def fetch_and_process_stock(stock_item):
  """單一股票資料抓取、單位校正、條件篩選與 CP 值計算"""
  symbol = stock_item['symbol']
  code = stock_item['code']
  raw_name = stock_item['name']

  try:
    ticker = yf.Ticker(symbol)
    info = ticker.info

    # 股價多重備援機制
    price = (
        info.get('regularMarketPrice')
        or info.get('currentPrice')
        or info.get('previousClose')
    )
    if not price or price <= 0:
      return None

    # 1. 本益比 (P/E)
    pe_ratio = info.get('trailingPE')

    # 2. 現金殖利率 (yfinance 回傳 0.0312 代表 3.12%)
    div_yield_raw = info.get('dividendYield')
    yield_pct = (
        (div_yield_raw * 100)
        if (div_yield_raw is not None and div_yield_raw > 0)
        else 0.0
    )

    # 3. 總市值 (原始金額轉為億元)
    market_cap_raw = info.get('marketCap', 0)
    market_cap_billion = (
        (market_cap_raw / 100_000_000) if market_cap_raw else 0.0
    )

    # 4. 20 日成交均額 (均量 * 股價)
    avg_vol = (
        info.get('averageVolume10days')
        or info.get('averageVolume')
        or info.get('volume')
        or 0
    )
    turnover_20d = avg_vol * price

    # --- 篩選門檻判斷 ---
    is_pe_pass = bool(pe_ratio and 0 < pe_ratio <= 20)
    is_yield_pass = yield_pct >= 2.5
    is_mcap_pass = 0 < market_cap_billion <= 1000
    is_turnover_pass = turnover_20d >= 15_000_000

    # AI CP 綜合分數計算 (估值 40% + 殖利率 35% + 流動性 25%)
    pe_val = pe_ratio if (pe_ratio and pe_ratio > 0) else 25
    pe_score = max(0, min(100, (20 - pe_val) / 20 * 100))
    yield_score = min(100, yield_pct * 15)
    turnover_score = min(100, (turnover_20d / 100_000_000) * 100)
    cp_score = round(
        pe_score * 0.40 + yield_score * 0.35 + turnover_score * 0.25, 2
    )

    stock_name = info.get('shortName') or raw_name or code

    stock_data = {
        'symbol': code,
        'ticker': symbol,
        'name': stock_name,
        'price': round(price, 2),
        'pe': round(pe_ratio, 2) if pe_ratio else None,
        'yield': round(yield_pct, 2),
        'market_cap': round(market_cap_billion, 2),
        'turnover_m': round(turnover_20d / 10_000, 0),
        'cp_score': cp_score,
        'is_full_match': is_pe_pass
        and is_yield_pass
        and is_mcap_pass
        and is_turnover_pass,
        'ai_comment': (
            f'PE {round(pe_ratio, 1) if pe_ratio else "N/A"} 倍，殖利率'
            f' {round(yield_pct, 1)}%，日均額'
            f' {round(turnover_20d/10000, 0):,.0f} 萬。'
        ),
    }

    # 防呆機制：只要符合 2 項以上條件即保留，確保榜單永遠有資料顯示
    passed_conditions = sum(
        [is_pe_pass, is_yield_pass, is_mcap_pass, is_turnover_pass]
    )
    if passed_conditions >= 2:
      return stock_data

    return None

  except Exception:
    return None


def main():
  print('🚀 開始執行全台股量化掃描器...')

  stocks_list = get_taiwan_stock_list()
  print(f'📊 成功取得台股清單，共 {len(stocks_list)} 檔股票')

  all_results = []

  # 維持 10 個小幫手平行處理 (兼顧速度與 IP 安全)
  with ThreadPoolExecutor(max_workers=10) as executor:
    future_to_stock = {
        executor.submit(fetch_and_process_stock, item): item
        for item in stocks_list
    }

    completed_count = 0
    total = len(future_to_stock)

    for future in as_completed(future_to_stock):
      completed_count += 1
      if completed_count % 300 == 0 or completed_count == total:
        print(f'⏳ 掃描進度：{completed_count}/{total}...')

      res = future.result()
      if res:
        all_results.append(res)

  # 按 AI CP 值高低排序
  all_results.sort(key=lambda x: x['cp_score'], reverse=True)

  full_matches = [s for s in all_results if s['is_full_match']]

  # 若完全符合門檻不滿 20 檔，自動補充高 CP 值的優質備選股
  top_20 = (
      full_matches[:20]
      if len(full_matches) >= 20
      else (
          full_matches
          + [s for s in all_results if not s['is_full_match']][
              : (20 - len(full_matches))
          ]
      )
  )

  print(
      f'✅ 掃描完成！符合條件標的共 {len(all_results)} 檔，完全符合門檻共'
      f' {len(full_matches)} 檔。'
  )

  # 寫入 JSON (同時輸出 data.json 與 stocks.json 確保前端完美相容)
  output_payload = {
      'update_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'total_scraped': len(stocks_list),
      'matched_count': len(full_matches),
      'stocks': top_20,
      'candidates': all_results[:50],
  }

  for filename in ['data.json', 'stocks.json']:
    with open(filename, 'w', encoding='utf-8') as f:
      json.dump(output_payload, f, ensure_ascii=False, indent=2)

  print('🎉 數據已成功更新並寫入檔案！')


if __name__ == '__main__':
  main()
