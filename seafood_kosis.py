"""Optional KOSIS *current monthly* official seafood series.

KOSIS credentials differ from the MOF statPortal credentials. Users supply
real, generated KOSIS statistical DATA URLs with {API_KEY} placeholders; no
unverified table IDs are invented and no response is silently treated as fact.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit, parse_qs
import json
import os
import requests

from seafood_mof_statistics import _response_rows, features_from_tables

KOSIS_INFO = 'https://kosis.kr/openapi/index/index.jsp'
KOSIS_DATA = 'https://kosis.kr/'
HEADERS = {'User-Agent': 'SeafoodInsightLab/2.0 (KOSIS public statistical data)'}


def validate_templates(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError('KOSIS_TABLE_URLS must be a JSON array')
    if not isinstance(value, list) or len(value) > 18:
        raise ValueError('KOSIS_TABLE_URLS must be an array with at most 18 tables')
    entries = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get('url'), str):
            raise ValueError('each KOSIS table needs name and url')
        name = str(entry.get('name') or '수산통계')[:70]
        url = entry['url'].strip()
        split = urlsplit(url)
        if split.scheme != 'https' or split.hostname != 'kosis.kr' or split.port is not None or split.username:
            raise ValueError('KOSIS table URL must use the official HTTPS domain')
        if split.path not in ('/openapi/statisticsData.do', '/openapi/Param/statisticsParameterData.do'):
            raise ValueError('a KOSIS statistical DATA URL is required, not the table list URL')
        query = parse_qs(split.query)
        if query.get('method') != ['getList'] or query.get('format') != ['json']:
            raise ValueError('KOSIS method=getList and format=json required')
        if (query.get('apiKey') not in (['{API_KEY}'], ['{KOSIS_API_KEY}']) or
                not ('{API_KEY}' in url or '{KOSIS_API_KEY}' in url)):
            raise ValueError('replace KOSIS key with {API_KEY} in each URL')
        if not query.get('prdSe') or not (query.get('tblId') or query.get('userStatsId')):
            raise ValueError('KOSIS table ID and frequency must be in URL')
        if not (query.get('newEstPrdCnt') or (query.get('startPrdDe') and query.get('endPrdDe'))):
            raise ValueError('KOSIS needs multiple actual reporting periods')
        entries.append((name, url))
    return entries


def kosis_features_from_tables(tables):
    raw = features_from_tables(tables, limit=40)
    normalized = []
    for feature in raw:
        f = dict(feature)
        f['id'] = 'kosis_' + f['id'].removeprefix('mofstats_')
        f['series_type'] = 'kosis_stats'
        f['source_type'] = '국가데이터처 KOSIS 공식 통계 API'
        f['subtitle'] = f['subtitle'].replace('해양수산통계', 'KOSIS')
        f['observed'] = f['observed'].replace('해양수산통계', '국가데이터처 KOSIS')
        f['data_links'] = [{'url': KOSIS_INFO, 'label': '국가데이터처 KOSIS 공식 통계자료'}]
        f['limitations'] = ('KOSIS 원 통계표의 동일 분류·항목·단위·시점 비교. 최신 수록시점은 실제 응답값 기준이며, '
                            '과거 관측값을 현재 가격이나 최근 수급으로 단정하지 않는다.')
        f['measurements'] = {**f['measurements'], 'provider': 'KOSIS'}
        normalized.append(f)
    return normalized


def fetch_kosis_features(session=None):
    key = os.getenv('KOSIS_API_KEY', '').strip()
    raw = os.getenv('KOSIS_TABLE_URLS', '').strip()
    if not key and not raw:
        return [], []  # Explicit opt-in; no new mandatory secret.
    if not key or not raw:
        return [], ['KOSIS: configure both KOSIS_API_KEY and KOSIS_TABLE_URLS']
    try:
        entries = validate_templates(raw)
    except ValueError as exc:
        return [], ['KOSIS config: ' + str(exc)]
    if not entries:
        return [], []
    client = session or requests
    def fetch_one(entry):
        name, template = entry
        url = template.replace('{API_KEY}', quote(key, safe='')).replace('{KOSIS_API_KEY}', quote(key, safe=''))
        try:
            response = client.get(url, timeout=(8, 25), headers=HEADERS)
            response.raise_for_status()
            return name, _response_rows(response.json()), None
        except (requests.RequestException, ValueError, TypeError) as exc:
            # NEVER log exceptions containing authenticated URLs.
            return name, None, type(exc).__name__
    tables = {}
    errors = []
    with ThreadPoolExecutor(max_workers=min(3, len(entries))) as pool:
        for name, rows, error in pool.map(fetch_one, entries):
            if error:
                print(f'SEAFOOD KOSIS table={name[:40]} error={error}', flush=True)
                errors.append(f'KOSIS {name[:40]}: {error}')
                continue
            tables.setdefault(name, []).extend(rows)
            print(f'SEAFOOD KOSIS table={name[:40]} rows={len(rows)}', flush=True)
    features = kosis_features_from_tables(tables)
    print(f'SEAFOOD KOSIS tables={len(entries)} features={len(features)}', flush=True)
    return features, errors
