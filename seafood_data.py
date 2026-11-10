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


def salmon_price_volume_feature(price,volume,today):
    common=sorted(set(price)&set(volume))
    if not common:return None
    year,week=common[-1]
    try:
        if (today-date.fromisocalendar(year,week,1)).days>28:return None
    except ValueError:return None
    prior=(year-1,week)
    if prior not in price or prior not in volume:return None
    price_delta=_pct(price[prior],price[(year,week)])
    volume_delta=_pct(volume[prior],volume[(year,week)])
    if None in (price_delta,volume_delta):return None
    current_price=price[(year,week)];current_volume=volume[(year,week)]
    period=f'{year}년 {week}주';prev=f'{year-1}년 {week}주'
    observed=(f'노르웨이 통계청 SSB {period}: 신선·냉장 연어 수출가격 {current_price:,.2f} NOK/kg '
              f'(전년 {prev} 대비 {price_delta:+.1f}%), 수출물량 {current_volume:,.0f}톤 '
              f'(전년 동주 대비 {volume_delta:+.1f}%). 동일 주차·동일 제품 분류 비교.')
    return {'id':'salmon_price_volume','name':'노르웨이 연어 가격·수출물량',
        'title':f'노르웨이 연어 수출가 {price_delta:+.1f}% · 물량 {volume_delta:+.1f}%',
        'subtitle':'노르웨이 통계청 SSB 신선·냉장 연어','period_start':prev,
        'period_end':period,'facts':[
          {'label':'수출가격','value':f'{current_price:,.2f} NOK/kg','detail':period},
          {'label':'전년 동기 수출가','value':f'{price_delta:+.1f}%','detail':prev},
          {'label':'수출물량','value':f'{current_volume:,.0f}톤','detail':period},
          {'label':'전년 동기 수출물량','value':f'{volume_delta:+.1f}%','detail':prev}],
        'observed':observed,'data_links':[{'url':SSB_LINK,'label':'노르웨이 통계청 신선·냉장 연어 주간 수출 가격·물량'}],
        'article_ids':[],'category':'원물 수급/시세','channels':[],
        'impact':f'가격 {price_delta:+.1f}% · 물량 {volume_delta:+.1f}%',
        'source_type':'공식 공개 API','series_type':'salmon_joint',
        'limitations':'SSB 신선·냉장 연어 수출가격은 NOK/kg, 물량은 수출 톤수다. 한국 수입 원가·원화 환산가격과 다르며 월간 수출 통계와 같은 자료로 합산할 수 없다.',
        'measurements':{'species':'연어','price_nok_kg':current_price,'tonnes':current_volume,'yoy_price_pct':price_delta,'yoy_qty_pct':volume_delta},
        'significance':min(34,abs(price_delta)*1.6+abs(volume_delta)*.7)+5}


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
    joint=salmon_price_volume_feature(salmon,volume,now.date()) if salmon and volume else None
    if joint:features.append(joint)
    if salmon and not joint:
        f=_series_feature('salmon_export_price','노르웨이 생연어 수출가','노르웨이 연어 수출가 변화가 국내 수입원가에 주는 신호',salmon,'NOK/kg',SSB_LINK,'노르웨이 통계청 SSB',now.date(),'원물 수급/시세',['마트','온라인','B2B'],'NOK 가격 하락은 원물가 하락 요인일 수 있으나 국내 매입가 하락 확정 아님', 'weekly')
        if f:features.append(f)
    if ssb_error:errors.append(ssb_error)
    if volume_error:errors.append(volume_error)
    fx,fx_errors=fetch_ecos(now)
    errors.extend(fx_errors)
    for currency, unit, title, channels in [
        ('USD','원/USD','원/달러 환율 변동과 수입 수산물 원가','마트·온라인·B2B'),
        ('JPY','원/100JPY','엔화 움직임과 일본 거래·수출 채산성','수출'),
        ('NOK','원/NOK','노르웨이 크로네 환율과 연어 매입원가','마트·온라인·B2B')]:
        if currency not in fx:continue
        f=_series_feature('fx_'+currency.lower(), currency+' 환율',title,fx[currency],unit,ECOS_LINK,'한국은행 ECOS',now.date(),'비용/거시',channels.split('·'),'환율 변화는 결제통화·계약시점에 따라 반영 시차 발생')
        if f:features.append(f)
    # Apply conversion only when both primary observations exist. Never claim landed cost.
    if salmon and 'NOK' in fx:
        latest_week=max(salmon)
        fx_latest=max(fx['NOK'])
        # Mixing non-matching observation dates here would be misleading;
        # show the official series separately rather than invent weekly landed cost.
        _=latest_week,fx_latest
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
