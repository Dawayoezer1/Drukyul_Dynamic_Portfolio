import numpy as np
import pandas as pd
import pytest
from performance_metrics import metrics


def test_hand_calculated_downside_and_drawdown():
    v=pd.Series([100,110,88,99],index=pd.date_range('2024-01-01',periods=4))
    m=metrics(v,100,pd.DataFrame(),99,risk_free=0,mar=0)
    annualizer=365.25
    assert m['total_return']==pytest.approx(-.01)
    assert m['max_drawdown']==pytest.approx(-.2)
    assert m['volatility']==pytest.approx(np.std([.1,-.2,.125],ddof=1)*np.sqrt(annualizer))
    assert m['downside_deviation']==pytest.approx(np.sqrt(.04/3)*np.sqrt(annualizer))


def test_zero_risk_ratios_undefined():
    v=pd.Series([100,100,100],index=pd.date_range('2024-01-01',periods=3))
    m=metrics(v,100,pd.DataFrame(),100,risk_free=0)
    assert np.isnan(m['sharpe']) and np.isnan(m['sortino'])


@pytest.mark.parametrize('bad',[[100,-10,110],[100,np.nan,110],[100,0,110]])
def test_invalid_nav_rejected(bad):
    with pytest.raises(ValueError):
        metrics(pd.Series(bad,index=pd.date_range('2024-01-01',periods=3)),100,pd.DataFrame(),110)
