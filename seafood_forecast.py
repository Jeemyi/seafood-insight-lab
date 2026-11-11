"""Conservative optional numeric forecast for continuous official monthly series.

No numeric prediction is published unless 48+ prior monthly observations,
rolling-origin backtests, and comparable units are available. This module is
not run on isolated latest-month, YoY, or weekly snapshot figures.
"""
from __future__ import annotations
from datetime import date
import math
import statistics


def _next_month(month):
    y,m=map(int,month.split('-'))
    return f'{y+1:04d}-01' if m==12 else f'{y:04d}-{m+1:02d}'


def _predict(history):
    if len(history)<36:return None
    # Same calendar month for the next observation, using three prior years.
    seasonal=.80*history[-12]+.15*history[-24]+.05*history[-36]
    # A small, bounded level adjustment guards against extreme recent swings.
    latest=statistics.mean(history[-3:])
    last_year=statistics.mean(history[-15:-12])
    adj=max(.80,min(1.20,latest/last_year)) if last_year>0 else 1
    return seasonal*(.05+.95*adj)


def backtested_monthly_forecast(rows, metric='가격', unit='원/kg'):
    """Return a forecast only if it beats *both* simple naive baselines.

    rows: [(YYYY-MM, observation), ...], ordered or unordered, same item,
    specification, reporting stage, currency, and unit throughout.
    """
    try:
        entries=sorted((str(k),float(v)) for k,v in rows)
        if len(entries)<48 or len({k for k,_ in entries})!=len(entries):return None
        if any(not math.isfinite(v) or v<=0 for _,v in entries):return None
        for (a,_),(b,_) in zip(entries,entries[1:]):
            if _next_month(a)!=b:return None
        values=[v for _,v in entries]
        points=[]
        for n in range(len(values)-12,len(values)):
            prediction=_predict(values[:n])
            if prediction is None:return None
            points.append((values[n],prediction,values[n-1],values[n-12]))
        mae=lambda index:statistics.mean(abs(row[0]-row[index]) for row in points)
        forecast_err=mae(1);persistence_err=mae(2);seasonal_err=mae(3)
        # Less than 5% improvement over both basic naive methods: suppress.
        if forecast_err >= .95*min(persistence_err,seasonal_err):return None
        mape=100*statistics.mean(abs(a-p)/a for a,p,_,_ in points)
        if mape>20:return None
        predicted=_predict(values)
        if predicted is None:return None
        # Empirical 80% error envelope; not a calibrated prediction interval.
        errors=sorted(abs(a-p) for a,p,_,_ in points)
        envelope=errors[min(len(errors)-1,math.ceil(.8*len(errors))-1)]
        lower=max(0,predicted-envelope);upper=predicted+envelope
        return {'metric':metric,'unit':unit,'target_month':_next_month(entries[-1][0]),
            'estimate':round(predicted,2),'lower':round(lower,2),'upper':round(upper,2),
            'backtest_mae':round(forecast_err,2),'backtest_mape_pct':round(mape,2),
            'test_months':12,'baseline_mae':round(min(persistence_err,seasonal_err),2),
            'method':'과거 3년 동월 자료에 최근 3개월의 전년 대비 수준을 반영한 단기 모형',
            'interval_note':'과거 12개 예측오차의 80번째 백분위수에 따른 참고 범위(확률적 신뢰구간 아님)'}
    except (ValueError,TypeError,OverflowError,ZeroDivisionError):
        return None
