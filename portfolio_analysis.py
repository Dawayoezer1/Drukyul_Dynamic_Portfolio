"""Ex-ante Markowitz workings and transparent historical strategy assessment."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from portfolio_optimizer import optimize


def workings(history,gamma,cap,rf=0.03):
    model=optimize(history,gamma,cap)
    w=model['weights'].to_numpy();cov=model['cov'];mu=model['mu'];sigma=model['risk']
    marginal=cov@w
    variance=float(w@cov@w)
    contribution=w*marginal
    returns=history.pct_change(fill_method=None).dropna()
    per_asset=pd.DataFrame(dict(id=history.columns,weight=w,annual_mean=mu,
        annual_volatility=np.sqrt(np.diag(cov)),weighted_return=w*mu,
        variance_contribution=contribution,
        volatility_contribution=contribution/sigma if sigma>1e-14 else np.full(len(w),np.nan),
        risk_share=contribution/variance if variance>1e-14 else np.full(len(w),np.nan)))
    return dict(model=model,assets=per_asset,covariance=pd.DataFrame(cov,index=history.columns,columns=history.columns),
        correlation=returns.corr(),variance=variance,
        estimated_sharpe=(model['expected_return']-rf)/sigma if sigma>1e-14 else np.nan,
        utility=model['expected_return']-gamma/2*variance)


def frontier(history,gamma,cap,points=25):
    info=workings(history,gamma,cap);model=info['model']
    mu,cov=model['mu'],model['cov'];n=len(mu)
    scale=max(float(np.max(np.abs(cov))),1e-12)
    def solve(target=None,initial=None):
        constraints=[dict(type='eq',fun=lambda w:w.sum()-1,jac=lambda w:np.ones(n))]
        if target is not None:constraints.append(dict(type='eq',fun=lambda w:w@mu-target,jac=lambda w:mu))
        out=minimize(lambda w:w@cov@w/scale,np.full(n,1/n) if initial is None else initial,
            jac=lambda w:2*cov@w/scale,bounds=[(0,cap)]*n,constraints=constraints,
            method='SLSQP',options={'ftol':1e-12,'maxiter':1500})
        if not out.success or abs(out.x.sum()-1)>1e-7 or out.x.min()<-1e-8 or out.x.max()>cap+1e-8:return None
        if target is not None and abs(out.x@mu-target)>1e-6:return None
        return out.x
    gmv=solve()
    if gmv is None:raise ValueError('Minimum-variance frontier calculation failed.')
    upper=np.zeros(n);left=1.
    for i in np.argsort(mu)[::-1]:upper[i]=min(left,cap);left-=upper[i]
    low,high=float(gmv@mu),float(upper@mu)
    rows=[]
    for goal in np.linspace(low,high,points):
        w=solve(float(goal),gmv)
        if w is not None:rows.append(dict(expected_return=float(w@mu),risk=float(np.sqrt(max(w@cov@w,0)))))
    return pd.DataFrame(rows)


def assessment(result,goal='Balance return and risk',demo=False):
    d,s=(result[k]['metrics'] for k in ('Dynamic','Static'))
    if goal=='Highest net return':field='total_return';larger=True;criterion='net return after costs'
    elif goal=='Lowest volatility':field='volatility';larger=False;criterion='observed volatility'
    else:field='sharpe';larger=True;criterion='Sharpe ratio (return above the risk-free rate per unit of volatility)'
    x,y=d[field],s[field]
    if not np.isfinite([x,y]).all() or np.isclose(x,y,atol=1e-10):winner='No clear winner'
    else:winner='Dynamic' if (x>y if larger else x<y) else 'Static'
    if max(d['total_return'],s['total_return'])<=0:
        candidate='Neither';reason='Both strategies lost money after costs in this period.'
    elif winner=='No clear winner':candidate=winner;reason=f'The selected {criterion} does not distinguish them reliably.'
    elif result[winner]['metrics']['total_return']<=0:
        candidate='Neither';reason=f'{winner} met the selected ranking criterion but still lost money after costs.'
    elif field=='sharpe' and result[winner]['metrics']['sharpe']<=0:
        candidate='Neither';reason='Neither delivered positive risk-adjusted excess return under the configured risk-free rate.'
    else:candidate=winner;reason=f'{winner} was stronger on {criterion} in this historical test.'
    nav=result['Dynamic']['nav'];elapsed=(nav.index[-1]-nav.index[0]).total_seconds()/86400
    short=elapsed<180 or len(nav)-1<60
    status='Demo only' if demo else 'Insufficient evidence for an investment choice' if short else 'Historical candidate for further validation'
    return dict(candidate=candidate,winner=winner,reason=reason,status=status,short_sample=short,
        caution='Synthetic results cannot support an investment decision.' if demo else
        'This short window cannot establish long-term performance. Test a longer daily history and an untouched later period.' if short else
        'This is a historical comparison, not a forecast. Validate on an untouched later period and check whether its risks fit your needs.')
