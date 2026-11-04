from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from backtesting import backtest,schedule
from config import Settings
from transaction_costs import Costs


def run(fixture, settings=None, prices=None):
    p,a,c=fixture
    if prices is not None: p=prices
    return backtest(p,p,p*0+1,a,str(p.index[150].date()),str(p.index[-1].date()),
                    settings or Settings(lookback=60),c)


@pytest.mark.parametrize('frequency,expected', [('Weekly',53),('Monthly',12),('Quarterly',4),('Semi-annually',2),('Yearly',1)])
def test_calendar(frequency,expected):
    dates=pd.bdate_range('2024-01-01','2024-12-31')
    assert len(schedule(dates,frequency))==expected


def test_static_buy_and_hold_exact(fixture):
    p,_,_=fixture
    r=run(fixture); v=r['Static']['nav']
    expected=100000*(p.iloc[-1]/p.iloc[150]).mean()
    assert v.iloc[-1]==pytest.approx(expected)
    assert len(r['Static']['rebalances'])==1
    assert len(r['Static']['trades'])==3
    assert r['Static']['metrics']['gross_return']==pytest.approx(r['Static']['metrics']['total_return'])


def test_costs_reconcile_and_reduce_nav(fixture):
    p,a,c=fixture
    profile=dict(c.profiles[0],rules=[dict(component='commission',value_rate=.002)])
    r=run((p,a,Costs([profile],spread_bps=3,fx_bps=0)))
    for strategy in ('Dynamic','Static'):
        x=r[strategy]; rb=x['rebalances']; trades=x['trades']
        assert np.allclose(rb.nav_before-rb.costs,rb.nav_after)
        assert x['nav'].iloc[-1] < x['gross_nav'].iloc[-1]
        assert trades.total_cost.sum()==pytest.approx(rb.costs.sum())
        assert x['nav'].iloc[1]==pytest.approx(100000-rb.costs.iloc[0])
        assert np.allclose(x['nav'].pct_change().dropna(),np.diff(x['nav'])/x['nav'].iloc[:-1])


def test_no_lookahead(fixture):
    p,_,_=fixture; before=run(fixture)
    cutoff=p.index[300]
    altered=p.copy(); altered.loc[cutoff:,'A']*=np.linspace(2,3,len(altered.loc[cutoff:]))
    after=run(fixture,prices=altered)
    a=before['decisions']; b=after['decisions']
    pd.testing.assert_frame_equal(a[a.date<=cutoff],b[b.date<=cutoff])
    assert (a.signal_last_date<a.date).all()


def test_selection_changes_calculation(fixture):
    p,a,c=fixture
    original=run(fixture)
    replacement=p.copy(); replacement['C']=100*np.exp(np.arange(len(p))*.001)
    changed=run((replacement,a,c))
    assert not np.isclose(original['Static']['nav'].iloc[-1],changed['Static']['nav'].iloc[-1])


def test_fail_on_insufficient_history_or_asset_mismatch(fixture):
    p,a,c=fixture
    with pytest.raises(ValueError,match='history'):
        run(fixture,Settings(lookback=300))
    with pytest.raises(ValueError,match='identity'):
        backtest(p[['A','B']],p,p*0+1,a,'2023-01-01','2023-12-01',Settings(),c)
