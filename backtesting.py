"""Close execution, lagged signals, explicit self-financing transaction accounting."""
import numpy as np
import pandas as pd
from portfolio_optimizer import optimize
from performance_metrics import metrics, extended_risk, compare_to_static
from config import NO_TRADE_BAND, TURNOVER_LAMBDA, BLEND

FREQUENCIES = {'Every minute': 'min', 'Every 5 minutes': '5min',
               'Every 15 minutes': '15min', 'Hourly': 'h', 'Daily': 'D', 'Weekly': 'W-SUN', 'Monthly': 'M', 'Quarterly': 'Q',
               'Semi-annually': '2Q', 'Yearly': 'Y'}


def schedule(index, frequency):
    if frequency not in FREQUENCIES:
        raise ValueError('Unsupported rebalance frequency.')
    if frequency in ('Every minute', 'Every 5 minutes', 'Every 15 minutes', 'Hourly', 'Daily'):
        keys = list(index.floor(FREQUENCIES[frequency]))
    elif frequency == 'Semi-annually':
        keys = [(d.year, (d.month - 1) // 6) for d in index]
    else:
        keys = list(index.to_period(FREQUENCIES[frequency]))
    return {d for i, d in enumerate(index) if i == 0 or keys[i] != keys[i-1]}


def allocate(current, cash, weights, date, raw, fx, assets, costs, base):
    """Solve target invested NAV + costs = existing NAV; sell proceeds fund buys."""
    wealth = float(current.sum() + cash)
    if wealth <= 0 or not np.isfinite(wealth):
        raise ValueError('Portfolio insolvent.')
    def evaluate(target_nav, ledger=False):
        delta = weights * target_nav - current
        rows = []
        for i, a in enumerate(assets):
            if abs(delta[i]) > wealth * 1e-12:
                row = costs.trade(a, date, delta[i], raw[i], fx[i], base) if costs else {
                    'total_cost': 0, 'gross_base': abs(delta[i]),
                    'net_cash_impact': -delta[i], 'id': a['id'], 'date': date}
                row.update(nav_before=wealth, previous_weight=current[i]/wealth,
                           target_weight=weights[i])
                rows.append(row)
        fee = sum(r['total_cost'] for r in rows)
        return target_nav + fee - wealth, rows if ledger else fee
    # The fee function can jump at rounded/minimum charges. Keep a feasible side.
    lo, hi = 0.0, wealth
    if evaluate(lo)[0] > 0:
        raise ValueError('Capital cannot fund required transaction costs.')
    for _ in range(80):
        mid = (lo + hi)/2
        if evaluate(mid)[0] <= 0:
            lo = mid
        else:
            hi = mid
    _, rows = evaluate(lo, True)
    fee = sum(r['total_cost'] for r in rows)
    target = weights * lo
    remaining_cash = wealth - target.sum() - fee
    if remaining_cash < -1e-7 or not np.isclose(target.sum()+remaining_cash, wealth-fee):
        raise ValueError('Self-financing reconciliation failed.')
    return target, max(0.0, remaining_cash), rows, fee


def backtest(prices, raw, fx, assets, start, end, settings, costs, base='USD'):
    ids = [a['id'] for a in assets]
    if not ids:
        raise ValueError('Choose at least one stock.')
    if settings.frequency in ('Every minute', 'Every 5 minutes', 'Every 15 minutes', 'Hourly', 'Daily'):
        duration = pd.Timedelta({'Every minute':'1min','Every 5 minutes':'5min',
            'Every 15 minutes':'15min','Hourly':'1h','Daily':'1day'}[settings.frequency])
        differences = prices.index.to_series().diff().dropna()
        if len(differences) and differences.min() > duration:
            raise ValueError('This rebalance frequency needs finer price bars. Choose matching intraday data.')
    if len(ids) != len(set(ids)) or list(prices.columns) != ids:
        raise ValueError('Asset/price identity mismatch or duplicate assets.')
    if settings.capital <= 0 or settings.lookback < 3:
        raise ValueError('Capital must be positive; lookback at least three returns.')
    for data in (prices, raw, fx):
        if (not data.index.equals(prices.index) or list(data.columns) != ids or
            data.index.has_duplicates or not data.index.is_monotonic_increasing or
            not np.isfinite(data.to_numpy()).all() or (data <= 0).any().any()):
            raise ValueError('Incomplete or inconsistent price/FX panels.')
    dates = prices.loc[start:end].index
    if len(dates) < 2:
        raise ValueError('Need at least two evaluation dates.')
    if (dates[0] - pd.Timestamp(start)).days > settings.max_gap_days or (pd.Timestamp(end) - dates[-1]).days > settings.max_gap_days:
        raise ValueError('Missing data near evaluation boundary; no shortened test accepted.')
    first = prices.index.get_loc(dates[0])
    if first < settings.lookback + 1:
        raise ValueError('Insufficient shared pre-start history for every selected asset.')
    for a in assets:
        for d in schedule(dates, settings.frequency):
            costs.profile(a, d)  # Fail before starting when a cost schedule is absent.
        decisions, targets = [], {}
    equal = np.full(len(ids), 1 / len(ids))
    w_prev = equal
    for d in sorted(schedule(dates, settings.frequency)):
        pos = prices.index.get_loc(d)
        history = prices.iloc[pos-settings.lookback-1:pos]
        result = optimize(history, settings.gamma, settings.cap,
                          w_prev=w_prev, turnover_lambda=TURNOVER_LAMBDA)
        w_final = BLEND * result['weights'].to_numpy() + (1 - BLEND) * equal
        targets[d] = w_final
        w_prev = w_final
        for a, w in zip(assets, targets[d]):
            decisions.append(dict(date=d, id=a['id'], target_weight=w,
                                  signal_last_date=history.index[-1],
                                  expected_return=result['expected_return'], risk=result['risk'],
                                  optimality_gap=result['optimality_gap']))
    baseline = dates[0] - pd.Timedelta(seconds=1)
    def simulate(dynamic, charge):
        current = np.zeros(len(ids)); cash = settings.capital
        values = [settings.capital]; ledger = []; rebalances = []; holdings = []
        for i, d in enumerate(dates):
            if i:
                current *= (prices.loc[d] / prices.loc[dates[i-1]]).to_numpy()
            due = False
            if dynamic and i > 0 and d in targets:
                invested = current.sum()
                cur_w = current / invested if invested > 0 else np.zeros(len(ids))
                due = np.max(np.abs(cur_w - targets[d])) > NO_TRADE_BAND
            if i == 0 or due:
                w = targets[d] if dynamic else np.full(len(ids), 1 / len(ids))
                before = float(current.sum() + cash)
                current, cash, rows, fee = allocate(current, cash, w, d,
                    raw.loc[d].to_numpy(), fx.loc[d].to_numpy(), assets,
                    costs if charge else None, base)
                ledger.extend(rows)
                rebalances.append(dict(date=d, nav_before=before,
                                       costs=fee, nav_after=current.sum()+cash, cash=cash))
            value = float(current.sum() + cash)
            values.append(value)
            holdings.append(dict(date=d, cash=cash, **dict(zip(ids, current))))
        return dict(nav=pd.Series(values, index=pd.DatetimeIndex([baseline, *dates])),
                    trades=pd.DataFrame(ledger), rebalances=pd.DataFrame(rebalances),
                    holdings=pd.DataFrame(holdings).set_index('date'))
    output = {}
    for label, dynamic in [('Dynamic', True), ('Static', False)]:
        net, gross = simulate(dynamic, True), simulate(dynamic, False)
        net['gross_nav'] = gross['nav']
        net['metrics'] = metrics(net['nav'], settings.capital, net['trades'],
                                  gross['nav'].iloc[-1], settings.risk_free, settings.mar)
        net['metrics'].update(extended_risk(net['nav'],settings.mar))
        md=abs(net['metrics']['max_drawdown'])
        net['metrics']['calmar']=net['metrics']['cagr']/md if md>1e-14 else np.nan
        net['metrics']['cost_drag']=net['metrics']['gross_return']-net['metrics']['total_return']
        output[label] = net
    output['Dynamic']['metrics'].update(compare_to_static(output['Dynamic']['nav'],output['Static']['nav'],output['Dynamic']['metrics']['annualizer'],settings.risk_free))
    output['Static']['metrics'].update(dict(tracking_error=0.,information_ratio=np.nan,alpha_to_static=0.,beta_to_static=1.,correlation_to_static=1.))
    output['decisions'] = pd.DataFrame(decisions).sort_values(['date', 'id'])
    for label in ('Dynamic', 'Static'):
        output[label]['metrics']['benchmark_relative_return'] = (
            output[label]['metrics']['total_return'] - output['Static']['metrics']['total_return'])
    return output

grid = [(g, l, s) for g in (2, 5, 10) for l in (0.1, 0.5, 1.0) for s in (0.3, 0.6, 0.9)]
# Run each combo on the first ~60% of dates, pick the best Sharpe,
# then report that one combo's results on the remaining 40%.