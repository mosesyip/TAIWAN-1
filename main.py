from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
import re
import sys
import requests
import yfinance as yf


def get_taiwan_stock_list():
  """抓取全台股上市 (TWSE) 與上櫃 (TPEx) 股票清單 (官方 OpenAPI)"""
  stocks = []
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      )
  }

  # 1. 上市股票 (TWSE OpenAPI)
  try:
    url_twse = 'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL'
    res = requests.get(url_twse, headers=headers, timeout=10)
    if res.status_code == 200:
      for item in res.json():
        code = item.get('Code', '').strip()
        name = item.get('Name', '').strip()
        if len(code) == 4 and code.isdigit():
          stocks.append({'symbol': f'{code}.TW', 'code': code, 'name': name})
  except Exception as e:
    print(f'⚠️ TWSE OpenAPI 抓取失敗: {e}')

  # 2. 上櫃股票 (TPEx OpenAPI)
  try:
    url_tpex = (
        'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis'
    )
    res = requests.get(url_tpex, headers=headers, timeout=10)
    if res.status_code == 200:
      for item in res.json():
        code = item.get('SecuritiesCompanyCode', '').strip() or item.get(
            'Code', ''
        ).strip()
        name = item.get('CompanyName', '').strip() or item.get(
            'Name', ''
        ).strip()
        if len(code) == 4 and code.isdigit():
          stocks.append({'symbol': f'{code}.TWO', 'code': code, 'name': name})
  except Exception as e:
    print(f'⚠️ TPEx OpenAPI 抓取失敗: {e}')

  # 3. 備援爬蟲 (萬一 OpenAPI 取得數量不足時)
  if len(stocks) < 500:
    print('⚠️ OpenAPI 數量不足，啟用 ISIN 備用爬蟲...')
    try:
      for mode, suffix in [('2', '.TW'), ('4', '.TWO')]:
        url = f'https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}'
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'big5'
        matches = re.findall(r'(\d{4})\s+([^\s<]+)', r.text)
        for code, name in matches:
          if len(code) == 4 and code.isdigit():
            stocks.append(
                {'symbol': f'{code}{suffix}', 'code': code, 'name': name.strip()}
            )
    except Exception as e:
      print(f'⚠️ ISIN 爬蟲失敗: {e}')

  # 去除重複股票
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

    # 1. 本益比 (P/E < 20)
    pe_ratio = info.get('trailingPE')

    # 2. 現金殖利率 (Yield >= 2.5%, yfinance 回傳 0.0312 代表 3.12%)
    div_yield_raw = info.get('dividendYield')
    yield_pct = (
        (div_yield_raw * 100)
        if (div_yield_raw is not None and div_yield_raw > 0)
        else 0.0
    )

    # 3. 總市值 (< 1,000 億 TWD)
    market_cap_raw = info.get('marketCap', 0)
    market_cap_billion = (
        (market_cap_raw / 100_000_000) if market_cap_raw else 0.0
    )

    # 4. 20 日成交均額 (>= 1,500 萬 TWD)
    avg_vol = (
        info.get('averageVolume10days')
        or info.get('averageVolume')
        or info.get('volume')
        or 0
    )
    turnover_20d = avg_vol * price

    # --- 條件篩選 ---
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

    # 至少符合 2 項條件納入備選池，確保榜單排序完整
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

  if len(stocks_list) == 0:
    print('❌ 錯誤：無法抓取台股清單，中斷執行以保護數據。')
    sys.exit(1)

  all_results = []

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

  if len(all_results) == 0:
    print('🚨 警告：本次掃描結果為 0，放棄更新以保護原有資料。')
    sys.exit(1)

  all_results.sort(key=lambda x: x['cp_score'], reverse=True)
  full_matches = [s for s in all_results if s['is_full_match']]

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
      f'✅ 掃描完成！候選池共 {len(all_results)} 檔，完全符合門檻共'
      f' {len(full_matches)} 檔。'
  )

  output_payload = {
      'update_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'total_scraped': len(stocks_list),
      'matched_count': len(full_matches),
      'stocks': top_20,
      'candidates': all_results[:50],
      'data': top_20,
  }

  for filename in ['data.json', 'stocks.json']:
    with open(filename, 'w', encoding='utf-8') as f:
      json.dump(output_payload, f, ensure_ascii=False, indent=2)

  print('🎉 數據已成功更新並寫入檔案！')


if __name__ == '__main__':
  main()
