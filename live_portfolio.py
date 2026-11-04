"""Forward paper accounting. No broker orders; static holdings never rebalance."""
from copy import deepcopy
import numpy as np
import pandas as pd
from backtesting import allocate, schedule


def due(last, now, frequency):
    if last is None:
        return True
    return len(schedule(pd.DatetimeIndex([pd.Timestamp(last), pd.Timestamp(now)]), frequency)) > 1


def tick(book, assets, quotes, weights, costs, capital, now, frequency, force=False):
    """Atomic update: removed stocks are sold; static retains its original shares."""
    now = pd.Timestamp(now)
    state = deepcopy(book) if book else dict(assets={}, dynamic={}, static={},
        cash_dynamic=capital, cash_static=capital, ledger=[], nav=[], last_rebalance=None,
        initial=capital, started=str(now))
    for asset in assets:
        state['assets'][asset['id']] = asset
    universe = list(state['assets'].values())
    ids = [a['id'] for a in universe]
    # Same-currency live paper mode: FX-supported research is in the backtest.
    if any(a['currency'] != 'USD' for a in universe):
        raise ValueError('Forward paper mode currently supports USD stocks only. Use historical comparison for FX portfolios.')
    if any(k not in quotes or not np.isfinite(quotes[k]) or quotes[k] <= 0 for k in ids):
        raise ValueError('Fresh positive quotes are required for every held or selected stock, including static holdings.')
    q = np.array([quotes[k] for k in ids])
    if force or due(state['last_rebalance'], now, frequency):
        w = np.array([float(weights.get(k, 0)) for k in ids])
        if not np.isfinite(w).all() or (w < 0).any() or not np.isclose(w.sum(), 1):
            raise ValueError('Live target weights must sum to one and be nonnegative.')
        current = np.array([state['dynamic'].get(k, 0) for k in ids]) * q
        target, cash, rows, _ = allocate(current, state['cash_dynamic'], w, now,
            q, np.ones(len(q)), universe, costs, 'USD')
        state['dynamic'] = dict(zip(ids, (target / q).tolist()))
        state['cash_dynamic'] = cash
        state['ledger'].extend([dict(r, strategy='Dynamic') for r in rows])
        state['last_rebalance'] = str(now)
    if not book:
        w = np.array([1 / len(assets) if k in {a['id'] for a in assets} else 0 for k in ids])
        target, cash, rows, _ = allocate(np.zeros(len(ids)), capital, w, now,
            q, np.ones(len(q)), universe, costs, 'USD')
        state['static'] = dict(zip(ids, (target / q).tolist()))
        state['cash_static'] = cash
        state['ledger'].extend([dict(r, strategy='Static') for r in rows])
    state['nav'].append(dict(date=str(now), Dynamic=sum(state['dynamic'].get(k, 0)*quotes[k] for k in ids)+state['cash_dynamic'],
        Static=sum(state['static'].get(k, 0)*quotes[k] for k in ids)+state['cash_static']))
    return state
