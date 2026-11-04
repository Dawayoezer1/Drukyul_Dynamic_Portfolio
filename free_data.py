"""No-key Yahoo Finance adapter. Real responses only; never synthetic fallback."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from io import StringIO
import re
import time
import numpy as np
import pandas as pd
import yfinance as yf
from config import CACHE

INTERVALS={'1day':'1d','1min':'1m','5min':'5m','15min':'15m','1h':'60m'}
SECONDS={'1min':60,'5min':300,'15min':900,'1h':3600}


def utc_now():
    return pd.Timestamp.now(tz='UTC').tz_localize(None)


def yahoo_symbol(asset):
    symbol=asset.get('yahoo_symbol')
    if symbol:return symbol
    ticker=asset['ticker']
    route=asset.get('route','')
    # Nasdaq public directory uses dots for US share classes; Yahoo uses hyphens.
    if asset.get('currency')=='USD' and route in ('NASDAQ','NYSE','NYSE Arca','NYSE American','BATS','IEX'):
        return ticker.replace('.','-').replace('$','-P')
    raise ValueError(f"Select a Yahoo ticker for {ticker}; exchange suffixes cannot be guessed.")


def validate_range(start,end,interval,now=None):
    now=pd.Timestamp(now) if now is not None else utc_now()
    begin,finish=pd.Timestamp(start),pd.Timestamp(end)
    if begin>=finish:raise ValueError('Data start must precede data end.')
    if interval not in INTERVALS:raise ValueError('Unsupported Yahoo data interval.')
    if interval!='1day':
        limit=7 if interval=='1min' else 60
        if begin<now-pd.Timedelta(days=limit)+pd.Timedelta(minutes=5):
            raise ValueError(f'Free {interval} data needs the whole request, including lookback, within the last {limit} days. Move comparison start later, reduce lookback, or choose Daily/Weekly/Monthly. No dates were silently changed.')


class FreeMarketData:
    def __init__(self,interval='1day',cache=CACHE):
        self.interval=interval;self.cache=cache;self.audit=[]
        self.cache.mkdir(parents=True,exist_ok=True)

    def _history(self,symbol,start,end,refresh=False,expected_currency=None):
        validate_range(start,end,self.interval)
        digest=sha256(json.dumps([symbol,str(start),str(end),self.interval],sort_keys=True).encode()).hexdigest()
        path=self.cache/('yahoo_'+digest+'.json')
        ttl=300 if self.interval!='1day' else 21600
        if path.exists() and not refresh and time.time()-path.stat().st_mtime<ttl:
            data=json.loads(path.read_text());frame=pd.read_json(StringIO(data['frame']),orient='split')
            frame.index=pd.to_datetime(frame.index,unit='ms')
            frame=frame.astype(float)
            currency=data.get('currency')
            stamp=data['retrieved_utc'];cached=True
        else:
            try:
                obj=yf.Ticker(symbol)
                # End is exclusive in Yahoo. The caller passes the following day for date-only end dates.
                frame=obj.history(start=pd.Timestamp(start).to_pydatetime(),end=pd.Timestamp(end).to_pydatetime(),
                    interval=INTERVALS[self.interval],auto_adjust=False,back_adjust=False,repair=False,
                    actions=False,prepost=False,keepna=True,timeout=20)
                if frame is None or frame.empty:
                    raise ValueError(f'No free price history for {symbol}. Check the symbol, dates and connection; Yahoo may be limiting requests.')
                currency=obj.history_metadata.get('currency')
                if not {'Close','Adj Close'}<=set(frame):
                    raise ValueError(f'{symbol}: Yahoo did not supply both Close and Adj Close. No adjusted prices were invented.')
                frame=frame[['Close','Adj Close']].rename(columns={'Close':'close','Adj Close':'adjusted'}).astype(float)
                index=pd.DatetimeIndex(frame.index)
                if self.interval=='1day':
                    index=index.tz_localize(None) if index.tz is not None else index
                else:
                    if index.tz is None:raise ValueError(f'{symbol}: intraday timezone is missing.')
                    # Yahoo labels bars at their start; the simulator executes at their close.
                    index=index.tz_convert('UTC').tz_localize(None)+pd.Timedelta(seconds=SECONDS[self.interval])
                frame.index=index
                frame=frame.sort_index()
                if self.interval!='1day':frame=frame[frame.index<=utc_now()]
                if frame.index.has_duplicates:raise ValueError(f'{symbol}: duplicate price timestamps.')
                if len(frame)<4 or not np.isfinite(frame.to_numpy()).all() or (frame<=0).any().any():
                    raise ValueError(f'{symbol}: missing, invalid or insufficient prices. The selected stock was not discarded.')
                stamp=datetime.now(timezone.utc).isoformat();cached=False
                path.write_text(json.dumps(dict(frame=frame.to_json(orient='split'),currency=currency,retrieved_utc=stamp)))
            except ValueError:raise
            except Exception as exc:
                raise ValueError(f'Yahoo Finance could not retrieve {symbol} ({type(exc).__name__}). Check internet access and try again later; no API key is needed.') from None
        if expected_currency and currency!=expected_currency:
            raise ValueError(f'{symbol}: expected currency {expected_currency}, Yahoo reports {currency}. Verify stock metadata.')
        self.audit.append(dict(provider='Yahoo Finance via yfinance',symbol=symbol,interval=self.interval,
            requested_start=str(start),requested_end=str(end),currency=currency,retrieved_utc=stamp,cached=cached,
            data_sha256=sha256(frame.to_csv().encode()).hexdigest()))
        return frame

    def history(self,asset,start,end,refresh=False):
        finish=pd.Timestamp(end)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(end)):
            finish+=pd.Timedelta(days=1)
        result=self._history(yahoo_symbol(asset),start,str(finish),refresh,asset['currency'])
        return result.loc[start:end]

    def fx(self,currency,base,start,end,refresh=False):
        if currency==base:return None
        # Yahoo FX convention: JPYUSD=X quotes USD per one JPY, suitable for conversion.
        asset=dict(ticker=currency+base+'=X',yahoo_symbol=currency+base+'=X',currency=base)
        return self.history(asset,start,end,refresh)['close']

    def quote(self,asset,refresh=False):
        symbol=yahoo_symbol(asset)
        try:
            obj=yf.Ticker(symbol)
            frame=obj.history(period='1d',interval='1m',auto_adjust=False,prepost=False,timeout=15)
            if frame is None or frame.empty:raise ValueError(f'No recent free quote for {symbol}.')
            meta=obj.history_metadata
            price=meta.get('regularMarketPrice');stamp=meta.get('regularMarketTime')
            if price is None or stamp is None:
                price=float(frame.Close.iloc[-1])
                index=pd.Timestamp(frame.index[-1])
                if index.tzinfo is None:raise ValueError('Quote timestamp has no timezone.')
                stamp=(index.tz_convert('UTC')+pd.Timedelta(minutes=1)).timestamp()
            if not np.isfinite(float(price)) or float(price)<=0:raise ValueError('Invalid latest price.')
            def epoch(value,default):
                if value is None:return default
                if isinstance(value,(int,float,np.integer,np.floating)):return float(value)
                timestamp=pd.Timestamp(value)
                if timestamp.tzinfo is None:raise ValueError('Market timestamp has no timezone.')
                return timestamp.timestamp()
            stamp=epoch(stamp,np.nan)
            regular=meta.get('currentTradingPeriod',{}).get('regular',{})
            now=pd.Timestamp.now(tz='UTC').timestamp()
            market_open=bool(epoch(regular.get('start'),float('inf'))<=now<epoch(regular.get('end'),-float('inf')))
            currency=meta.get('currency')
            if currency!=asset['currency']:raise ValueError(f'{symbol}: quote currency mismatch.')
            return dict(payload=dict(close=float(price),timestamp=int(stamp),is_market_open=market_open),
                retrieved_utc=str(utc_now()),status='Latest Yahoo quote; latency not verified',cached=False)
        except ValueError:raise
        except Exception as exc:raise ValueError(f'Free quote unavailable for {symbol} ({type(exc).__name__}). Try again later.') from None
