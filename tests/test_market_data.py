import numpy as np
import pandas as pd
import pytest
from market_data import MarketData,panel


def test_directory_cache_and_metadata(tmp_path,monkeypatch):
    calls=[]
    class Response:
        ok=True
        def json(self):
            return [dict(Code='AAA',Name='Alpha',Exchange='NYSE',Country='USA',Currency='USD',Type='ETF')]
    def get(*args,**kwargs): calls.append(1); return Response()
    monkeypatch.setattr('market_data.requests.get',get)
    c=MarketData('eodhd','secret',tmp_path,rpm=1000000)
    d=c.directory('US'); again=c.directory('US')
    assert d.id.iloc[0]=='AAA.US' and len(calls)==1
    assert c.audit[-1]['cached'] and 'secret' not in str(list(tmp_path.iterdir()))
    assert again.currency.iloc[0]=='USD'


def test_api_error_is_not_synthetic(tmp_path,monkeypatch):
    class Response:
        ok=True
        def json(self): return dict(status='error',message='no entitlement')
    monkeypatch.setattr('market_data.requests.get',lambda *a,**k:Response())
    with pytest.raises(ValueError,match='rejected'):
        MarketData('twelve','key',tmp_path).exchanges()


def test_panel_preserves_assets_and_converts_fx(fixture):
    p,assets,_=fixture
    histories={a['id']:pd.DataFrame({'close':p[a['id']],'adjusted':p[a['id']]}) for a in assets}
    assets[1]['currency']='JPY'
    histories['B']=histories['B'].drop(p.index[3])
    adjusted,raw,fx,q=panel(histories,{'USD':None,'JPY':pd.Series(.01,index=p.index)},assets)
    assert list(adjusted)==['A','B','C'] and len(adjusted)==len(p)-1
    assert adjusted.B.iloc[0]==pytest.approx(raw.B.iloc[0]*.01)
    assert q['omitted_dates']==1


def test_long_gaps_fail(fixture):
    p,assets,_=fixture
    h={a['id']:pd.DataFrame({'close':p[a['id']],'adjusted':p[a['id']]}) for a in assets}
    h['C']=h['C'].drop(p.index[10:40])
    with pytest.raises(ValueError,match='gap'): panel(h,{'USD':None},assets)


def test_etf_directory_does_not_mislabel_mutual_funds(tmp_path,monkeypatch):
    class Response:
        ok=True
        def json(self):
            return {'data':[dict(symbol='QQQ',exchange='NASDAQ',currency='USD',cfi_code='CECGEU'),
                            dict(symbol='FUND',exchange='NASDAQ',currency='USD',cfi_code='CIOGLU')]}
    monkeypatch.setattr('market_data.requests.get',lambda *a,**k:Response())
    d=MarketData('twelve','',tmp_path).directory('NASDAQ',kind='ETF')
    assert d.ticker.tolist()==['QQQ'] and d.asset_type.tolist()==['ETF']


def test_history_normalization(tmp_path,monkeypatch):
    class Response:
        ok=True
        def json(self):
            return [dict(date=f'2024-01-0{i}',close=100+i,adjusted_close=90+i) for i in range(1,5)]
    monkeypatch.setattr('market_data.requests.get',lambda *a,**k:Response())
    h=MarketData('eodhd','key',tmp_path).history({'id':'A.US'},'2024-01-01','2024-01-04')
    assert h.close.iloc[0]==101 and h.adjusted.iloc[0]==91
    assert len(h)==4 and h.index.is_monotonic_increasing
