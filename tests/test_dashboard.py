from pathlib import Path
from streamlit.testing.v1 import AppTest

APP=Path(__file__).parents[1]/'app.py'


def test_one_page_without_credentials():
    app=AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    assert len(app.sidebar.radio)==0
    assert any('Stocks' in x.label for x in app.multiselect)
    assert any('dynamic' in x.label.lower() for x in app.button)


def test_demo_backtest_full_dashboard():
    app=AppTest.from_file(str(APP)).run(timeout=20)
    app.selectbox[0].set_value('Demo — synthetic data').run()
    next(b for b in app.button if b.label=='Build dynamic portfolio & compare').click().run(timeout=90)
    assert not app.exception
    assert not app.error
    assert app.session_state['result'] is not None
    assert app.session_state['result']['manifest']['source']=='SYNTHETIC DEMO'
    assert len(app.dataframe)>=3
    # Changing selection invalidates the old experiment instead of silently showing it.
    app.multiselect[0].set_value(['AAPL|NASDAQ','MSFT|NASDAQ']).run()
    assert any('inputs changed' in x.value for x in app.info)


def test_free_default_needs_no_key():
    app=AppTest.from_file(str(APP)).run(timeout=20)
    assert app.selectbox[0].value=='Free Yahoo Finance — no API key'
    assert not any('API key' in widget.label for widget in app.text_input)
    assert not app.exception


def test_demo_live_session_and_stock_replacement():
    app=AppTest.from_file(str(APP)).run(timeout=20)
    app.selectbox[0].set_value('Demo — synthetic data').run()
    next(b for b in app.button if b.label=='Start / rebalance paper portfolio').click().run(timeout=60)
    assert not app.exception
    assert not app.error
    first=app.session_state['book']
    assert first and len(first['static'])==7
    app.slider[0].set_value(1.).run()
    app.multiselect[0].set_value(['TSLA|NASDAQ','AMZN|NASDAQ']).run()
    next(b for b in app.button if b.label=='Start / rebalance paper portfolio').click().run(timeout=60)
    assert not app.exception
    assert not app.error
    second=app.session_state['book']
    assert first['static']==second['static']
    assert second['dynamic']['AAPL|NASDAQ']==0


def test_free_dashboard_runs_with_mocked_yahoo_without_key(fixture,monkeypatch):
    import pandas as pd
    from free_data import FreeMarketData
    prices,_,_=fixture
    def history(self,asset,start,end,refresh=False):
        source=prices.iloc[:,sum(map(ord,asset['ticker']))%3].loc[start:end]
        return pd.DataFrame({'close':source,'adjusted':source})
    monkeypatch.setattr(FreeMarketData,'history',history)
    app=AppTest.from_file(str(APP)).run(timeout=20)
    app.date_input[0].set_value(pd.Timestamp('2023-01-02').date())
    app.date_input[1].set_value(prices.index[-1].date()).run()
    next(b for b in app.button if b.label=='Build dynamic portfolio & compare').click().run(timeout=60)
    assert not app.exception
    assert not app.error
    assert app.session_state['result']['manifest']['source']=='Yahoo Finance via yfinance'
    assert any('Which strategy' in x.value for x in app.subheader)
    assert any('Markowitz' in x.value for x in app.subheader)
    assert not any('API key' in widget.label for widget in app.text_input)
