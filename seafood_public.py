"""Additional public seafood-market series (no private company data).

MOF HSK monthly trade: public data portal API key required.
KAMIS national wholesale/retail prices: KAMIS key and account ID required.
Unavailable APIs produce no observations. Price/quantity statistics use their own
measurement units, scope and dates, never implied retail or company purchase costs.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import calendar
import math
import os
import re
import requests
from xml.etree import ElementTree as ET

MOF_URL='https://apis.data.go.kr/1192000/select0080List/getselect0080List'
MOF_PAGE='https://www.data.go.kr/data/15056602/openapi.do'
KAMIS_URL='https://www.kamis.or.kr/service/price/xml.do'
KAMIS_PAGE='https://www.kamis.or.kr/customer/reference/openapi_list.do?action=detail&boardno=1'
HEADERS={'User-Agent':'SeafoodInsightLab/2.0 (public official statistical data)'}

# Product names are matching criteria, NOT public proprietary data. Never infer
# species from an unrelated HSK heading. Entries containing several kinds are excluded.
SPECIES=[('광어','광어|넙치'),('우럭','우럭|조피볼락'),('오징어','오징어'),('연어','연어'),
         ('꽃게','꽃게'),('새우','새우'),('고등어','고등어'),('문어','문어'),
         ('장어','장어'),('조기','조기|굴비'),('낙지','낙지'),('주꾸미','주꾸미|쭈꾸미')]
FORM_PATTERNS=(('냉동','냉동|냉동한'),('신선·냉장','신선|냉장|활어|살아있는'),('가공','조제|보존처리|훈제|건조|염장'))

def _float(value):
    try:
        if value is None or str(value).strip() in ('','-','—'):return None
        out=float(str(value).replace(',','').replace(' ',''))
        return out if math.isfinite(out) else None
    except (TypeError,ValueError):return None

def _pct(current,prior):
    return 100*(current/prior-1) if prior and prior>0 else None

def _shift_month(yymm,delta):
    yy,mm=int(yymm[:4]),int(yymm[4:]); idx=yy*12+mm-1+delta
    return f'{idx//12:04d}{idx%12+1:02d}'

def _past_months(today):
    last=_shift_month(today.strftime('%Y%m'),-1)
    return [last]+[_shift_month(last,-i) for i in range(1,6)]

def _body_rows(payload):
    """Normalize JSON data.go.kr variants; reject API errors instead of using them as numbers."""
    if not isinstance(payload,dict):raise ValueError('not an API object')
    obj=payload.get('response',payload)
    if not isinstance(obj,dict):raise ValueError('bad API wrapper')
    # Some public-data gateways put operationNameResponse between root and
    # header/body. Do not silently report 0 when the wrapper changes.
    for _ in range(3):
        if 'header' in obj or 'body' in obj or 'items' in obj:break
        nested=[value for key,value in obj.items()
                if isinstance(value,dict) and str(key).lower().endswith('response')]
        if nested:obj=nested[0];continue
        error=obj.get('OpenAPI_ServiceResponse')
        if isinstance(error,dict):
            head=error.get('cmmMsgHeader',{})
            raise ValueError('MOF gateway error '+str(head.get('returnReasonCode','unknown'))
                             +' '+str(head.get('errMsg',''))[:50])
        raise ValueError('MOF unknown JSON fields '+','.join(str(x)[:24] for x in list(obj)[:6]))
    header=obj.get('header',{})
    if isinstance(header,dict) and header.get('resultCode') not in (None,'00','0',0):
        raise ValueError('MOF API returned resultCode='+str(header.get('resultCode'))+' / '+str(header.get('resultMsg',''))[:60])
    body=obj.get('body',obj)
    if not isinstance(body,dict):raise ValueError('bad API body')
    items=body.get('items',body.get('item',[]))
    if isinstance(items,dict):items=items.get('item',[])
    if isinstance(items,dict):items=[items]
    if not isinstance(items,list):items=[]
    total=body.get('totalCount',len(items))
    return items,int(total or 0)

def _mof_xml_payload(content):
    """Parse the officially documented XML alternative when JSON is unavailable."""
    root=ET.fromstring(content)
    error=root.find('.//cmmMsgHeader')
    if error is not None:
        code=error.findtext('returnReasonCode','unknown')
        raise ValueError('MOF gateway response error '+code)
    header_node=root.find('.//header')
    header={child.tag:child.text for child in header_node} if header_node is not None else {}
    body_node=root.find('.//body')
    if body_node is None:
        raise ValueError('MOF XML missing body')
    count=body_node.findtext('totalCount','0')
    items=[]
    for item in body_node.findall('.//item'):
        items.append({child.tag:child.text for child in item})
    return {'response':{'header':header,'body':{'items':{'item':items},'totalCount':count}}}


def _request_mof_month(month,key,session=None):
    client=session or requests
    rows=[];page=1
    while page<=20:
        resp=client.get(MOF_URL,params={'serviceKey':key,'numOfRows':1000,'pageNo':page,'type':'json','baseDt':month},
                        timeout=(8,25),headers=HEADERS)
        resp.raise_for_status()
        try:payload=resp.json()
        except ValueError:
            if resp.content.lstrip().startswith(b'<'):
                payload=_mof_xml_payload(resp.content)
            else:
                ctype=resp.headers.get('Content-Type','unknown') if hasattr(resp,'headers') else 'unknown'
                raise ValueError('MOF response not JSON/XML (type='+str(ctype)[:35]+')')
        items,total=_body_rows(payload)
        if page==1 and not items:
            wrapper=payload.get('response',payload) if isinstance(payload,dict) else {}
            body=wrapper.get('body',{}) if isinstance(wrapper,dict) else {}
            header=wrapper.get('header',{}) if isinstance(wrapper,dict) else {}
            print(f'SEAFOOD MOF API {month}: empty first page; reported_total={total}; '
                  f'result={header.get("resultCode","not_provided") if isinstance(header,dict) else "unknown"}; '
                  f'root_fields={list(payload)[:7] if isinstance(payload,dict) else "not_dict"}; '
                  f'body_keys={list(body)[:7] if isinstance(body,dict) else "not_dict"}',flush=True)
        rows.extend(items)
        if not items or len(rows)>=total:break
        page+=1
    return rows

def _species_and_form(name):
    text=re.sub(r'\s+','',name or '')
    if not text:return None
    matched=[species for species,pattern in SPECIES if re.search(pattern,text)]
    # Exclude HS categories naming more than one species.
    if len(matched)!=1:return None
    form=next((form for form,pat in FORM_PATTERNS if re.search(pat,text)), '기타')
    return matched[0],form

def _normalize_trade(rows):
    """One row per (HSK code, import/export); duplicate rows are de-duplicated."""
    output={}
    for row in rows:
        if not isinstance(row,dict):continue
        code=str(row.get('hskTrfclsfCode','')).strip()
        name=str(row.get('hsPrdlstNm','')).strip()
        kind=str(row.get('imxprtSeNm') or row.get('imxprtSeCode') or '').strip()
        if kind not in ('수입','I','수출','E') or len(code)<6:continue
        category=_species_and_form(name)
        if not category:continue
        mass=_float(row.get('imxprtWt'))
        value=_float(row.get('imxprtDollarAmount'))
        if mass is None or value is None or mass<=0 or value<0:continue
        direction='수입' if kind in ('수입','I') else '수출'
        key=(code,direction)
        if key in output:
            # API should contain one row per code and direction/month; repeated entries
            # could cause double counting, so accept only the first occurrence.
            continue
        output[key]={'name':name,'code':code,'category':category,'kg':mass,'usd':value,'direction':direction}
    return output

def trade_features_from_months(data,month,limit=8):
    """Generate comparable trade groups using only HSK codes present in both years."""
    previous=_shift_month(month,-12)
    this=_normalize_trade(data.get(month,[]))
    last=_normalize_trade(data.get(previous,[]))
    earlier=_normalize_trade(data.get(_shift_month(month,-1),[]))
    groups=defaultdict(list)
    for key,row in this.items():
        if key in last and last[key]['category']==row['category']:
            species,form=row['category']
            # Treat 'other' as heterogeneous, not a meaningful product form.
            if form=='기타':continue
            groups[(species,form,row['direction'])].append(key)
    features=[]
    for (species,form,direction),keys in groups.items():
        weight=sum(this[k]['kg'] for k in keys)
        old_weight=sum(last[k]['kg'] for k in keys)
        value=sum(this[k]['usd'] for k in keys)
        old_value=sum(last[k]['usd'] for k in keys)
        if min(weight,old_weight,value,old_value)<=0:continue
        # Low-volume categories can be volatile; publish with code coverage and limits.
        volume_delta=_pct(weight,old_weight)
        value_delta=_pct(value,old_value)
        unit=value/weight
        prior_unit=old_value/old_weight
        unit_delta=_pct(unit,prior_unit)
        if volume_delta is None or value_delta is None or unit_delta is None:continue
        ids={k[0] for k in keys}
        this_set={k[0] for k,row in this.items() if row['category']==(species,form) and row['direction']==direction}
        last_set={k[0] for k,row in last.items() if row['category']==(species,form) and row['direction']==direction}
        # Material code coverage changes should be treated as incomplete comparable samples.
        this_coverage=sum(this[k]['kg'] for k in keys)/sum(row['kg'] for k,row in this.items() if row['category']==(species,form) and row['direction']==direction)
        last_coverage=sum(last[k]['kg'] for k in keys)/sum(row['kg'] for k,row in last.items() if row['category']==(species,form) and row['direction']==direction)
        if min(this_coverage,last_coverage)<.88:continue
        prevkeys=[k for k in keys if k in earlier and earlier[k]['category']==(species,form)]
        mom_phrase=''
        if len(prevkeys)==len(keys):
            old_mom=sum(earlier[k]['kg'] for k in prevkeys)
            mom_delta=_pct(weight,old_mom)
            if mom_delta is not None:mom_phrase=f' · 전월 물량 {mom_delta:+.1f}%'
        latest=f'{month[:4]}년 {int(month[4:])}월'
        yoy=f'{previous[:4]}년 {int(previous[4:])}월'
        title=f'{species} {form} {direction}물량 {volume_delta:+.1f}% · 평균단가 {unit_delta:+.1f}%'
        obs=(f'{latest} {species} {form} {direction}: HSK {len(keys)}개 동일코드 비교, '
             f'{weight/1000:,.1f}톤(전년 동월 {old_weight/1000:,.1f}톤; {volume_delta:+.1f}%), '
             f'금액 {value/1e6:,.2f}백만 달러(전년 동월 {old_value/1e6:,.2f}백만 달러; {value_delta:+.1f}%), '
             f'평균 수출입단가 {unit:,.2f}달러/kg(전년 동월 {prior_unit:,.2f}달러/kg; {unit_delta:+.1f}%)'
             +mom_phrase)
        formspec=f'HSK 동일코드 {len(keys)}개, 코드 {", ".join(sorted(ids)[:6])}'
        facts=[{'label':f'{direction} 물량','value':f'{weight/1000:,.1f}톤','detail':latest},
               {'label':'전년 동월 물량','value':f'{volume_delta:+.1f}%','detail':yoy+' 대비'},
               {'label':'수출입 평균단가','value':f'{unit:,.2f} USD/kg','detail':f'전년 대비 {unit_delta:+.1f}%'},
               {'label':'금액 증감','value':f'{value_delta:+.1f}%','detail':'달러 기준 · 전년 동월 대비'}]
        features.append({'id':f'mof_{direction}_{species}_{form}'.replace('·','_'),
            'name':f'{species} {form} {direction}','title':title,'subtitle':f'해양수산부 HSK 월간 수출입 · {latest}',
            'period_start':yoy,'period_end':latest,'facts':facts,'observed':obs,
            'data_links':[{'url':MOF_PAGE,'label':'해양수산부 수산물 HSK 수출입 공식 API'}],
            'article_ids':[],'category':'원물 수급/시세' if direction=='수입' else '해외',
            'channels':['수출'] if direction=='수출' else [],'impact':f'물량 {volume_delta:+.1f}% · 평균단가 {unit_delta:+.1f}%',
            'source_type':'정부 공개 API','limitations':f'HSK {len(keys)}개 동일코드 비교. {formspec}. 금액/중량으로 계산한 통관 평균단가는 실제 거래가격·국내 도소매가격과 다를 수 있고 원산지 정보가 없다. 금액은 USD, 수량은 kg 기준이며 관세 분류 개정·거래구성 차이의 영향을 받을 수 있다.',
            'series_type':'trade','measurements':{'species':species,'form':form,'direction':direction,
               'current_month':month,'prior_month':previous,'kg':weight,'prev_kg':old_weight,
               'usd':value,'prev_usd':old_value,'unit_usd_kg':unit,'prev_unit_usd_kg':prior_unit,
               'yoy_qty_pct':volume_delta,'yoy_value_pct':value_delta,'yoy_unit_pct':unit_delta,'hsk_codes':sorted(ids)},
            'significance':min(60,abs(volume_delta)*.5+abs(unit_delta)*.7)+ (7 if species in ('광어','우럭','오징어','연어','꽃게') else 0)})
    return sorted(features,key=lambda f:(f['significance'],f['measurements']['kg']),reverse=True)[:limit]

def fetch_mof_features(today):
    key=(os.getenv('MOF_API_KEY') or os.getenv('DATA_GO_KR_SERVICE_KEY') or '').strip()
    if not key:return [],['수산물 수출입: MOF_API_KEY 미설정 — 추가 통계 연동 대기']
    errors=[]
    for candidate in _past_months(today):
        months=[candidate,_shift_month(candidate,-1),_shift_month(candidate,-12)]
        fetched={}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={m:pool.submit(_request_mof_month,m,key) for m in months}
            for m,f in futures.items():
                try:fetched[m]=f.result()
                except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                    # No auth keys or full requested URLs in diagnostics.
                    diagnostic=str(exc)[:95] if isinstance(exc,ValueError) else type(exc).__name__
                    errors.append(f'MOF {m}: {diagnostic}')
        if candidate in fetched and _shift_month(candidate,-12) in fetched:
            this=fetched.get(candidate,[]);prior=fetched.get(_shift_month(candidate,-12),[])
            valid_this=_normalize_trade(this);valid_prior=_normalize_trade(prior)
            shared=set(valid_this)&set(valid_prior)
            features=trade_features_from_months(fetched,candidate)
            print(f'SEAFOOD MOF {candidate}: raw={len(this)} prior_raw={len(prior)} '
                  f'recognized={len(valid_this)} prior_recognized={len(valid_prior)} '
                  f'shared_hsk={len(shared)} published={len(features)}',flush=True)
            if features:return features,errors
    return [],errors+['수산물 수출입: 비교 가능한 전년 동월 자료 없음']

def _kamis_xml_payload(content):
    """Some KAMIS installations return XML even when JSON is requested."""
    root=ET.fromstring(content)
    data=root.find('data') if root.tag!='data' else root
    if data is None:
        return {'data':{'error_code':root.findtext('error_code','001'),'item':[]}}
    code=data.findtext('error_code') or data.findtext('result_code') or '000'
    rows=[]
    for node in data.findall('item'):
        rows.append({child.tag:(child.text or '') for child in node})
    return {'data':{'error_code':code,'item':rows}}


def _kamis_items(payload):
    if not isinstance(payload,dict):return []
    data=payload.get('data',payload.get('price',{}))
    if isinstance(data,dict):
        result_code=str(data.get('error_code',data.get('result_code','000')))
        if result_code in ('900','200'):
            raise ValueError('KAMIS API denied or unavailable (result code '+result_code+')')
        if result_code not in ('000','0','001'):
            raise ValueError('KAMIS unexpected result code '+result_code)
        items=data.get('item',data.get('items',[]))
    else:items=data
    if isinstance(items,dict):items=[items]
    return [row for row in items if isinstance(row,dict)] if isinstance(items,list) else []

def _request_kamis(cls,key,ident,day=None):
    params={'action':'dailyPriceByCategoryList','p_cert_key':key,
            'p_cert_id':ident,'p_returntype':'json','p_product_cls_code':cls,
            'p_item_category_code':'600','p_convert_kg_yn':'Y'}
    if day is not None:
        params['p_regday']=day.isoformat()
    resp=requests.get(KAMIS_URL,params=params,timeout=(8,25),headers=HEADERS)
    resp.raise_for_status()
    try:payload=resp.json()
    except (ValueError,requests.exceptions.JSONDecodeError):
        if not resp.content.lstrip().startswith(b'<'):
            raise ValueError('KAMIS response is neither JSON nor XML')
        payload=_kamis_xml_payload(resp.content)
    return _kamis_items(payload)

def _kamis_day(value, as_of):
    """Parse an ACTUAL returned survey date, including Korean-formatted dates."""
    from datetime import datetime
    raw=str(value or '').strip()
    if not raw:return None
    # KAMIS can append a weekday, e.g. '2026.11.04(수)', or a clock time.
    raw=re.sub(r'\([^)]*\)','',raw)
    cleaned=(raw.replace('년','-').replace('월','-').replace('일','')
             .replace('/','-').replace('.','-').replace(' ','').strip('-'))
    cleaned=re.sub(r'[^0-9:-].*$','',cleaned).strip('-')
    for pattern in ('%Y-%m-%d','%Y-%m-%d-%H:%M:%S','%y-%m-%d'):
        try:return datetime.strptime(cleaned,pattern).date()
        except ValueError:pass
    for pattern in ('%m-%d',):
        try:
            partial=datetime.strptime(cleaned,pattern)
            candidate=date(as_of.year,partial.month,partial.day)
            if candidate>as_of+timedelta(days=2):candidate=date(as_of.year-1,partial.month,partial.day)
            return candidate
        except ValueError:pass
    return None

def kamis_features_from_rows(wholesale,retail,limit=8,as_of=None):
    results=[]
    from datetime import datetime
    as_of=as_of or date.today()
    for cls,rows,channel in [('도매',wholesale,'도매'),('소매',retail,'소매')]:
        for row in rows:
            name=str(row.get('item_name','')).strip()
            if not name or not any(re.search(pat,name) for _,pat in SPECIES):continue
            cur=_float(row.get('dpr1'));week=_float(row.get('dpr3'));month=_float(row.get('dpr5'));year=_float(row.get('dpr6'))
            if cur is None or cur<=0:continue
            sample_date=_kamis_day(row.get('day1') or row.get('lastest_date'),as_of)
            if sample_date is None:continue
            datekey=sample_date.isoformat()
            if (as_of-sample_date).days>45 or (sample_date-as_of).days>2:continue
            unit=str(row.get('unit','')).strip() or 'KAMIS 조사단위'
            kind=str(row.get('kind_name','')).strip()
            rank=str(row.get('rank','')).strip()
            pct_week=_pct(cur,week);pct_month=_pct(cur,month);pct_year=_pct(cur,year)
            previous=_float(row.get('_real_previous_price'))
            previous_day=row.get('_real_previous_date')
            pct_previous=_pct(cur,previous) if previous_day else None
            # Use explicit surveyed size, grade, variety to prevent invalid price comparisons.
            full=f'{name} {kind} {rank}'.strip()
            key=re.sub(r'\s+','_',full)
            facts=[{'label':f'{cls} 조사 가격','value':f'{cur:,.0f}원/{unit}','detail':datekey}]
            pieces=[f'{datekey} {cls} {full} {cur:,.0f}원/{unit}']
            if pct_week is not None:
                facts.append({'label':'1주 전 대비','value':f'{pct_week:+.1f}%','detail':str(row.get('day3',''))})
                pieces.append(f'1주 전 {week:,.0f}원/{unit}, {pct_week:+.1f}%')
            if pct_month is not None:
                facts.append({'label':'1개월 전 대비','value':f'{pct_month:+.1f}%','detail':str(row.get('day5',''))})
                pieces.append(f'1개월 전 {month:,.0f}원/{unit}, {pct_month:+.1f}%')
            if pct_year is not None:
                facts.append({'label':'전년 조사 대비','value':f'{pct_year:+.1f}%','detail':str(row.get('day6',''))})
                pieces.append(f'전년 조사 {year:,.0f}원/{unit}, {pct_year:+.1f}%')
            if pct_previous is not None and pct_week is None and pct_month is None and pct_year is None:
                facts.append({'label':'이전 실제 조사 대비','value':f'{pct_previous:+.1f}%',
                              'detail':str(previous_day)})
                pieces.append(f'{previous_day} 가격 {previous:,.0f}원/{unit}, 직전 조사 대비 {pct_previous:+.1f}%')
            if len(facts)<2:continue
            results.append({'id':f'kamis_{cls}_{key}','name':f'{full} {cls}가격',
                'title':f'{full} {cls}가격'+(f' 전년 대비 {pct_year:+.1f}%' if pct_year is not None else (f' 전주 대비 {pct_week:+.1f}%' if pct_week is not None else (f' 전월 대비 {pct_month:+.1f}%' if pct_month is not None else f' 직전 조사 대비 {pct_previous:+.1f}%'))),
                'subtitle':f'KAMIS {cls} 조사 · {datekey}', 'period_start':str(row.get('day6') or row.get('day3') or row.get('day5') or ''),
                'period_end':datekey,'facts':facts,'observed':' · '.join(pieces),
                'data_links':[{'url':KAMIS_PAGE,'label':'aT KAMIS 수산물 도소매 가격 공식 API'}],
                'article_ids':[],'category':'원물 수급/시세','channels':[],
                'impact':f'{cls} 관측가격 변화','source_type':'공식 공개 API','series_type':'kamis',
                'limitations':f'KAMIS 조사품목 {name}, 품종 {kind or "미표시"}, 등급 {rank or "미표시"}, 단위 {unit}, {cls} 조사값. 조사 지역·표본 변경, 행사 및 거래 규격에 따라 차이 발생. 산지가/수입통관가격과 단위 및 대상이 다르므로 직접 비교 불가.',
                'measurements':{'item':name,'kind':kind,'rank':rank,'unit':unit,'channel':cls,'current_price':cur,'week_price':week,'month_price':month,'year_price':year,
                                'week_pct':pct_week,'month_pct':pct_month,'yoy_pct':pct_year,'previous_pct':pct_previous,'date':datekey},
                'significance':min(40,abs(pct_year or pct_week or pct_month or 0))+(7 if any(k in name for k in ('광어','오징어','고등어','연어','꽃게')) else 0)})
    # A lookback search can return the same commodity on several dates. Keep
    # the latest valid survey observation, not the most dramatic old move.
    newest={}
    for feature in results:
        key=feature['id']
        if key not in newest or feature['measurements']['date']>newest[key]['measurements']['date']:
            newest[key]=feature
    return sorted(newest.values(),key=lambda r:r['significance'],reverse=True)[:limit]

def fetch_kamis_features(as_of=None):
    """Use latest publication, then prior survey days when the newest is absent.

    A retrieved historical observation retains its original survey date. A
    genuine 1-week, 1-month or 1-year comparator is required for a report.
    """
    key=os.getenv('KAMIS_API_KEY','').strip()
    ident=os.getenv('KAMIS_API_ID','').strip()
    if not (key and ident):return [],['KAMIS: KAMIS_API_KEY / KAMIS_API_ID 미설정 — 수산물 도소매 조사 미연결']
    as_of=as_of or date.today()
    errors=[]
    found={'도매':[],'소매':[]}
    attempts=[None]+[as_of-timedelta(days=n) for n in (3,7,14,21,28,42)]
    for day in attempts:
        # Continue probing only groups for which no comparable observations exist.
        need=[(name,code) for name,code in (('도매','02'),('소매','01'))
              if not kamis_features_from_rows(found[name] if name=='도매' else [],
                 found[name] if name=='소매' else [],as_of=as_of)]
        if not need:break
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={name:pool.submit(_request_kamis,code,key,ident,day) for name,code in need}
            for name,future in futures.items():
                try:
                    rows=future.result()
                    found[name].extend(rows)
                    print(f'SEAFOOD KAMIS {name} request={day.isoformat() if day else "latest"}: raw={len(rows)} '
                          f'comparable={len(kamis_features_from_rows(rows if name=="도매" else [],rows if name=="소매" else [],as_of=as_of))}',flush=True)
                except (requests.RequestException,ValueError,KeyError,TypeError,ET.ParseError) as exc:
                    kind=type(exc).__name__
                    # Date and type, but no credentials or raw URLs, appear in logs.
                    errors.append(f'KAMIS {name} {day.isoformat() if day else "latest"}: {kind}: {str(exc)[:60] if isinstance(exc,ValueError) else "request failed"}')
                    # Auth failures cannot be fixed by trying older dates.
                    if isinstance(exc,ValueError) and 'denied or unavailable' in str(exc):
                        print('SEAFOOD KAMIS authorization failed; stop historical retries',flush=True)
                        return [],errors
    # Compare observations at two real survey dates for the same product / grade /
    # unit only when the response has no populated dpr3/dpr5/dpr6 comparator.
    for channel in ('도매','소매'):
        by_item={}
        for row in found[channel]:
            sampled=_kamis_day(row.get('day1') or row.get('lastest_date'),as_of)
            cur=_float(row.get('dpr1'))
            if sampled is None or cur is None or cur<=0:continue
            key=tuple(str(row.get(k,'')).strip() for k in
                  ('item_name','kind_name','rank','unit'))
            by_item.setdefault(key,[]).append((sampled,cur,row))
        for rows in by_item.values():
            rows.sort(key=lambda x:x[0],reverse=True)
            for i,(sampled,cur,row) in enumerate(rows):
                earlier=next(((old,p) for old,p,_ in rows[i+1:]
                              if old<sampled and 1<=(sampled-old).days<=45),None)
                if earlier and not any(_float(row.get(x)) for x in ('dpr3','dpr5','dpr6')):
                    row['_real_previous_date']=earlier[0].isoformat()
                    row['_real_previous_price']=earlier[1]
    results=kamis_features_from_rows(found['도매'],found['소매'],as_of=as_of)
    if not results:
        # Safe diagnostics: field names and reason counts, no key or raw URLs.
        for channel in ('도매','소매'):
            reasons={'non_target_species':0,'no_current_price':0,'no_survey_date':0,
                     'stale_survey_date':0,'no_comparator':0}
            for row in found[channel]:
                item=str(row.get('item_name') or '')
                if not any(re.search(pat,item) for _,pat in SPECIES):reasons['non_target_species']+=1;continue
                cur=_float(row.get('dpr1'))
                if cur is None or cur<=0:reasons['no_current_price']+=1;continue
                day=_kamis_day(row.get('day1') or row.get('lastest_date'),as_of)
                if day is None:reasons['no_survey_date']+=1;continue
                if (as_of-day).days>45:reasons['stale_survey_date']+=1;continue
                if not any(_float(row.get(k)) for k in ('dpr3','dpr5','dpr6','_real_previous_price')):
                    reasons['no_comparator']+=1
            example_keys=list(found[channel][0])[:16] if found[channel] else []
            date_samples=list(dict.fromkeys(str(r.get('day1') or r.get('lastest_date') or '')[:25]
                for r in found[channel] if r.get('day1') or r.get('lastest_date')))[:3]
            print(f'SEAFOOD KAMIS {channel} rejected: {reasons}; '
                  f'response_fields={example_keys}; date_formats={date_samples}',flush=True)
    print(f'SEAFOOD KAMIS: wholesale_raw={len(found["도매"])} '
          f'retail_raw={len(found["소매"])} published={len(results)}',flush=True)
    if not results and not errors:errors.append('KAMIS: 최근 45일 중 비교 가능한 도소매 조사 가격 없음')
    return results,errors

def make_public_features(now):
    """Independent sources; one failed API does not suppress the other datasets."""
    from seafood_mof_statistics import fetch_statistics_features
    with ThreadPoolExecutor(max_workers=3) as pool:
        task_mof=pool.submit(fetch_mof_features,now.date())
        task_kamis=pool.submit(fetch_kamis_features,now.date())
        task_stats=pool.submit(fetch_statistics_features)
        try:trade,trade_errors=task_mof.result()
        except Exception as exc:trade,trade_errors=[],['MOF: '+type(exc).__name__]
        try:prices,price_errors=task_kamis.result()
        except Exception as exc:prices,price_errors=[],['KAMIS: '+type(exc).__name__]
        try:statistics,stats_errors=task_stats.result()
        except Exception as exc:statistics,stats_errors=[],['MOF statistics: '+type(exc).__name__]
    return trade+prices+statistics,trade_errors+price_errors+stats_errors
