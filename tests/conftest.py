import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pytest
from transaction_costs import Costs

@pytest.fixture
def fixture():
    rng = np.random.default_rng(17)
    dates = pd.bdate_range('2022-01-03', periods=550)
    prices = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0002,.01,(550,3)),axis=0)),
                          index=dates, columns=['A','B','C'])
    assets=[dict(id=k,ticker=k,exchange='X',route='X',country='Test',currency='USD',
                 asset_type='Common Stock') for k in prices]
    profile=dict(route='X',currency='USD',name='TEST ONLY',asset_types=['Common Stock'],
                 **{'from':'2000-01-01','to':'2100-01-01'}, rules=[])
    costs=Costs([profile],spread_bps=0,fx_bps=0)
    return prices, assets, costs
