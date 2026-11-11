"""Public-only, scope-aware research gap map for seafood market stories.

A keyword match is a lead, not proof that two observations are comparable or
causally linked. All data below originate from RSS/public research/official
metrics, never private company material. Quantities are NEVER fabricated.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Commodity/channel anchors avoid grouping every mention of "수출" or "가격"
# into the same invented market.
ANCHORS = {
    '연어': ('연어', 'salmon', 'norwegian salmon', 'mowi', 'salmar'),
    '오징어': ('오징어', '대왕오징어', 'squid', 'pota', 'dosidicus'),
    '광어·우럭': ('광어', '넙치', '우럭', '조피볼락'),
    '고등어': ('고등어', 'mackerel'),
    '새우': ('새우', 'shrimp', 'prawn'),
    '참치': ('참치', 'tuna'),
    '대형마트': ('홈플러스', '이마트', '롯데마트', '대형마트', '트레이더스', '코스트코'),
    '수산물 온라인': ('수산물 온라인', '온라인 수산', '신선식품 온라인'),
    '급식': ('급식', '식자재', '단체급식'),
}
FACETS = {
    'supply': ('생산량', '어획량', '생산', '어획', '수확', '출하량', '출하', '양륙량', '양식', 'harvest', 'landings', 'production'),
    'price': ('수출가격', '수입단가', '도매가격', '소매가격', '가격', '시세', '단가', '달러/kg', 'usd/kg', 'price', 'unit value'),
    'demand': ('소비량', '소비', '가정 내', '판매량', '판매', '소매매출', '매출', '매출액', '거래액', '판매실적', '수요', 'consumption', 'sales', 'demand'),
    'trade': ('수입량', '수출량', '수출물량', '수입', '수출', '통관', '무역', 'imports', 'exports', 'shipments'),
    'policy': ('어획 한도', '어획한도', '쿼터', '금어기', '수입 금지', '검역', '관세', '조업 제한', '규제', 'quota', 'restriction'),
    'distribution': ('점포', '납품', '정산', '폐점', '유통', '물류', '배송', '납품대금', '매장'),
    'fx': ('환율', '달러환산', '달러 환산', '크로네', 'nokr', 'nok/usd', 'usd/nok', 'exchange rate'),
}
# Years alone are not market measurements. Dates can contextualize but should
# not magically count towards numeric depth.
MEASURE = re.compile(r'(?<![\w])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:%|톤|만\s*톤|천\s*톤|kg|킬로그램|원/(?:kg|㎏)|달러/(?:kg|㎏)|달러|억원|억\s*원|개점|개소|개\s*점포|점포|개\s*업체|곳|t\b|tons?\b|kt\b)', re.I)
PRIORITY = ('supply', 'demand', 'price', 'trade', 'policy', 'distribution')
MARKET_AXES={
    '연어':('supply','demand','price','trade'),
    '오징어':('supply','trade','price','policy','demand'),
    '광어·우럭':('supply','price','demand','trade'),
    '고등어':('supply','price','trade','demand'),
    '새우':('trade','price','supply','demand'),
    '참치':('trade','supply','price','demand'),
    '대형마트':('distribution','demand','policy'),
    '수산물 온라인':('demand','distribution'),
    '급식':('demand','distribution','policy'),
}

LABELS = {'supply':'생산·어획·출하', 'demand':'실제 소비·판매', 'price':'가격·수입단가',
          'trade':'국가별 수출입', 'policy':'어획·통상 규제', 'distribution':'유통·납품', 'fx':'환율'}


def anchor_for(topic):
    name=str(topic.get('theme') or topic.get('subject') or '').lower()
    for label,terms in ANCHORS.items():
        if any(t.lower() in name for t in terms) or label.lower() in name:
            return label
    return None


def record_text(row):
    return ' '.join(str(row.get(k) or '') for k in ('title','name','summary','observed','facts','measurements'))


def facets(text):
    low=str(text).lower()
    return [k for k,terms in FACETS.items() if any(t in low for t in terms)]


def source_family(row):
    url=row.get('url','')
    if not url:
        links=row.get('data_links') or []
        url=links[0].get('url','') if links and isinstance(links[0],dict) else ''
    host=(urlparse(str(url)).hostname or '').lower().removeprefix('www.')
    # News redirect domains never stand for independent original publishers.
    if host=='news.google.com':
        return str(row.get('source') or 'news.google.com').strip().lower()
    return host or str(row.get('source') or row.get('name') or '').strip().lower()


def _relevant(row,anchor):
    if not anchor:return False
    text=record_text(row).lower()
    return any(term.lower() in text for term in ANCHORS[anchor])


def numeric_observations(records,anchor):
    """Source-labelled observed measurements; no synthetic arithmetic or data."""
    result=[]; seen=set()
    for row in records:
        if not _relevant(row,anchor):continue
        text=record_text(row)
        # A word such as '소비' elsewhere in a long news excerpt does not
        # demonstrate a measured demand series. Tie dimensions to the portion
        # containing a numerical observation (still a heuristic, never proof).
        matches=list(MEASURE.finditer(text))
        if not matches:continue
        dims=[]
        for m in matches[:12]:
            neighborhood=text[max(0,m.start()-90):min(len(text),m.end()+55)]
            for f in facets(neighborhood):
                if f!='fx' and f not in dims:dims.append(f)
        numbers=list(dict.fromkeys(m.group(0).strip() for m in matches))[:7]
        if not dims:continue
        sid=str(row.get('id') or '')
        if not sid or sid in seen:continue
        seen.add(sid)
        result.append({'id':sid,'source':source_family(row),
                       'facets':dims,'quantities':numbers,
                       'period':str(row.get('period_end') or row.get('published') or '')[:22],
                       'scope':str(row.get('title') or row.get('name') or '')[:110]})
    return result


def evidence_profiles(topics,articles,features,maximum=4):
    """Describe gaps, not causality: output is a *search plan*, not a story."""
    profiles=[]
    records=list(articles)+list(features)
    for topic in topics[:maximum]:
        anchor=anchor_for(topic)
        if not anchor:continue
        observations=numeric_observations(records,anchor)
        dims={d for o in observations for d in o['facets']}
        meaningful_axes=MARKET_AXES.get(anchor,PRIORITY)
        nonfx=[x for x in meaningful_axes if x in dims]
        missing=[x for x in meaningful_axes if x not in dims]
        unique_sources={x['source'] for x in observations if x['source']}
        profiles.append({'theme':topic.get('theme',''),'anchor':anchor,
            'dimensions_present':[LABELS[x] for x in nonfx],
            'dimensions_missing':[LABELS[x] for x in missing],
            'numeric_records':len(observations),'independent_sources':len(unique_sources),
            'observations':observations[:8],
            'gap_queries':gap_queries(anchor,missing)})
    return profiles


def gap_queries(anchor,missing):
    queries=[]
    forms={
      'supply':['공식 어획량 생산량 주간 월간 전년 비교', '생산업체 수확량 분기 실적'],
      'demand':['국가별 소비량 판매량 실적 전년 비교','주요 구매국 소비 수요 추이'],
      'price':['최근 3개월 주간 월간 가격 시계열','수입단가 도매가격 비교 통계'],
      'trade':['국가별 수출량 수입량 금액 전년 비교','최신 월간 통관 실적'],
      'policy':['어획 쿼터 조업 제한 발효일 물량','정부 수입 검역 관세 발표'],
      'distribution':['납품업체 매출 정산 자료', '유통채널 매출 점포 변화'],
    }
    for dimension in missing[:3]:
        for q in forms[dimension][:1]:queries.append(f'{anchor} {q}')
    # A single latest price or volume number is NOT an actual trend. Always
    # search recent comparable history for the axes that matter to this market.
    historical={
        '연어':['연어 최근 12주 수출가격 수출물량 시계열',
              '연어 주요 수입국 소비량 수입량 월별 변화'],
        '오징어':['오징어 최근 6개월 수입량 수입단가 월별 추이',
                '페루 대왕오징어 올해 어획 한도 조업 발표'],
        '광어·우럭':['광어 우럭 최근 3개월 산지가 출하량 수산업관측'],
        '대형마트':['대형마트 최근 분기 점포 매출 납품대금 조사'],
    }
    queries.extend(historical.get(anchor,[f'{anchor} 최신 월간 통계 과거 3개월 비교']))
    return list(dict.fromkeys(queries))[:5]


def published_report_evidence(report,evidence_by_id):
    """Audit only facts explicitly linked to actual public evidence IDs."""
    observations=[];fact_ids=set()
    for fact in report.get('facts',[]):
        text=str(fact.get('text',''))
        if not MEASURE.search(text):continue
        # Do not grant a price claim 'demand coverage' merely because an
        # underlying article also casually mentioned consumption elsewhere.
        dims=set(facets(text))-{'fx'}
        if not dims:continue
        fact_ids.add(re.sub(r'\s+','',text).lower())
        for ref in fact.get('refs',[]):
            row=evidence_by_id.get(ref)
            if not row:continue
            observations.append({'source':source_family(row),'id':ref,'facets':sorted(dims),
                                 'numbers':[m.group(0).strip() for m in MEASURE.finditer(text)]})
    uniq={x['id']:x for x in observations}
    dims={d for x in observations for d in x['facets']}
    sources={x['source'] for x in uniq.values() if x['source']}
    return {'numeric_evidence_records':len(uniq),'distinct_numeric_facts':len(fact_ids),
            'distinct_sources':len(sources), 'dimensions':sorted(dims),
            'details':list(uniq.values())[:8]}
