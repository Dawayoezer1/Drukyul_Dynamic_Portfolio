# Drukyul free portfolio dashboard

This update removes the Twelve Data API key requirement from the dashboard.
Yahoo Finance via **yfinance** is the default free source. There is also a
same-currency CSV importer and a clearly labelled synthetic demo. Free source
failures never cause synthetic prices to be substituted.

Extract into a new folder and double-click **START_APP.bat** on Windows.
Keep the terminal open and use **http://localhost:8501**. The launcher creates
the environment and installs requirements including yfinance. Python 3.11–3.13
is recommended. See QUICK_START.txt for manual commands and troubleshooting.
The Windows launcher was reviewed, not executed on Windows here.

## Why the earlier request returned 401

The earlier dashboard required authenticated Twelve Data history. HTTP 401
indicates rejected authentication/access, for example an invalid key. This
version uses a different no-key source rather than attempting to bypass the
provider's access controls. It needs no Twelve Data account or subscription.

## Free prices and stock browsing

The bundled dropdown contains 12,151 entries, compiled from the official Nasdaq
Trader US-listed symbol directories plus starter metadata. Names, symbols and
exchanges are shown together. Test issues and names explicitly describing rights,
warrants, units, notes and debentures were excluded. Non-ETF entries whose type
cannot be established from the directory are labelled Other listed security.
Directory membership is not a guarantee of supported price history. Refresh the
list from the dashboard; Yahoo search adds global stocks/ETFs after currency
metadata is checked. Search is optional; browsing US names needs no typing.

The provider is an unofficial Yahoo client. Data access can be delayed, rate
limited or unavailable. Check Yahoo terms for your intended use. No guaranteed
real-time exchange feed, universal global directory or brokerage connection is
included. Primary technical references:

- https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- https://github.com/ranaroussi/yfinance
- https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt
- https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt

The app restricts 1-minute requests to the most recent seven days and other
intraday requests to the most recent 60 days, including the pre-start lookback.
Daily histories can be longer. Date errors explain the problem; the app does not
silently shorten a backtest or manufacture bars. Yahoo bar starts are converted
to UTC bar-close timestamps for intraday accounting, and incomplete bars are
removed. Daily prices retain local date labels; global daily closes are not
simultaneous. FX observations must also match the equity timestamps; no missing
prices or FX are filled. Currency metadata is validated. Daily and intraday
responses are cached; quote refreshes request latest available data.

## Dynamic and static strategies

The dynamic optimizer maximizes `w.T mu - gamma/2 * w.T Sigma w`, subject to
weights summing to one, long-only weights and the allocation cap. Historical
arithmetic means and sample covariance are annualized using the number of
observed returns divided by elapsed calendar years. The lookback ends strictly
before each execution bar. Frequencies are minute, 5 minutes, 15 minutes, hour,
day, week, month, quarter, half-year and year. Daily bars cannot stand in for
intraday bars. A zero target weight removes a holding from the selected universe.

Static establishes an equal-weight portfolio once, pays initial purchase costs
and then holds its original shares/sleeves. Both strategies use the same initial
capital, universe, evaluation period, FX and cost rules. Changing the historical
universe starts a new experiment; it does not rewrite old trades. Changing
forward dynamic stocks sells removed holdings at its next rebalance; static
keeps its original shares.

## Markowitz calculations shown

For every selectable rebalance, the page shows the actual preceding estimation
window, weights, per-asset expected annual mean and volatility, weighted return,
variance contribution, volatility contribution and risk share. It also displays
portfolio expected return, variance, volatility, estimated Sharpe, weight-sum and
solver checks, covariance and correlation matrices, and a constrained efficient
frontier. The frontier and estimates exclude transaction costs and are not
forecasts. Expected return = `w.T mu`; variance = `w.T Sigma w`; volatility is its
square root. Volatility contributions sum to total portfolio volatility; variance
contributions sum to portfolio variance. The efficient frontier uses the same
past window and caps. The equal-weight marker is an initial target; static
holdings later drift.

