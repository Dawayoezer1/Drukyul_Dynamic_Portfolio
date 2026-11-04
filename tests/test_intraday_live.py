import numpy as np
import pandas as pd
import pytest
from backtesting import backtest,schedule
from portfolio_optimizer import optimize
from live_portfolio import tick,due
from config import Settings


def test_intraday_optimizer_and_lookahead(fixture):
    daily,assets,costs=fixture
    p=daily.iloc[:160].copy()
    p.index=pd.date_range('2024-01-02 14:30',periods=len(p),freq='min')
    assert optimize(p.iloc[:30])['annualizer']>100000
    settings=Settings(lookback=20,frequency='Every minute')
    args=(p,p,p*0+1,assets,str(p.index[30]),str(p.index[-1]),settings,costs)
    a=backtest(*args)
    changed=p.copy();changed.iloc[80:,0]*=2
    b=backtest(changed,changed,changed*0+1,assets,str(p.index[30]),str(p.index[-1]),settings,costs)
    cutoff=p.index[80]
    pd.testing.assert_frame_equal(a['decisions'].query('date <= @cutoff'),b['decisions'].query('date <= @cutoff'))
    assert len(a['Dynamic']['rebalances'])==130
    assert len(a['Static']['rebalances'])==1
    assert (a['decisions'].signal_last_date<a['decisions'].date).all()


def test_daily_cannot_fake_minute_prices(fixture):
    p,a,c=fixture
    with pytest.raises(ValueError,match='finer'):
        backtest(p,p,p*0+1,a,str(p.index[100]),str(p.index[-1]),Settings(lookback=20,frequency='Every minute'),c)


def test_hour_daily_and_quarter_schedule():
    idx=pd.date_range('2024-01-01 09:30',periods=130,freq='min')
    assert len(schedule(idx,'Hourly'))==3
    assert len(schedule(idx,'Every 5 minutes'))==26
    assert not due('2024-01-01 09:30','2024-01-01 09:31','Hourly')
    assert due('2024-01-01 09:30','2024-01-01 10:01','Hourly')


def test_paper_replacement_cost_reconciliation_and_frozen_static(fixture):
    _,assets,costs=fixture
    quotes={'A':100.,'B':50.,'C':25.}
    book=tick(None,assets,quotes,{'A':.5,'B':.3,'C':.2},costs,10000,pd.Timestamp('2024-01-02 10:00'),'Hourly')
    original_static=dict(book['static'])
    replacement=tick(book,assets[1:],quotes,{'B':.5,'C':.5},costs,10000,pd.Timestamp('2024-01-02 11:00'),'Hourly')
    assert replacement['static']==original_static
    assert replacement['dynamic']['A']==0
    assert replacement['nav'][-1]['Dynamic']==pytest.approx(10000)
    assert len([x for x in replacement['ledger'] if x['strategy']=='Static'])==3
    assert book['dynamic']['A']>0 # atomic: input unchanged


def test_intraday_adapter_paginates_without_skipping_dates(tmp_path,monkeypatch):
    from market_data import MarketData
    calls=[]
    def request(self,endpoint,params,refresh):
        calls.append(params)
        if len(calls)<=2:
            stamps=pd.date_range('2024-01-02 10:00',periods=5000,freq='min')
        else:stamps=pd.date_range('2024-01-02 09:50',periods=10,freq='min')
        return {'meta':{'currency':'USD'},'values':[{'datetime':str(x),'close':100} for x in stamps]}
    monkeypatch.setattr(MarketData,'request',request)
    client=MarketData('twelve','test',tmp_path,interval='1min')
    frame=client.history({'id':'A|X','ticker':'A','route':'X','currency':'USD'},'2024-01-02 09:50','2024-01-06')
    assert len(frame)==5010
    assert calls[2]['end_date']=='2024-01-02 09:59:59'
    assert calls[0]['timezone']=='UTC'


def test_paper_costs_reduce_each_book_once(fixture):
    from transaction_costs import Costs
    _,assets,zero=fixture
    costs=Costs([dict(zero.profiles[0],rules=[{'component':'commission','value_rate':.002}])],spread_bps=5,fx_bps=0)
    quotes={'A':100.,'B':50.,'C':25.}
    first=tick(None,assets,quotes,{'A':.5,'B':.3,'C':.2},costs,10000,pd.Timestamp('2024-01-02 10:00'),'Hourly')
    second=tick(first,assets[1:],quotes,{'B':.5,'C':.5},costs,10000,pd.Timestamp('2024-01-02 11:00'),'Hourly')
    for label in ('Dynamic','Static'):
        fees=sum(row['total_cost'] for row in second['ledger'] if row['strategy']==label)
        assert second['nav'][-1][label]==pytest.approx(10000-fees)
    assert second['nav'][-1]['Dynamic']<second['nav'][-1]['Static']


def test_extreme_intraday_cagr_is_undefined_not_infinite():
    from performance_metrics import metrics
    nav=pd.Series([100.,110.,120.],index=pd.date_range('2024-01-01',periods=3,freq='min'))
    assert np.isnan(metrics(nav,100,pd.DataFrame(),120)['cagr'])
