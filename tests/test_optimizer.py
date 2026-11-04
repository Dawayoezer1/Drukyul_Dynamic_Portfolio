import numpy as np
import pytest
from portfolio_optimizer import optimize


def test_constraints(fixture):
    prices,_,_=fixture
    r=optimize(prices.iloc[:127],gamma=8,cap=.4)
    w=r['weights']
    assert abs(w.sum()-1)<1e-8 and w.min()>=0 and w.max()<=.4+1e-8
    assert np.allclose(r['cov'],r['cov'].T)
    assert r['optimality_gap']<1e-5


def test_infeasible(fixture):
    with pytest.raises(ValueError,match='Infeasible'):
        optimize(fixture[0],cap=.3)


def test_single_asset_and_no_twenty_limit(fixture):
    p=fixture[0]
    assert optimize(p[['A']])['weights'].iloc[0]==pytest.approx(1)
    many=p[['A']].copy()
    for i in range(1,25): many[str(i)]=p.A*(1+i/100)
    assert len(optimize(many,cap=.1)['weights'])==25


def test_invalid_prices(fixture):
    p=fixture[0].copy(); p.iloc[2,1]=np.nan
    with pytest.raises(ValueError): optimize(p)
