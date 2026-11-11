"""Select market mechanisms, not loose thematic co-mentions.

Evidence clusters are hints for the model's own editorial decision. They never
prove causation, forecast a price, or include private business information.
"""
from __future__ import annotations
from urllib.parse import urlparse
import re

# Publicly relevant seafood markets and channels, deliberately much narrower
# than a keyword such as 'online', 'economy', 'growth', or 'food'.
SUBJECTS = (
    ('광어·우럭 양식 수급', ('광어', '넙치', '우럭', '조피볼락')),
    ('오징어 국내외 공급', ('오징어', '대왕오징어', '페루산 오징어')),
    ('고등어 국내외 공급', ('고등어', 'mackerel')),
    ('연어 국제 수급', ('연어', 'salmon')),
    ('꽃게·갑각류 공급', ('꽃게', '대게', '새우', 'shrimp')),
    ('방어·참치·회 원료', ('방어', '참치', 'tuna')),
    ('기타 주요 수산물', ('문어', '장어', '낙지', '주꾸미', '굴', '조기')),
    ('대형마트·창고형 유통', ('홈플러스','코스트코','이마트','롯데마트','트레이더스','대형마트','ssm')),
    ('회·초밥·가공 수산식품', ('회초밥','횟감','초밥','필렛','네타','수산물 간편식','수산 밀키트')),
    ('수산물 온라인 판매', ('온라인 수산','신선 수산','수산물 배송','수산물 온라인','수산물 이커머스')),
    ('수산물 식품안전·통상 규제', ('수산물 검역','수산물 검사','mmpa','수산물 수입금지','양식 규제')),
)
SIGNALS = {
    '공급': ('어획','양식','생산량','생산','출하','쿼터','자원량','양성물량','공급','재고','위판'),
    '가격': ('가격','산지가','수출가','평균단가','도매가','소매가','시세','가격지수'),
    '수출입': ('수출','수입','통관','무역','원산지','수입국','수출국'),
    '수요': ('소비','판매량','매출','수요','가정 내','외식','판매','구매'),
    '유통': ('점포','폐점','철수','매각','입점','배송','신제품','상품','유통','매장'),
    '제도': ('규제','검사','허가','금어기','관세','법안','안전','검역','협정'),
}


def _record_text(row):
    return ' '.join(str(row.get(k,'')) for k in ('title','name','snippet','observed','summary')) .lower()


def _identity(row):
    links=row.get('data_links') or []
    url=row.get('url') or (links[0].get('url','') if links and isinstance(links[0],dict) else '')
    host=(urlparse(url).hostname or '').lower().removeprefix('www.')
    # Google News RSS links are redirects; different publishers must not all
    # be treated as one independent Google source. Use the extracted publisher.
    if host=='news.google.com':
        publisher=str(row.get('source') or '').strip().lower()
        return publisher or 'news.google.com'
    for official in ('ssb.no','data.go.kr','kamis.or.kr','ecos.bok.or.kr','foc.re.kr','mof.go.kr'):
        if host.endswith(official):return official
    return host or str(row.get('source') or row.get('name') or '').strip().lower()


def build_story_clusters(articles, features, previous_headlines=None, limit=7):
    """Build *potential* evidence connections, preserving scope and provenance.

    The gate demands distinct origins AND kinds of market measurements/events.
    It rejects arbitrary company-earnings collections under 'online growth'.
    """
    records=[]
    for kind, rows in (('article',articles),('official',features)):
        for row in rows:
            if not row.get('id'):continue
            text=_record_text(row)
            if len(text.strip())<12:continue
            signals=[label for label,words in SIGNALS.items() if any(w in text for w in words)]
            records.append({'row':row,'kind':kind,'text':text,'signals':signals,'origin':_identity(row)})
    past=' '.join(previous_headlines or []).lower()
    results=[]
    for subject,terms in SUBJECTS:
        matches=[r for r in records if any(token in r['text'] for token in terms)]
        origins={r['origin'] for r in matches if r['origin']}
        signals=set(label for r in matches for label in r['signals'])
        # One source saying two things is not multi-source investigation.
        if len(matches)<2 or len(origins)<2 or len(signals)<2:continue
        # Avoid topic candidates that are only unrelated commodity price promotions.
        if signals <= {'가격','유통'}:continue
        # The model will decide whether these observations are *actually* connected.
        matches.sort(key=lambda e:(e['kind']=='official', bool(re.search(r'\d',e['text'])),len(e['signals'])),reverse=True)
        unique=[];seen=set()
        for r in matches:
            if r['row']['id'] in seen:continue
            seen.add(r['row']['id']);unique.append(r)
            if len(unique)>=8:break
        distinct_origins={r['origin'] for r in unique if r['origin']}
        distinct_signals={s for r in unique for s in r['signals']}
        if len(distinct_origins)<2 or len(distinct_signals)<2:continue
        cross_strength=len(distinct_signals)
        official_count=sum(x['kind']=='official' for x in unique)
        numeric_count=sum(bool(re.search(r'\d',x['text'])) for x in unique)
        novelty_penalty=9 if any(term in past for term in terms[:2] if len(term)>2) else 0
        score=12*cross_strength+7*len(distinct_origins)+6*official_count+3*numeric_count-novelty_penalty
        results.append({'subject':subject,'evidence_ids':[x['row']['id'] for x in unique],
             'distinct_variables':sorted(distinct_signals),'original_sources':sorted(distinct_origins),
             'measurable_records':numeric_count,'score':score,
             'observations':[{'id':x['row']['id'],'text':x['text'][:330]} for x in unique[:6]]})
    return sorted(results,key=lambda r:r['score'],reverse=True)[:limit]
