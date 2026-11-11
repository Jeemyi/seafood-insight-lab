"""Norges Bank official USD/NOK daily FX, summarized to ISO-week means.

An average FX translation of a weekly NOK export price is a display estimate,
not an observed transaction price or a Korean importer landed cost.
"""
from __future__ import annotations
import csv
import io
from collections import defaultdict
from datetime import datetime, date, timedelta
import math
import requests

URL = 'https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP'
LINK = 'https://www.norges-bank.no/en/topics/Statistics/exchange_rates/'


def parse_usd_nok_csv(content):
    text = content.decode('utf-8-sig') if isinstance(content, bytes) else str(content)
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not lines:
        raise ValueError('FX response empty')
    # Norges Bank CSV exposes TIME_PERIOD/OBS_VALUE; delimiter varies by format.
    header = lines[0]
    sep = ';' if header.count(';') > header.count(',') else ','
    reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=sep)
    fields = [str(f).strip().lstrip('\ufeff') for f in (reader.fieldnames or [])]
    if 'TIME_PERIOD' not in fields or 'OBS_VALUE' not in fields:
        raise ValueError('FX CSV fields missing')
    amounts = defaultdict(list)
    for row in reader:
        try:
            raw_day = str(row.get('TIME_PERIOD') or '').strip()
            if not raw_day:
                continue
            d = date.fromisoformat(raw_day[:10])
            raw_value = str(row.get('OBS_VALUE') or '').strip().replace(' ', '')
            if sep == ';':
                raw_value = raw_value.replace(',', '.')
            value = float(raw_value)
            if not math.isfinite(value) or not 2 < value < 30:
                continue
            year, week, _ = d.isocalendar()
            amounts[(year, week)].append(value)
        except (TypeError, ValueError):
            continue
    if not amounts:
        raise ValueError('No valid USD/NOK rates')
    return {key: sum(values) / len(values) for key, values in amounts.items()}


def fetch_weekly_usd_nok(now):
    today = now.date() if isinstance(now, datetime) else now
    start = today - timedelta(days=510)
    try:
        response = requests.get(URL, params={
            'format': 'csvfile', 'startPeriod': start.isoformat(),
            'endPeriod': today.isoformat(), 'locale': 'en'},
            headers={'User-Agent': 'SeafoodInsightLab/2.0 (public research)'},
            timeout=(8, 30))
        response.raise_for_status()
        result = parse_usd_nok_csv(response.content)
        return result, None
    except (requests.RequestException, ValueError) as exc:
        return {}, '노르웨이 중앙은행 USD/NOK 환율: ' + type(exc).__name__


def add_usd_to_salmon(feature, price_by_week, fx_by_week):
    if not feature or not fx_by_week or not price_by_week:
        return feature
    now_key = max((key for key in price_by_week if key in fx_by_week), default=None)
    if now_key is None:
        return feature
    prior_key = (now_key[0] - 1, now_key[1])
    latest = max(price_by_week)
    # Do not label older exchange rates as the latest price observation.
    if now_key != latest or prior_key not in fx_by_week or prior_key not in price_by_week:
        return feature
    this_usd = price_by_week[now_key] / fx_by_week[now_key]
    prior_usd = price_by_week[prior_key] / fx_by_week[prior_key]
    if prior_usd <= 0:
        return feature
    yoy = (this_usd / prior_usd - 1) * 100
    feature['measurements'].update({'price_usd_kg': round(this_usd, 4),
        'prior_price_usd_kg': round(prior_usd, 4), 'usd_yoy_pct': round(yoy, 2),
        'usd_nok_week_avg': round(fx_by_week[now_key], 5),
        'usd_nok_prev_year_week_avg': round(fx_by_week[prior_key], 5)})
    feature['facts'].insert(0, {'label': '달러 환산 수출가격', 'value': f'${this_usd:,.2f}/kg',
        'detail': f'{now_key[0]}년 {now_key[1]}주 · 전년 동주 {yoy:+.1f}%'})
    feature['observed'] += (f' · Norges Bank 주간 평균환율로 환산한 가격 '
        f'${this_usd:,.2f}/kg(전년 동주 ${prior_usd:,.2f}/kg, {yoy:+.1f}%). '
        '주간 공식 수출가격 NOK/kg을 환산한 참고가격이며 실제 달러 계약가격은 아님.')
    feature['data_links'].append({'url': LINK, 'label': 'Norges Bank USD/NOK 공식 일별 환율'})
    feature['title'] = (f'노르웨이 연어 달러 환산 수출가 {yoy:+.1f}%'
        f' · 수출량 {feature["measurements"]["yoy_qty_pct"]:+.1f}%')
    feature['impact'] = f'달러 환산가격 {yoy:+.1f}% · 물량 {feature["measurements"]["yoy_qty_pct"]:+.1f}%'
    feature['limitations'] = '달러 환산가격은 해당 주 USD/NOK 일별 평균환율을 이용한 참고값. 공식 NOK/kg 수출가격, 실제 달러 계약가격, 한국의 수입 통관단가는 서로 다름.'
    return feature
