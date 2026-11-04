"""One continuous dashboard. Run START_APP.bat or python -m streamlit run app.py."""
from dataclasses import asdict
from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
import importlib.metadata
import json
import platform
import zipfile
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from config import ROOT, Settings
from market_data import panel
from free_data import FreeMarketData, validate_range
from portfolio_analysis import workings, frontier, assessment
from portfolio_optimizer import optimize
from backtesting import backtest, FREQUENCIES
from transaction_costs import Costs
from catalog import load_catalog, refresh_catalog, resolve_global
from live_portfolio import tick, due
from bhutan_theme import apply_bhutan_theme, bhutan_banner
apply_bhutan_theme()
bhutan_banner()

st.set_page_config(page_title='Drukyul | Dynamic Portfolio',page_icon='📈',layout='wide',initial_sidebar_state='collapsed')
st.markdown('<style>'+ (ROOT/'styles.css').read_text()+'</style>',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">DRUKYUL · PORTFOLIO LAB</div>
<h1>Your dynamic portfolio. One workspace.</h1><p>Choose stocks → build allocations → follow prices → compare after trading costs.</p></div>''',unsafe_allow_html=True)
s=st.session_state
for k,v in dict(catalog=load_catalog(ROOT),result=None,book=None,live_enabled=False,quotes=None).items():
    if k not in s:s[k]=v


def table(df):
    st.dataframe(df,width='stretch',hide_index=True)


def chart(frame,title,percent=False):
    fig=px.line(frame,title=title,color_discrete_sequence=['#108971','#c29441','#5975b4'])
    fig.update_layout(template='plotly_white',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='white',
        font_color='#223954',legend_title_text='',xaxis_title='',yaxis_title='Return' if percent else 'Value',margin=dict(l=10,r=10,t=50,b=10))
    if percent:fig.update_yaxes(tickformat='.1%')
    st.plotly_chart(fig,width='stretch')


def err(exc):
    st.error(str(exc))
    st.caption('No substitute prices were generated. This free version needs no API key. Check internet access and dates; if Yahoo limits requests, wait and retry or use CSV files. Previous results are shown only when their inputs match.')


# Controls are on this page; no page navigation or sidebar.
mode=st.selectbox('Price source',['Free Yahoo Finance — no API key','Upload your own prices — CSV','Demo — synthetic data'])
is_demo=mode.startswith('Demo');is_csv=mode.startswith('Upload')
source_name='SYNTHETIC DEMO' if is_demo else 'User CSV' if is_csv else 'Yahoo Finance via yfinance'
price_upload=st.file_uploader('Upload prices CSV · date, ticker, close, adjusted, currency',type=['csv']) if is_csv else None
if is_demo:st.warning('DEMO: generated prices for learning. These are not live prices or evidence of investment performance.')
elif is_csv:st.caption('CSV timestamps must represent bar closes; include the pre-start lookback. This mode supports assets in the chosen base currency. No live quotes are available from a CSV.')
else:st.success('Free market data selected · no API key or Twelve Data subscription needed.')
st.caption('Latest Yahoo prices may be delayed or unavailable. Minute data is recent-history only; daily data is better for a long-term comparison. This app does not guarantee an exchange-grade live feed.')

st.subheader('1 · Pick your dynamic portfolio')
st.caption('Open the arrow to browse company names and tickers. The bundled US directory includes thousands of listed securities. Refresh it or add global stocks below.')
with st.expander('Browse more stocks · free directory and global search'):
    st.caption(f"{len(s.catalog):,} names available in the dropdown. US directory snapshot: "+json.loads((ROOT/'catalog_metadata.json').read_text()).get('retrieved_utc','unknown'))
    if st.button('Refresh free US stock directory'):
        try:
            s.catalog=refresh_catalog(ROOT)
            st.success(f'{len(s.catalog):,} securities available in the dropdown.')
        except Exception as exc:st.error(f'Directory refresh failed ({type(exc).__name__}). The bundled list remains available.')
    query=st.text_input('Optional global search · company name or Yahoo ticker')
    if st.button('Search global stocks'):
        try:
            import yfinance as yf
            candidates=yf.Search(query,news_count=0,lists_count=0,max_results=30).quotes
            s.global_matches=[x for x in candidates if x.get('quoteType') in ('EQUITY','ETF')]
        except Exception as exc:st.error(f'Free search is unavailable ({type(exc).__name__}). Retry later.')
    if s.get('global_matches'):
        matches={x['symbol']:x for x in s.global_matches}
        symbol=st.selectbox('Global search results',list(matches),format_func=lambda k:f"{matches[k].get('longname') or matches[k].get('shortname') or k} — {k} — {matches[k].get('exchDisp','')}")
        if st.button('Add global stock to dropdown'):
            try:
                asset=resolve_global(symbol)
                s.catalog=pd.concat([s.catalog,pd.DataFrame([asset])]).drop_duplicates('id',keep='last')
                st.success('Added to the stock dropdown. Select it below.')
            except Exception as exc:st.error(str(exc))
lookup=s.catalog.set_index('id').to_dict('index')
stock_ids=st.multiselect('Stocks · company name — ticker — exchange',list(lookup),
    default=['AAPL|NASDAQ','NVDA|NASDAQ','JPM|NYSE','AMZN|NASDAQ','AVGO|NASDAQ','WMT|NASDAQ','GLD|NYSE Arca'],
    format_func=lambda k:f"{lookup[k]['name']} — {lookup[k]['ticker']} — {lookup[k]['exchange']}",key='stock_ids')
assets=[{key:('' if isinstance(value,float) and np.isnan(value) else value) for key,value in dict(id=k,**lookup[k]).items()} for k in stock_ids]
st.caption(f'{len(assets)} selected · Removing a stock and adding another updates the next live paper rebalance. The static paper portfolio keeps its original holdings. A historical run always starts a new experiment.')

st.subheader('2 · Set the dynamic strategy')
a,b,c,d=st.columns(4)
capital=a.number_input('Starting capital',min_value=100.,value=110000.,step=1000.)
base=b.text_input('Base currency','USD').strip().upper()
frequency=c.selectbox('Dynamic rebalance frequency',list(FREQUENCIES),index=6)
interval_map={'Every minute':'1min','Every 5 minutes':'5min','Every 15 minutes':'15min','Hourly':'1h'}
interval=interval_map.get(frequency,'1day')
d.metric('Price bars',interval)
st.caption('Minute and hourly strategies use matching intraday bars, never daily prices resampled into minutes. Signals use only preceding completed bars. Market closures and API latency affect when updates occur.')
a,b,c=st.columns(3)
lookback=int(a.number_input('Lookback · completed return bars',min_value=3,value=252))
gamma=b.number_input('Risk aversion · higher means more cautious',min_value=.01,value=2.0)
cap=c.slider('Maximum allocation per stock',.01,1.,.25,.01)
# Intraday and daily date defaults need different horizons; reset only when bar size changes.
today=date.today()
if s.get('last_interval')!=interval:
    s.comparison_start=today-timedelta(days=3 if interval=='1min' else 14 if interval!='1day' else 730)
    s.comparison_end=today-timedelta(days=1)
    s.last_interval=interval
with st.expander('Backtest dates and risk settings',expanded=True):
    a,b,c,d=st.columns(4)
    today=date.today()
    start=a.date_input('Comparison start',key='comparison_start')
    end=b.date_input('Comparison end',key='comparison_end')
    rf=c.number_input('Annual risk-free rate (%)',min_value=-99.,value=3.)/100
    mar=d.number_input('Annual minimum acceptable return (%)',min_value=-99.,value=0.)/100
settings=Settings(capital,lookback,gamma,cap,frequency,rf,mar)

st.subheader('3 · Enter trading costs')
with st.expander('Broker charges · applied to both portfolios',expanded=True):
    cost_mode=st.selectbox('Fee setup',['Editable broker scenario','Dated market-specific fee JSON'])
    st.caption('Enter your actual broker terms for a closer estimate. Defaults are an illustrative scenario, not verified tariffs. Taxes, minima, exchange levies and historical changes require the dated JSON option. Spread and slippage remain estimates.')
    a,b,c,d=st.columns(4)
    commission=a.number_input('Commission per share · local currency',min_value=0.,value=.005,format='%.5f')
    minimum=b.number_input('Minimum commission per trade · local',min_value=0.,value=1.)
    sell_bps=c.number_input('Sell tax / regulatory charge (bps)',min_value=0.,value=0.,format='%.4f')
    spread=d.number_input('Spread + slippage per trade (bps)',min_value=0.,value=5.)
    a,b=st.columns(2)
    fx_bps=a.number_input('FX conversion per foreign trade (bps)',min_value=0.,value=2.)
    snapshot=b.checkbox('Allow dated fee snapshots outside their dates',False,help='An explicit modelling assumption, not historically exact fees.')
    fees_text=st.text_area('Dated fees JSON',(ROOT/'fees.json').read_text(),height=160) if cost_mode=='Dated market-specific fee JSON' else (ROOT/'fees.json').read_text()
    if is_demo:st.caption('Demo uses these same costs; they are not silently removed.')


def cost_profiles(current_assets):
    if cost_mode=='Dated market-specific fee JSON':
        profiles=json.loads(fees_text)
        if not isinstance(profiles,list) or not profiles:raise ValueError('Fee JSON must be a nonempty list.')
        return profiles
    groups={(a['route'],a['currency'],a['asset_type']) for a in current_assets}
    return [dict(route=r,currency=cur,asset_types=[typ],name='User-entered broker scenario',
        **{'from':'1900-01-01','to':'2100-12-31'},rules=[
        dict(component='commission',share_rate=commission,minimum=minimum),
        dict(component='regulatory',value_rate=sell_bps/10000,side='SELL')],
        notes='Constant scenario; not verified market tariffs. Values apply in each local currency.') for r,cur,typ in groups]


def make_client():return FreeMarketData(interval=interval)


def demo_history(current_assets,fetch_start,fetch_end):
    # Stable per-symbol synthetic prices; no network and never a real-data fallback.
    dates=pd.bdate_range('2010-01-01',pd.Timestamp(fetch_end).normalize()) if interval=='1day' else pd.date_range(pd.Timestamp(fetch_start).normalize(),pd.Timestamp(fetch_end).normalize()+pd.Timedelta(hours=23),freq={'1min':'min','5min':'5min','15min':'15min','1h':'h'}[interval])
    if interval!='1day':dates=dates[(dates.dayofweek<5)&(dates.hour>=14)&(dates.hour<20)]
    if len(dates)>150000:raise ValueError('Demo range too large; shorten intraday dates.')
    result={}
    for asset in current_assets:
        seed=int(sha256(asset['id'].encode()).hexdigest()[:8],16)
        rng=np.random.default_rng(seed)
        scale=.012 if interval=='1day' else .001
        x=100*np.exp(np.cumsum(rng.normal(scale/40,scale,len(dates))))
        result[asset['id']]=pd.DataFrame(dict(close=x,adjusted=x),index=dates).loc[fetch_start:fetch_end]
    return result


def fetch_history(current_assets,begin,finish,refresh=False):
    client=make_client()
    if is_demo:
        if any(a['currency']!=base for a in current_assets):raise ValueError('Demo supports only same-currency stocks.')
        histories=demo_history(current_assets,begin,finish)
        rates={base:None}
    elif is_csv:
        if price_upload is None:raise ValueError('Upload your prices CSV first.')
        frame=pd.read_csv(BytesIO(price_upload.getvalue()))
        required={'date','ticker','close','adjusted','currency'}
        if not required<=set(frame):raise ValueError('CSV needs date, ticker, close, adjusted and currency columns.')
        histories={}
        for asset in current_assets:
            rows=frame[frame.ticker.astype(str).isin([asset['ticker'],asset['id'],asset.get('yahoo_symbol','')])].copy()
            if rows.empty or not rows.currency.eq(asset['currency']).all():raise ValueError(f"CSV has missing prices or wrong currency for {asset['ticker']}.")
            rows['date']=pd.to_datetime(rows['date'],utc=True).dt.tz_localize(None)
            histories[asset['id']]=rows.set_index('date')[['close','adjusted']].astype(float).sort_index().loc[begin:finish]
        if any(a['currency']!=base for a in current_assets):raise ValueError('CSV mode currently supports same-currency assets only.')
        rates={base:None}
    else:
        validate_range(begin,str(pd.Timestamp(finish)+pd.Timedelta(days=1) if len(str(finish))==10 else finish),interval)
        histories={a['id']:client.history(a,begin,finish,refresh) for a in current_assets}
        rates={cur:client.fx(cur,base,begin,finish,refresh) for cur in sorted({a['currency'] for a in current_assets})}
    return (*panel(histories,rates,current_assets,settings.max_gap_days),client.audit)


def buffer_days():
    return lookback*4+60 if interval=='1day' else max(2,int(np.ceil(lookback*{'1min':1,'5min':5,'15min':15,'1h':60}[interval]/390*2))+1)

signature=sha256(json.dumps([assets,asdict(settings),str(start),str(end),base,source_name,sha256(price_upload.getvalue()).hexdigest() if price_upload else None,interval,cost_mode,
    commission,minimum,sell_bps,spread,fx_bps,snapshot,fees_text],sort_keys=True,default=str).encode()).hexdigest()


def export_run(result,manifest,prices,raw,fx,profiles):
    output=BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for label in ('Dynamic','Static'):
            for field in ('nav','gross_nav','trades','holdings','rebalances'):
                z.writestr(f'{label}_{field}.csv',result[label][field].to_csv())
        z.writestr('decisions.csv',result['decisions'].to_csv(index=False))
        z.writestr('metrics.csv',pd.DataFrame({k:result[k]['metrics'] for k in ('Dynamic','Static')}).to_csv())
        for name,frame in [('adjusted',prices),('raw',raw),('fx',fx)]:z.writestr(name+'.csv',frame.to_csv())
        z.writestr('manifest.json',json.dumps(manifest,indent=2,default=str))
        z.writestr('fees.json',json.dumps(profiles,indent=2))
        latest=result['decisions'].date.max();pos=prices.index.get_loc(latest)
        calc=workings(prices.iloc[pos-lookback-1:pos],gamma,cap,rf)
        z.writestr('Markowitz_latest_asset_workings.csv',calc['assets'].to_csv(index=False))
        z.writestr('Markowitz_latest_covariance.csv',calc['covariance'].to_csv())
        z.writestr('Markowitz_latest_correlation.csv',calc['correlation'].to_csv())
        z.writestr('calculation_notes.txt','All Markowitz estimates use bars strictly before the selected rebalance. Mu = mean interval returns x empirical annualizer; Sigma = sample interval covariance x annualizer; expected return = w.T mu; variance = w.T Sigma w; volatility = sqrt(variance). VaR/ES are historical losses per observed interval, including establishment costs, not annual forecasts. Alpha is an annualized excess-return regression intercept vs static, not a claim of skill. See README for assumptions.')
    return output.getvalue()

if st.button('Build dynamic portfolio & compare',type='primary',width='stretch'):
    try:
        if not assets:raise ValueError('Choose stocks from the dropdown above.')
        symbols=[a.get('yahoo_symbol',a['ticker']) for a in assets]
        if len(symbols)!=len(set(symbols)):raise ValueError('The same Yahoo stock was selected more than once through different directory entries. Keep one entry per stock.')
        if start>=end:raise ValueError('Comparison start must be earlier than end.')
        if len(base)!=3 or not base.isalpha():raise ValueError('Enter a three-letter base currency such as USD.')
        if len(assets)*cap<1-1e-10:raise ValueError('Allocation cap is too low for this number of stocks. Increase the cap or add stocks.')
        with st.spinner('Loading completed price bars and calculating portfolios…'):
            fetch_start=str(pd.Timestamp(start)-pd.Timedelta(days=buffer_days()))
            prices,raw,fx,quality,audit=fetch_history(assets,fetch_start,str(end))
            profiles=cost_profiles(assets)
            result=backtest(prices,raw,fx,assets,str(start),str(end),settings,Costs(profiles,snapshot,spread,fx_bps),base)
            manifest=dict(signature=signature,source=source_name,
                settings=asdict(settings),assets=assets,base=base,interval=interval,start=str(start),end=str(end),
                fees=cost_mode,spread_bps=spread,fx_bps=fx_bps,snapshot=snapshot,calendar=quality,api_audit=audit,
                python=platform.python_version(),versions={k:importlib.metadata.version(k) for k in ['numpy','pandas','scipy','streamlit','yfinance']},
                data_sha256=sha256(pd.concat({'adjusted':prices,'raw':raw,'fx':fx},axis=1).to_csv().encode()).hexdigest(),
                source_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')})
            package=export_run(result,manifest,prices,raw,fx,profiles)
            s.result=dict(signature=signature,result=result,package=package,manifest=manifest,prices=prices)
    except (ValueError,KeyError,TypeError,OverflowError) as exc:err(exc)

active=s.result and s.result['signature']==signature
if s.result and not active:st.info('Your inputs changed. Build again to update the historical comparison. Live paper holdings continue separately below.')
if active:
    result=s.result['result']; dynamic=result['Dynamic']; static=result['Static']; m=dynamic['metrics']
    st.subheader('Your dynamic portfolio · after costs')
    a,b,c,d=st.columns(4)
    a.metric('Dynamic value',f'{base} {m["final"]:,.2f}')
    b.metric('Dynamic net return',f'{m["total_return"]:.2%}')
    c.metric('Difference vs static',f'{100*m["benchmark_relative_return"]:+.2f} percentage points')
    d.metric('Dynamic trading costs',f'{base} {m["total_costs"]:,.2f}')
    if m['benchmark_relative_return']>0:st.success('Dynamic outperformed static after the configured costs in this experiment.')
    else:st.info('Dynamic did not outperform static after the configured costs in this experiment. More frequent rebalancing can increase costs and reduce returns.')
    nav=pd.DataFrame({k:result[k]['nav'] for k in ('Dynamic','Static')})
    chart(nav,'Dynamic first · portfolio value after trading costs')
    a,b=st.columns([1,1])
    with st.expander('Diagnostic · average dynamic weights vs static', expanded=True):
        hold = dynamic['holdings'].drop(columns='cash')
        wts = hold.div(hold.sum(axis=1), axis=0)
        diag = pd.DataFrame({
            'Stock': [lookup[k]['ticker'] for k in wts.columns],
            'Dynamic avg weight': wts.mean().values,
            'Static weight (equal)': 1 / len(wts.columns),
        })
        diag['Difference'] = diag['Dynamic avg weight'] - diag['Static weight (equal)']
        diag = diag.sort_values('Dynamic avg weight', ascending=False)
        for col in ['Dynamic avg weight', 'Static weight (equal)', 'Difference']:
            diag[col] = diag[col].map(lambda x: f'{x:.2%}')
        table(diag)
    with a:
        latest=result['decisions']; selected_date=st.selectbox('Inspect dynamic allocation at rebalance',sorted(latest.date.unique()),index=len(latest.date.unique())-1)
        alloc=latest[latest.date==selected_date].copy();alloc['stock']=alloc.id.map(lambda k:lookup[k]['ticker'])
        fig=px.bar(alloc,x='stock',y='target_weight',color_discrete_sequence=['#108971'],template='plotly_white',title='Markowitz target allocation')
        fig.update_yaxes(tickformat='.0%');st.plotly_chart(fig,width='stretch')
    with b:
        held=dynamic['holdings'].iloc[-1];values=held.drop('cash')
        table(pd.DataFrame({'Stock':values.index.map(lambda k:lookup[k]['name']+' — '+lookup[k]['ticker']),
            'Current value':[f'{base} {x:,.2f}' for x in values.values],'Current weight':[f'{x:.2%}' for x in values.values/held.sum()]}))
        st.caption(f'Residual cash: {base} {held["cash"]:,.2f}. Target allocation and current weight can differ as prices move.')
    st.subheader('Dynamic vs static · returns, risk and costs')
    percent_fields={'total_return','gross_return','cagr','volatility','downside_deviation','max_drawdown','turnover','var95','var99','es95','es99','win_rate','best_interval','worst_interval','tracking_error','cost_drag','alpha_to_static'}
    labels={'initial':'Initial capital','final':'Final value after costs','total_return':'Net total return','gross_return':'Gross total return (zero-cost counterfactual)',
        'cagr':'Annualized growth (CAGR)','volatility':'Annualized volatility','downside_deviation':'Annualized downside deviation',
        'sharpe':'Sharpe ratio','sortino':'Sortino ratio','calmar':'Calmar ratio','omega':'Omega ratio',
        'max_drawdown':'Maximum drawdown','var95':'Historical loss VaR 95% · per interval','es95':'Historical expected shortfall 95% · per interval',
        'var99':'Historical loss VaR 99% · per interval','es99':'Historical expected shortfall 99% · per interval',
        'win_rate':'Positive-return intervals','best_interval':'Best observed interval','worst_interval':'Worst observed interval',
        'total_costs':f'Total trading costs ({base})','cost_drag':'Cost drag · gross minus net return','trades':'Executed trades','turnover':'Turnover',
        'tracking_error':'Annualized tracking error vs static','information_ratio':'Information ratio vs static','alpha_to_static':'Annualized regression alpha vs static','beta_to_static':'Beta vs static',
        'correlation_to_static':'Correlation vs static'}
    def formatted(field,value):
        if not np.isfinite(value):return 'Undefined'
        if field in percent_fields:return f'{value:.2%}'
        if field in ('initial','final','total_costs'):return f'{base} {value:,.2f}'
        if field=='trades':return f'{int(value):,}'
        return f'{value:.4f}'
    comparison=pd.DataFrame({'Calculation':list(labels.values()),**{k:[formatted(field,result[k]['metrics'][field]) for field in labels] for k in ('Dynamic','Static')}})
    table(comparison)
    st.caption('Static buys equal weights once and pays initial costs, then holds. Both use the same starting capital, original asset universe, prices and cost rules. No final liquidation is assumed. VaR/expected shortfall describe the observed bar interval, include initial fees, and are not annual forecasts; negative loss estimates indicate gains. Short samples make tail estimates and annualized ratios unreliable.')
    st.subheader('Which strategy does this test support?')
    goal=st.selectbox('Your comparison priority',['Balance return and risk','Highest net return','Lowest volatility'])
    decision=assessment(result,goal,is_demo)
    st.info(f"{decision['status']}. Historical candidate under your selected rule: {decision['candidate']}.")
    st.write(decision['reason']);st.write(decision['caution'])
    st.caption('For balance, the ranking uses Sharpe; for growth, net return; for lower risk, volatility. A losing candidate is not endorsed. The choice does not account for your personal loss capacity, liquidity needs or investment horizon.')
    st.download_button('Download comparison table CSV',comparison.to_csv(index=False),'Drukyul_risk_comparison.csv')
    st.subheader('Markowitz · weights, risk and calculations')
    pos=s.result['prices'].index.get_loc(pd.Timestamp(selected_date))
    training=s.result['prices'].iloc[pos-lookback-1:pos]
    calc=workings(training,gamma,cap,rf);model=calc['model']
    a,b,c,d=st.columns(4)
    a.metric('Estimated annual return',f"{model['expected_return']:.2%}")
    b.metric('Estimated annual volatility',f"{model['risk']:.2%}")
    c.metric('Estimated annual variance',f"{calc['variance']:.6f}")
    d.metric('Estimated Sharpe',f"{calc['estimated_sharpe']:.3f}")
    st.caption(f"Ex-ante estimates for {pd.Timestamp(selected_date)}. Uses {len(training)-1} returns from {training.index[0]} through {training.index[-1]}, before the rebalance. These estimates are not the realized returns shown above.")
    detail=calc['assets'].copy();detail['Stock']=detail.id.map(lambda k:lookup[k]['name']+' — '+lookup[k]['ticker'])
    for column in ['weight','annual_mean','annual_volatility','weighted_return','volatility_contribution','risk_share']:
        detail[column]=detail[column].map(lambda x:f'{x:.2%}' if np.isfinite(x) else 'Undefined')
    table(detail[['Stock','weight','annual_mean','annual_volatility','weighted_return','variance_contribution','volatility_contribution','risk_share']])
    st.caption('Risk share = contribution to portfolio variance divided by total variance. Volatility contributions sum to portfolio volatility. A negative contribution can occur when an asset hedges other holdings.')
    with st.expander('Efficient frontier · compare feasible return and risk',expanded=True):
        try:
            frontier_frame=frontier(training,gamma,cap)
            fig=px.line(frontier_frame,x='risk',y='expected_return',template='plotly_white',title='Estimated efficient frontier · before costs')
            fig.add_scatter(x=[model['risk']],y=[model['expected_return']],mode='markers',marker=dict(size=13,color='#148970'),name='Dynamic target')
            equal=np.full(len(model['mu']),1/len(model['mu']))
            fig.add_scatter(x=[np.sqrt(equal@model['cov']@equal)],y=[equal@model['mu']],mode='markers',marker=dict(size=11,color='#c29441'),name='Equal-weight initial target')
            fig.update_xaxes(title='Estimated annual volatility',tickformat='.1%');fig.update_yaxes(title='Estimated annual return',tickformat='.1%')
            st.plotly_chart(fig,width='stretch')
            st.caption('Constrained minimum-variance portfolios at feasible expected-return targets; only the efficient branch is shown. The markers are initial targets estimated from the same past window. The static portfolio subsequently drifts. This frontier excludes transaction costs and is not a forecast.')
        except ValueError as exc:st.warning(str(exc))
    with st.expander('Covariance, correlation and formulas'):
        rename={k:lookup[k]['ticker'] for k in stock_ids}
        st.write('Annualized sample covariance matrix')
        st.dataframe(calc['covariance'].rename(index=rename,columns=rename),width='stretch')
        st.write('Correlation matrix')
        st.dataframe(calc['correlation'].rename(index=rename,columns=rename),width='stretch')
        st.latex(r"\mu=\bar r A,\quad \Sigma=\operatorname{Cov}(r)A")
        st.latex(r"E[R_p]=w^T\mu,\quad \sigma_p^2=w^T\Sigma w,\quad \sigma_p=\sqrt{w^T\Sigma w}")
        st.latex(r"\max_w \; w^T\mu-\frac{\gamma}{2}w^T\Sigma w\quad \text{subject to }\sum_i w_i=1,\;0\leq w_i\leq u")
        st.latex(r"\operatorname{Sharpe}=\frac{E[R_p]-r_f}{\sigma_p},\quad RC_i=\frac{w_i(\Sigma w)_i}{\sigma_p}")
        st.write(f"A is the number of observed returns divided by elapsed calendar years in the estimation window: {model['annualizer']:,.2f}. Risk aversion γ = {gamma}; weight cap u = {cap:.0%}; weights sum = {model['weights'].sum():.10f}; solver gap = {model['optimality_gap']:.2g}.")
        st.caption('Realized Sharpe/Sortino use net NAV interval returns and interval-specific risk-free/MAR hurdles. CAGR uses elapsed calendar time. Drawdown = NAV / running peak − 1. Historical VaR = empirical quantile of losses; expected shortfall = mean loss at or beyond that quantile. Alpha, beta and tracking error use static as the benchmark, not a market index. Alpha is the annualized excess-return regression intercept and does not establish skill.')
    chart(nav/nav.cummax()-1,'Risk · observed drawdowns',True)
    with st.expander('Rebalancing, trade history and cost breakdown',expanded=True):
        strategy=st.selectbox('Inspect trade ledger',['Dynamic','Static'])
        table(result[strategy]['trades'])
        table(result[strategy]['rebalances'])
    st.download_button('Download this experiment · prices, allocations, trades and audit ZIP',s.result['package'],'Drukyul_experiment.zip')

st.subheader('4 · Follow prices & run your forward dynamic portfolio')
st.caption('Live paper mode keeps running only while this dashboard is open. It simulates trades; it does not send broker orders. The static portfolio is frozen when the paper session starts. USD stocks are currently supported in forward mode.')
a,b,c=st.columns(3)
auto=a.checkbox('Automatically refresh prices',False)
refresh_seconds=b.selectbox('Refresh interval (seconds)',[60,120,300],index=0)
max_age=c.number_input('Maximum quote age for paper trades (minutes)',min_value=1,value=15)
# Fragment calls only the live section; historic backtests never auto-rerun.
@st.fragment(run_every=refresh_seconds if auto else None)
def live_section():
    a,b,c=st.columns(3)
    refresh_clicked=a.button('Refresh prices now')
    start_clicked=b.button('Start / rebalance paper portfolio',type='primary')
    if c.button('End paper session'):
        s.book=None;s.live_enabled=False;st.success('Paper session ended. Download its audit before ending if you need it.');st.rerun()
    if start_clicked:s.live_enabled=True
    # One batch per interval, not every settings rerun.
    now=pd.Timestamp.now(tz='UTC').tz_localize(None)
    elapsed=(now-pd.Timestamp(s.get('quote_refresh','1970-01-01'))).total_seconds()
    do_refresh=refresh_clicked or start_clicked or (auto and elapsed>=refresh_seconds)
    if do_refresh:
        try:
            if is_csv:raise ValueError('CSV mode has no live quotes. Use historical comparison above.')
            if not assets:raise ValueError('Choose stocks above first.')
            if s.live_enabled and base!='USD':raise ValueError('Use USD for forward paper mode; historical mode supports other base currencies.')
            if s.book and s.book.get('source') != source_name:
                raise ValueError('End the paper session before changing between demo and market data.')
            held_assets=list(s.book['assets'].values()) if s.book else []
            union={a['id']:a for a in [*held_assets,*assets]}
            quotes={};rows=[];fresh=True
            client=make_client()
            for k,asset in union.items():
                if is_demo:
                    # Demonstration quote path is independent of historical performance.
                    rng=np.random.default_rng(int(sha256((k+str(int(now.timestamp())//60)).encode()).hexdigest()[:8],16))
                    price=float(100+rng.normal(0,.25));stamp=now;open_market=True;status='SYNTHETIC DEMO'
                else:
                    data=client.quote(asset,True);payload=data['payload']
                    price=float(payload.get('close',payload.get('price',np.nan)))
                    stamp=pd.to_datetime(payload.get('timestamp'),unit='s',utc=True,errors='coerce')
                    if pd.isna(stamp):stamp=pd.to_datetime(payload.get('datetime'),utc=True,errors='coerce')
                    if pd.notna(stamp):stamp=stamp.tz_localize(None)
                    open_market=payload.get('is_market_open') is True
                    status='Market open' if open_market else 'Market closed or status unconfirmed'
                age=(now-stamp).total_seconds()/60 if pd.notna(stamp) else np.inf
                if not np.isfinite(price) or price<=0:raise ValueError(f'Invalid quote for {asset["ticker"]}.')
                fresh=fresh and 0<=age<=max_age and open_market
                quotes[k]=price
                rows.append(dict(Stock=asset['name'],Ticker=asset['ticker'],Currency=asset['currency'],Price=price,
                    Quote_UTC=str(stamp),Age_minutes=round(age,2),Status=status))
            s.quotes=rows;s.quote_refresh=str(now)
            if s.live_enabled:
                if not fresh:raise ValueError('Paper trade paused: market closed, timestamp missing, or a quote is stale. Quotes are displayed; no trade was executed.')
                profiles=cost_profiles(list(union.values()))
                should_trade=start_clicked or not s.book or due(s.book['last_rebalance'],now,frequency)
                weights={}
                if should_trade:
                    begin=str(now-pd.Timedelta(days=buffer_days()))
                    with st.spinner('Estimating live targets from completed historical bars…'):
                        prices,*_=fetch_history(assets,begin,str(now),True)
                        # Daily bars dated today can still be forming; exclude them conservatively.
                        if interval=='1day':prices=prices[prices.index.normalize()<now.normalize()]
                        history=prices.iloc[-lookback-1:]
                        if len(history)<lookback+1:raise ValueError('Insufficient completed bars for the live lookback.')
                        weights=optimize(history,gamma,cap)['weights'].to_dict()
                fill_time=pd.Timestamp.now(tz='UTC').tz_localize(None)
                if not is_demo and any((fill_time-pd.Timestamp(row['Quote_UTC'])).total_seconds()>max_age*60 for row in rows):
                    raise ValueError('Quote became stale while loading historical bars. Refresh again or reduce the lookback/API load.')
                s.book=tick(s.book,assets,quotes,weights,Costs(profiles,snapshot,spread,fx_bps),capital,fill_time,frequency,start_clicked)
                s.book['source']=source_name
                s.book.setdefault('update_audit',[]).append(dict(time=str(fill_time),selected_ids=stock_ids,
                    settings=asdict(settings),profiles=profiles,spread_bps=spread,fx_bps=fx_bps,quotes=rows,
                    target_weights=weights,rebalanced=should_trade))
                st.success('Paper portfolio updated. Static holdings remain frozen.')
        except (ValueError,KeyError,TypeError,OverflowError) as exc:err(exc)
    if s.quotes:
        table(pd.DataFrame(s.quotes));st.caption('Quote timestamps are UTC. Refresh is polling, not a streaming exchange feed. A refreshed request can still return a delayed or last-market-close price.')
    if s.book:
        book=s.book;nav=pd.DataFrame(book['nav']).set_index('date');latest=nav.iloc[-1]
        a,b,c=st.columns(3);a.metric('Forward dynamic · USD',f'{latest.Dynamic:,.2f}');b.metric('Frozen static · USD',f'{latest.Static:,.2f}');c.metric('Paper session started (UTC)',book['started'][:16])
        chart(nav,'Forward comparison · quote-based paper fills')
        table(pd.DataFrame([dict(Stock=book['assets'][k]['name'],Ticker=book['assets'][k]['ticker'],Shares=v,
            Static_shares=book['static'].get(k,0)) for k,v in book['dynamic'].items()]))
        if book['ledger']:table(pd.DataFrame(book['ledger']))
        st.download_button('Download forward paper session JSON',json.dumps(book,indent=2,default=str),'Drukyul_paper_session.json')
        st.caption('Fractional quote-based fills, estimated slippage and configured fees. No order book, actual execution, dividends, settlement or live brokerage connection. Session state resets if the app restarts. Changing settings affects future decisions only; prior trades stay recorded.')
live_section()

with st.expander('Market data & method · plain-English notes'):
    st.markdown('''**Dynamic:** long-only, fully invested Markowitz targets using a rolling historical mean and sample covariance. Allocation can reach zero, so holdings change within the selected universe. You can also replace stocks during the forward paper session; removed holdings are sold at the next rebalance. More frequent trades do not guarantee higher returns.

**Static:** equal-weight initial purchase, followed by buy-and-hold. It pays initial purchase costs and holds for the whole comparison. Its shares are not reset when you edit the dynamic universe in forward mode.

**Historical data:** actual shared equity and FX timestamps; no filled gaps or fabricated prices. Intraday timestamps are requested in UTC; cross-exchange daily closes are not simultaneous. Adjusted prices model synthetic total-return sleeves with implicit dividend reinvestment; raw closes calculate fractional share-equivalent trading costs. Signals end before each rebalance bar. Trades use that bar's close; this is a research execution assumption.

**Costs:** commissions, configured taxes/regulatory charges, estimated spread/slippage and FX conversions reduce NAV exactly once. Editable defaults are a constant scenario. Use dated fee JSON and your broker's terms for market-specific costs. Fractional shares, immediate settlement, zero cash interest and no terminal liquidation are assumed. Lot sizes, market impact, investor eligibility and withholding tax are excluded.

**Comparison:** dynamic outperformance is an observed result, never a promised outcome. Both strategies can lose. No automatic tuning against the displayed test period is performed. Present-day stock selection can introduce survivorship bias. Intraday CAGR and risk ratios can be unstable over short samples. CAGR that exceeds numeric range is shown as NaN.

**Free prices:** Yahoo Finance via yfinance needs no API key. It is an unofficial client intended for research/personal use; check Yahoo terms. Quotes may be delayed and requests can fail or be rate limited. The app polls while open. One-minute requests including lookback are restricted to recent days; other intraday requests are limited to the recent 60 days in this app. CSV is an offline alternative. Demo data are synthetic and labelled throughout. Yahoo Close may be split-adjusted, so per-share historical fees use synthetic share equivalents, not a reconstructed broker share register.

**Local launch:** The launcher window open and visit http://localhost:8501 on the same computer. An external IP address is not the local app address.''')
    if active:st.json(s.result['manifest'])
