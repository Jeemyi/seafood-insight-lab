"""Optional marine/fisheries statistics from MOF statPortal's independent OpenAPI.

Registration on https://www.mof.go.kr/statPortal/api/idx/main.do is NOT the
same as registration for data.go.kr's HSK trade API. The portal supplies an
API URL *per selected statistical table*. URLs must be configured explicitly;
we never invent table IDs, API endpoints, or statistical observations.

Secrets:
  MOF_STATS_API_KEY      - key issued by statPortal, NOT MOF_API_KEY
  MOF_STATS_TABLE_URLS   - JSON list of URL templates. Each URL contains
                           {API_KEY}, not an actual credential. Optional.

A successful response alone does not make it publication-quality data. We
publish only comparable observations for the same series, period frequency,
dimensions and unit. We never infer prices from production quantities.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote
import json
import math
import os
import re
import requests
from xml.etree import ElementTree as ET

PORTAL = 'https://www.mof.go.kr/statPortal/'
PORTAL_API = 'https://www.mof.go.kr/statPortal/api/idx/main.do'
HEADERS = {'User-Agent': 'SeafoodInsightLab/2.0 (official published statistics)'}
MARKET_TERMS = ('수산', '어업', '어획', '양식', '어종', '어류', '연근해', '원양', '위판', '수산물',
                '해면', '내수면', '연어', '오징어', '고등어', '명태', '광어', '넙치', '조피볼락',
                '새우', '꽃게', '패류', '굴', '전복', '수산식품', '수출입')


def _amount(value):
    s=str(value if value is not None else '').strip().replace(',','').replace(' ','')
    if not s or s in ('-', '…','...', '—', 'X', 'x'):return None
    try:
        v=float(s)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None


def _period(value):
    """Normalize annual (YYYY), monthly (YYYYMM), quarterly (YYYYQ#)."""
    s=str(value or '').strip().replace(' ','').replace('/','').replace('.','').replace('-','')
    q=re.fullmatch(r'(20\d{2})[Qq]([1-4])',s)
    if q:return (f'{q[1]}Q{q[2]}','Q')
    if re.fullmatch(r'20\d{2}',s):return (s,'Y')
    if re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',s):return (s,'M')
    return None


def _period_predecessor(period, frequency, yoy=True):
    if frequency=='Y':return str(int(period)-1)
    if frequency=='Q':
        year=int(period[:4]);q=int(period[-1]);return f'{year-1}Q{q}' if yoy else (f'{year}Q{q-1}' if q>1 else f'{year-1}Q4')
    if frequency=='M':
        year=int(period[:4]);month=int(period[4:]);return f'{year-1}{month:02d}' if yoy else (f'{year}{month-1:02d}' if month>1 else f'{year-1}12')
    return None


def _templates(raw):
    try:value=json.loads(raw)
    except (ValueError,TypeError):raise ValueError('table URL setting must be a JSON array')
    if not isinstance(value,list):raise ValueError('table URL setting must be a JSON array')
    if len(value)>24:raise ValueError('max 24 selected statistical tables per run')
    result=[]
    for entry in value:
        if isinstance(entry,str):entry={'name':'해양수산통계','url':entry}
        if not isinstance(entry,dict) or not isinstance(entry.get('url'),str):
            raise ValueError('table entries need a URL')
        name=str(entry.get('name') or '해양수산통계')[:75]
        url=entry['url'].strip()
        p=urlsplit(url)
        # Never fetch arbitrary URLs, localhost, paths outside the portal or HTTP.
        if (p.scheme!='https' or p.hostname!='www.mof.go.kr' or
                not p.path.lower().startswith('/statportal/') or
                'openapi' not in p.path.lower()):
            raise ValueError('table URL must be an official statPortal OpenAPI HTTPS URL')
        if '{API_KEY}' not in url and '{MOF_STATS_API_KEY}' not in url:
            # A pasted URL with an embedded real key is not accepted or logged.
            raise ValueError('replace the authentication value in the table URL with {API_KEY}')
        result.append((name,url))
    return result


def _response_rows(payload):
    """Support array and common structured data wrappers, never treat errors as data."""
    if isinstance(payload,list):
        # Portal may return an error as an array with one errMsg/code object.
        if any(isinstance(x,dict) and any(x.get(flag) for flag in ('errMsg','error','ERROR','Error')) for x in payload):
            raise ValueError('statistical API returned an error')
        return [x for x in payload if isinstance(x,dict)]
    if not isinstance(payload,dict):raise ValueError('unexpected JSON shape')
    # Some portal error responses also have a valid HTTP 200 code.
    for flag in ('errMsg','error','ERROR','Error'):
        if payload.get(flag):raise ValueError('statistical API returned an error')
    for field in ('data','DATA','rows','ROWS','items','ITEMS','result','RESULT','response','body'):
        x=payload.get(field)
        if isinstance(x,list):return [v for v in x if isinstance(v,dict)]
        if isinstance(x,dict):
            try:return _response_rows(x)
            except ValueError:pass
    raise ValueError('response has no recognizable statistical records')


def _xml_rows(content):
    root=ET.fromstring(content)
    result=[]
    for el in root.iter():
        if el.tag.rsplit('}',1)[-1].lower() not in ('row','item'):continue
        row={child.tag.rsplit('}',1)[-1]: ''.join(child.itertext()).strip() for child in el}
        if row:result.append(row)
    if not result:raise ValueError('XML has no statistical rows')
    return result


def _fetch(name,template,key,session=None):
    url=template.replace('{API_KEY}',quote(key,safe='')).replace('{MOF_STATS_API_KEY}',quote(key,safe=''))
    client=session or requests
    response=client.get(url,timeout=(8,25),headers=HEADERS)
    response.raise_for_status()
    try:return _response_rows(response.json())
    except (ValueError,TypeError):
        content=getattr(response,'content',b'')
        if content.lstrip().startswith(b'<'):
            return _xml_rows(content)
        raise ValueError('invalid statistical JSON response')


def features_from_tables(tables, limit=24):
    """Accept {table_name: records}. Compare identical indicator/dimension/unit only."""
    grouped=defaultdict(dict)
    for provided_name,rows in tables.items():
        for row in rows:
            if not isinstance(row,dict):continue
            x={str(k).upper():v for k,v in row.items()}
            period_data=_period(x.get('PRD_DE') or x.get('PRDDE') or x.get('PERIOD'))
            amount=_amount(x.get('DT') if 'DT' in x else x.get('VALUE'))
            if not period_data or amount is None:continue
            period,freq=period_data
            table=str(x.get('TBL_NM') or x.get('TBLNM') or provided_name).strip()
            measure=str(x.get('ITM_NM') or x.get('ITMNM') or x.get('INDICATOR') or '관측값').strip()
            unit=str(x.get('UNIT_NM') or x.get('UNITNM') or x.get('UNIT') or '').strip()
            dims=tuple(str(x.get(f'C{i}_NM') or x.get(f'C{i}NM') or '').strip() for i in range(1,9))
            dims=tuple(y for y in dims if y)
            identity=' '.join((provided_name,table,*dims)).lower()
            if not any(term in identity for term in MARKET_TERMS):continue
            if not unit:continue  # No comparisons without known measurement units.
            table_id=str(x.get('TBL_ID') or x.get('TBLID') or provided_name)
            item_id=str(x.get('ITM_ID') or x.get('ITMID') or measure)
            # Table/indicator/dimensions/unit/frequency are part of series identity.
            key=(table_id,item_id,measure,dims,unit,freq,table,provided_name)
            if period in grouped[key]:
                # Duplicated conflicting cells are not reliable observations.
                if grouped[key][period]!=amount:grouped[key][period]=None
            else:grouped[key][period]=amount
    features=[]
    for (table_id,item_id,measure,dims,unit,freq,table,provided_name),values in grouped.items():
        valid={p:v for p,v in values.items() if v is not None}
        if len(valid)<2:continue
        latest=max(valid)
        prior=_period_predecessor(latest,freq,True)
        label='전년 동기'
        if prior not in valid:
            prior=_period_predecessor(latest,freq,False)
            label='직전 조사기간'
        if prior not in valid or valid[prior] is None or valid[prior]==0:continue
        # Do not mix rates/percent and absolute units; require positive denominator.
        current=valid[latest];before=valid[prior]
        pct=100*(current/before-1)
        if not math.isfinite(pct):continue
        scope=' · '.join(dims) if dims else '전체'
        # KOSIS often labels tables merely '어류' or '주요품목별'.
        # Preserve the selected fisheries source name so the scope stays clear.
        display_table = table if provided_name in table else f'{provided_name} · {table}'
        series_name=f'{display_table} · {scope} · {measure}'
        hashed=sha256(repr((table_id,item_id,measure,dims,unit,freq)).encode()).hexdigest()[:12]
        fmt=lambda v:f'{v:,.1f}' if abs(v)<100 or v%1 else f'{v:,.0f}'
        observed=(f'해양수산통계 {display_table}, {scope}, {measure}: {latest} {fmt(current)}{unit}, '
                  f'{prior} {fmt(before)}{unit}; {label} 대비 {pct:+.1f}%')
        features.append({
            'id':'mofstats_'+hashed,'name':series_name,'title':f'{series_name} {label} 대비 {pct:+.1f}%',
            'subtitle':f'해양수산통계 · {latest}', 'period_start':prior,'period_end':latest,
            'observed':observed,'facts':[
                {'label':latest+' 관측','value':fmt(current)+unit,'detail':scope},
                {'label':prior+' 비교','value':fmt(before)+unit,'detail':label},
                {'label':label+' 변화율','value':f'{pct:+.1f}%','detail':f'{prior} → {latest}'}],
            'data_links':[{'url':PORTAL,'label':'해양수산부 해양수산통계시스템 공식 통계표'}],
            'article_ids':[],'category':'원물 수급/시세','channels':[],
            'impact':f'{measure} {label} 대비 {pct:+.1f}%',
            'source_type':'해양수산통계 공식 OpenAPI','series_type':'mof_stats',
            'measurements':{'table':table,'configured_table':provided_name,'item':measure,'dimensions':list(dims),'unit':unit,
                            'frequency':freq,'period':latest,'previous_period':prior,
                            'value':current,'previous_value':before,'change_pct':pct},
            'limitations':'동일 통계표·항목·분류·단위의 비교. 통계 시점과 발표일은 다를 수 있으며 국가 전체 생산량과 품목별 수입량을 혼동하지 않는다.',
            'significance':min(50,abs(pct)*.6)+5,
        })
    # Give each selected table a chance to appear before adding volatile sub-series.
    by_table=defaultdict(list)
    for f in features:
        by_table[f['measurements']['configured_table']].append(f)
    first=[];remaining=[]
    for items in by_table.values():
        items.sort(key=lambda f:f['significance'],reverse=True)
        first.append(items[0])
        remaining.extend(items[1:3])  # No one table should dominate the evidence queue.
    first.sort(key=lambda f:f['significance'],reverse=True)
    remaining.sort(key=lambda f:f['significance'],reverse=True)
    if len(first)>=limit:return first[:limit]
    return (first+remaining)[:limit]


def fetch_statistics_features(session=None):
    key=os.getenv('MOF_STATS_API_KEY','').strip()
    raw=os.getenv('MOF_STATS_TABLE_URLS','').strip()
    if not (key or raw):return [],[]  # Entirely optional until the user configures it.
    if not key or not raw:return [],['MOF statistics: set both MOF_STATS_API_KEY and MOF_STATS_TABLE_URLS']
    try:entries=_templates(raw)
    except ValueError as exc:return [],['MOF statistics config: '+str(exc)]
    if not entries:return [],['MOF statistics: no tables selected']
    tables={};errors=[]
    def fetch_one(entry):
        name,template=entry
        try:
            return name,_fetch(name,template,key,session=session),None
        except (requests.RequestException,ValueError,ET.ParseError) as exc:
            # Do not return exception strings: requests exceptions can contain a key-bearing URL.
            return name,None,type(exc).__name__
    # Bounded concurrency avoids turning 14 sequential timeouts into a prolonged run.
    # Results are processed in configuration order for stable logs.
    with ThreadPoolExecutor(max_workers=min(3,len(entries))) as pool:
        for name,rows,error_kind in pool.map(fetch_one,entries):
            if error_kind:
                print(f'SEAFOOD MOF STATS table={name[:48]} error={error_kind}',flush=True)
                errors.append('MOF statistics '+name[:35]+': '+error_kind)
                continue
            if name in tables:tables[name].extend(rows)
            else:tables[name]=rows
            print(f'SEAFOOD MOF STATS table={name[:48]} rows={len(rows)}',flush=True)
    features=features_from_tables(tables)
    print(f'SEAFOOD MOF STATS tables={len(entries)} features={len(features)}',flush=True)
    if not features and not errors:errors.append('MOF statistics: no comparable selected market statistics')
    return features,errors
