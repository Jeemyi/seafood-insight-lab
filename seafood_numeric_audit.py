"""Conservative but tolerant numeric citation checks for Korean market reporting.

Accept measurements that differ within a small reporting/rounding tolerance.
NEVER apply relative tolerance to year, month, day, week number, or identifiers.
Compare compatible units and (when recognizable) the same market measure.
Evidence supplied by the publishing pipeline remains public-source-only.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os
import re

_NUMBER = r'\d[\d,]*(?:\.\d+)?'
# Korean combined forms: "15만 9,810톤", "3만1천톤", "1억 2,000만".
_QUANTITY = rf'(?:{_NUMBER}\s*[억만천]\s*){{1,4}}(?:{_NUMBER})?|{_NUMBER}'
_PATTERN = re.compile(
    rf'(?<![\w])(?P<sign>[+\-−]?)(?P<value>{_QUANTITY})\s*(?P<unit>USD/kg|NOK/kg|달러/kg|원/kg|퍼센트포인트|%p|pp|bp|퍼센트|킬로그램|톤|달러|크로네|원|kg|㎏|주차|개월|년도|년|월|일|주|배|곳|명|개|건|%|t\b)?',
    re.I,
)
_COMPONENT = re.compile(rf'({_NUMBER})\s*([억만천])')
_SCALE = {'억': Decimal(100000000), '만': Decimal(10000), '천': Decimal(1000)}
_METRICS = (
    ('수출가격','export_price'), ('수입가격','import_price'),
    ('수입단가','import_price'), ('수출단가','export_price'),
    ('도매가격','wholesale_price'), ('소매가격','retail_price'),
    ('수출물량','exports'), ('수출량','exports'), ('수입물량','imports'), ('수입량','imports'),
    ('어획량','landings'), ('양륙량','landings'), ('출하량','shipments'),
    ('생산량','production'), ('수확량','harvest'), ('판매량','sales'), ('소비량','consumption'),
    ('정산 지연','settlement'), ('대금 정산','settlement'), ('매출액','revenue'), ('매출','revenue'),
    ('수출액','export_value'), ('수입액','import_value'),
    ('환율','fx'), ('가격','price'), ('단가','price'), ('시세','price'),
)
_DATE_UNITS = {'년','년도','월','일','주','주차','개월'}
_APPROX = re.compile(r'(?:약|가량|대략|내외|안팎|수준|정도|여\s*$)')


def _decimal(text: str) -> Decimal | None:
    try:
        raw = text.strip()
        if any(c in raw for c in _SCALE):
            total = Decimal(0)
            last = 0
            for match in _COMPONENT.finditer(raw):
                total += Decimal(match.group(1).replace(',','')) * _SCALE[match.group(2)]
                last = match.end()
            tail = raw[last:].strip()
            if tail:
                total += Decimal(tail.replace(',',''))
            return total
        return Decimal(raw.replace(',',''))
    except (InvalidOperation, ValueError):
        return None


def _unit(unit: str, prefix: str) -> str:
    unit = (unit or '').lower().replace('㎏','kg')
    if unit in ('%','퍼센트'):return 'percent'
    if unit in ('pp','%p','퍼센트포인트'):return 'percentage_point'
    if unit == 'bp':return 'basis_point'
    if unit in _DATE_UNITS:return 'date:'+unit
    if unit in ('톤','t'):return 'ton'
    if unit in ('kg','킬로그램'):return 'kg'
    if unit in ('usd/kg','달러/kg'):return 'usd_per_kg'
    if unit in ('nok/kg',):return 'nok_per_kg'
    if unit == '원/kg':return 'won_per_kg'
    if unit == '달러' or prefix == '$':return 'usd'
    if unit == '크로네':return 'nok'
    if unit == '원' or prefix == '₩':return 'won'
    if unit == '배':return 'ratio'
    if unit in ('곳','명','개','건'):return 'count'
    return 'plain'


def _metric_near(text: str, start: int, end: int) -> str:
    """Use the local sentence, not metric words in preceding JSON fields."""
    # Delimiters in source text are explicit newlines; periods followed by a
    # space split Korean narrative sentences (but not decimals like 74.98).
    left=text.rfind('\n',0,start)+1
    boundaries=[left]
    boundaries += [m.end() for m in re.finditer(r'(?:다\.|[!?])\s+',text[left:start])]
    left=max(boundaries)
    right=text.find('\n',end)
    if right<0:right=len(text)
    nxt=re.search(r'(?:다\.|[!?])\s+',text[end:right])
    if nxt:right=end+nxt.start()
    segment=text[left:right]
    found=[]
    for word,label in _METRICS:
        for match in re.finditer(re.escape(word),segment):
            p=left+match.start()
            distance=max(start-(p+len(word)), p-end, 0)
            found.append((distance,-len(word),label))
    if not found:return ''
    found.sort()
    # Long-distance matches in a lengthy sentence are weak context: leave
    # unlabeled rather than attaching the wrong market measure.
    return found[0][2] if found[0][0]<=95 else ''


def numeric_observations(text: str) -> list[dict]:
    text=str(text or '')
    found=[]
    for match in _PATTERN.finditer(text):
        raw=match.group('value')
        value=_decimal(raw)
        if value is not None and match.group('sign') in ('-','−'):
            value=-value
        if value is None:continue
        prefix=text[max(0,match.start()-1):match.start()]
        unit=_unit(match.group('unit'),prefix)
        if unit=='usd' and text[match.end():match.end()+3]=='/kg':unit='usd_per_kg'
        if unit=='plain' and value==int(value) and Decimal(1900)<=value<=Decimal(2100):
            # Bare Gregorian year in source metadata or '2025 vs 2026'.
            unit='date:년'
        # A standalone one-digit number is usually a list index. Keep it if it
        # carries a real unit: e.g. 8달러, 3%, 1년.
        if len(raw.strip())<2 and unit=='plain':continue
        start,end=match.span()
        before=text[max(0,start-13):start].strip()
        after=text[end:min(len(text),end+10)].strip()
        if unit in ('percent','percentage_point') and match.group('sign') not in ('-','−','+'):
            # Sources often write '7.3% 감소', while summaries write '-7.3%'.
            if re.match(r'(?:가량\s*)?(?:감소|하락|축소|줄었|줄어|내렸|떨어|낮아|역성장)',after) or re.search(r'(?:감소율|하락률|축소율)\s*$',before):
                value=-value
        approx=bool(_APPROX.search(before))
        found.append({'raw':text[start:end].strip(), 'value':value, 'unit':unit,
                      'metric':_metric_near(text,start,end), 'approx':approx,
                      'start':start, 'end':end})
    return found


def _limit(name: str, default: str, minimum: float, maximum: float) -> Decimal:
    try:val=float(os.getenv(name,default))
    except ValueError:val=float(default)
    return Decimal(str(min(max(val,minimum),maximum))) / 100


def _compatible(a: dict, b: dict) -> bool:
    if a['unit'] != b['unit']:
        return False
    if a['unit'].startswith('date:'):
        return True  # Year/week/date are exact by value, not by topic label.
    a_metric,b_metric=a['metric'],b['metric']
    if a_metric and b_metric and a_metric!=b_metric:
        # An absolute export volume often appears next to an export *value*
        # label in a mixed statistics sentence; tonnes are still tonnes.
        if a['unit']=='ton' and {a_metric,b_metric}=={'export_value','exports'}:
            return True
        if a['unit']=='ton' and {a_metric,b_metric}=={'import_value','imports'}:
            return True
        if a['unit']=='percent':
            # A source-local exact percentage may occur in a sentence with two
            # metrics; the inferred nearest label is only a heuristic.
            return {a_metric,b_metric} not in ({'exports','imports'},
                                              {'import_price','export_price'})
        # General 'price' can reference a specifically labeled observed price.
        if a_metric!='price' and b_metric!='price':return False
        if a_metric not in ('price','export_price','import_price','wholesale_price','retail_price'):
            return False
        if b_metric not in ('price','export_price','import_price','wholesale_price','retail_price'):
            return False
    return True


def _similar(a: dict, b: dict) -> bool:
    if not _compatible(a,b):return False
    av,bv=a['value'],b['value']
    if a['unit'].startswith('date:'):
        return av==bv
    if a['unit'] in ('count',):
        # Survey respondent totals and enumerated units are discrete values.
        return av==bv
    if a['unit'] in ('basis_point',):return abs(av-bv)<=Decimal('0.5')
    if av==bv:return True
    if a['metric'] and b['metric'] and a['metric']!=b['metric']:
        related=({'export_value','exports'},{'import_value','imports'},
                 {'price','export_price'},{'price','import_price'},
                 {'price','wholesale_price'},{'price','retail_price'})
        if {a['metric'],b['metric']} not in related:
            return False  # Similar-but-different metrics must not match by luck.
    rel=_limit('SEAFOOD_NUMERIC_TOLERANCE_PCT','3',0,5)
    if a['approx'] or b['approx']:
        rel=max(rel,_limit('SEAFOOD_APPROX_TOLERANCE_PCT','5',0,8))
    diff=abs(av-bv)
    if a['unit'] in ('percent','percentage_point'):
        # Allow publication rounding, but not arbitrary small-rate changes.
        rounded=Decimal('0.12') if max(abs(av),abs(bv))>=Decimal('3') else Decimal('0.03')
        return diff<=rounded or (max(abs(av),abs(bv))>0 and
                                diff/max(abs(av),abs(bv))<=rel)
    return max(abs(av),abs(bv))>0 and diff/max(abs(av),abs(bv))<=rel


def missing_numeric_claims(claim: str, source_text: str) -> list[dict]:
    source=numeric_observations(source_text)
    missing=[]
    for item in numeric_observations(claim):
        if any(_similar(item, candidate) for candidate in source):continue
        compatible=[s for s in source if _compatible(item,s)]
        compatible.sort(key=lambda s:abs(s['value']-item['value']))
        missing.append({'claim':item['raw'],'unit':item['unit'],
                        'metric':item['metric'],
                        'nearest_source':compatible[0]['raw'] if compatible else None})
    return missing


def supported(claim: str, source_text: str) -> bool:
    return not missing_numeric_claims(claim,source_text)


def evidence_number_inventory(records: list[dict], limit_per_source: int = 18) -> list[dict]:
    """Only used to guide model correction; numbers remain linked to public IDs."""
    from json import dumps
    result=[]
    for row in records:
        payload=dumps({k:v for k,v in row.items() if k not in ('id','url','data_links')},ensure_ascii=False)
        numbers=[]
        for n in numeric_observations(payload):
            if n['raw'] not in numbers:numbers.append(n['raw'])
            if len(numbers)>=limit_per_source:break
        result.append({'id':row.get('id'),'numbers':numbers})
    return result
