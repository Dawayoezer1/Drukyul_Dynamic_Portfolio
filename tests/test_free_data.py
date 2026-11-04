from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import pytest
from free_data import FreeMarketData,validate_range
from portfolio_analysis import workings,frontier,assessment
from catalog import load_catalog,parse_nasdaq
from config import ROOT


def test_free_intraday_and_cache(tmp_path,monkeypatch):
    now=pd.Timestamp.now(tz='UTC').normalize()
    index=pd.date_range(now-pd.Timedelta(days=2)+pd.Timedelta(hours=14),periods=20,freq='5min')
    raw=pd.DataFrame({'Close':np.arange(20)+100.,'Adj Close':np.arange(20)+99.},index=index)
    calls=[]
    class Ticker:
        history_metadata={'currency':'USD'}
        def __init__(self,symbol):pass
        def history(self,**kwargs):calls.append(kwargs);return raw.copy()
    monkeypatch.setattr('free_data.yf.Ticker',Ticker)
    client=FreeMarketData('5min',tmp_path)
    a=dict(id='A|NASDAQ',ticker='A',route='NASDAQ',currency='USD')
    begin=str((now-pd.Timedelta(days=3)).date());end=str((now-pd.Timedelta(days=1)).date())
    first=client.history(a,begin,end);second=client.history(a,begin,end)
    assert len(calls)==1
    assert calls[0]['auto_adjust'] is False
    assert first.index[0]==index[0].tz_localize(None)+pd.Timedelta(minutes=5)
    assert client.audit[-1]['cached']
    pd.testing.assert_frame_equal(first,second,check_freq=False)


def test_free_rejects_wrong_currency_and_missing_adjustment(tmp_path,monkeypatch):
    class Ticker:
        history_metadata={'currency':'JPY'}
        def __init__(self,symbol):pass
        def history(self,**kwargs):return pd.DataFrame({'Close':[100.,101.,102.,103.]},index=pd.date_range('2024-01-01',periods=4,tz='UTC'))
    monkeypatch.setattr('free_data.yf.Ticker',Ticker)
    client=FreeMarketData(cache=tmp_path)
    with pytest.raises(ValueError,match='both Close and Adj Close'):
        client.history(dict(id='A',ticker='A',yahoo_symbol='A',currency='USD'),'2024-01-01','2024-01-10')


def test_free_old_intraday_request_stops_before_network():
    with pytest.raises(ValueError,match='last 7 days'):
        validate_range('2026-10-01','2026-10-20','1min',pd.Timestamp('2026-10-30'))
    with pytest.raises(ValueError,match='last 60 days'):
        validate_range('2026-01-01','2026-10-20','5min',pd.Timestamp('2026-10-30'))
    validate_range('2020-01-01','2026-10-20','1day',pd.Timestamp('2026-10-30'))


def test_free_directory_has_names_tickers_and_no_test_issues():
    catalog=load_catalog(ROOT)
    assert len(catalog)>1000
    assert {'AAPL|NASDAQ','NVDA|NASDAQ','JPM|NYSE','GLD|NYSE Arca'}<=set(catalog.id)
    parsed=parse_nasdaq('Symbol|Security Name|Test Issue|ETF\nAA|Alpha Common Stock|N|N\nTEST|Test Common Stock|Y|N\nWW|Warrant Warrants|N|N\n',True)
    assert parsed.ticker.tolist()==['AA']


def test_markowitz_workings_risk_contributions_and_frontier(fixture):
    history=fixture[0].iloc[:126]
    calc=workings(history,5,.4)
    assert calc['assets'].variance_contribution.sum()==pytest.approx(calc['variance'])
    assert calc['assets'].volatility_contribution.sum()==pytest.approx(calc['model']['risk'])
    assert calc['assets'].weighted_return.sum()==pytest.approx(calc['model']['expected_return'])
    curve=frontier(history,5,.4)
    assert len(curve)>10
    assert np.diff(curve.expected_return).min()>-1e-8
    assert np.diff(curve.risk).min()>-1e-6


def test_assessment_does_not_recommend_demo_short_or_losing_window():
    nav=pd.Series([100,99,98],index=pd.date_range('2026-10-01',periods=3))
    a=dict(total_return=-.02,sharpe=-.1,volatility=.1)
    b=dict(total_return=-.03,sharpe=-.2,volatility=.2)
    result={'Dynamic':dict(metrics=a,nav=nav),'Static':dict(metrics=b,nav=nav)}
    out=assessment(result)
    assert out['candidate']=='Neither'
    assert out['short_sample']
    assert 'Insufficient' in out['status']
    assert assessment(result,demo=True)['status']=='Demo only'


def test_tail_risk_hand_calculation():
    from performance_metrics import extended_risk,compare_to_static
    nav=pd.Series([100,110,88,99],index=pd.date_range('2024-01-01',periods=4))
    out=extended_risk(nav)
    losses=np.array([-.1,.2,-.125])
    assert out['var95']==pytest.approx(np.quantile(losses,.95))
    assert out['es95']==pytest.approx(.2)
    pair=compare_to_static(nav,nav,365.25)
    assert pair['beta_to_static']==pytest.approx(1)
    assert pair['alpha_to_static']==pytest.approx(0)
    assert pair['tracking_error']==pytest.approx(0)


def test_free_quote_accepts_yfinance_timestamp_metadata(monkeypatch,tmp_path):
    now=pd.Timestamp.now(tz='UTC')
    class Ticker:
        history_metadata={'currency':'USD','regularMarketPrice':125.,'regularMarketTime':now,
            'currentTradingPeriod':{'regular':{'start':now-pd.Timedelta(hours=1),'end':now+pd.Timedelta(hours=1)}}}
        def __init__(self,symbol):pass
        def history(self,**kwargs):return pd.DataFrame({'Close':[125.]},index=[now-pd.Timedelta(minutes=1)])
    monkeypatch.setattr('free_data.yf.Ticker',Ticker)
    result=FreeMarketData(cache=tmp_path).quote(dict(ticker='A',route='NASDAQ',currency='USD'))
    assert result['payload']['close']==125.
    assert result['payload']['is_market_open']
    assert result['payload']['timestamp']==int(now.timestamp())
