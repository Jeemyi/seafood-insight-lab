"""Evidence-gated public seafood-market research.

Uses only public snippets and officially observed metrics. Never sends company
internal figures. Rejects unsupported numeric statements; one guided retry.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
import requests
from seafood_research_depth import evidence_profiles, published_report_evidence, LABELS
from seafood_report_policy import evidence_class
from seafood_prose_quality import review_prose, repair_guidance, drop_detached_caveats
from seafood_numeric_audit import (numeric_observations, missing_numeric_claims,
                                   supported as tolerant_supported,
                                   evidence_number_inventory)

API='https://api.openai.com/v1/responses'
MODEL='gpt-6.1-sol'
CATEGORIES=['원물 수급/시세','코스트코','대형마트/SSM','매장 운영','온라인','B2B/급식','식품안전/소비심리','시즌/트렌드','비용/거시','해외']

def obj(fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}

MAIN_SCHEMA=obj({'reports':{'type':'array','items':obj({
    'depth':{'type':'string','enum':['핵심','보조']},
    'kind':{'type':'string','enum':CATEGORIES},
    'time_frame':{'type':'string'},
    'headline':{'type':'string'},'thesis':{'type':'string'},'lead':{'type':'string'},
    'facts':{'type':'array','items':obj({'text':{'type':'string'},'refs':{'type':'array','items':{'type':'string'}}})},
    'market_change':{'type':'string'},'mechanism':{'type':'array','items':{'type':'string'}},
    'structural_insight':{'type':'string'},
    'scenario_up':obj({'condition':{'type':'string'},'interpretation':{'type':'string'}}),
    'scenario_down':obj({'condition':{'type':'string'},'interpretation':{'type':'string'}}),
    'what_changes':{'type':'string'},'one_sentence':{'type':'string'},'limitations':{'type':'string'},
    'article_ids':{'type':'array','items':{'type':'string'}},
    'feature_ids':{'type':'array','items':{'type':'string'}},
    'policy_ids':{'type':'array','items':{'type':'string'}},
    'confidence':{'type':'string','enum':['중간','낮음']},
    'channels':{'type':'array','items':{'type':'string','enum':['코스트코','마트','매장','온라인','B2B','수출']}},
    'impact':{'type':'string'},'followup':{'type':'string'}
})}})

# v5.4: one forward judgment; no mandatory "positive vs negative" future grid.
_MAIN_ITEM=MAIN_SCHEMA['properties']['reports']['items']
for _field in ('scenario_up','scenario_down'):
    _MAIN_ITEM['properties'].pop(_field,None)
    _MAIN_ITEM['required'].remove(_field)
_MAIN_ITEM['properties']['outlook']=obj({
    'direction':{'type':'string','enum':['상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외']},
    'horizon':{'type':'string'},
    'judgment':{'type':'string'},
    'basis':{'type':'string'},
    'revision_trigger':{'type':'string'},
    'numeric_estimate':{'type':'string'},
    'forecast_method':{'type':'string'},
    'backtest':{'type':'string'},
    'evidence_ids':{'type':'array','items':{'type':'string'}},
})
_MAIN_ITEM['required'].append('outlook')

# An editorial outline separates finding a real contradiction from filling a template.
# All evidence IDs are checked against the public context before drafting.
PLAN_SCHEMA=obj({'topics':{'type':'array','items':obj({
    'subject':{'type':'string'},'angle':{'type':'string'},
    'evidence_ids':{'type':'array','items':{'type':'string'}},
    'observed_difference':{'type':'string'},'causal_explanation':{'type':'string'},
    'competing_explanation':{'type':'string'},'outlook_test':{'type':'string'}
})}})

_PLAN_ITEM=PLAN_SCHEMA['properties']['topics']['items']
_PLAN_ITEM['properties'].update({
    'why_events_connected':{'type':'string'},
    'tentative_outlook':{'type':'string'},
    'outlook_horizon':{'type':'string'},
})
_PLAN_ITEM['required']+=['why_events_connected','tentative_outlook','outlook_horizon']

PLAN_PROMPT='''너는 한국 수산업·식품유통 전문지 편집 데스크다. 먼저 후보 기사·통계들을 검토한 다음, 서로 다른 사건이 연결되어 새로운 결론을 내릴 수 있는 주제 최대 3개를 고른다. 충분하지 않으면 0~2개여도 괜찮다.

[소재 선정 기준 — 중요도 순서]
- 품목별 국내외 공급·가격·수요가 충돌하거나, 양식 생산·수입대체·어획규제·유통점포 변동이 실제 공급/판매에 영향을 주는 사건을 우선한다.
- 공개자료를 추가로 찾은 뒤 주제를 다시 결정한다. RSS 첫 기사나 유행어(온라인 성장, 가격 상승)에 종속되지 않는다.
- 인과적으로 이어지는 사건 또는 동일한 시장을 측정하는 서로 다른 변수가 최소 두 가지 있어야 한다. 함께 일어났다는 사실만으로 인과관계를 만들지 않는다.
- 전체 온라인 거래액, 개별 소매기업의 매출, 서로 관계없는 식자재 회사 취급고를 모두 '유통 확대'로 묶는 것은 금지한다.
- 기사 A와 B가 같은 발표를 복제한 경우 둘을 독립 증거로 세지 않는다. 자료의 발표일, 기준 기간, 어종, 규격과 거래단계까지 맞춘다.
- 어획량이 늘었다면 수입·규격·유통 수요·가격 중 어떤 자료가 이 사건을 설명하거나 다른 해석을 가능하게 하는지 찾아라.
- 중요한 뉴스라도 연결 근거가 없으면 심층 분석에서 제외하고 기사 목록으로 둔다. 분야별 할당 금지, 연어 우대 금지. 특정 수산물을 우대하지 않는다.
- 과거 글과 동일한 결론을 반복하지 않는다. 비공개 회사 자료는 사용하지 않는다.

[판단·전망]
- observed_difference는 구체적인 두 변수의 변화. causal_explanation은 근거로 좁힌 설명이며 일반적인 경제원리는 근거가 아니다.
- why_events_connected에 두 사건을 같은 글로 다뤄야 하는 이유를 써라. competing_explanation은 실제 근거로 비교할 만한 가장 강한 대안 한 가지다.
- tentative_outlook은 현재 가장 유력한 1가지 방향을 선택해 잠정 결론으로 작성한다. 'A이면 A이고 B이면 B'처럼 결론을 미루지 않는다.
- outlook_horizon은 전망의 적절한 기간(자료가 월간이면 다음 1~3개월 등)을 명시하되 임의로 숫자를 만들지 않는다.
- 수치 가격 예측은 입력에 검증된 모형 결과가 있을 때만. 그 외에는 방향과 근거를 제시한다. 방향도 근거가 없으면 해당 주제를 제외한다.
- evidence_ids는 제공된 공개 근거 ID만 사용하고 기본적으로 서로 독립적인 2개 출처 이상의 자료에 근거한다.
- 숫자는 입력에 존재하는 수치 또는 자료에 명시된 계산값만 사용. JSON 스키마를 따를 것.
- evidence_depth_profiles의 dimensions_missing과 observations를 먼저 읽어라. 자료가 부족한 축을 단순 경제상식으로 대체하지 말라. 실제 공급·소비·가격·수출입 자료에서 최소 두 가지 다른 수치의 움직임을 비교할 수 있는 주제를 우선한다.
- 환율 환산은 가격 비교의 보조 과정이다. 환율 자체가 중요한 독립 사건이 아니라면 논지의 중심으로 삼지 않는다. 오래된 연간 통계만으로 당월 수급이나 가격을 단정하지 않는다.
'''

DATA_SCHEMA=obj({'reports':{'type':'array','items':obj({
    'feature_id':{'type':'string'},'headline':{'type':'string'},'conclusion':{'type':'string'},
    'market_observation':{'type':'string'},'transmission':{'type':'array','items':{'type':'string'}},
    'structural_insight':{'type':'string'},'alternative':{'type':'string'},
    'scenario_support':{'type':'string'},'scenario_challenge':{'type':'string'},
    'investor_meaning':{'type':'string'},'limits':{'type':'string'},
    'article_ids':{'type':'array','items':{'type':'string'}},
    'confidence':{'type':'string','enum':['중간','낮음']},
})}})

# Section 02 also gives one evidence-led direction, not two empty alternatives.
_DATA_ITEM=DATA_SCHEMA['properties']['reports']['items']
for _field in ('scenario_support','scenario_challenge','investor_meaning'):
    _DATA_ITEM['properties'].pop(_field,None)
    _DATA_ITEM['required'].remove(_field)
_DATA_ITEM['properties']['outlook']=obj({
    'direction':{'type':'string','enum':['상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외']},
    'horizon':{'type':'string'},'judgment':{'type':'string'},
    'basis':{'type':'string'},'revision_trigger':{'type':'string'},
})
_DATA_ITEM['required'].append('outlook')

MAIN_PROMPT='''너는 한국 경제지·산업 전문지의 수산시장 담당 기자이자 데이터 분석가다. 금융시장 리포트에 준하는 논리·가독성을 갖추되, 보고서는 산업 전문지 기사처럼 자연스러운 한국어로 쓴다.

[기사의 목적]
한 기사나 한 지표를 길게 풀어쓰는 것이 아니라, 서로 다른 자료와 사건을 연결해서 새로운 시장 판단을 제시한다. 한 번의 요청에서는 지정된 중요 시장 주제 한 편만 작성한다. 하루 기사 편수 목표는 프로그램이 별도로 관리한다. 편수를 채우기 위한 원고는 만들지 않는다. 핵심은 '누가 무엇을 발표했다'보다 '복수의 사건이 같은 시장에 어떻게 작용하고 앞으로 어떤 결과가 유력한가'다.

[기사 유형에 맞는 구성 — 단일 경직 조건 금지]
- 먼저 시장 전체에서 중요 사건을 선정한다. 품목·국가별 기사 할당은 없다.
- 심층 시장 분석: 비교 가능한 독립 근거와 둘 이상의 시장 변수를 연결해 충분히 설명할 수 있는 경우.
- 주요 산업 이슈: 중요한 규제·검역·통상·유통 사건은 신뢰할 공식 1차 발표 1곳만으로도 다룰 수 있다. 발표에 없는 파급 효과를 사실로 단정하지 말고 공식 근거를 명시한다.
- 데이터 브리핑: 공식 가격·생산·교역 통계 1종이 의미 있는 변화를 보이면 독립 단신으로 정리한다. 두 변수를 채우려고 무관한 자료를 섞거나 전망을 지어내지 않는다.
- 발표일, 보도일, 실제 조사일, 통계 기준월, 법령 시행일을 구분한다. 다른 시점의 관측값은 추세 설명에 사용해도 같은 시점 수치라고 주장하지 않는다.
- 2026-11-09와 11월 9일은 같은 날이다. 서로 다른 기관의 반올림·집계법 차이는 비교 대상이 같은 경우에만 설명하고 허용한다.
- 자료가 일부 부족하면 곧바로 빈 배열을 반환하지 말고 가능한 한 검증 가능한 유형으로 전환해 작성하라. 아무 공식/공개 근거도 없다면 반드시 빈 배열이다.
- '전망 제외'는 전망이 유효하지 않은 사실 위주의 규제·공식 지표 브리핑에만 사용한다. 전망을 넣기 위해 없는 값을 만들지 않는다.

[주제·근거]
- 특정 수산물을 우대하지 않는다. 사전에 검토한 editorial_outline과 market_story_clusters를 먼저 읽는다. 심층 분석은 연관된 독립 근거 2곳 이상을 사용한다. 다만 중요한 공식 규제 발표나 단일 공식 통계는 해당 자료가 입증하는 범위의 산업 이슈·데이터 브리핑으로 작성한다. 같은 발표의 기사 복제는 독립 근거로 세지 않는다.
- ① 중요한 관측(연도·월·어종·규격) → ② 다른 사건/지표와 맞물리는 지점 → ③ 공급·수요·대체재·유통경로에 미치는 실질 영향 → ④ 하나의 잠정 전망이라는 흐름으로 논증한다.
- 분석 중 새로운 공개자료가 더 중요해 보이면 논지를 수정하되 연결 고리가 끊긴 사건을 같은 글에 넣지 않는다. 온라인쇼핑 전체 거래액, 컬리 매출, CJ프레시웨이 취급고 등 무관한 실적을 '식품시장 확대'로 억지로 엮지 않는다.
- 출처별 날짜·대상·통화·분류가 다르면 비교할 수 있는 범위만 비교한다. 한 주의 연어 FOB 가격과 한국 소비자가격을 동일시하지 않는다.
- 서로 다른 사건을 입증하기 어렵다면 심층 리포트를 강행하지 말고 신뢰 가능한 공식 발표·관측값에 근거한 산업 이슈 또는 데이터 브리핑 형식으로 축소한다.

[분명한 잠정 전망: 예측의 수준 구별]
- 가장 유력한 가격·물량·규제·유통 변화의 방향을 하나 선택한다. 방향을 정할 근거가 충분하지 않다면 outlook.direction='전망 제외'로 두되, 전망 없는 소재가 분석 가치까지 낮다면 보고서 자체를 제외하라.
- outlook.horizon에 전망의 예상 시점을, outlook.judgment에 자연스러운 한국어의 완결된 잠정 결론을, outlook.basis에 실제 근거를 쓴다. outlook.revision_trigger는 전망을 뒤집을 가장 구체적인 변수 하나를 덧붙이는 용도다.
- '가격이 계속 내리면 하락이 이어진다', '뒤집히면 다시 확인해야 한다' 등 순환논법 금지. 양쪽 시나리오를 동등하게 나열하지 말 것.
- 공식 시계열로 검증한 forecast_results가 입력에 포함된 **해당 품목·규격·기간에 한해서만** outlook.numeric_estimate, forecast_method, backtest 작성. 없으면 이 세 필드는 빈 문자열로 둔다. 모델 스스로 예측 가격, 신뢰구간, 확률을 만드는 행위 금지.
- 지금 근거만으로 예상 방향은 말할 수 있으나 상승 폭이 불명이라면 정확한 숫자는 생략한다. 근거가 약한 전망을 확실한 사실처럼 쓰지 않는다.

[한국어 문체 — 결과 중심 경제 기사]
- 한국인 기자가 쓴 산업 기사처럼 구체적 사실이 앞에 오고 뒤에 배경과 판단이 이어져야 한다.
- 본문의 각 문단은 '실제로 확인된 수치/사건 → 시장에서 일어난 변화 또는 입증되는 영향'을 전달한다. 수치가 없는 설명은 새로운 사실이나 구체적인 경제적 영향을 밝힐 때만 남긴다.
- 독자에게 분석법을 가르치지 마라. 'A와 B는 서로 다른 질문이다', '합쳐서 해석하면 안 된다', '단정할 수 없다', '따로 확인해야 한다', '이를 구분해야 한다', '해석하면 시장별 차이를 놓친다', '상권 경쟁과 거래 안정성은 별개다' 같은 수업식 결론을 작성하지 않는다.
- 예시(나쁨): '점포별 매출과 업태 전체 실적은 다른 질문이므로 구분해야 한다.'
- 예시(좋음): '폐점 인근 경쟁점 매출은 11.4% 늘었지만, 상반기 대형마트 전체 매출은 7.3% 감소했다. 폐점 반사이익이 일부 점포에 집중된 모습이다.'  (이 숫자는 문체 예시일 뿐 실제 원고에서는 제공된 근거가 있을 때만 쓴다.)
- 예시(나쁨): '전년 대비와 장기 평균을 함께 봐야 한다.'
- 예시(좋음): '어획량은 전년보다 128.5% 늘었지만 5년 평균에는 18.9% 못 미쳤다. 어획 반등에도 물량은 예년 수준에 도달하지 못했다.' (실제 원고에서는 반드시 근거 확인.)
- structural_insight에는 앞 문단의 요약이나 독자 대상 충고가 아니라 **새로운 구체적 산업 판단 한 가지**를 써라. 예: 출하량 증가가 가격 하락을 상쇄했는지, 수출국별 판매가 어느 쪽에 집중됐는지, 납품 피해가 어디에 누적되는지. 독립적인 추가 결론이 없다면 간결하게 마무리하라.
- 입증되지 않은 경제 원리, 당연한 설명, 일반론적인 주의 문장은 빼고, 근거가 불충분한 인과나 전망도 지어내지 않는다. 적절한 결론이 없으면 짧게 마무리한다.
- 아래의 표현은 작성하지 않는다: '구조적 통찰', '관측이 강화된다', '시사한다', '시사점', '인과 경로', '조건부 경로', '양적 측면과 가격 측면', '확인할 필요가 있다', '지켜봐야 한다', '핵심은 A가 아니라 B다', '자료를 종합하면 알 수 있다'.
- 읽는 사람이 이미 아는 일반 상식·면책성 설명을 문단마다 반복하지 않는다. 반복되는 사실은 한 번만 쓴다. 불확실성은 실질적으로 결론을 바꾸는 경우에만 한 번 짚는다.
- '추가 검증이 필요하다', '확인해야 한다', '단정하기 어렵다', '별도로 살펴봐야 한다'로 본문을 채우지 않는다. 조사 중 확인되지 않은 사실은 억지로 넣지 않고 뺀다. 조사 방법을 설명하는 대신 조사 결과를 제시한다.
- 독자가 경제신문을 읽는 것처럼 문장이 자연스럽게 이어지게 쓴다. 번역투·추상적 명사 남용('시장 흡수', '수요가 뒷받침되는 국면', '경로가 작동')을 피하고 익숙한 한국어 동사로 풀어 쓴다.
- 사내 보고서에서 쓰던 상품 규격이나 업무 용어를 문장에 억지로 끼우지 않는다. 예를 들어 '필렛·슬라이스·초밥용 네타·소포장 회' 같은 목록은 해당 상품별 가격·수요가 실제 결론에 필요한 경우가 아니라면 삭제한다.
- 해외 연어 기사라고 해서 국내 가공업체의 원가나 이익률, 대형마트 판매를 자동으로 연결하지 않는다. 확인한 한국 자료가 없으면 해외시장 자체를 깊이 분석하고 마무리한다.
- 달러 기준 가격이 가능한 품목은 공인된 환율로 같은 주차 또는 같은 기간의 비교가격을 환산해 독자가 이해하기 쉬운 USD/kg를 우선한다. 검증된 환산 자료가 없으면 현지 공식통화를 유지하고 달러 가격을 지어내지 않는다.
- 본문은 사실 → 원인 → 시장 영향 → 가장 유력한 전망으로 읽히게 작성한다. 취재 뒷이야기, 교훈, 인용 없는 가정, 형식적 반론은 쓰지 않는다.
- context.evidence_depth_profiles는 해당 주제의 공급·가격·수요·수출입 수치를 찾았는지 보여주는 점검표다. 가능한 한 서로 다른 원출처의 실제 관측치 3개 이상을 토대로 원인과 가격·수급 방향을 분석하되, 없는 수치는 만들지 않는다. 같은 수출가격의 NOK/USD 환산은 별개의 시장 관측치 두 개가 아니다.
- 수치 우선은 '많을수록 좋다'가 아니다. 핵심 주장과 직접 연결된 절대 규모(톤·금액·가격), 변화율, 비교 기준 기간을 실제 출처가 제공하는 범위에서 우선 사용한다. 변화율만 있으면 원물량을 지어내지 않는다. 관련성 낮은 통계는 수치가 풍부해도 제외한다.
- 각 문단이 전달하는 **새 정보**를 먼저 결정하라: 시장 변화에는 변동 규모·누가 영향을 받았는지, 배경에는 새로 확인한 원인·계약/생산/유통 메커니즘, 영향에는 구체적인 수익·물량·공급망 변화, 전망에는 자료가 뒷받침하는 시간·변수를 쓴다. 같은 수치와 결론을 세 문단에서 반복하지 않는다.
- 경제 일반론('고객은 다른 매장으로 이동할 수 있다')을 길게 풀지 않는다. 확인된 시장 자료가 없다면 억지로 '왜'를 추측하지 말고 관측과 영향만 서술한다. 정량 지표 없이도 공식 규제의 적용 대상·기한·변경 사항처럼 결정적 사실은 구체적으로 기술한다.
- 예시(나쁨): '경쟁점에는 반사이익이 있고 납품업체는 어려워질 수 있다.'
- 예시(좋음): '폐점 인근 두 이마트 점포의 매출은 11.4% 증가했다. 거래업체 조사에서 63%는 매출 감소를 응답했고, 피해업체 72곳은 모두 정산 지연을 지목했다. 소비 이전이 기존 납품업체의 매출·대금 회복으로 연결되지는 않았다.' (문체 예시, 실제 원고에는 자료가 있을 때만.)
- 숫자만 다시 나열한 '배경' 문단은 삭제하거나 실질적인 연결 과정으로 다시 쓴다. 전망에서 앞의 결론을 그대로 반복하지 말고 미래를 바꿀 변수(확정된 조업 제한, 출하량, 재고, 매출·정산 경과 등)와 영향을 받는 시장 주체를 명시한다. 예측 근거가 없으면 전망을 생략한다.
- 본문은 기사 제목과 lead의 핵심 수치가 시장 변화/배경/영향 중 자연스러운 위치에서 다시 근거로 쓰일 수 있으나, 동일한 수치 세트를 문단마다 복제하지 않는다.
- 통계의 전년 대비만 늘어놓지 말고 최근 1~3개월 변화와 기준연도 또는 장기 평균을 구분해 연결한다. 2025년 실적만 있다면 이를 근거로 2026년 현재 가격 흐름을 단정하지 말고 최신 발표를 우선한다.
- 가격 기사면 가격 변화의 기간과 폭, 공급·수요 자료와의 관계를 설명한다. 수출 기사면 물량·금액·단가 및 주요 거래국 변화 중 실제 확보한 지표를 비교한다. 수급 기사면 국내 생산·해외 조달·규제·소비가 맞물리는지 조사한 결과를 넣는다.
- **검증과 발행문을 분리한다.** 서로 다른 상품형태·규격·조업 범위가 섞이지 않았는지는 내부적으로 엄격히 확인하되, 올바른 수치와 비교를 사용한 본문 끝에 '단순 합산이 어렵다', '실제 판매가격과 같지 않다', '통계상 범위가 다르다' 같은 통계 사용법을 덧붙이지 마라. 기사 독자에게 필요한 것은 해당 산업의 변화와 실제 결과다.
- 나쁜 결말: '다만 수출통계는 여러 상품 형태를 묶은 평균이므로 특정 규격의 실제 판매가격과 같지는 않다.' 좋은 결말: '수출물량이 87.8% 증가한 반면 수출액은 48.7% 늘어 평균 수출단가는 약 20.8% 낮아졌다. 지난해 수출액 성장은 단가 상승보다 물량 확대에 의존했다.' 숫자는 입력에 있는 근거/정당한 계산이 있을 때만 사용한다.
- 나쁜 결말: '두 생산 통계는 조업 해역과 포함 품목 범위도 달라 단순 합산해서 동일 원료의 공급량으로 쓰기 어렵다.' 좋은 결말: '연근해 오징어 어획은 1만7,438톤 늘었지만 5년 평균보다 7,272톤 적었다. 원양 오징어류는 전년보다 17.4% 감소해 생산 회복이 연근해 부문에 집중됐다.' 이 사실만으로 수출 증가가 연근해 어획에서 비롯됐다고 단정하지 않는다.
- 결론의 우선순위: (1) 실제 물량·가격·매출·대금·수출금액 변화 (2) 특정 국가·유통채널·생산 부문에 집중된 변화 (3) 실제 기업·생산자·거래처에 미치는 입증 가능한 영향 (4) 근거가 있는 다음 분기·다음 조업기의 변수. 이 목록을 채우기 위해 무관한 통계를 연결하거나 금액·이익을 추정하지 마라.
- 한 단락 끝의 '주의해야 한다/단정하기 어렵다/비교할 수 없다'가 핵심 결론으로 기능하면 대체하거나 삭제하라. 단, 이 정보가 빠지면 **내용 자체가 허위로 읽히는 경우**에는 사실을 정확하게 다시 표현해야 한다. 수치의 단위·분모·기간·상품범위를 임의로 통합하지 않는다.
- mechanism은 같은 이유를 두 번 반복하지 않는다. 서로 다른 근거와 실제 작동 과정을 쓸 수 있을 때만 문단을 나누고, 수치 없는 구조 설명도 구체적 거래/생산 사실을 추가한다면 허용한다. 억지로 숫자·날짜를 끼우지 않는다.
- 심층 분석을 완성할 근거가 모자라면 분량을 불리지 말고 해당 근거를 정확히 설명할 수 있는 짧은 기사 유형으로 전환한다. 주장 자체를 입증하지 못하면 제외한다. 검증을 마치지 못했다는 변명 문장을 본문에 넣지 않는다. 내용 없이 '관측 사실과 해석 구분', '추가 분석 필요' 같은 메타 안내를 반복하지 않는다.
- 제목은 실제 결론이 들어가는 경제지 스타일로. '인사이트'라는 단어 남발 금지. 숫자 기반 비교는 근거가 있을 때만.

[필드별 역할 — 글을 잘게 쪼개기 위한 구색 채우기 금지]
- headline, thesis: 첫 두 문장 안에 핵심 변화와 잠정 판단. 제목이 리포트 내용을 과장하지 않아야 함.
- lead, market_change: 독자의 배경 이해와 시간·비교대상 설명. 기사의 주요 배경은 짧게.
- facts: 확인된 원출처 사실마다 evidence ID를 붙임. 독립 출처 두 곳 미만인 원고는 심층 분석이라고 주장하지 말 것. 서로 다른 통계의 기간을 숨기지 말 것.
- mechanism: 서로 다른 사건·변수의 작용을 설명하는 문단 2개 이상. 각각 독립적인 새로운 정보를 추가해야 함.
- structural_insight: 앞 문단 요약이 아닌 두 자료의 결합에서 도출되는 구체적인 산업 판단.
- what_changes: 내부 검증·후속 수집용 메타데이터다. 본문에는 노출되지 않으므로 짧게 적는다.
- one_sentence: 화면 내부 처리용 결론 요약. 다른 필드에 똑같은 문장을 복붙하지 말 것.
- limitations: 공개 원자료의 핵심 제한만 내부 메타데이터에 짧게 기록. 본문 분량을 늘리려고 확인/검증 필요성을 독자에게 말하지 말 것. 기사 원문을 확인하지 못했으면 전문을 읽은 것처럼 쓰지 말 것.
- output depth '핵심'은 충분한 자료가 있을 때만. 분량보다 서로 다른 근거의 연결이 우선이다.
- 공개 출처와 공식 통계만 사용. 내부 회사의 비공개 거래조건·매출·마진·전략은 절대 쓰지 않는다.
- 필드 schema만 채우려는 장황함, 재진술, 형식적 낙관/비관 시나리오 금지. 반드시 지정 JSON 스키마로 응답한다.
'''

DATA_PROMPT='''너는 한국 수산업 전문지의 데이터 담당 기자다. 공식 자료와 관련 기사에서 **한 품목을 실제로 설명하는 다른 관측**이 연결되는 경우에만 독립된 품목별 분석을 작성한다.
- 환율·금리 단독 글은 작성하지 않는다. 공식 관측치 하나와 무관한 기사 제목을 조합해 길게 늘리지 않는다. 그런 자료는 이미 화면의 수치 카드로 제공된다.
- 한 품목에서 수입 물량/평균단가, 산지가/출하량, 도매/소매, 수출/생산처럼 서로 다른 단계를 **관측된 사실로** 비교한다. 규격·기간이 다르면 차이를 분명히 설명한다.
- 관측치가 뒷받침할 때만 가장 유력한 향후 방향을 적고, 그렇지 않으면 outlook.direction='전망 제외'로 둔다. 전망 제외일 때 나머지 outlook 필드는 빈 문자열이어도 된다. 가격 하락이 이어지면 더 하락한다 같은 빈말은 금지.
- 근거 없이 확률·가격 범위·다음 달 숫자를 만들지 말고, 별도의 검증된 forecast_results가 제공되지 않으면 숫자 예측은 금지한다.
- 한국 경제지 기사처럼 짧고 자연스럽게 작성한다. '양적 측면', '조건부 경로', '관측이 강화된다', '확인할 필요가 있다', '시사점' 등의 어색한 표현은 사용하지 않는다.
- 더 확인해야 한다는 안내나 자료의 결핍을 본문 분량으로 쓰지 않는다. 실제 확인된 비교 결과만 풀어 쓴다. 근거 없는 미래 전망은 쓰지 않는다.
- 시장 일반론·분석 방법론을 데이터 해설 대신 쓰지 않는다. 'A와 B는 다른 질문이다', '따로 살펴봐야 한다', '단정할 수 없다', '이렇게 해석하면 안 된다' 같은 문장은 삭제하고 실제 증감률·기간·수출액·가격·업체 영향을 구체적으로 설명한다.
- 핵심 지표와 직접 관련 있는 절대 규모·변동률·비교 기간은 제공된 근거에서 확인되면 적극 활용한다. 숫자를 두 개 이상 채우려는 목적의 무관한 통계 연결은 금지한다.
- 본문의 통계 해설은 측정된 결과와 그로부터 직접 확인되는 산업적 변화에 집중한다. '합산하기 어렵다', '단가가 개별 판매가격은 아니다', '해석에 유의해야 한다' 같은 별도의 주의사항을 결론처럼 쓰지 않는다. 핵심 제한은 limits 필드에 짧게 기록한다. 단위·분류·기간이 다르면 계산을 합치지 않고, 표기 자체를 정확하게 유지한다.
- conclusion은 가장 중요한 측정 결과를 제시하고, structural_insight는 그 결과로 실제 달라진 물량·단가·공급·판매의 관계를 설명하되 결론을 복제하지 않는다. 둘을 나눌 실질적 정보가 없으면 짧게 작성한다.
- structural_insight와 conclusion은 해당 수치가 보여주는 물량/단가/공급/판매의 변화를 직접 진술한다. 근거가 부족하면 빈 결론을 길게 꾸미지 말고 검증된 사실만 짧게 적는다.
- 사내보고서처럼 상품형태·취급규격을 줄줄이 나열하거나 근거 없는 국내 수입·가공 수익성 연결을 만들지 않는다. 달러 환산 근거가 있는 경우 USD/kg를 먼저 사용한다.
- 직접 인용한 공식 데이터 ID와 공개 기사 ID만 활용하고, 비교 가능한 수치를 보존한다. 장황한 면책 문구나 소제목을 채우려는 반복 문장을 쓰지 않는다.
- 숫자 하나뿐이라면 reports=[]로 둔다. 이는 실패가 아니라 자료가 충분할 때만 심층 분석을 하려는 결정이다.
- evidence_depth_profiles를 참고해 서로 다른 측정 축(가격·생산·수요·수입 등)에서 실제 근거가 연결된 경우만 데이터를 분석한다. 두 통계가 같은 공식 발표를 재인용하면 독립 근거로 세지 않는다.
''' 


def _response_text(body):
    return ''.join(piece.get('text','') for item in body.get('output',[]) for piece in item.get('content',[]) if piece.get('type')=='output_text')


def _call(prompt, context, schema, name, repair_note=''):
    key=os.getenv('OPENAI_API_KEY','').strip()
    messages=[{'role':'system','content':prompt},
              {'role':'user','content':json.dumps(context,ensure_ascii=False)+('\n[재작성 지침] '+repair_note if repair_note else '')}]
    req={'model':os.getenv('OPENAI_MODEL',MODEL),'input':messages,
         'text':{'format':{'type':'json_schema','name':name,'schema':schema,'strict':True}},
         'max_output_tokens':16000 if name=='seafood_deep_research_v1' else (8500 if name=='seafood_story_outline_v1' else 10500),
         'reasoning':{'effort':os.getenv('OPENAI_REASONING_EFFORT','medium')},
         'store':False}
    r=requests.post(API,json=req,timeout=(12,240),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    r.raise_for_status()
    result=json.loads(_response_text(r.json()))
    key='topics' if name=='seafood_story_outline_v1' else 'reports'
    if not isinstance(result,dict) or not isinstance(result.get(key),list):
        raise ValueError('output schema mismatch')
    return result


def choose_research_candidates(articles, focus_topics=None, maximum=20):
    """Keep multiple important events per category, not just one headline.

    Sources are leads. Reprinting one release does not constitute independent
    evidence; that is verified later against originating publisher/agency.
    """
    from seafood_editorial import evaluate_article
    pool=balanced_article_pool(articles,maximum=max(36,maximum*3))
    by_id={a['id']:a for a in articles if a.get('id')}
    chosen=[];used=set();counts={}
    def add(item):
        if not item or item['id'] in used or len(chosen)>=maximum:return
        cat=item.get('category','')
        if counts.get(cat,0)>=4:return
        chosen.append(item);used.add(item['id'])
        counts[cat]=counts.get(cat,0)+1
    # A selected event needs more than a single representative headline.
    if focus_topics:
        for topic in focus_topics[:5]:
            for aid in topic.get('article_ids',[])[:4]:add(by_id.get(aid))
    ranked=sorted(pool,key=lambda a:(evaluate_article(dict(a)),a.get('score',0),a.get('timestamp',0)),reverse=True)
    # Broad market pass: cover distinct kinds of changes without forcing them
    # into output articles or making news count itself a signal of importance.
    for item in ranked:
        if counts.get(item.get('category',''),0)<2:add(item)
    for item in ranked:add(item)
    return chosen[:maximum]


_RESEARCH_QUERIES={
    '원물 수급/시세':['수산물 가격 생산량 통계','수산업관측센터 어종별 가격','관세청 수산물 수입'],
    '코스트코':['코스트코 한국 점포 식품 공시','회원제 창고형 마트 식품 매출'],
    '대형마트/SSM':['대형마트 월간 매출 산업통상부','대형마트 납품 거래 실태조사'],
    '매장 운영':['대형마트 점포 폐점 출점 공시','수산 매장 영업 규제'],
    '온라인':['온라인쇼핑 농축수산물 거래액 통계','신선식품 온라인 거래 동향'],
    'B2B/급식':['학교 급식 식자재 입찰','단체급식 수산물 조달'],
    '식품안전/소비심리':['수산물 검역 통계 공식','수산물 원산지 단속 발표'],
    '시즌/트렌드':['수산물 소비자 구매 통계','수산물 제철 가격 추이'],
    '비용/거시':['수산물 수입단가 환율','냉동 물류 운임 수산물'],
    '해외':['해양수산부 수산물 수출 통계','Norwegian seafood exports salmon statistics','Japan seafood import tariff'],
}


def event_search_phrase(title):
    """Generate a short event-level lead, never broad Boolean keyword soup."""
    words=re.findall(r'[A-Za-z가-힣][A-Za-z가-힣0-9·-]*',str(title))
    ignore={'단독','속보','종합','뉴스','보도자료','발표','기자','현장','정부는',
            '올해','지난해','지난달','속보입니다','어떻게','왜','전망','이슈'}
    words=[w for w in words if len(w)>1 and w.lower() not in ignore]
    # RSS headlines are often full sentences. Searching the first five tokens
    # verbatim reproduces news prose and can be too restrictive.
    return ' '.join(words[:3]).strip()


def _short_search(query, max_words=5):
    """Short noun-like search intent; never submit whole article sentences."""
    raw=re.sub(r'[“”"「」\[\]()]',' ',str(query or ''))
    raw=re.split(r'[.!?…]|(?:\s+[–—]\s+)',raw,1)[0]
    skip={'전망입니다','가능성이','확인해야','필요하다','나타났다',
          '분석한다','공식적으로','살펴본다','비교하라'}
    return ' '.join([w for w in raw.split() if w not in skip][:max_words]).strip()


def _topic_search_phrases(theme):
    """Explore either half of a compound issue before attempting to connect it."""
    txt=str(theme or '').strip()
    if not txt:return []
    bits=[b.strip() for b in re.split(r'[·/]',txt) if b.strip()]
    if len(bits)>=2:
        # For 'Japan/US exports' search individual destinations as well.
        shared=next((w for w in ('수출','수입','어획','가격','유통','판매') if w in txt),'수산물')
        result=[_short_search(f'{b} {shared} 통계',4) for b in bits[:3]]
    else:
        result=[_short_search(txt+' 통계',4)]
    return list(dict.fromkeys(q for q in result if q))


def build_research_queries(choices, features, focus_topics=None, depth_profiles=None):
    """Separate broad discovery from *event-specific* follow-up searches."""
    categories=list(dict.fromkeys(x.get('category') for x in choices if x.get('category')))
    year=datetime.now().year
    questions=[]
    if focus_topics:
        # Numeric-gap queries outrank generic category searches.
        for profile in (depth_profiles or [])[:3]:
            questions.extend(_short_search(q,5) for q in profile.get('gap_queries',[])[:3])
        selected_ids={i for t in focus_topics[:4] for i in t.get('article_ids',[])[:3]}
        # First search the actual news events, not merely their broad category.
        for item in choices:
            if item.get('id') in selected_ids:
                phrase=event_search_phrase(item.get('title'))
                if phrase:questions.append(phrase)
                if len(questions)>=8:break
        for topic in focus_topics[:4]:
            theme=topic.get('theme','')
            questions.extend(_topic_search_phrases(theme))
            cat=topic.get('category','')
            if cat in _RESEARCH_QUERIES:questions.extend(_RESEARCH_QUERIES[cat][:1])
    else:
        # Incident discovery should also survive a full RSS outage.
        for item in choices[:6]:
            phrase=event_search_phrase(item.get('title'))
            if phrase:questions.append(phrase)
        categories=list(dict.fromkeys([
            '원물 수급/시세','해외','대형마트/SSM','식품안전/소비심리']+categories))
        for cat in categories[:9]:questions.extend(_RESEARCH_QUERIES.get(cat,[])[:2])
    # Additional searches follow the newly ranked events. Never add mandatory
    # salmon/squid/retail queries because they happened to be demo subjects.
    for f in features[:4]:
        name=str(f.get('name','')).strip()
        if name:questions.append(_short_search(name+' 통계',5))
    # 25 unrelated intents in ONE web_search request is not 25 executed
    # searches. Prefer concise, focused search plans that the model can act on.
    return list(dict.fromkeys(_short_search(q,5) for q in questions if q))[:15 if focus_topics else 16]


def infer_research_category(title, excerpt):
    """Classify the cited passage itself, not the first article in the query."""
    text=(str(title)+' '+str(excerpt)[:800]).lower()
    rules=[
        ('코스트코',('코스트코','costco','커클랜드')),
        ('대형마트/SSM',('홈플러스','대형마트','롯데마트','이마트','트레이더스','ssm')),
        ('온라인',('수산물 온라인','신선식품 온라인','온라인 신선식품','쿠팡 신선','컬리 수산')),
        ('B2B/급식',('학교급식','군급식','단체급식','급식 수산물','식자재 납품')),
        ('식품안전/소비심리',('수산물 검역','수산물 검사','수산물 안전','수산물 원산지')),
        ('해외',('수산물 수출','수산물 수입','수출 연어','salmon export','seafood export','대미 관세')),
        ('원물 수급/시세',('연어','salmon','광어','넙치','우럭','오징어','고등어','어획량','어업생산','수산업','수산물 가격','수산물 생산','양식 어류','꽃게','새우','tuna','shrimp')),
    ]
    for cat,terms in rules:
        if any(t in text for t in terms):return cat
    return None


def research_public_sources(articles, features, now, focus_topics=None):
    """Web-grounded discovery / targeted fact research, two separate passes.

    Only an attributed, cited excerpt may become evidence. Links returned by
    the search tool without a cited passage are not converted to invented facts.
    """
    phase='focused' if focus_topics else 'discovery'
    if not os.getenv('OPENAI_API_KEY','').strip() or os.getenv('SEAFOOD_WEB_RESEARCH','1')=='0':
        return [],f'{phase}: 웹 검색 미사용'
    choices=choose_research_candidates(articles,focus_topics,maximum=20)
    depth_profiles=evidence_profiles(focus_topics or [],articles,features,maximum=4)
    if not choices and not features and not focus_topics:
        # Continue searching official releases even on a complete RSS outage.
        print('SEAFOOD RESEARCH: RSS empty; primary-source discovery fallback',flush=True)
    search_plan=build_research_queries(choices,features,focus_topics,depth_profiles)
    focus_rule=(
        '선정된 사건이 실제로 왜 발생했는지 확인하는 두 번째 조사다. 주제별로 같은 보도를 반복하지 말고 '
        '최초 공식 발표와 별개인 가격·출하·수요·수출입 자료를 찾아라. 첫 조사에서 빠진 자료를 우선 찾고, '
        '근거가 없는 인과관계는 만들지 마라. 부족한 수치(공급/수요/가격/수출입)가 무엇인지 우선 판단하고 해당 자료부터 조사하라.'
        if focus_topics else
        '첫 조사에서는 특정 업종을 미리 정하지 말고 최근 주요 사건을 넓게 찾아라. '
        '수산물 생산·가격·수출입·안전·유통을 고르게 조사하되 이슈가 중요한지는 실제 수치와 시장 영향으로 판단하라.'
    )
    prompt=(
      '너는 공개 자료를 조사하는 한국 수산시장 산업 리서처다. 반드시 웹 검색을 사용하라. '
      +focus_rule+
      ' 제공한 검색문은 각각 별개의 검색 의도이며, 하나의 긴 검색문으로 합치지 마라. '
      '최근 30~45일 발표를 우선하되 원인과 계절성을 확인할 과거 1~5년 비교통계는 별도로 찾아라. '
      '시장에 영향을 미친 실제 사건, 그 규모, 관련 공식통계, 발표일과 측정기간을 구분하라. '
      'KMI, 수협, 해양수산부, 관세청, 통계청, 식약처, 기업 공시, 해외 정부 통계와 독립 취재를 우선한다. '
      '보도자료를 여러 언론이 복제했다면 한 개의 원출처로 취급하라. '
      '각 핵심 사실을 검색 결과의 출처 링크와 함께 적고 최소한 실제 확인한 내용을 수치·기간·단위와 연결하라. '
      '확인하지 못한 수치나 회사 내부 실적을 지어내지 말라. 취재가 미완성인 전망 문장을 쓰지 말라. '
      '결과는 한국어의 짧은 근거 문단으로 작성하고 문단별 URL 인용을 포함하라. '      '수치를 찾았다면 실제 숫자·단위·발표일·집계기간·비교기간·원출처를 한 문단에 명시하라. '      '서로 다른 통계의 어종/형태/기간을 동일한 값처럼 합치지 말라. '      '외화 가격을 환산한 동일 관측치는 하나의 가격 자료로 취급하고 환율 설명을 기사 본론으로 늘리지 마라.'
    )
    context={'today_kst':now.date().isoformat(),'research_phase':phase,
             'separate_search_intents':search_plan,
             'focus_topics':(focus_topics or [])[:4],
             'measurement_gaps_and_existing_evidence':depth_profiles,
             'news_candidates':[{'id':x['id'],'title':x['title'],'category':x['category'],
                                 'source':x.get('source'),'url':x.get('url'),
                                 'published':x.get('published')} for x in choices],
             'official_observations':[{'name':f.get('name'),'period':f.get('period_end'),
                                       'observed':f.get('observed'),
                                       'url':f['data_links'][0]['url'] if f.get('data_links') else ''}
                                      for f in features if not str(f.get('id','')).startswith('fx_')][:12]}
    print(f'SEAFOOD RESEARCH {phase}: {len(choices)} event leads, '
          f'{len(search_plan)} independent search intents',flush=True)
    req={'model':os.getenv('OPENAI_RESEARCH_MODEL',os.getenv('OPENAI_MODEL',MODEL)),
         'reasoning':{'effort':'low'},
         'tools':[{'type':'web_search','search_context_size':'high'}],
         'tool_choice':'required','include':['web_search_call.action.sources'],
         'input':[{'role':'system','content':prompt},
                  {'role':'user','content':json.dumps(context,ensure_ascii=False)}],
         'max_output_tokens':8500,'store':False}
    try:
        resp=requests.post(API,json=req,timeout=(12,240),headers={
            'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],
            'Content-Type':'application/json'})
        resp.raise_for_status()
        body=resp.json()
        collected=[];urls=set();citation_count=0
        for item in body.get('output',[]):
            if item.get('type')!='message':continue
            for content in item.get('content',[]):
                if content.get('type')!='output_text':continue
                full=content.get('text','')
                for anno in content.get('annotations',[]):
                    if anno.get('type')!='url_citation':continue
                    url=anno.get('url','')
                    from urllib.parse import urlparse
                    parsed=urlparse(url)
                    if parsed.scheme not in ('http','https') or not parsed.netloc or url in urls:continue
                    pos=anno.get('start_index',0)
                    if not isinstance(pos,int) or pos<0 or pos>len(full):continue
                    start=max(0,full.rfind('\n',0,pos)+1)
                    end=full.find('\n',pos)
                    excerpt=full[start:end if end!=-1 else len(full)].strip()[:850]
                    if len(excerpt)<35:continue
                    title=anno.get('title') or '검색으로 확인한 공개 근거'
                    # Do not attach an irrelevant citation to the first news
                    # topic simply because the search generated that citation.
                    category=infer_research_category(title,excerpt)
                    if not category:
                        continue
                    urls.add(url);citation_count+=1
                    collected.append({'id':'web-'+__import__('hashlib').sha1(url.encode()).hexdigest()[:12],
                        'url':url,'source':parsed.netloc.removeprefix('www.'),
                        'title':title,'summary':excerpt,
                        'summary_type':'웹 검색 인용 문단 · 원문 미열람',
                        'published':'발행일 별도 확인','timestamp':0,
                        'category':category,'channels':[],'tags':[],'score':0,
                        'official':False,'research_phase':phase,
                        'impact':'공개 근거 문단','followup':'해당 원문 및 통계 기준기간'} )
        print(f'SEAFOOD RESEARCH {phase}: citation_passages={citation_count}, '
              f'usable={min(24,len(collected))}',flush=True)
        return collected[:24],f'{phase} 근거 출처 {len(collected[:24])}건'
    except requests.HTTPError as exc:
        status=exc.response.status_code if exc.response is not None else 'unknown'
        code='unknown'
        if exc.response is not None:
            try:code=str(exc.response.json().get('error',{}).get('code') or 'unknown')[:40]
            except (ValueError,TypeError,AttributeError):pass
        return [],f'{phase} 웹 검색 HTTP {status} (code={code})'
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        return [],f'{phase} 웹 검색 실패: {type(exc).__name__}'


def _numeric_tokens(text):
    """Backward-compatible numeric values with Korean quantity normalization."""
    return [format(n['value'].normalize(), 'f') for n in numeric_observations(text)]


def _supported(text, evidence):
    """Accept compatible measured values within bounded reporting error.

    Never approximate years, weeks, months, survey counts, or distinct units.
    Exact source-local citation checks are performed separately from full prose.
    """
    return tolerant_supported(text,evidence)


def _evidence_text(records):
    # Keep each field on its own line: metric labels in a title must not become
    # the nearest measurement label in an otherwise unrelated snippet.
    keys=('title','name','snippet','summary','observed','facts','period_start','period_end',
          'published','related_observations','measurements')
    pieces=[]
    for row in records:
        for key in keys:
            if key not in row:continue
            value=row[key]
            rendered=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
            # The published date is a press timestamp, not the period of a
            # measured price/volume or the effective date of a regulation.
            pieces.append('보도일 '+rendered if key=='published' else rendered)
    return '\n'.join(pieces)


def _all_evidence(context):
    text=_evidence_text(context.get('articles',[])+context.get('official_series',[]))
    # One explicitly reproducible derived quantity: unit-value percentage change
    # = (1+export-value growth)/(1+export-volume growth)-1. Use source-local rates.
    values=[]
    for a in context.get('articles',[]):
        source=a.get('snippet','')
        if '수출액' not in source or not any(w in source for w in ('수출량','수출물량')):continue
        m1=re.search(r'수출액(?:은|이)?\s*(\d+(?:\.\d+)?)\s*%',source)
        m2=re.search(r'(?:수출물량|수출량)(?:은|이)?\s*(\d+(?:\.\d+)?)\s*%',source)
        if m1 and m2:
            revenue=float(m1.group(1));volume=float(m2.group(1))
            if 0<=revenue<=150 and 0<=volume<=150:
                change=((1+revenue/100)/(1+volume/100)-1)*100
                values.append(f'검산 공식 수출액 지수 {(1+revenue/100):.2f}, 물량 지수 {(1+volume/100):.2f}, 평균단가 변화율 {change:.1f}%')
    return text+' '.join(values)


def _numeric_feedback(issues,limit=4):
    result=[]
    for issue in issues[:limit]:
        nearest=issue.get('nearest_source')
        part=f"{issue['claim']}"+(f" (인용 근거의 유사 숫자: {nearest})" if nearest else ' (근거 수치 없음)')
        if part not in result:result.append(part)
    return '; '.join(result)[:390]


def balanced_article_pool(articles, maximum=36):
    """Distribute available *evidence candidates*, not required output topics.

    When news is concentrated in one commodity, keep strong stories from other
    categories visible to the model. Never invent a category or report.
    """
    eligible=sorted((a for a in articles if len(a.get('summary',''))>=35 or len(a.get('title',''))>=18),
                    key=lambda a:(a.get('score',0),a.get('timestamp',0)),reverse=True)
    buckets={cat:[] for cat in CATEGORIES}
    for article in eligible:
        if article.get('category') in buckets:
            buckets[article['category']].append(article)
    selected=[];ids=set();counts={c:0 for c in CATEGORIES}
    def add(article):
        if article['id'] in ids or len(selected)>=maximum:return
        selected.append(article);ids.add(article['id']);counts[article['category']]+=1
    # First pass reserves *at most* one strong reportable article per populated topic.
    for cat in CATEGORIES:
        if buckets[cat]:add(buckets[cat][0])
    # For independent cross-article comparison, prefer a second publisher in each topic.
    for cat in CATEGORIES:
        if buckets[cat]:
            other=next((a for a in buckets[cat][1:] if a['source']!=buckets[cat][0]['source']),None)
            if other:add(other)
    # Fill remaining slots by significance, but keep a reasonable category cap.
    for article in eligible:
        if counts.get(article['category'],0)<6:add(article)
    if len(selected)<maximum:
        for article in eligible:add(article)
    return selected[:maximum]


def _main_context(articles,features,now,issues,focus_topics=None):
    pool=balanced_article_pool(articles,maximum=60)
    included={a['id'] for a in pool}
    # Verified-search citations must be visible even when their scores are lower than news RSS.
    pool += [a for a in articles if a.get('id','').startswith('web-') and a['id'] not in included][:14]
    rows=[{'id':a['id'],'source':a['source'],'title':a['title'],'published':a['published'],
           'category':a['category'],'snippet':a.get('summary','')[:850],
           'official':bool(a.get('official')),'url':a.get('url',''),
           'channels':a.get('channels',[]),'impact':'관측 보도'} for a in pool]
    prioritized_features=sorted(features,key=lambda f:(f.get('role')!='context' and not str(f.get('id','')).startswith('fx_'), f.get('significance',0)),reverse=True)
    series=[{'id':f['id'],'name':f['name'],'period_start':f['period_start'],'period_end':f['period_end'],
             'observed':f['observed'],'facts':f['facts'],'data_links':f.get('data_links',[]),
             'limits':f['limitations'],'related_observations':f.get('related_observations',[])} for f in prioritized_features[:20]]
    depth=evidence_profiles((focus_topics or []),pool,prioritized_features,maximum=5)
    return {'now_kst':now.isoformat(),'articles':rows,'official_series':series,'evidence_depth_profiles':depth,
            'topic_candidates':(focus_topics or [{'theme':i['theme'],'article_ids':i['article_ids']} for i in issues[:5]])[:5],
            'source_limit':'공개 RSS 소개문과 공식 시계열만 사용, 기사 전문·비공개 거래정보는 이용하지 않음'}


def _same_source_name(source):
    """Avoid mistaking reprints of one institutional release for independent evidence."""
    source=str(source or '').lower().strip()
    for institution in ('해양수산부','국가데이터처','산업통상','kmi','수산업관측','노르웨이 통계청','ssb','norwegian seafood council','수산물위원회'):
        if institution.lower() in source:
            return institution.lower()
    return source.split(' · ')[0].split(' | ')[0]


def _public_source_family(record):
    """Two series from the same official endpoint are NOT independent sources."""
    from urllib.parse import urlparse
    urls=record.get('data_links') or record.get('links') or []
    for link in urls:
        url=link.get('url','') if isinstance(link,dict) else ''
        host=urlparse(url).hostname or ''
        if host:
            host=host.lower().removeprefix('www.')
            if host.endswith('ssb.no'):return 'ssb.no'
            if host.endswith('data.go.kr'):return 'data.go.kr'
            if host.endswith('kamis.or.kr'):return 'kamis.or.kr'
            if host.endswith('ecos.bok.or.kr'):return 'ecos.bok.or.kr'
            return host
    name=str(record.get('source') or record.get('name') or '')
    family=_same_source_name(name)
    # Two distinct original datasets released by the same institution can
    # support different facts. A press reprint of one dataset is not independent.
    if record.get('official') and record.get('title'):
        return family+' / '+str(record['title']).strip().lower()[:100]
    return family


def make_editorial_outline(ctx, previous_headlines=None):
    """Ground the story before drafting. Failure is nonfatal: original evidence remains."""
    if not ctx.get('articles') and not ctx.get('official_series'):
        return []
    if os.getenv('SEAFOOD_EDITORIAL_PLAN','1')=='0':
        return []
    eligible={x['id']:x for x in ctx['articles']+ctx['official_series']}
    payload={
        'today_kst':ctx['now_kst'],
        'public_articles':ctx['articles'][:45],
        'official_statistics':ctx['official_series'][:15],
        'topic_candidates':ctx.get('topic_candidates',[])[:5],
        'market_story_clusters':ctx.get('story_candidates',[])[:6],
        'evidence_depth_profiles':ctx.get('evidence_depth_profiles',[])[:5],
        'previously_published_titles':(previous_headlines or [])[:6],
        'never_use_internal_business_documents':True,
    }
    try:
        result=_call(PLAN_PROMPT,payload,PLAN_SCHEMA,'seafood_story_outline_v1')
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        print('SEAFOOD editorial outline skipped:',type(exc).__name__)
        return []
    plans=[];used_subjects=set()
    for entry in result.get('topics',[])[:4]:
        try:
            ids=list(dict.fromkeys(x for x in entry['evidence_ids'] if x in eligible))
            # Independent public evidence, or official series with two distinct data sources.
            origins={_public_source_family(eligible[x]) for x in ids}
            fields=('subject','angle','observed_difference','causal_explanation','competing_explanation','outlook_test')
            if len(ids)<2 or len(origins)<2 or any(len(entry.get(k,'').strip())<18 for k in fields):
                continue
            if entry['subject'] in used_subjects:continue
            # The old exact cluster-ID intersection silently eliminated valid
            # independent sources when keyword clustering missed the event.
            # Keep the actual relevance test without making the heuristic a gate.
            from seafood_story_selection import shared_market_anchor
            if not shared_market_anchor([eligible[i] for i in ids]):
                continue
            # Only select a plan whose claims are grounded in the supplied public materials.
            if not _supported(' '.join(entry[k] for k in fields),json.dumps([eligible[i] for i in ids],ensure_ascii=False)):
                continue
            plans.append({**{k:entry[k] for k in fields},'evidence_ids':ids[:8],
                          'why_events_connected':entry.get('why_events_connected',''),
                          'tentative_outlook':entry.get('tentative_outlook',''),
                          'outlook_horizon':entry.get('outlook_horizon','')})
            used_subjects.add(entry['subject'])
            if len(plans)>=3:break
        except (KeyError,TypeError,AttributeError):continue
    return plans


def _duplicate_passages(report):
    """Flag near-identical filler passages; do not reject a legitimate repeated statistic."""
    from difflib import SequenceMatcher
    blocks=[report.get('market_change','')]+list(report.get('mechanism',[]))+[report.get('structural_insight',''),report.get('what_changes','')]
    blocks=[' '.join(str(x).split()) for x in blocks if len(str(x).strip())>=45]
    for i,first in enumerate(blocks):
        for second in blocks[i+1:]:
            # Substantially the same paragraph, not normal reference to the same species.
            if SequenceMatcher(None,first,second).ratio()>=.81:
                return True
    return False


def _validate_main(payload,ctx,diagnostics=None):
    allowed_a={a['id'] for a in ctx['articles']}
    allowed_f={f['id'] for f in ctx['official_series']}
    allowed=allowed_a|allowed_f
    evidence_by_id={x['id']:x for x in ctx['articles']+ctx['official_series']}
    evidence=_all_evidence(ctx)
    good=[];reasons=[];seen=set()
    for r in payload.get('reports',[])[:5]:
        try:
            fields=('headline','thesis','lead','market_change','structural_insight','what_changes','one_sentence','limitations','followup')
            # Presence and grounding matter; an arbitrary character quota does
            # not measure analytical quality.  It previously rejected valid
            # concise sentences before their citations were even checked.
            required_prose=('headline','thesis','lead','market_change','structural_insight','one_sentence')
            malformed=[k for k in fields if not isinstance(r.get(k),str)]
            missing=[k for k in required_prose if isinstance(r.get(k),str) and not r[k].strip()]
            if malformed or missing:
                reasons.append('필수 원고 항목 누락: '+','.join(malformed+missing));continue
            if r['kind'] not in CATEGORIES or r['headline'] in seen:
                reasons.append('분류 또는 제목 중복');continue
            if not isinstance(r.get('mechanism'),list) or not r['mechanism'] or any(
                    not isinstance(x,str) or not x.strip() for x in r['mechanism']):
                reasons.append('시장 영향 설명 누락: mechanism');continue
            outlook=r.get('outlook')
            if outlook is not None:
                if not isinstance(outlook,dict) or outlook.get('direction') not in (
                        '상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외'):
                    reasons.append('전망의 우세 방향 누락');continue
                # A factual regulation/data brief may explicitly exclude a
                # speculative outlook. Deep analysis still needs a reasoned view.
                required_outlook=('horizon','judgment','basis') if outlook['direction']!='전망 제외' else ()
                absent=[k for k in required_outlook if not isinstance(outlook.get(k),str) or not outlook[k].strip()]
                if absent:
                    reasons.append('전망 항목 누락: '+','.join(absent));continue
                if outlook.get('numeric_estimate') and not ctx.get('forecast_results'):
                    reasons.append('검증하지 않은 예측 가격·물량 수치');continue
                if outlook.get('numeric_estimate'):
                    allowed_forecasts=json.dumps(ctx.get('forecast_results',[]),ensure_ascii=False)
                    if not _supported(str(outlook['numeric_estimate']),allowed_forecasts):
                        reasons.append('공식 시계열 예측 결과와 일치하지 않는 값');continue
                if not set(outlook.get('evidence_ids',[])).issubset(allowed):
                    reasons.append('전망에 존재하지 않는 출처');continue
            elif not all(isinstance(r.get(s),dict) and isinstance(r[s].get(k),str) and r[s][k].strip()
                         for s in ('scenario_up','scenario_down') for k in ('condition','interpretation')):
                # Historical demonstration cards still use the earlier schema.
                reasons.append('조건부 시나리오 부족');continue
            facts=[]
            for fact in r['facts']:
                refs=list(dict.fromkeys(str(x) for x in fact.get('refs',[]) if x in allowed))
                source_text=_evidence_text([evidence_by_id[i] for i in refs])
                # A short cited fact can be decisive (e.g. a quota or price).
                # Validate its content rather than discarding it at 29 chars.
                fact_text=fact.get('text','')
                if isinstance(fact_text,str) and fact_text.strip() and refs and _supported(fact_text,source_text):
                    facts.append({'text':fact_text,'refs':refs})
                elif diagnostics is not None and isinstance(fact_text,str) and fact_text.strip() and refs:
                    missing=missing_numeric_claims(fact['text'],source_text)
                    if missing:
                        diagnostics.append({'part':'인용 사실','source_ids':refs,
                                            'claim':fact['text'][:130],
                                            'mismatches':missing[:5]})
            if not facts:
                reasons.append('검증 가능한 출처 연결 사실 없음');continue
            cited={ref for fact in facts for ref in fact['refs']}
            report_type,audit=evidence_class(r,facts,evidence_by_id)
            if not report_type:
                reasons.append('심층·산업 이슈·데이터 브리핑 중 어느 유형에도 근거 미달');continue
            if report_type=='심층 시장 분석' and len(r['mechanism'])<2:
                reasons.append('심층 분석의 상이한 원인·시장 영향 설명 부족');continue
            # A one-source original release is acceptable as a cited policy
            # update / data brief, never promoted to multi-source analysis.
            if report_type!='심층 시장 분석' and len(cited)<2 and not any(
                    evidence_by_id[i].get('data_links') or evidence_by_id[i].get('url') for i in cited):
                reasons.append('원출처 URL 확인 불가');continue
            # Checked numbers in all analytical paragraphs; numeric tokens must be public evidence.
            forward=(list(outlook.get(k,'') for k in ('judgment','basis','revision_trigger')) if outlook is not None else
                     [r['scenario_up']['condition'],r['scenario_down']['condition'],
                      r['scenario_up']['interpretation'],r['scenario_down']['interpretation']])
            # Technical limitations/follow-up metadata is not a market claim;
            # a historical context month there must not invalidate verified
            # facts elsewhere. Visible article claims are still checked.
            claim_fields=tuple(x for x in fields if x not in ('limitations','followup','what_changes'))
            prose=' '.join([r[k] for k in claim_fields]+r['mechanism']+forward)
            if not _supported(prose,evidence):
                missing=missing_numeric_claims(prose,evidence)
                reasons.append('근거에 없는 숫자 사용')
                if diagnostics is not None and missing:
                    diagnostics.append({'part':'분석 본문','source_ids':[],
                                        'claim':'본문 전체', 'mismatches':missing[:7]})
                continue
            if _duplicate_passages(r):
                reasons.append('같은 문단의 내용 반복');continue
            if outlook is not None:
                banned=('구조적 통찰','조건부 경로','양적 측면','시사점을','관측이 강화','인과 경로',
                        '전망이 강화된다','지속되면 지속','핵심 인사이트')
                if any(token in prose for token in banned):
                    reasons.append('기사답지 않은 추상·순환 표현');continue
                from seafood_story_selection import shared_market_anchor
                if report_type=='심층 시장 분석' and not shared_market_anchor(
                        [evidence_by_id[i] for i in cited]):
                    # New material is not rejected merely because the commodity
                    # is missing from a prewritten list. Require the selected
                    # evidence to share a sufficiently specific lead term.
                    label=str(ctx.get('target_market') or '')
                    terms=[x.lower() for x in re.findall(r'[a-zA-Z가-힣]{2,}',label)
                           if x not in ('시장','해외','국내','수출입','동향','변화','주요','수급','전망')]
                    rows=[str(evidence_by_id[i].get('title') or evidence_by_id[i].get('name') or '')+' '+
                          str(evidence_by_id[i].get('snippet') or evidence_by_id[i].get('observed') or '')
                          for i in cited]
                    if not terms or not all(any(t in text.lower() for t in terms) for text in rows):
                        reasons.append('인용 자료가 동일 품목·시장에 관한 근거가 아님');continue
            # A stitched general online-market/foodservice article is not a
            # cross-market seafood insight. The cited evidence must share a
            # measured product/channel or an explicitly linked mechanism.
            if r['kind']=='온라인':
                evidence_text=[str(evidence_by_id[i].get('title',''))+' '+str(evidence_by_id[i].get('summary','')) for i in cited if i in evidence_by_id]
                food_terms=('음식료품','농축수산물','수산물 거래','신선식품 거래','수산식품','수산물 판매','생선','해산물','회초밥','식품 온라인쇼핑')
                has_product_data=any(any(t in x for t in food_terms) for x in evidence_text)
                if not has_product_data:
                    reasons.append('온라인 전체 거래와 개별 업체의 실적만 연결됨 · 수산/식품 품목 근거 없음');continue
                if any('CJ프레시웨이' in x and not any(t in x for t in ('온라인','이커머스','식품 온라인','쇼핑몰')) for x in evidence_text):
                    reasons.append('온라인 유통과 비온라인 식자재 취급고를 동일시장으로 연결함');continue
            weak_phrases=('판단할 수 없다','확인되지 않았다','입증하지 않는다','확인할 수 없다','제공되지 않았다','판단하기 어렵다','단정할 수 없다')
            if sum(prose.count(p) for p in weak_phrases)>=4:
                reasons.append('긍정적인 분석보다 불확실성·면책 설명이 지나치게 많음');continue
            catalog_list=('필렛·슬라이스·초밥용 네타·소포장 회','필렛, 슬라이스, 초밥용 네타')
            if any(x in prose for x in catalog_list):
                reasons.append('시장 분석과 무관한 사내 보고서식 품목·규격 나열');continue
            if not set(r['article_ids']).issubset(allowed_a) or not set(r['feature_ids']).issubset(allowed_f):
                reasons.append('존재하지 않는 출처 ID');continue
            # Normalize labels; metadata differences must never reject a sound report.
            aliases={'대형마트/SSM':'마트','대형마트':'마트','SSM':'마트',
                     '마트/SSM':'마트','급식':'B2B','식자재':'B2B',
                     '수산물':'','원물 수급/시세':'','해외':'수출'}
            clean_channels=[]
            for ch in r.get('channels',[]):
                ch=aliases.get(ch,ch)
                if ch in ('코스트코','마트','매장','온라인','B2B','수출') and ch not in clean_channels:
                    clean_channels.append(ch)
            r=dict(r);r['channels']=clean_channels;r['facts']=facts[:5];r['policy_ids']=[]
            r['report_type']=report_type;r['status']='공개 자료 기반 '+report_type
            r['depth']='핵심' if report_type=='심층 시장 분석' else '보조'
            r['character_count']=len(prose);r['length_tier']='충실' if len(prose)>=900 else '간결'
            r['evidence_depth']=audit
            good.append(r);seen.add(r['headline'])
            if len(good)>=3:break
        except (KeyError,TypeError,AttributeError,ValueError):
            reasons.append('출력 필드 형식 오류')
    return good,reasons


def analyze(articles,features,now,issues,focus_topics=None,previous_headlines=None):
    if not os.getenv('OPENAI_API_KEY','').strip():
        return [],'새로운 분석을 작성하지 못했습니다.'
    ctx=_main_context(articles,features,now,issues,focus_topics)
    if not ctx['articles'] and not ctx['official_series']:
        return [],'리서치 보류: 공개 뉴스와 공식 시계열 근거를 충분히 확보하지 못했습니다.'
    from seafood_story_selection import build_story_clusters
    ctx['story_candidates']=build_story_clusters(ctx['articles'],ctx['official_series'],previous_headlines)
    ctx['depth_validation']=True
    print('SEAFOOD DEPTH - topic evidence:',[(x['anchor'],x['numeric_records'],x['dimensions_present'],x['dimensions_missing'][:2]) for x in ctx['evidence_depth_profiles'][:4]],flush=True)
    ctx['previous_headlines']=(previous_headlines or [])[:6]
    # Optional: a *continuous, verified, same-specification monthly series*
    # can yield an audited numeric forecast. The current SSB weekly snapshot,
    # isolated MOF YoY comparison and ECOS FX series do NOT qualify.
    from seafood_forecast import backtested_monthly_forecast
    ctx['forecast_results']=[]
    for feature in features:
        if not feature.get('history_verified') or feature.get('role')=='context':
            continue
        result=backtested_monthly_forecast(feature.get('history',[]),
            metric=feature.get('name','수산물 가격'),unit=feature.get('history_unit',''))
        if result:
            result['feature_id']=feature['id']
            result['reference']=feature.get('data_links',[])
            ctx['forecast_results'].append(result)
    ctx['editorial_outline']=make_editorial_outline(ctx,previous_headlines) if os.getenv('SEAFOOD_EDITORIAL_PLAN','1')!='0' else []
    print('SEAFOOD evidence clusters:',[(x['subject'],x['score']) for x in ctx['story_candidates'][:4]],flush=True)
    # An independently measured, same-market dossier is a valid draft lead
    # even when the heuristic keyword cluster/outline happens to be empty.
    from seafood_topic_tracks import coverage_tracks
    if not ctx['story_candidates'] and not ctx['editorial_outline'] and not any(
        t['ready'] for t in coverage_tracks(articles,features,focus_topics or ())):
        return [],'연관된 사건·독립 자료를 갖춘 분석 후보가 부족합니다.'
    from seafood_topic_tracks import coverage_tracks, track_for_report, records_for_track
    lanes=coverage_tracks(articles,features,focus_topics or ())
    # No fixed market slots. Rank the day's measured issues independently.
    candidates=[lane for lane in lanes if lane['ready']]
    # v5.18: aim for TWO independently verified new topics, not three drafts.
    # Keep more ranked candidates as fallback; researching leads is not a
    # commitment to publish them. All paid composing and repair calls share
    # the existing capped budget.
    target=max(1,min(3,int(os.getenv('SEAFOOD_REPORT_TARGET','2'))))
    budget=max(1,min(8,int(os.getenv('SEAFOOD_DRAFT_CALL_LIMIT','6'))))
    candidates=candidates[:6]
    assignments=[]
    for lane in candidates:
        anchor=lane['anchor']
        local_articles,local_features=records_for_track(anchor,articles,features,
            {'theme':lane['label'],'article_ids':lane['headline_ids'],
             'feature_ids':lane['feature_ids']})
        local_ctx=_main_context(local_articles,local_features,now,issues,focus_topics)
        local_ctx['articles']=[row for row in local_ctx['articles'] if row['id'] in
                               {a['id'] for a in local_articles}]
        local_ctx['official_series']=[row for row in local_ctx['official_series'] if row['id'] in
                                      {f['id'] for f in local_features}]
        local_ctx.update({'depth_validation':True,'forecast_results':ctx['forecast_results'],
            'story_candidates':[x for x in ctx['story_candidates'] if
                 anchor in (str(x.get('subject',''))+str(x.get('theme',''))).lower()][:3],
            'editorial_outline':[x for x in ctx['editorial_outline'] if
                 anchor in str(x.get('subject','')).lower()][:2],
            'target_market':lane['label'],
            'target_evidence_coverage':{'numeric_records':lane['numeric_records'],
                'sources':lane['sources'],'dimensions':lane['dimensions']}})
        numeric_ids={x.get('id') for x in lane.get('observations',[]) if x.get('quantities')}
        local_ctx['draft_source_brief']=[{'id':row.get('id'),
            'source':row.get('source'),'title':row.get('title') or row.get('name'),
            'period':row.get('published') or row.get('period_end'),
            'observed':str(row.get('snippet') or row.get('observed') or '')[:420]}
            for row in (local_ctx['articles']+local_ctx['official_series'])
            if row.get('id') in numeric_ids][:10]
        assignments.append((lane,local_ctx))
    if not assignments:
        # Fallback for an independently supported market whose heuristic
        # track cannot be categorized into one of the predefined anchors.
        assignments=[({'anchor':None,'label':'전체 우선순위 시장',
                       'numeric_records':0,'sources':0},ctx)]
    print(f'SEAFOOD DRAFT TARGET: {target} validated topics; '
          f'candidate_backups={len(assignments)}; paid_call_limit={budget}',flush=True)
    calls=0;good=[];outcomes=[];published=set();seen_titles=set()

    def attempt(lane,local_ctx,guidance,number,repair=False):
        nonlocal calls
        anchor=lane['anchor']
        calls+=1  # Count attempted requests even if HTTP or JSON fails.
        try:
            response=_call(MAIN_PROMPT,local_ctx,MAIN_SCHEMA,
                           'seafood_deep_research_v1',guidance)
            issues=[]
            accepted,reasons=_validate_main(response,local_ctx,issues)
            accepted=[r for r in accepted if not anchor or
                      anchor.startswith('topic:') or track_for_report(r)==anchor]
            accepted=[r for r in accepted if
                      re.sub(r'\s+','',r.get('headline','')).lower() not in seen_titles]
            if issues:
                brief=' | '.join(f"{x['part']} {x.get('source_ids',[])}: {_numeric_feedback(x['mismatches'])}"
                                 for x in issues[:3])[:590]
                print(f'SEAFOOD NUMERIC {"REPAIR" if repair else "AUDIT"} {anchor}: {brief}',flush=True)
            if not response.get('reports'):
                print(f'SEAFOOD DRAFT EMPTY {anchor}: model_returned_empty_array; '
                      f'input_articles={len(local_ctx["articles"])} '
                      f'official={len(local_ctx["official_series"])} '
                      f'measured={lane.get("numeric_records",0)} '
                      f'original_sources={lane.get("sources",0)}',flush=True)
            if accepted:
                chosen=accepted[0]
                chosen['market_anchor']=anchor
                chosen['market_label']=lane['label']
                return chosen,'',issues,response.get('reports',[])[:1]
            reason=' / '.join(dict.fromkeys(reasons))[:180] or (
                    '중복 제목 또는 다른 소재' if response.get('reports')
                    else 'AI가 원고를 작성하지 않음 (reports=[])')
            if issues:
                reason+=' | 숫자 확인: '+' / '.join(
                    _numeric_feedback(x['mismatches'],2) for x in issues[:3])[:270]
            return None,reason,issues,response.get('reports',[])[:1]
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            return None,'API·JSON 오류 '+type(exc).__name__,[],[]

    for index,(lane,local_ctx) in enumerate(assignments):
        if len(good)>=target or calls>=budget:
            break
        anchor=lane['anchor']
        if anchor in published:
            continue
        if not local_ctx['articles'] and not local_ctx['official_series']:
            outcomes.append(f'{anchor}: 관련 원출처 부족')
            continue
        guidance=(f"오늘 선정된 '{lane['label']}'의 시장 변화 한 가지를 분석한 기사 1편을 작성하라. "
           '제공된 출처 ID와 관측치만 사용하고 다른 시장 이야기로 대체하지 마라. '
           '심층 분석에 필요한 다원 근거가 부족하다면 검증된 공식 발표의 주요 산업 이슈 또는 데이터 브리핑으로 작성하라. '
           '없는 가격·소비지표를 만들어 넣지 말고, 일부 분석 축이 비었다고 관련 사실을 버리지 말라. '
           '숫자가 있으면 관련 사건에 직접 연결되는 절대 규모·증감률·비교 기간부터 선택하라. 숫자 몇 개를 채우려는 무관한 통계 연결은 금지한다. '
           '본문의 변화·배경·영향이 각각 새 정보를 제공하도록 쓰고, 같은 수치 문장을 그대로 세 번 반복하지 마라. '
           '충분한 근거가 실제로 없을 때만 reports=[]로 반환하라.')
        report,reason,issues,previous=attempt(lane,local_ctx,guidance,index+1)
        print(f'SEAFOOD DRAFT {index+1} {anchor or "general"}: '
              f'proposed={len(previous)} accepted={int(report is not None)} '
              f'reasons={[reason] if reason else []}',flush=True)
        if report:
            good.append(report)
            published.add(anchor)
            seen_titles.add(re.sub(r'\s+','',report.get('headline','')).lower())
            outcomes.append(f'{anchor}: 통과 ({report.get("report_type", "분석")})')
            continue

        outcomes.append(f'{anchor}: 최초 집필 실패: {reason}')
        # Repair the SAME story now, before paying to draft another candidate.
        # Reserve enough first attempts for other candidates to reach the 2-
        # report target if this repair fails. Never exceed the daily cap.
        remaining_candidates=len(assignments)-index-1
        reserve=min(target-len(good),remaining_candidates)
        if budget-calls<=reserve:
            outcomes.append(f'{anchor}: 재작성 건너뜀 (다음 후보 집필 예산 보존)')
            continue
        repair_ctx=dict(local_ctx)
        repair_ctx['repair_previous_draft']={'reports':previous,'numeric_issues':issues[:4]}
        note=(f"'{lane['label']}' 보완 원고만 작성하라. 이전 검수 결과: {reason}. "
              '처음에 reports=[]였다면 원고 미작성이다. '
              'draft_source_brief의 수치와 출처 ID를 우선 사용해 검증 가능한 기사 한 편을 완성하라. '
              '중요한 공식 정책 사건이나 유의미한 공식 통계는 원출처 한 곳으로도 짧은 보고서가 가능하다. '
              '같은 지표·기간·단위에서 소폭 반올림 차이는 검수기가 허용한다. '
              '근거에서 확인할 수 없는 숫자는 삭제하고 서로 다른 집계 대상은 혼동하지 마라. '
              '검증할 근거가 정말 없으면 reports=[]를 반환하라. '
              '원출처 수치: '+json.dumps(evidence_number_inventory(
                  repair_ctx.get('articles',[])[:8]+repair_ctx.get('official_series',[])[:5],
                  limit_per_source=9),ensure_ascii=False)[:1700])
        fixed,repair_reason,_,_=attempt(lane,repair_ctx,note,index+1,repair=True)
        print(f'SEAFOOD REPAIR {index+1} {anchor or "general"}: '
              f'accepted={int(fixed is not None)} '
              f'reason={repair_reason[:200]}',flush=True)
        if fixed:
            good.append(fixed)
            published.add(anchor)
            seen_titles.add(re.sub(r'\s+','',fixed.get('headline','')).lower())
            outcomes.append(f'{anchor}: 즉시 재작성 통과')
        else:
            outcomes.append(f'{anchor}: 즉시 재작성 탈락: {repair_reason[:150]}')
    # No extra AI rewriting once two validated topics are secured. This avoids
    # spending remaining capacity on optional polish rather than the user's
    # minimum viable daily report. Deterministic prose cleanup still runs.
    # Editorial fallback changes NO figures or factual claims: it only omits
    # two extremely specific detached methodology footnotes. Substantive
    # source restrictions remain recorded separately in limitations.
    good=[drop_detached_caveats(r) for r in good]
    print('SEAFOOD DRAFT - calls:',calls,'/',budget,'target:',target,
          'achieved:',len(good),'per-track:',outcomes,flush=True)
    if good:
        kinds={k:sum(r.get('report_type')==k for r in good) for k in ('심층 시장 분석','주요 산업 이슈','데이터 브리핑')}
        print('SEAFOOD EDITORIAL - published types:',kinds,flush=True)
        return good[:target],f'새 시장 분석 {len(good)}편 · 공개 근거 검증 완료'
    return [],'새 시장 분석 0편 · '+('; '.join(outcomes)[:230] or '자료와 수치 부족')


def _data_context(features,articles,main_reports,now):
    # Sharing an indicator with the daily research is NOT a reason to drop it.
    # Section 02 asks a different, numeric decomposition question.
    # One-price/one-FX series cannot support a multi-source industry report.
    # A genuine commodity dataset must have a relevant second source/observation.
    eligible=[]
    for f in features:
        if f.get('role')=='context' or f.get('id','').startswith('fx_'):
            continue
        linked=[a for a in articles if a.get('id') in set(f.get('article_ids',[]))]
        nontrivial=[a for a in linked if len(a.get('summary',''))>=55 and
                    any(t in a.get('title','')+a.get('summary','') for t in ('수입','수출','생산','어획','출하','가격','판매','양식','연어','오징어','광어','우럭','꽃게','고등어'))]
        independent=set(a.get('source','') for a in nontrivial)
        if f.get('related_observations') or independent:
            eligible.append(f)
    eligible=sorted(eligible,key=lambda f:f.get('significance',0),reverse=True)
    return {'now_kst':now.isoformat(),'evidence_depth_profiles':evidence_profiles(
             [{'theme':f.get('name','')} for f in eligible],articles,features,maximum=5),
            'features':[{'id':f['id'],'name':f['name'],'title':f['title'],
                  'period_start':f['period_start'],'period_end':f['period_end'],
                  'observed':f['observed'],'facts':f['facts'], 'limitations':f['limitations'], 'related_observations':f.get('related_observations',[]),
                  'article_ids':f.get('article_ids',[])} for f in eligible[:10]],
            'already_covered':[r['headline'] for r in main_reports],
            'articles':[{'id':a['id'],'title':a['title'],'snippet':a.get('summary','')[:350]} for a in articles[:25]]}


def _validate_data(payload,context):
    f_map={f['id']:f for f in context['features']}
    article_ids={a['id'] for a in context['articles']}
    good=[];reasons=[];used=set()
    for r in payload.get('reports',[])[:7]:
        try:
            fid=r['feature_id']
            if fid not in f_map or fid in used:
                reasons.append('01번과 중복 또는 유효하지 않은 지표');continue
            fields=('headline','conclusion','market_observation','structural_insight','alternative','limits')
            # Do not force a generic paragraph or invented caveat just to hit
            # arbitrary length. A short factually dense data brief is valid.
            lengths={'headline':12,'conclusion':25,'market_observation':25,'structural_insight':20,
                     'alternative':0,'limits':0}
            if any(not isinstance(r.get(k),str) or len(r[k].strip())<lengths[k] for k in fields):
                reasons.append('완결된 설명 부족');continue
            outlook=r.get('outlook')
            if outlook is not None:
                if not isinstance(outlook,dict) or outlook.get('direction') not in (
                        '상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외'):
                    reasons.append('전망 판단이 불분명함');continue
                if outlook['direction']!='전망 제외' and any(len(str(outlook.get(k,'')))<n for k,n in (
                    ('horizon',3),('judgment',30),('basis',35),('revision_trigger',15))):
                    reasons.append('방향·근거·예상 시점 부족');continue
            else:
                old_fields=('scenario_support','scenario_challenge','investor_meaning')
                if any(len(str(r.get(k,'')))<25 for k in old_fields):
                    reasons.append('기존 전망 항목 누락');continue
                fields+=old_fields
            if not isinstance(r['transmission'],list) or any(
                not isinstance(x,str) or (x.strip() and len(x.strip())<15) for x in r['transmission']):
                reasons.append('자료에 근거한 영향 설명 부족');continue
            # Evidence can come from the official series AND a separately cited
            # related public article; previously all article numbers were rejected.
            relevant_articles=[a for a in context['articles'] if a['id'] in r['article_ids']]
            observed=json.dumps(list(f_map.values())+relevant_articles,ensure_ascii=False)
            prose=' '.join([r[k] for k in fields]+r['transmission']+([outlook.get(k,'') for k in ('judgment','basis','revision_trigger')] if outlook else []))
            if not _supported(prose,observed):
                reasons.append('공식 원자료에 없는 숫자');continue
            if not set(r['article_ids']).issubset(article_ids):
                reasons.append('유효하지 않은 뉴스 출처');continue
            feature=f_map[fid]
            # Report must use a genuinely distinct market fact, not seven variations
            # of the same weekly official table. A lone metric remains a data card.
            has_cross=bool(feature.get('related_observations'))
            if not has_cross and not r['article_ids']:
                reasons.append('단일 지표의 반복 해설');continue
            rr=dict(r);rr['length_tier']='충실' if len(prose)>=700 else '간결'
            rr['status']='공식 수치 기반 AI 분석 · 통계와 가설 구분'
            good.append(rr);used.add(fid)
            if len(good)>=4:break
        except (KeyError,ValueError,AttributeError,TypeError):
            reasons.append('출력 필드 형식 오류')
    return good,reasons


def analyze_data(features,articles,main_reports,now):
    if not os.getenv('OPENAI_API_KEY','').strip():
        return [],'OpenAI API 키 미연결 · 공식 숫자만 표시'
    context=_data_context(features,articles,main_reports,now)
    if not context['features']:
        return [],'다른 자료와 비교할 수 있는 품목별 관측이 아직 없습니다.'
    note='';last='근거 부족'
    for attempt in range(2):
        try:
            obj=_call(DATA_PROMPT,context,DATA_SCHEMA,'seafood_data_research_v1',note)
            reports,errors=_validate_data(obj,context)
            if reports:return reports,f'AI 데이터 해설 {len(reports)}편 · 공식 수치와 비교기간 검증'
            last=' / '.join(dict.fromkeys(errors))[:200] or '근거 부족'
            note='이전 원고 탈락: '+last+'. 숫자는 facts와 observed에서만 사용; 부족하면 숫자를 반복하지 말고 근거 안에서 재작성.'
        except requests.HTTPError as e:
            return [],f'데이터 AI 요청 실패 HTTP {e.response.status_code if e.response is not None else "unknown"}'
        except requests.RequestException as e:
            return [],f'데이터 AI 요청 실패 {type(e).__name__}'
        except (ValueError,KeyError,TypeError) as e:
            last=type(e).__name__;note='JSON 형식 오류 수정. 유효한 지표만 선택.'
    return [],'데이터 해설 보류: '+last
