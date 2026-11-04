"""Calendar-time annualization with explicit interval risk-free and MAR."""
import numpy as np
import pandas as pd


def metrics(values, initial, trades, gross_final, risk_free=.03, mar=0):
    v = values.astype(float)
    if (len(v) < 2 or not isinstance(v.index, pd.DatetimeIndex) or
        v.index.has_duplicates or not v.index.is_monotonic_increasing or
        not np.isfinite(v).all() or (v <= 0).any() or initial <= 0 or
        not np.isfinite([risk_free, mar]).all() or min(risk_free, mar) <= -1):
        raise ValueError('Invalid NAV, dates, initial capital or annual rate.')
    # First NAV is the pre-trade capital baseline, not the post-cost first value.
    if not np.isclose(v.iloc[0], initial):
        raise ValueError('NAV must begin with the initial capital baseline.')
    r = v.pct_change(fill_method=None).iloc[1:]
    if not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError('Invalid periodic return.')
    dt = v.index.to_series().diff().dt.total_seconds().iloc[1:] / (365.25 * 86400)
    years = float(dt.sum())
    ann = len(r) / years
    rf = (1 + risk_free) ** dt.to_numpy() - 1
    hurdle = (1 + mar) ** dt.to_numpy() - 1
    excess = r.to_numpy() - rf
    downside = float(np.sqrt(np.mean(np.minimum(r.to_numpy() - hurdle, 0) ** 2)) * np.sqrt(ann))
    vol = float(r.std(ddof=1) * np.sqrt(ann)) if len(r) > 1 else np.nan
    ex_vol = float(np.std(excess, ddof=1) * np.sqrt(ann)) if len(r) > 1 else np.nan
    # Sortino numerator uses MAR; Sharpe numerator uses risk-free.
    sortino = float(np.mean(r.to_numpy() - hurdle) * ann / downside) if downside > 1e-14 else np.nan
    costs = float(trades['total_cost'].sum()) if len(trades) else 0.0
    # Half gross traded notional / pre-trade NAV, summed; initial purchase included.
    turnover = float((trades['gross_base'] / trades['nav_before']).sum() / 2) if len(trades) else 0.0
    log_growth = float(np.log(v.iloc[-1]/initial)/years)
    cagr = float(np.expm1(log_growth)) if log_growth <= np.log(np.finfo(float).max)-1 else np.nan
    return dict(initial=initial, final=float(v.iloc[-1]), total_return=float(v.iloc[-1]/initial-1),
                cagr=cagr, volatility=vol,
                sharpe=float(excess.mean()*ann/ex_vol) if ex_vol > 1e-14 else np.nan,
                sortino=sortino, downside_deviation=downside,
                max_drawdown=float((v/v.cummax()-1).min()), total_costs=costs,
                gross_return=float(gross_final/initial-1), turnover=turnover,
                trades=len(trades), observations=len(r), annualizer=ann)


def extended_risk(values,mar=0):
    """Historical loss quantiles per observed interval, not annual loss forecasts."""
    returns=values.pct_change(fill_method=None).dropna()
    losses=-returns.to_numpy()
    var95=float(np.quantile(losses,.95));var99=float(np.quantile(losses,.99))
    years=(values.index[-1]-values.index[0]).total_seconds()/(365.25*86400)
    dt=values.index.to_series().diff().dt.total_seconds().iloc[1:].to_numpy()/(365.25*86400)
    shortfall=returns.to_numpy()-((1+mar)**dt-1)
    denominator=float(-np.minimum(shortfall,0).sum())
    return dict(var95=var95,var99=var99,es95=float(losses[losses>=var95].mean()),
        es99=float(losses[losses>=var99].mean()),win_rate=float((returns>0).mean()),
        best_interval=float(returns.max()),worst_interval=float(returns.min()),
        omega=float(np.maximum(shortfall,0).sum()/denominator) if denominator>1e-14 else np.nan,
        elapsed_days=years*365.25)


def compare_to_static(dynamic,static,annualizer,risk_free=.03):
    r=dynamic.pct_change(fill_method=None).dropna();b=static.pct_change(fill_method=None).dropna()
    excess=r-b
    tracking=float(excess.std(ddof=1)*np.sqrt(annualizer))
    dt=dynamic.index.to_series().diff().dt.total_seconds().iloc[1:].to_numpy()/(365.25*86400)
    rf=(1+risk_free)**dt-1
    rp=r-rf;rb=b-rf
    variance=float(rb.var(ddof=1))
    beta=float(rp.cov(rb)/variance) if variance>1e-18 else np.nan
    alpha=float((rp.mean()-beta*rb.mean())*annualizer) if np.isfinite(beta) else np.nan
    return dict(tracking_error=tracking,information_ratio=float(excess.mean()*annualizer/tracking) if tracking>1e-14 else np.nan,
        alpha_to_static=alpha,beta_to_static=beta,correlation_to_static=float(r.corr(b)) if variance>1e-18 and r.var(ddof=1)>1e-18 else np.nan)
