# Free-version validation

Build date: 30 October 2026.

## Automated checks

- `python -m pytest -q`: **49 passed**.
- `python -m compileall -q .`: passed.
- Local Streamlit server subprocess: HTTP health **200 ok**.
- Dashboard tests execute default no-key startup, a mocked free-data backtest,
  a full synthetic backtest, result invalidation after input changes, and forward
  paper initialization/replacement with unchanged static shares.
- Numerical tests verify Markowitz constraints, stationarity, covariance and risk
  contribution sums, efficient-frontier ordering, fee arithmetic, self-financing
  accounting, gross/net consistency, static buy-and-hold and no future-price use.
- Free-adapter tests cover raw/adjusted columns, cache consistency, currency/data
  validation, UTC bar-close conversion, recent intraday limits and Timestamp-based
  quote metadata. Tail loss quantiles, expected shortfall and benchmark-relative
  alpha/beta arithmetic are checked against known examples.
- Assessment tests reject demo results and short/losing windows as evidence for
  an investment choice.

## Actual external-data checks

The no-key adapter retrieved real Yahoo responses for:

- AAPL daily history: five observed rows, currency USD.
- AAPL five-minute history: 1,092 rows spanning 12–29 October 2026.
- AAPL latest price/quote metadata: price, timestamp and market status parsed.
- The user's seven stocks: AAPL, NVDA, JPM, AMZN, AVGO, WMT and GLD.

The seven-stock integration run used 1,092 common five-minute price bars including
pre-start history. Evaluation was 16–29 October 2026, lookback 120 returns, capital
USD110,000, cap 25%, risk aversion 5, five-minute rebalances. It completed 780
dynamic rebalances and one static establishment. The test fee scenario used
USD0.005/share, USD1 minimum per trade and 5 bps spread/slippage (sell levy zero;
all stocks USD, so no FX conversion). These are illustrative inputs, not verified
broker tariffs. `LIVE_INTEGRATION_CHECK.json` records the observed metrics.

In that particular sample, dynamic net return was about -9.03%, static -0.48%;
dynamic costs were about USD7,393.10, static USD61.97. This is a short historical
integration check, not evidence of future returns or a long-term investment
recommendation. No result was changed to make dynamic win. Source data may later
be revised or unavailable; free access is not guaranteed.

The stock-directory snapshot was downloaded successfully from the official Nasdaq
Trader symbol directory endpoints and bundled for immediate name/ticker browsing.

## Verification limits

The automated suite uses synthetic or mocked data; actual external checks are
separate and identified above. Global stock suffixes, every directory entry,
foreign-currency history and every market's latest quotes were not tested.
Free Yahoo data may be delayed, rate limited, changed or unavailable. No guaranteed
exchange-grade feed or actual brokerage execution is provided.

The Windows BAT/PowerShell launcher was reviewed, not executed on Windows.
UI flows were tested through Streamlit AppTest, not pixel-level Chromium
inspection. The layout remains the tested one-page design. Legacy bundled fee
snapshots were not freshly verified against broker tariffs or legal schedules;
fee tests validate arithmetic, not current law or exact historical invoices.
