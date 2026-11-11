"""Optional KOSIS *current monthly* official seafood series.

KOSIS credentials differ from the MOF statPortal credentials. Users supply
real, generated KOSIS statistical DATA URLs with {API_KEY} placeholders; no
unverified table IDs are invented and no response is silently treated as fact.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit, urlunsplit, parse_qs, parse_qsl, urlencode
from xml.etree import ElementTree as ET
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



# KOSIS can return HTTP 200 containing a JSON or XML API *error*. Never log
# response bodies, URLs, or the server-supplied message: those may include keys.
_ERROR_KINDS = {
    '10': 'missing_api_key', '11': 'invalid_api_key',
    '12': 'expired_api_key', '20': 'missing_parameter',
    '21': 'invalid_parameter', '30': 'no_matching_data',
    '31': 'too_many_cells', '40': 'request_rate_limit',
    '41': 'account_data_limit', '42': 'access_restricted',
    '50': 'server_error',
}


class KOSISAPIError(ValueError):
    def __init__(self, code='unknown'):
        value = str(code).strip()
        self.code = value if value in _ERROR_KINDS else 'unknown'
        self.kind = _ERROR_KINDS.get(self.code, 'invalid_or_unexpected_response')
        super().__init__(self.kind)


def _error_code_from_payload(value):
    if isinstance(value, list):
        for row in value:
            code = _error_code_from_payload(row)
            if code is not None:
                return code
        return None
    if not isinstance(value, dict):
        return None
    lowered = {str(k).lower(): v for k, v in value.items()}
    if 'errmsg' in lowered or 'error' in lowered:
        return lowered.get('err') or lowered.get('errcode') or lowered.get('errorcode') or 'unknown'
    # Responses using a bare "err" status should not be mistaken for rows.
    if 'err' in lowered and 'dt' not in lowered and 'prd_de' not in lowered:
        return lowered.get('err') or 'unknown'
    return None


def _error_code_from_xml(data):
    if not isinstance(data, (str, bytes)):
        return None
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, TypeError):
        return None
    tag = str(root.tag).split('}')[-1].lower()
    if tag != 'error':
        return None
    for node in root.iter():
        field = str(node.tag).split('}')[-1].lower()
        if field in ('err', 'errcode', 'errorcode') and (node.text or '').strip():
            return (node.text or '').strip()
    return 'unknown'


def _response_data_rows(response):
    try:
        payload = response.json()
    except (ValueError, TypeError):
        # The official error guide documents XML <error><err>31</err>...
        # responses even for JSON statistical-data requests.
        content = getattr(response, 'content', b'')
        code = _error_code_from_xml(content)
        if code is not None:
            raise KOSISAPIError(code)
        raise KOSISAPIError('unknown')
    code = _error_code_from_payload(payload)
    if code is not None:
        raise KOSISAPIError(code)
    try:
        return _response_rows(payload)
    except (ValueError, TypeError):
        raise KOSISAPIError('unknown')


def _split_species_query(url, max_species=5):
    """Split a large valid request by its existing, explicit species codes.

    Preserve all other dimensions and reporting periods; never change the
    user's chosen species or infer missing values.  Used ONLY after KOSIS
    explicitly returns error 31 (query > 40,000 cells).
    """
    url_parts = urlsplit(url)
    parameters = parse_qsl(url_parts.query, keep_blank_values=True)
    raw_species = next((v for k, v in parameters if k == 'objL2'), '')
    species = raw_species.split()
    if len(species) <= max_species or any(v.upper() == 'ALL' for v in species):
        return []
    result = []
    for i in range(0, len(species), max_species):
        subset = ' '.join(species[i:i + max_species]) + ' '
        updated = [(k, subset if k == 'objL2' else v) for k, v in parameters]
        result.append(urlunsplit((url_parts.scheme, url_parts.netloc,
                                  url_parts.path, urlencode(updated), url_parts.fragment)))
    return result


def _get_rows(client, url):
    response = client.get(url, timeout=(8, 25), headers=HEADERS)
    response.raise_for_status()
    return _response_data_rows(response)


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
            return name, _get_rows(client, url), None
        except KOSISAPIError as exc:
            if exc.code == '31':
                parts = _split_species_query(url)
                if parts:
                    records = []
                    for part in parts:
                        try:
                            records.extend(_get_rows(client, part))
                        except KOSISAPIError as sub_exc:
                            return name, None, f'KOSIS_{sub_exc.code}_{sub_exc.kind}_after_split'
                        except (requests.RequestException, ValueError, TypeError):
                            return name, None, 'split_request_failed'
                    print(f'SEAFOOD KOSIS table={name[:40]} query_split={len(parts)}', flush=True)
                    return name, records, None
            return name, None, f'KOSIS_{exc.code}_{exc.kind}'
        except requests.RequestException:
            # Requests exceptions can print authenticated URLs; do not reveal them.
            return name, None, 'HTTP_or_network_error'
        except (ValueError, TypeError):
            return name, None, 'invalid_or_unexpected_response'
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
