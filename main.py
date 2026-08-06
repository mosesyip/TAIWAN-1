import datetime
import json
import sys
import requests


def fetch_twse_data():
  """抓取上市 (TWSE) 中文名稱、本益比、殖利率與行情"""
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      )
  }
  stocks_dict = {}

  try:
    # 1. 上市本益比、殖利率、中文名稱
    r_pe = requests.get(
        'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL',
        headers=headers,
        timeout=10,
    )
    if r_pe.status_code == 200:
      for item in r_pe.json():
        code = item.get('Code', '').strip()
        if len(code) == 4 and code.isdigit():
          pe = (
              float(item['PEratio'])
              if item.get('PEratio') and item['PEratio'] != '-'
              else None
          )
          dy = (
              float(item['DividendYield'])
              if item.get('DividendYield') and item['DividendYield'] != '-'
              else 0.0
          )
          stocks_dict[code] = {
              'symbol': code,
              'ticker': f'{code}.TW',
              'name': item.get('Name', '').strip(),  # 官方中文名稱
              'pe': pe,
              'yield': dy,
          }

    # 2. 上市當日成交金額與股價
    r_day = requests.get(
        'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
        headers=headers,
        timeout=10,
    )
    if r_day.status_code == 200:
      for item in r_day.json():
        code = item.get('Code', '').strip()
        if code in stocks_dict:
          price = (
              float(item['ClosingPrice'])
              if item.get('ClosingPrice') and item['ClosingPrice'] != '-'
              else 0.0
          )
          trade_val = (
              float(item['TradeValue'])
              if item.get('TradeValue') and item['TradeValue'] != '-'
              else 0.0
          )
          stocks_dict[code]['price'] = price
          stocks_dict[code]['turnover_m'] = round(trade_val / 10_000, 0)
  except Exception as e:
    print(f'⚠️ TWSE API 抓取失敗: {e}')

  return list(stocks_dict.values())


def fetch_tpex_data():
  """抓取上櫃 (TPEx) 中文名稱、本益比、殖利率與行情"""
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      )
  }
  stocks_dict = {}

  try:
    # 1. 上櫃本益比、殖利率、中文名稱
    r_pe = requests.get(
        'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis',
        headers=headers,
        timeout=10,
    )
    if r_pe.status_code == 200:
      for item in r_pe.json():
        code = item.get('SecuritiesCompanyCode', '').strip() or item.get(
            'Code', ''
        ).strip()
        if len(code) == 4 and code.isdigit():
          pe = (
              float(item['PERatio'])
              if item.get('PERatio') and item['PERatio'] != '-'
              else None
          )
          dy = (
              float(item['DividendYield'])
              if item.get('DividendYield') and item['DividendYield'] != '-'
              else 0.0
          )
          name = item.get('CompanyName', '').strip() or item.get(
              'Name', ''
          ).strip()
          stocks_dict[code] = {
              'symbol': code,
              'ticker': f'{code}.TWO',
              'name': name,  # 官方中文名稱
              'pe': pe,
              'yield': dy,
          }

    # 2. 上櫃當日金額與股價
    r_day = requests.get(
        'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
        headers=headers,
        timeout=10,
    )
    if r_day.status_code == 200:
      for item in r_day.json():
        code = item.get('SecuritiesCompanyCode', '').strip() or item.get(
            'Code', ''
        ).strip()
        if code in stocks_dict:
          price = (
              float(item['Close'])
              if item.get('Close') and item['Close'] != '-'
              else 0.0
          )
          trade_val = (
              float(item['TradeAmount'])
              if item.get('TradeAmount') and item['TradeAmount'] != '-'
              else 0.0
          )
          stocks_dict[code]['price'] = price
          stocks_dict[code]['turnover_m'] = round(trade_val / 10_000, 0)
  except Exception as e:
    print(f'⚠️ TPEx API 抓取失敗: {e}')

  return list(stocks_dict.values())


def main():
  print('🚀 開始執行台股官方中文 API 量化掃描...')

  all_stocks = fetch_twse_data() + fetch_tpex_data()
  print(f'📊 成功取得台股清單，共 {len(all_stocks)} 檔股票')

  if not all_stocks:
    print('❌ 無法取得官方 API 資料')
    sys.exit(1)

  processed_results = []

  for s in all_stocks:
    price = s.get('price', 0)
    pe_ratio = s.get('pe')
    yield_pct = s.get('yield', 0.0)
    turnover_w = s.get('turnover_m', 0)  # 萬元
    turnover_raw = turnover_w * 10_000

    if price <= 0:
      continue

    is_pe_pass = bool(pe_ratio and 0 < pe_ratio <= 20)
    is_yield_pass = yield_pct >= 2.5
    is_turnover_pass = turnover_raw >= 15_000_000

    pe_val = pe_ratio if (pe_ratio and pe_ratio > 0) else 25
    pe_score = max(0, min(100, (20 - pe_val) / 20 * 100))
    yield_score = min(100, yield_pct * 15)
    turnover_score = min(100, (turnover_raw / 100_000_000) * 100)
    cp_score = round(
        pe_score * 0.40 + yield_score * 0.35 + turnover_score * 0.25, 2
    )

    stock_item = {
        'symbol': s['symbol'],
        'ticker': s['ticker'],
        'name': s['name'],
        'price': round(price, 2),
        'pe': round(pe_ratio, 2) if pe_ratio else None,
        'yield': round(yield_pct, 2),
        'market_cap': '中小型',
        'turnover_m': turnover_w,
        'cp_score': cp_score,
        'is_full_match': is_pe_pass and is_yield_pass and is_turnover_pass,
        'ai_comment': (
            f'PE {round(pe_ratio, 1) if pe_ratio else "N/A"} 倍，殖利率'
            f' {round(yield_pct, 1)}%，日成交額 {int(turnover_w):,} 萬。'
        ),
    }

    if is_pe_pass or is_yield_pass or is_turnover_pass:
      processed_results.append(stock_item)

  processed_results.sort(key=lambda x: x['cp_score'], reverse=True)
  full_matches = [s for s in processed_results if s['is_full_match']]

  top_20 = (
      full_matches[:20]
      if len(full_matches) >= 20
      else (
          full_matches
          + [s for s in processed_results if not s['is_full_match']][
              : (20 - len(full_matches))
          ]
      )
  )

  output_payload = {
      'update_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'total_scraped': len(all_stocks),
      'matched_count': len(full_matches),
      'stocks': top_20,
      'candidates': processed_results[:50],
      'data': top_20,
  }

  for filename in ['data.json', 'stocks.json']:
    with open(filename, 'w', encoding='utf-8') as f:
      json.dump(output_payload, f, ensure_ascii=False, indent=2)

  print(
      f'🎉 成功處理 {len(all_stocks)} 檔股票，符合條件 {len(full_matches)} 檔！'
  )


if __name__ == '__main__':
  main()
