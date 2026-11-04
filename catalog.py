"""Starter browsing list, not a current exchange membership guarantee."""
import pandas as pd


def starter():
    entries = [
        ('AAPL','Apple Inc.','NASDAQ'), ('MSFT','Microsoft Corporation','NASDAQ'),
        ('NVDA','NVIDIA Corporation','NASDAQ'), ('AMZN','Amazon.com Inc.','NASDAQ'),
        ('GOOGL','Alphabet Inc. Class A','NASDAQ'), ('META','Meta Platforms Inc.','NASDAQ'),
        ('TSLA','Tesla Inc.','NASDAQ'), ('AVGO','Broadcom Inc.','NASDAQ'),
        ('AMD','Advanced Micro Devices Inc.','NASDAQ'), ('NFLX','Netflix Inc.','NASDAQ'),
        ('ADBE','Adobe Inc.','NASDAQ'), ('COST','Costco Wholesale Corporation','NASDAQ'),
        ('INTC','Intel Corporation','NASDAQ'), ('CSCO','Cisco Systems Inc.','NASDAQ'),
        ('QCOM','QUALCOMM Incorporated','NASDAQ'), ('PEP','PepsiCo Inc.','NASDAQ'),
        ('JPM','JPMorgan Chase & Co.','NYSE'), ('V','Visa Inc.','NYSE'),
        ('MA','Mastercard Incorporated','NYSE'), ('UNH','UnitedHealth Group Incorporated','NYSE'),
        ('WMT','Walmart Inc.','NASDAQ'), ('JNJ','Johnson & Johnson','NYSE'),
        ('XOM','Exxon Mobil Corporation','NYSE'), ('KO','The Coca-Cola Company','NYSE'),
        ('DIS','The Walt Disney Company','NYSE'), ('BA','The Boeing Company','NYSE'),
        ('CAT','Caterpillar Inc.','NYSE'), ('BAC','Bank of America Corporation','NYSE'),
        ('GE','GE Aerospace','NYSE'), ('VRT','Vertiv Holdings Co','NYSE'),
        ('ORCL','Oracle Corporation','NYSE'), ('PLTR','Palantir Technologies Inc.','NASDAQ'),
        ('SPY','SPDR S&P 500 ETF Trust','NYSE Arca'), ('QQQ','Invesco QQQ Trust','NASDAQ'),
        ('GLD','SPDR Gold Shares','NYSE Arca'), ('BND','Vanguard Total Bond Market ETF','NASDAQ')]
    return pd.DataFrame([dict(id=f'{t}|{e}',ticker=t,name=n,exchange=e,route=e,country='United States',
        currency='USD',asset_type='ETF' if t in ('SPY','QQQ','GLD','BND') else 'Common Stock',provider='twelve') for t,n,e in entries])


def parse_nasdaq(text,nasdaq=True):
    """Official symbol directory metadata; exclude tests and derivatives by name."""
    from io import StringIO
    frame=pd.read_csv(StringIO(text),sep='|',dtype=str).fillna('')
    rows=[]
    exchange_map={'N':'NYSE','A':'NYSE American','P':'NYSE Arca','Z':'BATS','V':'IEX'}
    for row in frame.to_dict('records'):
        symbol=row.get('Symbol' if nasdaq else 'ACT Symbol','')
        name=row.get('Security Name','')
        if not symbol or row.get('Test Issue')!='N' or not name:continue
        import re
        if re.search(r'\b(warrants?|rights?|units?|notes?|debentures?)\b',name,re.I):continue
        exchange='NASDAQ' if nasdaq else exchange_map.get(row.get('Exchange',''),'Other US')
        typ='ETF' if row.get('ETF')=='Y' else 'Common Stock' if re.search(r'common|ordinary|depositary|ads\b',name,re.I) else 'Other listed security'
        rows.append(dict(id=f'{symbol}|{exchange}',ticker=symbol,name=name,exchange=exchange,route=exchange,
            country='United States',currency='USD',asset_type=typ,provider='Yahoo Finance',
            yahoo_symbol=symbol.replace('.','-').replace('$','-P')))
    return pd.DataFrame(rows)


def load_catalog(root):
    path=root/'stocks_us.csv'
    base=starter()
    base['yahoo_symbol']=base.ticker.str.replace('.','-',regex=False)
    if path.exists():
        full=pd.read_csv(path,keep_default_na=False)
        return pd.concat([base,full]).drop_duplicates('id',keep='last').sort_values(['name','ticker']).reset_index(drop=True)
    return base


def refresh_catalog(root):
    import requests,json
    from datetime import datetime,timezone
    frames=[]
    for file,nasdaq in [('nasdaqlisted',True),('otherlisted',False)]:
        response=requests.get(f'https://www.nasdaqtrader.com/dynamic/SymDir/{file}.txt',timeout=25)
        response.raise_for_status()
        frame=parse_nasdaq(response.text,nasdaq)
        if frame.empty:raise ValueError('The public directory returned no usable entries. The bundled list was kept.')
        frames.append(frame)
    combined=pd.concat(frames).drop_duplicates('id')
    combined.to_csv(root/'stocks_us.csv',index=False)
    (root/'catalog_metadata.json').write_text(json.dumps(dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),
        source='Nasdaq Trader official symbol directories',rows=len(combined)),indent=2))
    return load_catalog(root)


def resolve_global(symbol):
    import yfinance as yf
    obj=yf.Ticker(symbol)
    history=obj.history(period='5d',auto_adjust=False,timeout=15)
    meta=obj.history_metadata
    if history.empty or not meta.get('currency') or meta.get('instrumentType') not in ('EQUITY','ETF'):
        raise ValueError('A current stock/ETF with currency metadata is required. Choose another search result.')
    exchange=meta.get('fullExchangeName') or meta.get('exchangeName','Yahoo')
    typ='ETF' if meta.get('instrumentType')=='ETF' else 'Common Stock'
    return dict(id=f'{symbol}|{exchange}',ticker=symbol,yahoo_symbol=symbol,
        name=meta.get('longName') or meta.get('shortName') or symbol,exchange=exchange,route=exchange,
        country=meta.get('exchangeTimezoneName',''),currency=meta['currency'],asset_type=typ,provider='Yahoo Finance')
