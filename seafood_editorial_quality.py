"""Small, auditable safeguards for the public homepage.

Scores *events* rather than rewarding a large percentage by itself, and keeps
procedural/methodological filler out of interpretive articles.  This module
never invents a market conclusion and is not a replacement for source checks.
"""
from __future__ import annotations
import re

EFFECTS = (
    (('영업중단','조업중단','전면중단','공급중단','판매중단','수입금지','수출금지','리콜','회생절차','파산'),18),
    (('정산 지연','미지급','점포 폐점','점포 매각','폐업','폐점','철수','검역 강화','관세 부과','금어기','쿼터 소진'),12),
    (('공급 부족','공급 차질','생산 차질','수입 차질','납품 중단','수출 제한','어획 제한','급등','급락'),9),
    (('정부 발표','시행','확정','긴급','수입규제','쿼터','수급','도매가격','산지가','수입량','수출량'),4),
)
LOW_VALUE = ('이벤트','할인 행사','신상품 소개','레시피','맛집','홍보대사','협찬')
NUMERIC_PRESS_RELEASE = ('통계','생산량','수출량','어획량','수출액','조사 결과')
FILLER_PATTERNS = (
    r'별도로 (?:검증|확인|살펴)(?:해야|할 필요)',
    r'(?:추가|향후) (?:확인|검증|조사)(?:이|가)? 필요',
    r'판단(?:하|하기) (?:어렵|전에는)',
    r'(?:단정|확정)할 수 없',
    r'[^.]{0,40}지표(?:로|만으로) (?:판단|해석)하면 안',
    r'(?:자료|통계)를 (?:살펴|함께 봐|대조해)야',
    r'(?:인과 경로|구조적 통찰|조건부 경로|양적 측면|시사점|관측이 강화)',
    r'(?:주목해야 할|확인해야 할) (?:지표|변수)',
    r'(?:A|가)이면 [^.]{0,70}(?:B|나)일 수 있',
)


def event_priority(issue, source_rows, now=None):
    """Rank editorial priority; magnitude without real consequences is not impact.

    High score represents a reason to *read* the original.  It never proves
    that the reported event caused any other market movement.
    """
    headline=str(issue.get('headline') or '').lower()
    text=' '.join((str(r.get('title',''))+' '+str(r.get('summary',''))[:170]).lower() for r in source_rows)
    score=18.0
    for terms,points in EFFECTS:
        if any(term in headline for term in terms):score+=points
        elif any(term in text for term in terms):score+=points*.5
    if any(t in headline for t in LOW_VALUE):score-=20
    # Percentages cannot by themselves establish economy-wide relevance.
    if re.search(r'\d+(?:\.\d+)?\s*%',headline):score+=1
    if any(t in headline for t in NUMERIC_PRESS_RELEASE) and not any(t in headline for t in
            ('금지','차질','중단','부족','폐점','회생','급등','급락','규제','관세')):
        score-=5
    publishers={str(r.get('source','')).strip().lower() for r in source_rows if r.get('source')}
    if len(publishers)>1:score+=min(8,3*(len(publishers)-1))
    if len(source_rows)>1:score+=min(4,len(source_rows)-1)
    # A historical/dummy item must not outrank a timely news event by its title.
    if now is not None and issue.get('lead_published'):
        from datetime import datetime
        try:
            age=(now-datetime.fromisoformat(issue['lead_published'])).total_seconds()/86400
            score+=8 if 0<=age<=2 else 4 if 0<=age<=7 else -15
        except ValueError:pass
    # Preserve original RSS relevance as a small tiebreaker, not the main score.
    score+=min(6,max(0,float(issue.get('score',0)))*.12)
    return round(score,2)


def editorial_filler_flags(text):
    text=str(text or '')
    return [p for p in FILLER_PATTERNS if re.search(p,text,re.IGNORECASE)]


def substantive_news_analysis(item):
    """No homepage analysis made mainly of methodology or hedging."""
    fields=[item.get(k,'') for k in ('observed_change','interpretation','conclusion')]
    if any(not isinstance(x,str) or len(x.strip())<22 for x in fields):return False
    filler=sum(len(editorial_filler_flags(x)) for x in fields)
    if filler>=2:return False
    if not strong_editorial_claim(item.get('headline',''),item.get('conclusion','')):return False
    if len(set(re.sub(r'\s+','',x) for x in fields))<3:return False
    return True