## Realized risk and performance

The comparison formats percentage metrics as percentages and monetary values in
the chosen base currency. It includes initial/final value, net and gross return,
CAGR, volatility, downside deviation, Sharpe, Sortino, Calmar, Omega, drawdown,
historical 95%/99% loss VaR and expected shortfall, positive-return frequency,
best/worst intervals, total costs, cost drag, trades and turnover. Alpha, beta,
correlation, tracking error and information ratio use static as the reference.

- NAV returns include initial establishment costs. CAGR uses elapsed calendar time.
- Risk annualization uses observed intervals / elapsed calendar years.
- Risk-free and minimum acceptable returns are converted to each interval's time.
- Sharpe uses risk-free excess returns; Sortino uses the configured MAR.
- VaR is an empirical quantile of observed losses. Expected shortfall averages
  losses at or beyond that quantile. These are **per observed interval**, not
  annual forecasts. Signed loss estimates can be negative when returns are positive.
- Alpha is the annualized excess-return regression intercept vs static; it does
  not prove skill. Beta is estimated from excess interval returns.
- Turnover is half gross traded value / pre-trade NAV, summed including inception.
- Undefined ratios and numerically unrepresentable short-window CAGR are NaN.

Short intraday histories provide weak tail estimates and unstable annualized
statistics. No statistical confidence of future outperformance is claimed.

## Which strategy does the test support?

The user selects a transparent priority: Sharpe for balancing return/risk, net
return for growth, or volatility for lower risk. The app reports the historical
winner, rejects a losing candidate as an investment endorsement, and labels
samples shorter than 180 calendar days or 60 observations as insufficient for an
investment choice. These thresholds are an educational evidence gate, not a
statistical guarantee. Demo results cannot support an investment decision.
Longer histories still require an untouched later validation period and a check
of the investor's horizon, liquidity needs and ability to absorb losses. The app
does not select parameters using the displayed holdout or force dynamic to win.

## Costs and accounting limitations

Editable defaults are a constant fee scenario, not verified actual broker fees.
Enter broker commission, minimum charge, sell-side tax/levy, spread/slippage and
FX conversion. For market-specific effective dates, caps, rounding and exemptions,
use dated JSON. Bundled fee snapshots are inherited examples, not freshly verified
current tariffs. Applying a snapshot outside its date is an explicit assumption.
The self-financing allocation solves invested NAV + costs = current wealth; each
fee reduces NAV once. Gross NAV is a separate zero-cost simulation.

Historical Yahoo Close can already be split-adjusted; Adj Close also reflects
provider adjustments. The simulator uses synthetic total-return sleeves with
implicit dividend reinvestment, and Close-based fractional share equivalents for
per-share fee calculations. It does not reconstruct actual historical broker
shares around corporate actions. Exact broker invoices, lot sizes, impact,
settlement, custody, withholding and investor eligibility are not modelled. Cash
earns zero; no final liquidation is assumed. These limits also apply when comparing
frequent dynamic trades with static holdings. A free source does not make trades
or brokerage costs free.

## Forward paper tracking and downloads

Latest available Yahoo price, quote timestamp, age and market status are shown.
This is polling while the dashboard stays open, not guaranteed streaming. Stale,
closed or incomplete quote metadata pauses paper trades. The USD-only paper mode
uses fractional quote-based fills and records trades, settings, targets and quote
snapshots. Static shares stay frozen. Session memory resets when the app restarts;
download JSON before closing. It is an audit export, not an importable session.
No order book, dividend processing, settlement or actual broker execution is
modelled in forward mode.

The historical download contains prices, FX, targets, NAV, zero-cost NAV,
trade/rebalance ledgers, metrics, fees, source/data hashes, versions and the last
rebalance's Markowitz calculations, covariance and correlation. The comparison
can also be downloaded as CSV. See TEST_RESULTS.md for verification scope.

Legacy market_data.py contains the earlier authenticated provider adapters for
compatibility and their original regression tests; the free dashboard does not
call those adapters. The yfinance adapter is free_data.py.
