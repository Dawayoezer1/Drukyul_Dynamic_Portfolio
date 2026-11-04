"""Provider directories first; histories only for selected instruments. No fallback."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import time
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
from config import CACHE


def utc():
    return datetime.now(timezone.utc).isoformat()


class MarketData:
    def __init__(self, provider, key, cache=CACHE, rpm=8, interval="1day"):
        if provider not in ('eodhd', 'twelve'):
            raise ValueError('Unknown provider.')
        self.provider, self.key, self.cache = provider, key, Path(cache)
        self.rpm, self.last_call = max(1, int(rpm)), 0.0
        self.cache.mkdir(parents=True, exist_ok=True)
        self.audit = []
        self.interval = interval

    def request(self, endpoint, params=None, refresh=False, ttl=86400):
        params = params or {}
        # Neither filenames nor errors contain credentials.
        digest = sha256(json.dumps([self.provider, endpoint, params],
                                  sort_keys=True).encode()).hexdigest()
        path = self.cache / (digest + '.json')
        if path.exists() and not refresh and time.time() - path.stat().st_mtime < ttl:
            envelope = json.loads(path.read_text())
            self.audit.append(dict(endpoint=endpoint, cached=True,
                                   updated=envelope['updated'], sha256=digest))
            return envelope['data']
        if not self.key and not (self.provider == 'twelve' and endpoint in ('stocks', 'etfs', 'exchanges', 'symbol_search')):
            raise ValueError(f'Configure the {self.provider} API key in .env.')
        delay = 60 / self.rpm - (time.monotonic() - self.last_call)
        if delay > 0:
            time.sleep(delay)
        base = ('https://eodhd.com/api/' if self.provider == 'eodhd'
                else 'https://api.twelvedata.com/')
        auth = {'api_token': self.key, 'fmt': 'json'} if self.provider == 'eodhd' else ({'apikey': self.key} if self.key else {})
        try:
            self.last_call = time.monotonic()
            response = requests.get(base + endpoint, params={**params, **auth}, timeout=45)
            if not response.ok:
                raise ValueError(f'{self.provider}: HTTP {response.status_code} at {endpoint}. '
                                 'Check subscription, ticker and rate limit.')
            data = response.json()
        except (requests.RequestException, json.JSONDecodeError):
            raise ValueError(f'{self.provider}: connection or JSON failure at {endpoint}.') from None
        if isinstance(data, dict) and (data.get('status') == 'error' or 'error' in data):
            raise ValueError(f'{self.provider}: API rejected {endpoint}; check entitlement/limits.')
        stamp = utc()
        path.write_text(json.dumps({'updated': stamp, 'data': data}))
        self.audit.append(dict(endpoint=endpoint, cached=False, updated=stamp, sha256=digest))
        return data

    def exchanges(self, refresh=False):
        data = self.request('exchanges-list/' if self.provider == 'eodhd' else 'exchanges',
                            refresh=refresh, ttl=7 * 86400)
        return pd.DataFrame(data if isinstance(data, list) else data['data'])

    def directory(self, exchange='', country='', kind='Common Stock', refresh=False,
                  delisted=False):
        if self.provider == 'eodhd':
            if not exchange:
                raise ValueError('Choose a provider exchange code.')
            rows = self.request('exchange-symbol-list/' + exchange,
                                {'delisted': int(delisted)}, refresh, 7 * 86400)
            records = [dict(id=f"{r['Code']}.{exchange}", ticker=r['Code'],
                            name=r.get('Name', ''), exchange=r.get('Exchange', exchange),
                            country=r.get('Country', ''), currency=r.get('Currency', ''),
                            asset_type=r.get('Type', ''), provider=self.provider,
                            route=exchange) for r in rows]
        else:
            params = {k: v for k, v in {'exchange': exchange, 'country': country,
                                       'type': kind}.items() if v}
            endpoint = 'etfs' if kind == 'ETF' else 'stocks'
            if kind == 'ETF':
                params.pop('type', None)
            rows = self.request(endpoint, params, refresh, 7 * 86400)['data']
            # The ETF directory also contains mutual funds. Do not call all rows ETFs.
            if kind == 'ETF':
                rows = [r for r in rows if r.get('type') == 'ETF' or r.get('cfi_code', '').startswith('CE')]
                for r in rows:
                    r['type'] = 'ETF'
            records = [dict(id=f"{r['symbol']}|{r['exchange']}", ticker=r['symbol'],
                            name=r.get('name', ''), exchange=r['exchange'],
                            country=r.get('country', ''), currency=r.get('currency', ''),
                            asset_type=r.get('type', ''), provider=self.provider,
                            route=r['exchange'], mic_code=r.get('mic_code', '')) for r in rows]
        frame = pd.DataFrame(records)
        if frame.empty:
            raise ValueError('Provider returned no directory entries for these filters.')
        frame['availability'] = 'Directory only; history/entitlement not yet checked'
        frame['directory_updated_utc'] = self.audit[-1]['updated']
        return frame.drop_duplicates('id').reset_index(drop=True)

    def search(self, query):
        if not query.strip():
            raise ValueError('Enter a ticker or company name.')
        if self.provider == 'eodhd':
            rows = self.request('search/' + quote(query.strip(), safe=''), {'limit': 50}, ttl=3600)
            records = [dict(id=f"{r['Code']}.{r['Exchange']}", ticker=r['Code'],
                name=r.get('Name',''), exchange=r['Exchange'], route=r['Exchange'],
                country=r.get('Country',''), currency=r.get('Currency',''),
                asset_type=r.get('Type',''), provider=self.provider) for r in rows]
        else:
            rows = self.request('symbol_search', {'symbol':query.strip()}, ttl=3600).get('data',[])
            records = [dict(id=f"{r['symbol']}|{r['exchange']}", ticker=r['symbol'],
                name=r.get('instrument_name',''), exchange=r['exchange'], route=r['exchange'],
                country=r.get('country',''), currency=r.get('currency',''),
                asset_type=r.get('instrument_type',''), mic_code=r.get('mic_code',''),
                provider=self.provider) for r in rows]
        allowed = ('Common Stock','Preferred Stock','ETF')
        return pd.DataFrame([dict(r, availability='Search metadata; history not checked',
                                  directory_updated_utc=self.audit[-1]['updated'])
                             for r in records if r['asset_type'] in allowed])

    def history(self, asset, start, end, refresh=False):
        if self.provider == 'eodhd':
            if self.interval != '1day':
                raise ValueError('Choose Twelve Data for intraday backtests.')
            rows = self.request('eod/' + asset['id'], {'from': start, 'to': end,
                                                     'period': 'd'}, refresh)
            frame = pd.DataFrame(rows).rename(columns={'date': 'date',
                                                       'adjusted_close': 'adjusted'})
        else:
            common = dict(symbol=asset['ticker'], exchange=asset['route'], interval=self.interval, timezone='UTC',
                          start_date=start, end_date=end, outputsize=5000, order='asc')
            if asset.get('mic_code'):
                common['mic_code'] = asset['mic_code']
            parts = []
            # Paginate backwards: never silently accept the provider's 5,000-row cap.
            until = end
            while True:
                adjusted = self.request('time_series', {**common, 'end_date': until,
                                                        'adjust': 'all'}, refresh)
                raw = self.request('time_series', {**common, 'end_date': until,
                                                  'adjust': 'none'}, refresh)
                a = pd.DataFrame(adjusted.get('values', []))
                b = pd.DataFrame(raw.get('values', []))
                if a.empty or b.empty:
                    raise ValueError(f"No history for {asset['id']}.")
                if adjusted.get('meta', {}).get('currency') != asset['currency']:
                    raise ValueError(f"Currency mismatch for {asset['id']}.")
                parts.append(a[['datetime', 'close']].rename(columns={'close': 'adjusted'})
                             .merge(b[['datetime', 'close']], on='datetime', validate='one_to_one'))
                oldest = pd.to_datetime(a['datetime']).min()
                if len(a) < 5000 or oldest <= pd.Timestamp(start):
                    break
                step = pd.Timedelta(days=1) if self.interval == '1day' else pd.Timedelta(seconds=1)
                new_until = (oldest - step).strftime('%Y-%m-%d %H:%M:%S')
                if new_until == until:
                    raise ValueError('History pagination made no progress; shorten the range.')
                until = new_until
            frame = pd.concat(parts).rename(columns={'datetime': 'date'})
        if not {'date', 'close', 'adjusted'} <= set(frame):
            raise ValueError(f"Missing raw/adjusted prices: {asset['id']}.")
        frame['date'] = pd.to_datetime(frame['date'])
        frame = frame.set_index('date')[['close', 'adjusted']].astype(float).sort_index()
        if frame.index.has_duplicates:
            raise ValueError(f"Duplicate history dates: {asset['id']}.")
        if len(frame) < 4 or not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
            raise ValueError(f"Invalid or insufficient history: {asset['id']}.")
        frame = frame.loc[start:end]
        if self.interval != '1day':
            seconds = {'1min': 60, '5min': 300, '15min': 900, '1h': 3600}[self.interval]
            # Drop the still-forming bar: only completed bars may drive decisions.
            now = pd.Timestamp.now(tz='UTC').tz_localize(None)
            frame = frame[frame.index + pd.Timedelta(seconds=seconds) <= now]
        return frame

    def fx(self, currency, base, start, end, refresh=False):
        if currency == base:
            return None
        if self.provider == 'eodhd':
            instrument = dict(id=f'{currency}{base}.FOREX')
            return self.history(instrument, start, end, refresh)['close']
        rows = self.request('time_series', dict(symbol=f'{currency}/{base}',
                            interval=self.interval, timezone='UTC', start_date=start, end_date=end,
                            outputsize=5000, order='asc'), refresh).get('values', [])
        if len(rows) >= 5000:
            raise ValueError('FX response reached 5000 rows; shorten the requested range.')
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ValueError(f'No FX history for {currency}/{base}.')
        return pd.Series(frame['close'].astype(float).to_numpy(),
                         index=pd.to_datetime(frame['datetime'])).sort_index()

    def quote(self, asset, refresh=False):
        if self.provider == 'eodhd':
            payload = self.request('real-time/' + asset['id'], refresh=refresh, ttl=60)
            status = 'Provider live/delayed endpoint; delay not verified'
        else:
            payload = self.request('quote', dict(symbol=asset['ticker'],
                                   exchange=asset['route'], timezone='UTC', **({'mic_code':asset['mic_code']} if asset.get('mic_code') else {})), refresh, 60)
            status = 'Provider quote; real-time entitlement/delay not verified'
        return {'status': status, 'payload': payload, 'retrieved_utc': self.audit[-1]['updated'],
                'cached': self.audit[-1]['cached']}


def panel(histories, fx, assets, max_gap_days=10):
    """Intersection calendar: never forward-fill, back-fill, or discard an asset."""
    adjusted, raw, rates = {}, {}, {}
    for a in assets:
        key = a['id']
        h = histories[key]
        rate = fx[a['currency']]
        f = pd.Series(1.0, index=h.index) if rate is None else rate.reindex(h.index)
        adjusted[key], raw[key], rates[key] = h['adjusted'] * f, h['close'], f
    joined = pd.concat({ 'adjusted': pd.DataFrame(adjusted),
                         'raw': pd.DataFrame(raw), 'fx': pd.DataFrame(rates)}, axis=1)
    complete = joined.dropna()
    if len(complete) < 4:
        raise ValueError('Too few shared equity/FX observation dates; no assets removed.')
    x = complete.to_numpy(float)
    if not np.isfinite(x).all() or (x <= 0).any():
        raise ValueError('Non-positive or invalid equity/FX observations.')
    if complete.index.to_series().diff().dt.days.max() > max_gap_days:
        raise ValueError('Excessive gap on shared calendar; inspect missing data.')
    return (complete['adjusted'], complete['raw'], complete['fx'],
            {'union_rows': len(joined), 'shared_rows': len(complete),
             'omitted_dates': len(joined) - len(complete),
             'first_shared': str(complete.index[0]), 'last_shared': str(complete.index[-1])})
