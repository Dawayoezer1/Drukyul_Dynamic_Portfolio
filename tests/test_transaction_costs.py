import json
from pathlib import Path
import pytest
from transaction_costs import Costs,rounded


def test_rounding():
    assert rounded(.005)==.01
    assert rounded(1.001,1,True)==2


def test_published_us_commission_and_sec():
    profiles=json.loads((Path(__file__).parents[1]/'fees.json').read_text())
    c=Costs(profiles,spread_bps=0,fx_bps=0)
    a=dict(id='A.US',ticker='A',route='US',exchange='NYSE',country='USA',currency='USD',asset_type='Common Stock')
    r=c.trade(a,'2026-10-29',-100000,100,1,'USD')
    assert r['commission']==5
    assert r['regulatory']==2.06  # SEC; CAT rounds to zero at this quantity
    assert r['net_cash_impact']==pytest.approx(100000-r['total_cost'])
    with pytest.raises(ValueError,match='dated'): c.profile(a,'2024-01-01')


def test_hk_rounding_and_etf_exemption_not_guessed():
    profiles=json.loads((Path(__file__).parents[1]/'fees.json').read_text())
    c=Costs(profiles,spread_bps=0,fx_bps=0)
    a=dict(id='1',ticker='1',route='HKEX',exchange='HKEX',country='Hong Kong',currency='HKD',asset_type='Common Stock')
    r=c.trade(a,'2026-10-29',10000.1,100,1,'HKD')
    assert r['tax']==11 and r['regulatory']==pytest.approx(.29) and r['exchange_fee']==pytest.approx(.57)
    a['asset_type']='ETF'
    with pytest.raises(ValueError): c.profile(a,'2026-10-29')


def test_fx_and_estimated_spread(fixture):
    _,assets,c=fixture
    a=dict(assets[0],currency='JPY')
    profile=dict(c.profiles[0],currency='JPY')
    r=Costs([profile],spread_bps=10,fx_bps=20).trade(a,'2024-01-02',1000,100,.01,'USD')
    assert r['quantity']==1000 and r['total_cost']==pytest.approx(3)
