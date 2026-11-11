"""Keyless, source-verified annual fisheries observations from e-Nara Indicators.

This is an optional supplemental source, not a substitute for current monthly
KOSIS series. Only explicit same-scope year/current/prior values are accepted.
Never take numbers from site navigation, dynamic charts or unrelated tables.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import math
import re
import requests
from bs4 import BeautifulSoup

SOURCE_URL = 'https://index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2748'
HEADERS = {'User-Agent': 'SeafoodInsightLab/2.0 (public fisheries statistics)'}

# Official page's factual explanatory text; table/chart JavaScript is intentionally
# not parsed, because a date in a graph alone cannot establish a measured value.
TOTAL = re.compile(
    r'어업생산량은\s*(20\d{2})년\s*([\d,]+)\s*천\s*톤으로\s*전년\s*\(\s*([\d,]+)\s*천\s*톤\s*\)\s*대비\s*([\d.]+)\s*%\s*(증가|감소)')
COMPONENT = re.compile(
    r'(연근해어업|해면양식업|내수면어업|원양어업)은\s*([\d,]+)\s*천\s*톤으로\s*전년\s*\(\s*([\d,]+)\s*천\s*톤\s*\)\s*대비\s*([\d.]+)\s*%\s*(증가|감소)')


def _series(name, year, current, previous, published_pct, direction):
    current = int(current.replace(',', ''))
    previous = int(previous.replace(',', ''))
    displayed = float(published_pct)
    if not (2000 <= year <= date.today().year + 1 and current >= 0 and previous > 0):
        return None
    pct = 100.0 * (current / previous - 1.0)
    if not math.isfinite(pct):
        return None
    # Official quantities are rounded to the nearest thousand tonnes. A 44 vs
    # 41 thousand-ton pair can therefore truthfully accompany a 9.3% official
    # growth rate even though the rounded quotient is 7.3%. Validate against
    # the *range* allowed by rounding instead of silently 'correcting' the agency.
    low = 100.0 * (max(0, current - .5) / (previous + .5) - 1)
    high = 100.0 * ((current + .5) / max(.5, previous - .5) - 1)
    signed = displayed if direction == '증가' else -displayed
    if not (low - .12 <= signed <= high + .12):
        return None
    if (pct >= 0) != (direction == '증가'):
        return None
    prevyear = str(year - 1)
    period = str(year)
    note = (f'국가데이터처 어업생산동향조사 · {name}: {period}년 {current:,}천 톤, '
            f'{prevyear}년 {previous:,}천 톤, 전년 대비 {published_pct}% {direction}')
    unique = sha256(f'e-nara-2748-{name}-{year}'.encode()).hexdigest()[:12]
    return {
        'id': 'enara_' + unique, 'name': f'어업생산동향 · {name}',
        'title': f'{name} {period}년 생산량 전년 대비 {published_pct}% {direction}',
        'subtitle': f'e-나라지표 · {period}년 수록값',
        'period_start': prevyear, 'period_end': period,
        'observed': note,
        'facts': [
            {'label': f'{period}년 생산량', 'value': f'{current:,}천 톤', 'detail': name},
            {'label': f'{prevyear}년 생산량', 'value': f'{previous:,}천 톤', 'detail': name},
            {'label': '전년 대비', 'value': f'{published_pct}% {direction}', 'detail': f'{prevyear}→{period}'}
        ],
        'data_links': [{'url': SOURCE_URL, 'label': 'e-나라지표 · 어업생산량 및 양식량'}],
        'article_ids': [], 'category': '원물 수급/시세', 'channels': [],
        'impact': f'{name} 연간 생산량 {direction}', 'source_type': '정부 공식 공개 지표',
        'series_type': 'enara_fisheries',
        'measurements': {'table': '어업생산량 및 양식량', 'item': '생산량',
                         'dimensions': [name], 'unit': '천 톤', 'frequency': 'Y',
                         'period': period, 'previous_period': prevyear,
                         'value': current, 'previous_value': previous,
                         'change_pct': pct, 'source_reported_change_pct': displayed},
        'limitations': f'{period}년 연간 공식 생산 통계(천 톤 단위 반올림). 해당 자료의 수록연도와 현재 거래시점을 구분한다.',
        'significance': min(23.0, 8.0 + abs(pct) * 0.35),
    }


def parse_national_fisheries(text, today=None):
    today = today or date.today()
    normalized = re.sub(r'\s+', ' ', text or '').replace('，', ',')
    blocks = list(TOTAL.finditer(normalized))
    # Pages sometimes retain several prior-year commentary paragraphs. Choose
    # the latest valid reporting year and take component figures only from its
    # own block, never from a different annual release.
    blocks = [(int(m[1]),m) for m in blocks if today.year - 4 <= int(m[1]) <= today.year]
    if not blocks:
        return []
    year, match = max(blocks, key=lambda x: x[0])
    total = _series('전체', year, match[2], match[3], match[4], match[5])
    if not total:
        return []
    items = [total]
    next_block = next((b.start() for b in TOTAL.finditer(normalized) if b.start()>match.start()),len(normalized))
    for sub in COMPONENT.finditer(normalized[match.end():next_block]):
        component = _series(sub[1], year, sub[2], sub[3], sub[4], sub[5])
        if component:
            items.append(component)
    return items


def fetch_national_fisheries_features(session=None, today=None):
    client = session or requests
    try:
        response = client.get(SOURCE_URL, timeout=(7, 15), headers=HEADERS)
        response.raise_for_status()
        html = response.text
        text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
        features = parse_national_fisheries(text, today=today)
        if not features:
            return [], ['e-Nara fisheries: no verified recent annual values in current page']
        print(f'SEAFOOD ENARA official annual year={features[0]["period_end"]} features={len(features)}', flush=True)
        return features, []
    except (requests.RequestException, ValueError, TypeError) as exc:
        return [], ['e-Nara fisheries: ' + type(exc).__name__]
