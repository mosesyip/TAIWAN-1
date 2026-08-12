# 台股量化選股監控台

以 GitHub Pages 發布的桌面優先台股量化排行榜。Python 從 TWSE／TPEx OpenAPI 更新 `data.json`，網站再以原生 JavaScript 顯示結果。

## 功能

- TWSE / TPEx 資料與每日自動更新
- 綜合 CP、防禦價值、成長／動能排行榜
- PE、殖利率、成交金額、EPS 與可取得的基本面欄位
- 合理價與 Upside 欄位預留；沒有可靠官方資料時為 `null`
- 搜尋、排序及 Yahoo Finance 個股連結

## 評分模型

| 構面 | 權重 | 說明 |
| --- | ---: | --- |
| Value | 25% | PE 6–10 為最佳區域，極低 PE 不給滿分。 |
| Growth | 30% | 僅採官方 EPS YoY / 營收 YoY。 |
| Quality | 20% | 可取得時採 ROE、負債比、毛利率、營益率。 |
| Dividend | 15% | 殖利率高於 8% 不再額外加分。 |
| Liquidity | 10% | 日成交額採 log 平滑；門檻為 5,000 萬元。 |

缺少資料的構面不會被偽造為 0 分，而會以現有可靠構面重新加權。這不是投資建議。

## 資料來源與限制

- [TWSE OpenAPI](https://openapi.twse.com.tw/)
- [TPEx OpenAPI](https://www.tpex.org.tw/openapi/)

Yahoo Finance 僅用於個股連結。官方 API 沒有穩定提供所有公司的 EPS YoY、ROE、自由現金流或分析師預估 EPS；這些欄位會保持 `null`，不使用推測值。`Fair Value` 與 `Upside` 也因此不會被杜撰。

## 技術

Python、HTML、JavaScript、GitHub Actions、GitHub Pages。

## 本機更新

```bash
pip install requests
python fetch_data.py
```

## Disclaimer

本網站僅提供資料整理與量化模型分析，不構成投資建議。量化分數不代表未來報酬，投資人應自行判斷風險。
