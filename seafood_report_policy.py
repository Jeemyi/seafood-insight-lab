"""Evidence-sensitive editorial categories, not fixed commodity quotas.

The quantitative validator runs BEFORE this classifier. A single reliable
primary source can support an important policy event or a data brief, but not
an unqualified multivariable deep report. Nothing here verifies causality.
"""
from __future__ import annotations

from urllib.parse import urlparse
import re
from seafood_numeric_audit import numeric_observations
from seafood_research_depth import published_report_evidence, source_family

PRIMARY_DOMAINS=(
    'go.kr','data.go.kr','ssb.no','seafood.no','produccion.gob.pe',
    'gov','gov.uk','gov.au','gov.cn','gov.jp','europa.eu',
    'fao.org','oecd.org','kamis.or.kr','bok.or.kr','foc.re.kr',
)
POLICY_EVENT=re.compile(r'(검역|검사|식품안전|통관|규제|금지|허용|어획.{0,4}한도|쿼터|조업.{0,4}(제한|중단)|'
                        r'관세|발효|시행|리콜|회수|적발|영업정지|수입금지|폐점|법정관리|회생|'
                        r'quota|recall|tariff|restriction|ban\b)',re.I)


def primary_source(row):
    links=row.get('data_links') or []
    url=str(row.get('url') or (links[0].get('url','') if links and isinstance(links[0],dict) else ''))
    host=(urlparse(url).hostname or '').lower()
    source_type=str(row.get('source_type') or '').lower()
    if '공식' in source_type or 'official' in source_type:return True
    for d in PRIMARY_DOMAINS:
        if host==d or host.endswith('.'+d):return True
    return False


def factual_market_numbers(text):
    """Reject dates/indices as a source of quantitative market depth."""
    return [n for n in numeric_observations(text)
            if not n['unit'].startswith('date:') and n['unit'] not in ('plain',)]


def evidence_class(report,facts,evidence_by_id):
    checked={**report,'facts':facts}
    detail=published_report_evidence(checked,evidence_by_id)
    cited={sid for fact in facts for sid in fact.get('refs',[]) if sid in evidence_by_id}
    source_ids={source_family(evidence_by_id[sid]) for sid in cited}
    originals=[sid for sid in cited if primary_source(evidence_by_id[sid])]
    measured=[fact for fact in facts if factual_market_numbers(fact.get('text',''))]
    has_policy=bool(POLICY_EVENT.search(' '.join(f.get('text','') for f in facts)))
    independent=len(source_ids)
    # Article-level quantitative measurements must support the *fact citations*.
    deep=(len(measured)>=2 and len(facts)>=2 and independent>=2 and
          detail['distinct_numeric_facts']>=2 and len(detail['dimensions'])>=2)
    if deep:
        return '심층 시장 분석',detail
    if (has_policy and (originals or independent>=2)) or (len(facts)>=2 and independent>=2):
        return '주요 산업 이슈',detail
    if measured and originals:
        return '데이터 브리핑',detail
    return None,detail
