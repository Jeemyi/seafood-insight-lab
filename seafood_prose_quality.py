"""Soft editorial review for evidence-led articles.

This is NOT a numeric fact checker. It flags low-information prose for a
bounded, optional rewrite. Sources, dates, numeric claims and market identity
are still enforced by seafood_ai._validate_main. No numerical quota is set.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from copy import deepcopy
import re
from seafood_numeric_audit import numeric_observations

_GENERIC_PATTERNS=(
    r'(?:서로|별개|다른)\s*질문(?:이다|이므로|으로)',
    r'(?:해석|구분|판단|확인|살펴|검토).{0,13}(?:해야\s*한다|할\s*필요가\s*있다|중요하다|하면\s*안\s*된다)',
    r'(?:시사점|인사이트|구조적\s*통찰|일반적으로|경제\s*원리)',
    r'(?:변수|요인)로\s*작용할\s*(?:수\s*있다|것)',
    r'(?:(?:영향|부담|변화|차이).{0,8}(?:있을|나타날)\s*수\s*있다)',
)
_GENERIC=re.compile('|'.join(f'(?:{p})' for p in _GENERIC_PATTERNS))


# A detached methodology/caveat sentence is not an industry insight.
# These narrowly scoped forms are safe to delete from already-verified prose.
# Material uncertainty about the actual finding stays in the source metadata.
_DETACHED_CAVEAT_PATTERNS = (
    re.compile(r'^(?:다만\s*)?(?:수출|수입|생산|어획|가격)\s*통계(?:는|가|의)?.{0,130}(?:특정\s*규격|실제\s*판매가격|상품\s*형태).{0,100}(?:같지(?:는)?\s*않|아니|어렵)(?:다|는다)?[.!?]?$', re.I),
    re.compile(r'^두\s*(?:생산|수출|수입|가격)\s*통계.{0,180}(?:단순\s*합산|동일\s*원료|같은\s*수치).{0,90}(?:어렵|안\s*된다|달라)(?:다|진다)?[.!?]?$', re.I),
)


def detached_caveat_sentences(text):
    """Only very specific standalone caveats, never substantive evidence."""
    sentences = [x.strip() for x in re.split(r'(?<=[.!?])\s+(?=[가-힣A-Za-z])', text or '') if x.strip()]
    return [part for part in sentences if any(p.search(part) for p in _DETACHED_CAVEAT_PATTERNS)]


def drop_detached_caveats(report):
    """Last-resort deletion-only edit if the model rewrite cannot be afforded.

    A removal may not introduce or change numbers, dates or attribution. If
    removing a whole mechanism paragraph would invalidate a deep report's
    minimum structure, leave it for future editorial revision.
    """
    result=deepcopy(report)
    edited=[]
    for key in ('lead','market_change','structural_insight'):
        value=str(result.get(key) or '')
        bad=detached_caveat_sentences(value)
        if not bad:continue
        new=' '.join(x.strip() for x in re.split(r'(?<=[.!?])\s+(?=[가-힣A-Za-z])',value)
                     if x.strip() and x.strip() not in bad)
        if new:
            result[key]=new; edited.append(key)
    mechanism=list(result.get('mechanism') or [])
    clean=[]; changed=False
    for paragraph in mechanism:
        bad=detached_caveat_sentences(paragraph)
        if not bad:
            clean.append(paragraph);continue
        new=' '.join(x.strip() for x in re.split(r'(?<=[.!?])\s+(?=[가-힣A-Za-z])',paragraph)
                     if x.strip() and x.strip() not in bad)
        if new:clean.append(new);changed=True
        else:changed=True
    minimum=2 if result.get('report_type')=='심층 시장 분석' else 0
    if changed and len(clean)>=minimum:
        result['mechanism']=clean;edited.append('mechanism')
    if edited:result['editorial_caveat_trimmed']=True
    return result


def _has_measure(text):
    return any(n['unit'] not in ('plain',) and not n['unit'].startswith('date:')
               for n in numeric_observations(text or ''))


def _similar(a,b):
    # A repeated topic term or ordinary shared figure isn't a duplicated paragraph.
    a=re.sub(r'\s+', '',a or '')
    b=re.sub(r'\s+', '',b or '')
    return len(a)>=45 and len(b)>=45 and SequenceMatcher(None,a,b).ratio() >= .80


def review_prose(report):
    """Return *advice*, not reject reasons; can be empty for short accurate news.

    A number is useful only when linked to the SAME source-backed market fact.
    Policy news without a market percentage is legitimate and will not receive
    a "more numbers" requirement.
    """
    change=str(report.get('market_change') or '')
    lead=str(report.get('lead') or '')
    mechanism=[str(x) for x in (report.get('mechanism') or []) if x]
    impact=str(report.get('structural_insight') or '')
    outlook=report.get('outlook') or {}
    sections=[change,*mechanism,impact,str(outlook.get('judgment') or '')]
    notes=[]
    detached=[x for x in [lead,*sections] if detached_caveat_sentences(x)]
    if detached:
        notes.append('통계 해석 주의 문장을 본문에 길게 노출했다. 통계의 실제 관측 결과·변동 규모·시장 주체에 대한 결론으로 대체하라. 반드시 필요한 통계 범위 설명은 limitations 메타데이터로 옮겨라.')
    generic=[x for x in sections if _GENERIC.search(x)]
    if len(generic)>=2:
        notes.append('방법론·일반론 문장이 여러 군데 있다. 실제 확인된 시장 변화와 구체적 영향으로 바꾸거나 삭제하라.')
    if _similar(lead,change) or _similar(change,impact) or any(
        _similar(a,b) for i,a in enumerate(mechanism) for b in mechanism[i+1:]):
        notes.append('변화·배경·영향 중 같은 사실을 문장만 바꿔 반복한다. 새 근거 또는 다른 작동 과정을 설명하고, 없으면 합쳐라.')
    facts=' '.join(str(f.get('text') or '') for f in report.get('facts',[]))
    if _has_measure(facts) and not _has_measure(' '.join(sections+[lead])):
        notes.append('핵심 근거에는 실제 시장 수치가 있는데 본문에서 빠졌다. 가장 직접적인 수치 1~2개만 기준기간·단위와 함께 자연스럽게 반영하라.')
    # A forecast with direction but no market-relevant change is weak, but its
    # absence is NOT a fault for a policy update / data brief.
    judgment=str(outlook.get('judgment') or '')
    if outlook.get('direction') not in (None,'전망 제외') and judgment and _GENERIC.search(judgment):
        notes.append('전망이 추상적이다. 실제 관측치가 뒷받침하는 공급·판매·가격·정책 조건 한 가지로 좁혀라.')
    return notes


def repair_guidance(notes):
    return ('편집 데스크의 문장 품질 보완. 아래 문제만 수정하고 **새 사건·새 숫자·새 출처를 만들어내지 마라**: '
            + ' / '.join(notes[:3]) + '. '
            '시장 변화에는 무엇이 얼마나 달라졌는지, 배경에는 확인 가능한 원인과 실제 거래·생산 과정을, '
            '영향/전망에는 누가 어떤 조건에서 영향을 받는지 쓴다. '
            '절대 수치·비교 기간·품목·규격은 출처가 있을 때만 적는다. '
            '근거 없는 수치와 억지로 엮은 통계는 넣지 않는다. 숫자 개수 할당은 없다. '
            '특히 결론을 통계상 서로 다르다/합산이 어렵다/실제 가격과 같지 않다 로 끝내지 마라. '
            '이미 제시된 물량·금액·단가·기준기간으로 도출 가능한 실제 결과를 쓰고, '
            '근거가 없는 경우에는 억지로 결론을 추가하지 말고 해당 문장을 삭제하라. '
            '필수 집계 범위 정보는 limitations 메타데이터에만 기록하라. '
            '기존 facts.refs 연결을 유지하고, 간결해져도 좋다. 그럴듯한 일반론 대신 실증적으로 한 가지 더 알려라.')
