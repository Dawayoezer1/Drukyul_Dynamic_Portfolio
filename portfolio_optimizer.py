"""Markowitz with shrinkage (Ledoit-Wolf covariance, shrunk returns) and a turnover penalty, solved by CVXPY."""
import numpy as np
import pandas as pd
import cvxpy as cp
from sklearn.covariance import LedoitWolf

def optimize(prices, gamma=2.0, cap=1.0, w_prev=None, turnover_lambda=0.0, shrink=0.2):
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError('Prices need a DatetimeIndex.')
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError('Dates must be unique and increasing.')
    x = prices.to_numpy(float)
    if len(x) < 4 or not np.isfinite(x).all() or (x <= 0).any():
        raise ValueError('Need at least four complete positive price rows.')
    n = x.shape[1]
    if not np.isfinite([gamma, cap, turnover_lambda, shrink]).all() or gamma <= 0 or not 0 < cap <= 1:
        raise ValueError('Risk aversion must be positive; cap must be in (0,1].')
    if turnover_lambda < 0 or not 0 <= shrink <= 1:
        raise ValueError('turnover_lambda must be >= 0 and shrink in [0,1].')
    if n * cap < 1 - 1e-10:
        raise ValueError(f'Infeasible: {n} assets × {cap:.2%} cap is below 100%.')
    r = x[1:] / x[:-1] - 1
    years = (prices.index[-1] - prices.index[0]).total_seconds() / (365.25 * 86400)
    if years <= 0:
        raise ValueError('Estimation dates must span time.')
    annualizer = len(r) / years

    # Shrunk expected returns: pull noisy asset means toward the cross-sectional average
    mu_raw = r.mean(axis=0) * annualizer
    mu = shrink * mu_raw.mean() + (1 - shrink) * mu_raw
    # Ledoit-Wolf shrunk covariance
    cov = np.atleast_2d(LedoitWolf().fit(r).covariance_) * annualizer
    cov = (cov + cov.T) / 2

    if w_prev is None:
        w_prev = np.full(n, 1 / n)
    w_prev = np.asarray(w_prev, float)
    if w_prev.shape != (n,):
        raise ValueError('w_prev must have one weight per asset.')

    w = cp.Variable(n)
    objective = (mu @ w
                 - gamma / 2 * cp.quad_form(w, cp.psd_wrap(cov))
                 - turnover_lambda * cp.norm1(w - w_prev))
    problem = cp.Problem(cp.Maximize(objective), [cp.sum(w) == 1, w >= 0, w <= cap])
    try:
        problem.solve(solver=cp.CLARABEL)   # more accurate than the default
    except Exception:
        problem.solve()
    if problem.status not in ('optimal', 'optimal_inaccurate') or w.value is None:
        raise ValueError(f'Optimizer failed: {problem.status}')

    wv = np.clip(w.value, 0, cap)
    wv /= wv.sum()
    if wv.max() > cap + 1e-4:                # tolerance matches solver accuracy
        raise ValueError(f'Optimizer produced infeasible weights (max {wv.max():.6f} vs cap {cap}).')
    wv = np.minimum(wv, cap)                 # snap tiny overshoots back to the cap

    return {'weights': pd.Series(wv, index=prices.columns), 'mu': mu, 'cov': cov,
            'expected_return': float(wv @ mu),
            'risk': float(np.sqrt(max(wv @ cov @ wv, 0))),
            'annualizer': annualizer, 'optimality_gap': 0.0,
            'observations': len(r), 'last_observation': str(prices.index[-1])}