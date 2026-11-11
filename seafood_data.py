"""Verified public numeric series for seafood procurement monitoring.

Only records from official APIs. No fallback values, no assumed procurement costs.
SSB weekly export FOB price != any Korean buyer's landed/purchase price.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import os
import re
import requests

SSB_META = 'https://data.ssb.no/api/pxwebapi/v2/tables/03024/metadata'
SSB_DATA = 'https://data.ssb.no/api/pxwebapi/v2/tables/03024/data'
SSB_LINK = 'https://www.ssb.no/en/statbank/table/03024/'
ECOS_LINK = 'https://ecos.bok.or.kr/'
HEADERS = {'User-Agent': 'SeafoodInsightLab/1.0 (public research, sources linked)'}


def _get_json(url, params=None, timeout=(8, 18)):
    response = requests.get(url, params=params, timeout=timeout, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def _dimension_choices(dim):
    cat = dim.get('category') or {}
    idx = cat.get('index') or {}
    labels = cat.get('label') or {}
    codes = list(idx) if isinstance(idx, dict) else list(idx)
    return [(str(code), str(labels.get(str(code), str(code)))) for code in codes]


def _metadata_dimensions(payload):
    # json-stat2 metadata can have its dimensions either at root or under 'dimension'.
    dims = payload.get('dimension', {})
    ids = payload.get('id', list(dims))
    return [(name, dims[name]) for name in ids if name in dims]


def _choose_salmon_codes(payload):
    dims = _metadata_dimensions(payload)
    result = {}
    for name, dim in dims:
        choices = _dimension_choices(dim)
        label = (name + ' ' + dim.get('label','')).lower()
        if 'tid' == name.lower() or 'week' in label or 'time' in label:
            result[name] = 'top(190)'
        elif 'content' in label or 'measure' in label or 'statistic' in label:
            found = next((c for c,v in choices if 'price' in v.lower() and ('kg' in v.lower() or 'kilo' in v.lower())), None)
            if found is None:
                raise ValueError('SSB price-per-kg code missing')
            result[name] = found
        else:
            found = next((c for c,v in choices if ('fresh' in v.lower() or 'chilled' in v.lower()) and 'salmon' in v.lower()), None)
            if found is None:
                raise ValueError('SSB fresh salmon code missing')
            result[name] = found
    if not any('top(' in v for v in result.values()) or len(result) < 3:
        raise ValueError('SSB unexpected metadata dimensions')
    return result


def _jsonstat_values(payload):
    ids = payload.get('id') or []
    dims = payload.get('dimension') or {}
    size = payload.get('size') or []
    values = payload.get('value')
    if not isinstance(values, list) or not ids or len(ids) != len(size):
        raise ValueError('SSB unexpected data schema')
    time_position = next((i for i,key in enumerate(ids) if key.lower() == 'tid' or
                         'week' in str(dims.get(key,{}).get('label','')).lower() or
                         'time' in str(dims.get(key,{}).get('label','')).lower()), None)
    if time_position is None:
        raise ValueError('SSB week dimension missing')
    time_id=ids[time_position]
    choices = _dimension_choices(dims[time_id])
    result={}
    for i, (week, _) in enumerate(choices):
        # Pick time index i; all other dimensions are explicitly singleton filters.
        coord=[0]*len(size)
        coord[time_position]=i
        flat=0
        for j, s in enumerate(size):
            flat=flat*int(s)+coord[j]
        if flat >= len(values) or values[flat] is None:
            continue
        try:
            val=float(values[flat])
        except (ValueError, TypeError):
            continue
        if not math.isfinite(val) or val<=0:
            continue
        match=re.match(r'^(20\d{2})[UW](\d{1,2})$', week, re.I)
        if match:
            result[(int(match.group(1)),int(match.group(2)))]=val
    return result


def _choose_salmon_volume_codes(metadata):
    chosen=_choose_salmon_codes(metadata)
    for name,dim in _metadata_dimensions(metadata):
        key=(name+' '+dim.get('label','')).lower()
        if 'content' not in key and 'measure' not in key and 'statistic' not in key:continue
        choices=_dimension_choices(dim)
        volume=next((code for code,label in choices if
            any(t in label.lower() for t in ('quantity','volume','weight')) and
            any(t in label.lower() for t in ('tonne','tonnes','metric ton'))),None)
        if volume:
            chosen[name]=volume
            return chosen
    raise ValueError('SSB quantity series not available')


def fetch_ssb_salmon_volume():
    try:
        metadata=_get_json(SSB_META,{'lang':'en'})
        chosen=_choose_salmon_volume_codes(metadata)
        params={'lang':'en'}
        for k,v in chosen.items():params[f'valueCodes[{k}]']=v
        values=_jsonstat_values(_get_json(SSB_DATA,params))
        if len(values)<4:raise ValueError('SSB insufficient quantity observations')
        return values,None
    except Exception as exc:
        return {},'SSB 연어 물량: '+type(exc).__name__


def salmon_price_volume_feature(price, volume, today, usd_per_nok=None):
    """Show USD/kg only if ECB dates cover both comparison weeks.

    Absent matching exchange rates, publish the verified volume observation,
    but never show a NOK price as though it were a USD purchasing price.
    """
    common=sorted(set(price)&set(volume))
    if not common:return None
    year,week=common[-1]
    try:
        if (today-date.fromisocalendar(year,week,1)).days>28:return None
    except ValueError:return None
    prior=(year-1,week)
    if prior not in price or prior not in volume:return None
    volume_delta=_pct(volume[prior],volume[(year,week)])
    if volume_delta is None:return None
    current_volume=volume[(year,week)]
    period=f'{year}년 {week}주';prev=f'{year-1}년 {week}주'
    facts=[{'label':'연어 수출량','value':f'{current_volume:,.0f}톤','detail':period},
           {'label':'수출물량 전년 동기 대비','value':f'{volume_delta:+.1f}%','detail':prev}]
    obs=f'노르웨이 통계청 SSB {period} 신선·냉장 연어 수출량 {current_volume:,.0f}톤(전년 동주 {volume_delta:+.1f}%).'
    title=f'노르웨이 연어 수출량 전년 대비 {volume_delta:+.1f}%'
    measurements={'species':'연어','tonnes':current_volume,'yoy_qty_pct':volume_delta}
    links=[{'url':SSB_LINK,'label':'노르웨이 통계청 · 연어 수출 통계'}]
    series_type='salmon_volume'
    significance=abs(volume_delta)*.7+5
    usd_per_nok=usd_per_nok or {}
    if (year,week) in usd_per_nok and prior in usd_per_nok:
        current_usd=price[(year,week)]*usd_per_nok[(year,week)]
        prior_usd=price[prior]*usd_per_nok[prior]
        price_delta=_pct(prior_usd,current_usd)
        if price_delta is not None and all(math.isfinite(v) for v in (current_usd,prior_usd)):
            facts=[{'label':'연어 수출가 · 달러 환산','value':f'${current_usd:.2f}/kg',
                    'detail':f'{period} · ECB 주간 환율 적용'},
                   {'label':'달러 기준 전년 동기 대비','value':f'{price_delta:+.1f}%','detail':prev}]+facts
            title=f'노르웨이 연어 수출가 {price_delta:+.1f}% · 물량 {volume_delta:+.1f}%'
            obs=f'{period} 신선·냉장 연어 수출가 ${current_usd:.2f}/kg(전년 동주 {price_delta:+.1f}%) · 수출량 {current_volume:,.0f}톤({volume_delta:+.1f}%). SSB 가격을 ECB 동일 주차 일별 환율 평균으로 달러 환산.'
            measurements.update(price_usd_kg=round(current_usd,4),yoy_price_pct=round(price_delta,2))
            links.append({'url':'https://data.ecb.europa.eu/data/datasets/EXR',
                          'label':'유럽중앙은행(ECB) · 일별 환율'})
            series_type='salmon_joint'
            significance+=abs(price_delta)*1.6
    return {'id':'salmon_price_volume','name':'노르웨이 연어 수출가격·물량',
        'title':title,'subtitle':'노르웨이 통계청 SSB · ECB 달러 환산',
        'period_start':prev,'period_end':period,'facts':facts,'observed':obs,
        'data_links':links,'article_ids':[],'category':'원물 수급/시세',
        'channels':[],'impact':f'수출물량 {volume_delta:+.1f}%' +
            (f' · 달러 가격 {measurements["yoy_price_pct"]:+.1f}%' if 'yoy_price_pct' in measurements else ''),
        'source_type':'공식 공개 API','series_type':series_type,
        'limitations':'가격은 SSB 수출가격의 ECB 환율 환산값이며 계약·국내 소비자가격은 아니다.' if series_type=='salmon_joint' else 'ECB 달러환율이 확보되지 않아 가격은 표시하지 않았다.',
        'measurements':measurements,'significance':min(50,significance)}


def fetch_ssb_salmon():
    """Official open PxWeb v2 API; failures are explicit and no values invented."""
    try:
        metadata=_get_json(SSB_META, {'lang':'en'})
        chosen=_choose_salmon_codes(metadata)
        params={'lang':'en'}
        for k,v in chosen.items():
            params[f'valueCodes[{k}]']=v
        payload=_get_json(SSB_DATA, params)
        series=_jsonstat_values(payload)
        if len(series)<4:
            raise ValueError('SSB insufficient weekly observations')
        return series,None
    except Exception as exc:
        return {},'SSB 연어: '+type(exc).__name__


def _ecos_items(api_key):
    """Discover per-currency item IDs rather than assume JPY/NOK codes."""
    try:
        url=f'https://ecos.bok.or.kr/api/StatisticItemList/{api_key}/json/kr/1/400/731Y001'
        payload=_get_json(url)
        return payload.get('StatisticItemList',{}).get('row', [])
    except Exception:
        return []


def _ecos_code(items, currency):
    targets={'USD':['미국달러','미국 달러','원/미국달러','원/달러'],
             'JPY':['일본엔','일본 엔','원/일본엔'],
             'NOK':['노르웨이크로네','노르웨이 크로네','노르웨이 크론']}
    for row in items:
        name=str(row.get('ITEM_NAME','') or row.get('ITEM_NAME1','')).replace(' ','')
        if any(t.replace(' ','') in name for t in targets[currency]):
            return str(row.get('ITEM_CODE') or row.get('ITEM_CODE1') or '').strip()
    return '0000001' if currency=='USD' else ''


def fetch_ecos_currency(code, key, start, end):
    if not code:
        return {},'항목 코드 미확인'
    try:
        url=f'https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/731Y001/D/{start:%Y%m%d}/{end:%Y%m%d}/{code}'
        payload=_get_json(url, timeout=(8,22))
        rows=payload.get('StatisticSearch',{}).get('row',[])
        if not isinstance(rows,list) or not rows:
            raise ValueError('ECOS rows missing')
        result={}
        for row in rows:
            try:
                d=datetime.strptime(row['TIME'],'%Y%m%d').date()
                value=float(str(row['DATA_VALUE']).replace(',',''))
                if math.isfinite(value) and value>0:
                    result[d]=value
            except (ValueError,KeyError,TypeError):
                continue
        if not result:
            raise ValueError('ECOS no numeric observations')
        return result,None
    except Exception as exc:
        return {},'ECOS '+type(exc).__name__


def fetch_ecos(now):
    key=os.environ.get('ECOS_API_KEY','').strip()
    if not key:
        return {},['ECOS: ECOS_API_KEY 미설정 (한국은행 환율 자동 수집 제외)']
    items=_ecos_items(key)
    start=now.date()-timedelta(days=1190)
    series={};errors=[]
    for currency in ('USD','JPY','NOK'):
        code=_ecos_code(items,currency)
        data,error=fetch_ecos_currency(code,key,start,now.date())
        if data:
            series[currency]=data
        if error:
            errors.append(f'ECOS {currency}: {error}')
    return series,errors


def _pct(a,b):
    return (b/a-1)*100 if a else None


def _series_feature(fid, name, title, observations, unit, source_url, source_name, today,
                    category, channels, direction_note, time_type='daily'):
    if len(observations)<2:
        return None
    times=sorted(observations)
    current=times[-1]
    if time_type=='daily':
        if (today-current).days>12:
            return None
        ref_lastweek = current-timedelta(days=7)
        prior_candidates=[d for d in times if d<=ref_lastweek]
        prior=prior_candidates[-1] if prior_candidates else None
        year_prior=current.replace(year=current.year-1) if not (current.month==2 and current.day==29) else current.replace(year=current.year-1,day=28)
        year_candidates=[d for d in times if d<=year_prior]
        prev_year=year_candidates[-1] if year_candidates and (year_prior-year_candidates[-1]).days<=12 else None
        avg_vals=[]
        for year in (current.year-1,current.year-2,current.year-3):
            try: near=current.replace(year=year)
            except ValueError: near=current.replace(year=year,day=28)
            candidates=[d for d in times if d<=near]
            if candidates and (near-candidates[-1]).days<=12:
                avg_vals.append(observations[candidates[-1]])
        period_end=current.isoformat(); period_start=prior.isoformat() if prior else times[0].isoformat()
    else:
        cy,cw=current
        try:
            last_week=date.fromisocalendar(cy,cw,1)
        except ValueError:
            return None
        if (today-last_week).days>28:
            return None
        prior=times[-2] if len(times)>=2 and (cy*53+cw)-(times[-2][0]*53+times[-2][1])<=2 else None
        prev_year=(cy-1,cw) if (cy-1,cw) in observations else None
        avg_vals=[observations[(y,cw)] for y in (cy-1,cy-2,cy-3) if (y,cw) in observations]
        period_end=f'{cy}년 {cw}주'; period_start=f'{prior[0]}년 {prior[1]}주' if prior else period_end
    current_value=observations[current]
    facts=[{'label':name, 'value':f'{current_value:,.2f} {unit}', 'detail':f'관측 {period_end} · {source_name}'}]
    pieces=[f'{name} {current_value:,.2f} {unit} ({period_end}, {source_name} 발표값)']
    if prior is not None:
        delta=_pct(observations[prior],current_value)
        if delta is not None:
            facts.append({'label':'전주 대비', 'value':f'{delta:+.2f}%', 'detail':f'{period_start} 대비 · 실제 계산'})
            pieces.append(f'전주 대비 {delta:+.2f}%')
    if prev_year is not None:
        yoy=_pct(observations[prev_year],current_value)
        facts.append({'label':'전년 동일 시점 대비', 'value':f'{yoy:+.2f}%', 'detail':'전년 동기 원자료 비교'})
        pieces.append(f'전년 동기 대비 {yoy:+.2f}%')
    if len(avg_vals)==3:
        baseline=sum(avg_vals)/3
        vs=_pct(baseline,current_value)
        facts.append({'label':'과거 3년 동일 시점 평균 대비', 'value':f'{vs:+.2f}%', 'detail':'과거 3년 같은 주차/날짜의 단순 평균'})
        pieces.append(f'과거 3년 동기 평균 대비 {vs:+.2f}%')
    else:
        pieces.append('3년 평균 비교 자료 부족 — 표시 보류')
    return {'id':fid,'name':name,'title':title,'subtitle':source_name,
            'period_start':period_start,'period_end':period_end,
            'facts':facts,'observed':' · '.join(pieces),
            'data_links':[{'url':source_url,'label':source_name+' 공식 통계'}],
            'article_ids':[], 'category':category,'channels':channels,
            'impact':direction_note,'source_type':'공식 공개 API',
            'limitations':'수출 FOB 가격과 한국 내 실제 매입가·운임·환율·가공비는 서로 다르며, 데이터의 공표 시점 및 규격 차이를 고려해야 합니다.' if fid=='salmon_export_price' else '매매기준율은 납품계약의 적용환율·실제 결제환율과 다를 수 있습니다.'}


def make_features(now):
    features=[]; errors=[]
    salmon,ssb_error=fetch_ssb_salmon()
    volume,volume_error=fetch_ssb_salmon_volume()
    from seafood_currency import fetch_ecb_usd_per_nok
    usd_per_nok={}
    if salmon:
        usd_per_nok,ecb_error=fetch_ecb_usd_per_nok(now.date())
        if ecb_error:errors.append(ecb_error)
    joint=salmon_price_volume_feature(salmon,volume,now.date(),usd_per_nok) if salmon and volume else None
    if joint:features.append(joint)
    # No legacy NOK price-only fallback: raw Norwegian-currency observations
    # remain internal until a supported USD comparison can be constructed.
    if ssb_error:errors.append(ssb_error)
    if volume_error:errors.append(volume_error)
    fx,fx_errors=fetch_ecos(now)
    errors.extend(fx_errors)
    for currency,unit,title,channels in [
        ('USD','원/USD','원/달러 환율','마트·온라인·B2B'),
        ('JPY','원/100JPY','엔화 환율','수출')]:
        if currency not in fx:continue
        f=_series_feature('fx_'+currency.lower(),currency+' 환율',title,fx[currency],unit,
                          ECOS_LINK,'한국은행 ECOS',now.date(),'비용/거시',channels.split('·'),'참고 환율')
        if f:
            f['role']='context'
            features.append(f)
    # New public sources. They stay optional and never generate placeholder values.
    from seafood_public import make_public_features
    extra,public_errors=make_public_features(now)
    features.extend(extra)
    errors.extend(public_errors)
    # Keep some FX/salmon context, but prioritize species-specific production/trade
    # and surveyed consumer prices over three generic macro cards.
    features.sort(key=lambda x:(x.get('significance',0),
                 4 if x.get('series_type') in ('trade','kamis') else 0),reverse=True)
    return features,errors