# Editorial-value failures that keyword-only removal in v5.30 could not catch.
# These are *publish-time* checks, not user-facing explanations.
NO_VALUE_PATTERNS=(
    r'(?:환율|통화).{0,50}(?:가격|실적).{0,35}(?:달라질 수|방향이 달랐|흐름은 달랐)',
    r'서로 다른 (?:방향|흐름)(?:으로)? (?:움직|나타)',
    r'(?:곧바로|반드시).{0,45}(?:의미하지|연결되지|뜻하지)',
    r'(?:판단|해석)(?:할|하기) (?:수 없|어렵)',
    r'(?:지표|자료|수치).{0,35}(?:더 확인|확인해야|살펴봐야|비교해야)',
    r'(?:한 가지|하나의) (?:수치|통계|지표).{0,45}(?:설명|판단|해석)',
    r'(?:쉽게|성급하게) (?:판단|단정|해석)',
    r'독자의 판단에 (?:도움|중요)',
    r'(?:공급|판매|시장) (?:상황|여건)(?:은|이)? 서로 달랐',
)

def no_reader_value_flags(text):
    return [pattern for pattern in NO_VALUE_PATTERNS if re.search(pattern,str(text or ''),re.I)]

def important_numeric_evidence(source_rows):
    """Only ask for a measured result when the cited source has one.

    Dates, article years and issue IDs are NOT measured changes.
    """
    text=' '.join(str(r.get('title',''))+' '+str(r.get('summary',''))+' '+str(r.get('observed',''))
                  for r in source_rows if isinstance(r,dict))
    return bool(re.search(r'(?:[+−-]?\d[\d,.]*\s*%|[+−-]?\d[\d,.]*\s*(?:톤|달러|원|억원|만톤|개점|개소|곳|배|kg|킬로그램))',text,re.I))

def quantified_change(text):
    """Specific observation rather than the publication year."""
    return bool(re.search(r'(?:[+−-]?\d[\d,.]*\s*%|[+−-]?\d[\d,.]*\s*(?:톤|달러|원|억원|곳|배|kg|킬로그램))',str(text),re.I))

def strong_editorial_claim(headline,claim):
    """Stop generic disclaimers occupying the conclusion slot."""
    if no_reader_value_flags(claim):return False
    if editorial_filler_flags(claim):return False
    if len(str(claim).strip())<24:return False
    return True


# Concrete business usefulness is a validation step, not a public paragraph.
# A summary is not an insight just because it mentions "market" or "risk".
BUSINESS_OBJECTS=('매입','구매','발주','납품','거래처','판로','판매처','정산','대금','채권',
                  '수금','재고','수요처','입점','계약','도매','유통점','소싱','매장','바이어',
                  '공급처','물량','수급','시세','단가','원가','판매가격','가격','공급')
DECISION_WORDS=('확보','조정','협의','우선','변경','전환','줄이','확대','재검토','대응',
                '관리','제한','선별','선택','중단','기준','계획','수정','낮춰','높여','조달','계약')
EMPTY_BUSINESS_PATTERNS=(
  r'고객은 경쟁점으로 옮겨갔',
  r'기존 공급업체의 미수금은 남았다',
  r'소비 이전에도 미수금',
  r'납품망의 손실',
  r'시장에 미치는 영향을 살펴',
  r'거래망의 회복 속도',
  r'시장의 흐름은 서로 달랐',
  r'여러 (?:변수|요인)를 (?:함께|종합적으로) 고려',
)

def concrete_business_decision(text):
    value=str(text or '')
    return (len(value.strip())>=35 and
            any(x in value for x in BUSINESS_OBJECTS) and
            any(x in value for x in DECISION_WORDS) and
            not editorial_filler_flags(value) and
            not no_reader_value_flags(value))

def empty_business_buzzword_flags(text):
    return [p for p in EMPTY_BUSINESS_PATTERNS if re.search(p,str(text or ''),re.I)]
