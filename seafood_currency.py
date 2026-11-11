"""Official ECB EUR-cross exchange rates, converted to USD per NOK.

ECB EXR D.USD+NOK.EUR.SP00.A quotes units of currency per EUR.
Daily USD/NOK = USD/EUR divided by NOK/EUR. SSB weekly NOK/kg is
converted using the arithmetic mean of the *daily matching* USD/NOK rates.
The displayed price is an ECB-reference-rate conversion, not an invoice price.
"""
from __future__ import annotations
import csv
import io
import math
from datetime import date, timedelta
import requests

ECB_API='https://data-api.ecb.europa.eu/service/data/EXR/D.USD+NOK.EUR.SP00.A'
ECB_PAGE='https://data.ecb.europa.eu/data/datasets/EXR'

def parse_ecb_usd_per_nok(csv_text):
    daily={}
    for row in csv.DictReader(io.StringIO(csv_text.lstrip('\ufeff'))):
        cur=str(row.get('CURRENCY','')).strip().upper()
        if cur not in ('USD','NOK'):continue
        if str(row.get('CURRENCY_DENOM','EUR')).upper()!='EUR':continue
        try:
            d=date.fromisoformat(row['TIME_PERIOD'])
            x=float(row['OBS_VALUE'])
            if not math.isfinite(x) or x<=0:continue
        except (KeyError,ValueError,TypeError):continue
        daily.setdefault(d,{})[cur]=x
    observations={d:v['USD']/v['NOK'] for d,v in daily.items()
                  if set(v)=={'USD','NOK'}}
    # Require matching rate dates, not separately averaged mismatched samples.
    per_week={}
    for d,v in observations.items():
        y,w,_=d.isocalendar()
        per_week.setdefault((y,w),[]).append(v)
    return {k:sum(v)/len(v) for k,v in per_week.items() if len(v)>=2}

def fetch_ecb_usd_per_nok(today):
    start=today-timedelta(days=735)
    try:
        response=requests.get(ECB_API,params={
            'format':'csvdata','startPeriod':start.isoformat(),
            'endPeriod':today.isoformat()},timeout=(10,35),
            headers={'Accept':'text/csv','User-Agent':'SeafoodInsightLab/1.0'})
        response.raise_for_status()
        rates=parse_ecb_usd_per_nok(response.text)
        if not rates:raise ValueError('ECB exchange series missing matching trading days')
        return rates,None
    except (requests.RequestException,ValueError,OverflowError) as exc:
        return {},'ECB 달러 환산: '+type(exc).__name__
