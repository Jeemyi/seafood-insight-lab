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

PLAN_PROMPT='''너는 한국 수산업·식품유통 전문지 편집 데스크다. 먼저 후보 기사·통계들을 검토한 다음, 서로 다른 사건이 연결되어 새로운 결론을 내릴 수 있는 서로 다른 주요 이슈를 3~4개까지 우선 검토한다. 실제 기사·독립 근거가 갖춰진 최소 두 개를 우선 선정하되 부족하면 만들어내지 않는다.

[소재 선정 기준 — 중요도 순서]
- 품목별 국내외 공급·가격·수요가 충돌하거나, 양식 생산·수입대체·어획규제·유통점포 변동이 실제 공급/판매에 영향을 주는 사건을 우선한다.
- 공개자료를 추가로 찾은 뒤 주제를 다시 결정한다. RSS 첫 기사나 유행어(온라인 성장, 가격 상승)에 종속되지 않는다.
- 인과적으로 이어지는 사건 또는 동일한 시장을 측정하는 서로 다른 변수가 최소 두 가지 있어야 한다. 함께 일어났다는 사실만으로 인과관계를 만들지 않는다.
- 전체 온라인 거래액, 개별 소매기업의 매출, 서로 관계없는 식자재 회사 취급고를 모두 '유통 확대'로 묶는 것은 금지한다.
- 기사 A와 B가 같은 발표를 복제한 경우 둘을 독립 증거로 세지 않는다. 자료의 발표일, 기준 기간, 어종, 규격과 거래단계까지 맞춘다.
- 어획량이 늘었다면 수입·규격·유통 수요·가격 중 어떤 자료가 이 사건을 설명하거나 다른 해석을 가능하게 하는지 찾아라.
- 중요한 뉴스라도 연결 근거가 없으면 심층 분석에서 제외하고 기사 목록으로 둔다. 분야별 할당 금지, 연어 우대 금지. 특정 수산물을 우대하지 않는다.
- 과거 글과 동일한 결론을 반복하지 않는다. 비공개 회사 자료는 사용하지 않는다.

[편집 전 선별]
- 수출·어획·생산 연간 통계 한 건이 사실일 뿐이라면, 최근 7일의 사건을 밀어내고 '오늘의 핵심 분석'으로 올리지 않는다. 영향을 받은 계약·업체·가격·공급의 구체적 결과가 있는 뉴스를 우선한다.
- 동일 품목 두 통계가 다른 방향인 사실 자체는 연결 가치가 아니다. 그 두 숫자가 실제로 같은 거래시장이나 행동 결과를 설명할 때만 연결한다.
- 실질적인 결론 없이 '서로 다른 현상이 나타났다'를 설명하는 원고는 기획안에서 제외한다.

[판단·전망]
- observed_difference는 구체적인 두 변수의 변화. causal_explanation은 근거로 좁힌 설명이며 일반적인 경제원리는 근거가 아니다.
- why_events_connected에 두 사건을 같은 글로 다뤄야 하는 이유를 써라. competing_explanation은 실제 근거로 비교할 만한 가장 강한 대안 한 가지다.
- tentative_outlook은 현재 가장 유력한 1가지 방향을 선택해 잠정 결론으로 작성한다. 'A이면 A이고 B이면 B'처럼 결론을 미루지 않는다.
- outlook_horizon은 전망의 적절한 기간(자료가 월간이면 다음 1~3개월 등)을 명시하되 임의로 숫자를 만들지 않는다.
- 수치 가격 예측은 입력에 검증된 모형 결과가 있을 때만. 그 외에는 방향과 근거를 제시한다. 방향도 근거가 없으면 해당 주제를 제외한다.
- evidence_ids는 제공된 공개 근거 ID만 사용하고 기본적으로 서로 독립적인 2개 출처 이상의 자료에 근거한다.
- 숫자는 입력에 존재하는 수치 또는 자료에 명시된 계산값만 사용. JSON 스키마를 따를 것.

[산업 기사로서 읽을 가치]
- 구매·영업·유통 현장에 실제로 영향을 미치는 변화라면 그 영향까지 설명한다. 다만 모든 사건을 구매·영업의 행동지침으로 끝내지 않는다.
- 독자의 판단을 바꿀 만한 새로운 사실 또는 예측을 우선한다. 단순 통계 증감, 환율 상식, 어종 분류, 형식적 방법론 안내는 시장 결론이 아니다.
- 해외 시세는 확인 가능한 USD/kg와 기준기간·변화폭을 우선 제시한다. 검증되지 않은 USD 환산값을 만들어내거나 환율 환산의 일반론을 본문에 붙이지 않는다.
- 다른 기사·공식 발표·업종 실적에서 연결 근거가 있다면 실제 작용 경로와 파급효과를 구체적으로 밝히고 가장 개연성 높은 전망을 선택한다.
- 한국 산업·경제 전문지에서 자연스럽게 읽히는 제목과 문장을 사용한다. 지표는 주장을 뒷받침하는 증거이지 그 자체가 통찰이 아니다.
- 구체적인 사실이 뒷받침되지 않는 단어('경쟁점', '소비 이전', '구조적 의미', '관측 사실을 종합하면')로 글을 포장하지 않는다.
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

[발행 스타일 — 실제 독자가 읽을 글]
- 제목은 사건·구체적 수치·중요한 시장 변화까지 담는다. 예: '홈플러스 폐점 인근 이마트 매출 11.4% 증가…납품업체는 판로 확보 경쟁 심화'. 실제 출처가 뒷받침할 때만 해당 수치를 쓰고, 제목을 복사하지 않는다.
- 사건의 실질 영향이나 다음 시장 방향이 없는 기사는 본문을 늘리지 말고 다음 후보로 이동한다.
- '무엇이 달라졌나', '왜 달라졌나', '영업·구매에서 활용할 점', '영향과 판단', '여기서 얻는 인사이트' 같은 소제목을 모델 출력 텍스트에 포함하지 않는다.
- 실무를 언급해야 한다는 의무가 없다. 가격, 공급, 경쟁, 제도, 소비의 영향을 가장 자연스럽게 설명하라.
- 늘었다/줄었다라고만 하지 말고 공식 근거에 있는 원수치·변화율·기준일을 쓰되 숫자는 주장의 근거일 뿐 결론이 아니다.
- 일반적으로 이미 알려진 진술을 결론으로 채우지 말라: '점포가 폐점하면 인근 매출이 늘 수 있다', '상권과 매장마다 다르다', '환율 변화로 표시 가격이 다를 수 있다', '하나의 지표로 시장을 판단할 수 없다'.
- 가능한 경우 한 기사에서 관측되지 않는 파급효과를 독립 기사·공식 자료와 연결해 논리적으로 추론하고, 가장 설득력 있는 시장 전망을 제시하라. 충분한 논리와 근거가 있다면 확신이 100%가 아니어도 판단을 피하지 않는다.
- facts와 mechanism에는 서로 다른 내용을 넣고, structural_insight에는 반론이 아니라 구체적인 시장 결론을 써라. what_changes는 자연스러운 후속 전망이 없는 한 빈 문자열로 둔다.

[기사의 목적]
서로 다른 기사·통계를 무리하게 이어 붙이지 않는다. 사건의 실질적 원인과 결과가 연결될 때만 하나의 기사로 분석한다. 서로 다른 핵심 이슈를 매일 2~3편 발행하는 것을 목표로 한다. 서로 다른 근거를 확보할 수 있는 후보를 우선 분석한다. 실제 근거가 부족할 때는 숫자나 사건을 만들어 2편을 채우지 않는다. 단독으로 중요한 사건은 뉴스 해석에서 다루고, 서로 다른 독립 자료를 결합해 새로운 결론을 낼 수 있을 때 심층 분석한다.

[주제·근거]
- 특정 수산물을 우대하지 않는다. 사전에 검토한 editorial_outline과 market_story_clusters를 먼저 읽는다. 실제로 연관된 공개 근거 2개 이상을 사용하고, 같은 발표의 기사 복제는 독립 근거로 세지 않는다.
- ① 중요한 관측(연도·월·어종·규격) → ② 다른 사건/지표와 맞물리는 지점 → ③ 공급·수요·대체재·유통경로에 미치는 실질 영향 → ④ 하나의 잠정 전망이라는 흐름으로 논증한다.
- 분석 중 새로운 공개자료가 더 중요해 보이면 논지를 수정하되 연결 고리가 끊긴 사건을 같은 글에 넣지 않는다. 온라인쇼핑 전체 거래액, 컬리 매출, CJ프레시웨이 취급고 등 무관한 실적을 '식품시장 확대'로 억지로 엮지 않는다.
- 출처별 날짜·대상·통화·분류가 다르면 비교할 수 있는 범위만 비교한다. 한 주의 연어 FOB 가격과 한국 소비자가격을 동일시하지 않는다.
- 데이터가 부족해 서로 다른 사건을 논증할 수 없다면 새 심층 리포트를 만들지 않는다. 기사와 공식 데이터 표시는 별도로 한다.

[분명한 잠정 전망: 예측의 수준 구별]
- 가장 유력한 가격·물량·규제·유통 변화의 방향을 하나 선택한다. 방향을 정할 근거가 충분하지 않다면 outlook.direction='전망 제외'로 두되, 전망 없는 소재가 분석 가치까지 낮다면 보고서 자체를 제외하라.
- outlook.horizon에 전망의 예상 시점을, outlook.judgment에 자연스러운 한국어의 완결된 잠정 결론을, outlook.basis에 실제 근거를 쓴다. outlook.revision_trigger는 전망을 뒤집을 가장 구체적인 변수 하나를 덧붙이는 용도다.
- '가격이 계속 내리면 하락이 이어진다', '뒤집히면 다시 확인해야 한다' 등 순환논법 금지. 양쪽 시나리오를 동등하게 나열하지 말 것.
- 공식 시계열로 검증한 forecast_results가 입력에 포함된 **해당 품목·규격·기간에 한해서만** outlook.numeric_estimate, forecast_method, backtest 작성. 없으면 이 세 필드는 빈 문자열로 둔다. 모델 스스로 예측 가격, 신뢰구간, 확률을 만드는 행위 금지.
- 지금 근거만으로 예상 방향은 말할 수 있으나 상승 폭이 불명이라면 정확한 숫자는 생략한다. 근거가 약한 전망을 확실한 사실처럼 쓰지 않는다.

[한국어 문체]
- 한국인 기자가 쓴 산업 기사처럼 구체적 사실이 앞에 오고 뒤에 배경과 판단이 이어져야 한다.
- 아래의 표현은 작성하지 않는다: '구조적 통찰', '관측이 강화된다', '시사한다', '시사점', '인과 경로', '조건부 경로', '양적 측면과 가격 측면', '확인할 필요가 있다', '지켜봐야 한다', '핵심은 A가 아니라 B다', '자료를 종합하면 알 수 있다'.
- 읽는 사람이 이미 아는 일반 상식·면책성 설명을 문단마다 반복하지 않는다. 반복되는 사실은 한 번만 쓴다. 불확실성은 내용상 중요한 지점에만 한 번 짚는다.
- 제목은 실제 결론이 들어가는 경제지 스타일로. '인사이트'라는 단어 남발 금지. 숫자 기반 비교는 근거가 있을 때만.


[편집 데스크의 최종 판단]
- “연근해 어획 증가와 원양 생산 감소는 서로 다르다”, “환율에 따라 통화별 가격이 다르다”, “한 지표로는 판단할 수 없다”는 그 자체로 독자가 얻는 결론이 아니다. 그 설명밖에 나오지 않으면 소재를 폐기한다.
- 수치를 확보한 사건은 **누가·언제·얼마나** 변했는지를 먼저 적는다. ‘크게 늘었다’ ‘빠르게 줄었다’만 반복해서 변화 규모를 숨기지 않는다. 수치가 없으면 꾸며 넣지 않는다.
- 구조적 결론은 실제 공급·판매·정산·수출입·정책 집행의 **어느 주체에게 어떤 결과가 생겼는지** 말한다. A도 맞고 B도 맞다는 병렬 설명은 결론이 아니다.
- 검증·비교·읽는 법은 작성자의 작업 과정이다. 최종 독자에게 ‘이 통계는 이렇게 보면 안 된다’고 가르치지 않는다.
- 노르웨이 연어 가격은 USD/kg 환산 공식 관측이 근거에 있을 때만 달러 수치를 사용하고, 원화나 크로네 원자료를 본문에서 병렬 해설하지 않는다. USD 가격이 확보되지 않으면 가격 분석을 지어내지 않고 거래량 등 다른 확인된 사실만 싣는다.
- 모든 전망에 국내 유통과 가공업체를 덧붙이지 않는다. 실제 사건의 직접적인 시장 결과가 글을 결정한다.

[필드별 역할 — 글을 잘게 쪼개기 위한 구색 채우기 금지]
- headline, thesis: 첫 두 문장 안에 핵심 변화와 잠정 판단. 제목이 리포트 내용을 과장하지 않아야 함.
- lead, market_change: 독자의 배경 이해와 시간·비교대상 설명. 기사의 주요 배경은 짧게.
- facts: 서로 다른 공개 근거 2개 이상; fact마다 해당 evidence ID를 붙임. 서로 다른 통계의 기간을 숨기지 말 것.
- mechanism: 실제 연결되는 사건·변수의 작용을 설명하는 문단. 짧더라도 충분하면 1개로 끝낼 것. 불필요한 문단을 늘리지 말 것.
- structural_insight: 앞 문단 요약이 아닌 두 자료의 결합에서 도출되는 구체적인 산업 판단.
- what_changes: 시장에 실제로 나타난 변화 또는 근거가 있는 향후 변화. 없으면 빈 문자열로 둘 것. '무엇을 확인해야 하는가' 식의 방법론적 제언은 쓰지 않는다.
- one_sentence: 화면 내부 처리용 결론 요약. 다른 필드에 똑같은 문장을 복붙하지 말 것.
- limitations: 실제로 결론을 바꿀 만한 중요한 근거상의 제약만 짧게. 일반적인 통계 사용 주의사항은 비워 둔다. 기사 원문을 확인하지 못했으면 전문을 읽은 것처럼 쓰지 말 것.
- output depth '핵심'은 충분한 자료가 있을 때만. 분량보다 서로 다른 근거의 연결이 우선이다.
- 공개 출처와 공식 통계만 사용. 내부 회사의 비공개 거래조건·매출·마진·전략은 절대 쓰지 않는다.
- 필드 schema를 채우려고 문단을 늘리지 말 것. 원인과 결과가 구체적으로 확인되지 않은 필드는 빈 문자열로 둔다. 발행 문장은 자료 조사 과정이나 한계 설명이 아니라 확인된 사실과 결론만 담는다.
- 앞선 단락을 다시 요약하는 '같은 지표만으로 판단할 수 없다', '추가로 확인할 필요가 있다', '이는 ~ 시사한다' 같은 문장은 금지. 생략해도 논지에 지장이 없으면 삭제.
- 필드 schema만 채우려는 장황함, 재진술, 형식적 낙관/비관 시나리오 금지. 반드시 지정 JSON 스키마로 응답한다.

[산업 기사로서 읽을 가치]
- 구매·영업·유통 현장에 실제로 영향을 미치는 변화라면 그 영향까지 설명한다. 다만 모든 사건을 구매·영업의 행동지침으로 끝내지 않는다.
- 독자의 판단을 바꿀 만한 새로운 사실 또는 예측을 우선한다. 단순 통계 증감, 환율 상식, 어종 분류, 형식적 방법론 안내는 시장 결론이 아니다.
- 해외 시세는 확인 가능한 USD/kg와 기준기간·변화폭을 우선 제시한다. 검증되지 않은 USD 환산값을 만들어내거나 환율 환산의 일반론을 본문에 붙이지 않는다.
- 다른 기사·공식 발표·업종 실적에서 연결 근거가 있다면 실제 작용 경로와 파급효과를 구체적으로 밝히고 가장 개연성 높은 전망을 선택한다.
- 한국 산업·경제 전문지에서 자연스럽게 읽히는 제목과 문장을 사용한다. 지표는 주장을 뒷받침하는 증거이지 그 자체가 통찰이 아니다.
- 구체적인 사실이 뒷받침되지 않는 단어('경쟁점', '소비 이전', '구조적 의미', '관측 사실을 종합하면')로 글을 포장하지 않는다.
'''

DATA_PROMPT='''너는 한국 수산업 전문지의 데이터 담당 기자다. 공식 자료와 관련 기사에서 **한 품목을 실제로 설명하는 다른 관측**이 연결되는 경우에만 독립된 품목별 분석을 작성한다.
- 환율·금리 단독 글은 작성하지 않는다. 공식 관측치 하나와 무관한 기사 제목을 조합해 길게 늘리지 않는다. 그런 자료는 이미 화면의 수치 카드로 제공된다.
- 한 품목에서 수입 물량/평균단가, 산지가/출하량, 도매/소매, 수출/생산처럼 서로 다른 단계를 **관측된 사실로** 비교한다. 규격·기간이 다르면 차이를 분명히 설명한다.
- 한 가지 시장 판단과 하나의 가장 유력한 향후 방향을 쓴다. 각 outlook 필드에 방향·예상 시기·실제 근거·판단이 바뀔 조건을 적는다. 가격 하락이 이어지면 더 하락한다 같은 빈말은 금지.
- 근거 없이 확률·가격 범위·다음 달 숫자를 만들지 말고, 별도의 검증된 forecast_results가 제공되지 않으면 숫자 예측은 금지한다.
- 한국 경제지 기사처럼 짧고 자연스럽게 작성한다. '양적 측면', '조건부 경로', '관측이 강화된다', '확인할 필요가 있다', '시사점' 등의 어색한 표현은 사용하지 않는다.
- 직접 인용한 공식 데이터 ID와 공개 기사 ID만 활용하고, 비교 가능한 수치를 보존한다. 장황한 면책 문구나 소제목을 채우려는 반복 문장을 쓰지 않는다.
- 숫자 하나뿐이라면 reports=[]로 둔다. 이는 실패가 아니라 자료가 충분할 때만 심층 분석을 하려는 결정이다.
- 공식 숫자의 증감률만 가지고 원고를 늘리지 않는다. 가격·수급·거래·규제의 실제 결과 또는 독립 보도와의 인과 연결이 없으면 reports=[]로 둔다.
- 공식 원자료에 수량과 증가율이 있으면 정확한 기준·값·전년비를 먼저 적는다. 단순히 '증가했다'로 대체하지 않는다.
- 결론을 '지표 해석 주의', '환율 때문에 방향이 다르다'로 마무리하지 않는다. 어떤 상품·판매망·수급에 어떤 결과가 나왔는지 설명한다.
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
    key={'seafood_story_outline_v1':'topics','seafood_news_digest_v1':'briefs'}.get(name,'reports')
    if not isinstance(result,dict) or not isinstance(result.get(key),list):
        raise ValueError('output schema mismatch')
    return result


def research_public_sources(articles, features, now, focus_topics=None):
    """One web-grounded research pass to enrich short RSS snippets.

    Citations are exposed to readers as external source links. This method
    cannot guarantee page-level verification, so downstream numeric checking
    still uses the returned research memo as attributed evidence, not as a
    substitute for independent primary-statistics verification.
    """
    if not os.getenv('OPENAI_API_KEY','').strip() or os.getenv('SEAFOOD_WEB_RESEARCH','1')=='0':
        return [],'검색 미사용'
    pool=balanced_article_pool(articles,maximum=25)
    choices=[];seen=set()
    for item in sorted(pool,key=lambda a:(a.get('score',0),a.get('timestamp',0)),reverse=True):
        if item['category'] not in seen:
            choices.append(item);seen.add(item['category'])
        if len(choices)>=8:break
    # Topic scoring is based on market changes, not a quota of one per category.
    if focus_topics and os.getenv('SEAFOOD_PRESELECT_TOPIC','0')=='1':
        chosen_ids=[aid for topic in focus_topics[:4] for aid in topic.get('article_ids',[])[:2]]
        source_map={a['id']:a for a in pool}
        focused=[source_map[i] for i in chosen_ids if i in source_map]
        if focused:choices=list(dict((a['id'],a) for a in focused).values())[:8]
    if not choices and not features:return [],'공개 자료 없음'
    prompt=(
      '너는 수산물·식품유통 산업의 자료 조사 담당자다. 반드시 웹 검색을 통해 아래 기사 후보 가운데 서로 다른 사건이 엮일 수 있는 3~5개 후보에 대해 '
      '최근 45일 이슈를 출발점으로 과거 3~5년의 비교 통계도 찾아 독립적인 원자료(국가통계, KMI, 수협, 관세청, 통계청, 해외 정부, 기업 실적공시, 다른 언론의 독자 취재)를 찾아라. '
      '연어에 편중하지 말고 한국 수산시장과 유통업계도 조사하라. 주제별 공식 통계의 날짜·대상·단위·변화율을 명확히 구분하라. '
      '동일 보도자료 재인용은 독립 근거가 아니라고 밝혀라. 미확인 수치는 제외하라. RSS 뉴스 후보가 빈약하거나 유통·거시 기사만 있다면 수산물 공식자료를 직접 검색하고 시장 전체의 중요한 변화를 찾아라. '
      '각 주제의 최초 사건 보도, 생산·수입·가격과 같은 서로 다른 통계, 수요·유통 변화를 구분해서 조사하라. 숫자는 기준기간·통화·어종·규격별로 명확히 구분하며, 수산물·대형유통 분야를 우선해 최소 8~12개의 확인 가능한 근거 문장을 작성하고, 각 문장에 검색으로 확인한 실제 출처 링크를 인용하라. '
      '추상적 제언·기업 원가/이익률 추정·가공한 숫자 금지. 반드시 실제 검색 결과를 이용하라. '
      '글은 한국어로 쓰되 광고/검색 요약이 아닌 사실관계를 개조식으로 정리하라.'
    )
    context={'today_kst':now.date().isoformat(),
             'focus_topics':(focus_topics or [])[:4],
             'news_candidates':[{'title':x['title'],'category':x['category'],'source':x['source'],'url':x['url'],'published':x['published']} for x in choices],
             'official_observations':[{'name':f['name'],'period':f['period_end'],'observed':f['observed'],'url':f['data_links'][0]['url'] if f.get('data_links') else ''} for f in features if not f.get('id','').startswith('fx_')][:11],
             'research_targets_when_news_feed_is_thin':[
               '국내외 수산업·식품유통 전반에서 최근 발생한 공급 중단·규제·기업 구조조정·유통채널 변화',
               '해당 사건과 직접 연결되는 생산량·가격·수출입·매출 등 독립 근거',
               '사건과 직접 관련 없는 특정 어종을 검색 목표로 강제하지 말 것' ]}
    req={'model':os.getenv('OPENAI_RESEARCH_MODEL',os.getenv('OPENAI_MODEL',MODEL)),
         'reasoning':{'effort':'low'},
         'tools':[{'type':'web_search','search_context_size':'high'}],
         'tool_choice':'required','include':['web_search_call.action.sources'],
         'input':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(context,ensure_ascii=False)}],
         'max_output_tokens':8500,'store':False}
    try:
        resp=requests.post(API,json=req,timeout=(12,240),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
        resp.raise_for_status()
        body=resp.json()
        collected=[];urls=set()
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
                    # The cited search sentence, not a fabricated full-article quote.
                    start=max(0,full.rfind('\n',0,pos)+1)
                    end=full.find('\n',pos)
                    excerpt=full[start:end if end!=-1 else len(full)].strip()[:850]
                    if len(excerpt)<35:continue
                    urls.add(url)
                    collected.append({'id':'web-'+__import__('hashlib').sha1(url.encode()).hexdigest()[:12],
                        'url':url,'source':parsed.netloc.removeprefix('www.'),
                        'title':anno.get('title') or '웹 검색 출처',
                        'summary':excerpt,'summary_type':'검색 결과의 출처 표기 · 원문 확인 권장',
                        'published':'발행일 별도 확인','timestamp':0,
                        'category':next((a['category'] for a in choices if any(x in excerpt for x in (a['title'][:12],a['category']))),choices[0]['category'] if choices else CATEGORIES[0]),
                        'channels':[],'tags':[],'score':0,'official':False,
                        'impact':'외부 원문 근거','followup':'해당 원문·통계 기준일 확인'})
        return collected[:20],('보강 출처 '+str(len(collected[:20]))+'건')
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        return [],'웹 근거 검색 실패: '+type(exc).__name__


def _numeric_tokens(text):
    # Compare numeric VALUE, not formatting: '37' = '37.0', '1,000' = '1000'.
    # Still ignore isolated one-digit labels and retain percentage/price changes.
    from decimal import Decimal, InvalidOperation
    # Accept Korean large-number spelling: 15만9,810톤 == 159810톤.
    # The original numeric-regex incorrectly read it as 15 and 810,
    # rejecting valid Korean news prose and encouraging unnatural digits.
    text=re.sub(r'(\d+)\s*만\s*(\d{1,3}(?:,\d{3})?|\d{1,4})(?!\d)',
                lambda m:str(int(m.group(1))*10000+int(m.group(2).replace(',',''))),str(text))
    values=[]
    for token in re.findall(r'(?<![\w])\d[\d,]*(?:\.\d+)?',text):
        raw=token.replace(',','')
        if len(raw)<2:continue
        try:values.append(format(Decimal(raw).normalize(),'f'))
        except InvalidOperation:continue
    return values


def _supported(text, evidence):
    support=set(_numeric_tokens(evidence))
    for n in _numeric_tokens(text):
        if n not in support:
            # 100% / 10-minute routine and other unsupported claims are blocked.
            return False
    return True


def _all_evidence(context):
    text=json.dumps(context.get('articles',[])+context.get('official_series',[]),ensure_ascii=False)
    # A limited, auditable derived value: unit export value is revenue / volume.
    # It can only be computed when BOTH growth rates are explicitly in the SAME cited source.
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
    pool=balanced_article_pool(articles,maximum=78)
    included={a['id'] for a in pool}
    # Verified-search citations must be visible even when their scores are lower than news RSS.
    pool += [a for a in articles if a.get('id','').startswith('web-') and a['id'] not in included][:22]
    rows=[{'id':a['id'],'source':a['source'],'title':a['title'],'published':a['published'],
           'category':a['category'],'snippet':a.get('summary','')[:850],
           'official':bool(a.get('official')),'url':a.get('url',''),
           'channels':a.get('channels',[]),'impact':'관측 보도'} for a in pool]
    series=[{'id':f['id'],'name':f['name'],'period_start':f['period_start'],'period_end':f['period_end'],
             'observed':f['observed'],'facts':f['facts'],'data_links':f.get('data_links',[]),
             'limits':f['limitations'],'related_observations':f.get('related_observations',[])} for f in features[:17]]
    return {'now_kst':now.isoformat(),'articles':rows,'official_series':series,
            'topic_candidates':(focus_topics or [{'theme':i['theme'],'article_ids':i['article_ids']} for i in issues[:6]])[:7],
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
        'public_articles':ctx['articles'][:65],
        'official_statistics':ctx['official_series'][:15],
        'topic_candidates':ctx.get('topic_candidates',[])[:5],
        'market_story_clusters':ctx.get('story_candidates',[])[:6],
        'previously_published_titles':(previous_headlines or [])[:6],
        'never_use_internal_business_documents':True,
    }
    try:
        result=_call(PLAN_PROMPT,payload,PLAN_SCHEMA,'seafood_story_outline_v1')
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        print('SEAFOOD editorial outline skipped:',type(exc).__name__)
        return []
    plans=[];used_subjects=set()
    for entry in result.get('topics',[])[:7]:
        try:
            ids=list(dict.fromkeys(x for x in entry['evidence_ids'] if x in eligible))
            # Independent public evidence, or official series with two distinct data sources.
            origins={_public_source_family(eligible[x]) for x in ids}
            fields=('subject','angle','observed_difference','causal_explanation','competing_explanation','outlook_test')
            if len(ids)<2 or len(origins)<2 or any(len(entry.get(k,'').strip())<18 for k in fields):
                continue
            if entry['subject'] in used_subjects:continue
            # Planning must follow a meaningful cross-event cluster after research.
            clusters=ctx.get('story_candidates',[])
            if clusters and not any(len(set(ids)&set(b['evidence_ids']))>=2 for b in clusters):
                continue
            # Only select a plan whose claims are grounded in the supplied public materials.
            if not _supported(' '.join(entry[k] for k in fields),json.dumps([eligible[i] for i in ids],ensure_ascii=False)):
                continue
            plans.append({**{k:entry[k] for k in fields},'evidence_ids':ids[:8],
                          'why_events_connected':entry.get('why_events_connected',''),
                          'tentative_outlook':entry.get('tentative_outlook',''),
                          'outlook_horizon':entry.get('outlook_horizon','')})
            used_subjects.add(entry['subject'])
            if len(plans)>=4:break
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


def _validate_main(payload,ctx):
    allowed_a={a['id'] for a in ctx['articles']}
    allowed_f={f['id'] for f in ctx['official_series']}
    allowed=allowed_a|allowed_f
    evidence_by_id={x['id']:x for x in ctx['articles']+ctx['official_series']}
    evidence=_all_evidence(ctx)
    good=[];reasons=[];seen=set()
    for r in payload.get('reports',[])[:5]:
        try:
            fields=('headline','thesis','lead','market_change','structural_insight','what_changes','one_sentence','limitations','followup')
            mandatory={'headline':10,'thesis':25,'lead':18,'market_change':24,'structural_insight':24,'one_sentence':14}
            if any(not isinstance(r.get(k),str) or len(r[k].strip())<minimum
                   for k,minimum in mandatory.items()):
                reasons.append('핵심 사실·결론 부족');continue
            if any(not isinstance(r.get(k),str) for k in fields):
                reasons.append('원고 필드 누락');continue
            if r['kind'] not in CATEGORIES or r['headline'] in seen:
                reasons.append('분류 또는 제목 중복');continue
            if (not isinstance(r.get('mechanism'),list)
                or not (1<=len(r['mechanism'])<=5)
                or any(not isinstance(x,str) or len(x.strip())<22 for x in r['mechanism'])):
                reasons.append('사건 연결 설명 부족');continue
            outlook=r.get('outlook')
            if outlook is not None:
                if not isinstance(outlook,dict) or outlook.get('direction') not in (
                        '상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외'):
                    reasons.append('전망의 우세 방향 누락');continue
                if outlook.get('direction')!='전망 제외' and any(
                        len(str(outlook.get(k,'')).strip())<minimum for k,minimum in (
                        ('horizon',2),('judgment',20),('basis',20))):
                    reasons.append('근거가 있는 잠정 전망 누락');continue
                if outlook.get('numeric_estimate') and not ctx.get('forecast_results'):
                    reasons.append('검증하지 않은 예측 가격·물량 수치');continue
                if outlook.get('numeric_estimate'):
                    allowed_forecasts=json.dumps(ctx.get('forecast_results',[]),ensure_ascii=False)
                    if not _supported(str(outlook['numeric_estimate']),allowed_forecasts):
                        reasons.append('공식 시계열 예측 결과와 일치하지 않는 값');continue
                if not set(outlook.get('evidence_ids',[])).issubset(allowed):
                    reasons.append('전망에 존재하지 않는 출처');continue
            elif not all(len(r[s][k].strip())>=18 for s in ('scenario_up','scenario_down') for k in ('condition','interpretation')):
                # Historical demonstration cards still use the earlier schema.
                reasons.append('조건부 시나리오 부족');continue
            facts=[]
            for fact in r['facts']:
                refs=list(dict.fromkeys(str(x) for x in fact.get('refs',[]) if x in allowed))
                source_text=json.dumps([evidence_by_id[i] for i in refs],ensure_ascii=False)
                if len(fact.get('text',''))>=30 and refs and _supported(fact['text'],source_text):
                    facts.append({'text':fact['text'],'refs':refs})
            if len(facts)<2:
                reasons.append('검증 가능한 원문 근거 2개 미만/숫자 미일치');continue
            cited={r for fact in facts for r in fact['refs']}
            independent={_public_source_family(evidence_by_id[i]) for i in cited}
            if len(independent)<2:
                reasons.append('서로 다른 출처 근거 부족');continue
            # Checked numbers in all analytical paragraphs; numeric tokens must be public evidence.
            forward=(list(outlook.get(k,'') for k in ('judgment','basis','revision_trigger')) if outlook is not None else
                     [r['scenario_up']['condition'],r['scenario_down']['condition'],
                      r['scenario_up']['interpretation'],r['scenario_down']['interpretation']])
            prose=' '.join([r[k] for k in fields]+r['mechanism']+forward)
            if not _supported(prose,evidence):
                reasons.append('근거에 없는 숫자 사용');continue
            if _duplicate_passages(r):
                reasons.append('같은 문단의 내용 반복');continue
            if outlook is not None:
                banned=('구조적 통찰','조건부 경로','양적 측면','시사점을','관측이 강화','인과 경로',
                        '전망이 강화된다','지속되면 지속','핵심 인사이트')
                if any(token in prose for token in banned):
                    reasons.append('기사답지 않은 추상·순환 표현');continue
                clusters=ctx.get('story_candidates',[])
                if clusters and not any(len(cited & set(cluster['evidence_ids']))>=2 for cluster in clusters):
                    reasons.append('서로 연결된 사건·통계가 아닌 느슨한 근거 묶음');continue
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
                reasons.append('분석 대신 주의사항·면책 설명이 반복됨');continue
            from seafood_editorial_quality import editorial_filler_flags
            public_analysis=' '.join([r['thesis'],r['market_change'],r['structural_insight']]+r['mechanism'])
            if len(editorial_filler_flags(public_analysis))>=3:
                reasons.append('방법론적 문장이 실제 분석을 대신함');continue
            from seafood_editorial_quality import no_reader_value_flags, important_numeric_evidence, quantified_change, strong_editorial_claim
            if not strong_editorial_claim(r['headline'],r['structural_insight']):
                reasons.append('실제 결과 없는 상식·방법론적 결론');continue
            if sum(len(no_reader_value_flags(x)) for x in [r['thesis'],r['market_change']]+r['mechanism'])>=2:
                reasons.append('당연한 설명 또는 해석 유보가 본문을 차지함');continue
            if important_numeric_evidence([evidence_by_id[i] for i in cited]) and not quantified_change(r['market_change']+' '+r['lead']):
                reasons.append('근거에 있는 변화 수치를 본문에서 생략함');continue
            from seafood_editorial_quality import empty_business_buzzword_flags
            # Business decisions are welcome when genuinely supported, never compulsory.
            # A policy, supply or price event can warrant research without a canned
            # 'what sales/procurement should do' paragraph.
            if empty_business_buzzword_flags(' '.join([r['thesis'],r['structural_insight'],r.get('what_changes','')])):
                reasons.append('부자연스러운 설명 또는 기계적인 결론');continue
            if '크로네' in public_analysis or 'NOK/kg' in public_analysis or 'NOK ' in public_analysis:
                reasons.append('본문에 환산되지 않은 노르웨이 통화 가격 사용');continue
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
            r=dict(r);r['channels']=clean_channels;r['facts']=facts[:5];r['policy_ids']=[];r['status']='공개 자료 기반 AI 분석 · 관측 사실과 해석 구분'
            r['character_count']=len(prose);r['length_tier']='충실' if len(prose)>=900 else '간결'
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
    ctx['editorial_outline']=make_editorial_outline(ctx,previous_headlines)
    print('SEAFOOD evidence clusters:',[(x['subject'],x['score']) for x in ctx['story_candidates'][:4]],flush=True)
    if not ctx['story_candidates'] and len(ctx['articles'])<4:
        return [],'서로 다른 기사와 분석 근거가 부족합니다.'
    # Clusters suggest what to study, but they are not a hard whitelist.
    # Two unrelated major events can coexist inside one broad subject, or
    # a verified event may be missed by the narrow keyword taxonomy.
    if not ctx['story_candidates']:
        print('SEAFOOD research: investigating unclustered recent news; the evidence validator still applies',flush=True)
    note='';last_reason='근거 부족'
    accepted=[]
    # Important: previously one accepted result stopped the entire analysis.
    # Continue drafting a *different documented event* to target two full
    # research articles, rather than padding the first article with statistics.
    for attempt in range(4):
        try:
            # Rebuild the evidence pool after the first accepted article.
            # A reminder in a prompt is not enough: if the first article's
            # evidence remains in the input, the model tends to repeat it.
            work_ctx=ctx
            if accepted:
                excluded_articles={x for r in accepted for x in r.get('article_ids',[])}
                excluded_series={x for r in accepted for x in r.get('feature_ids',[])}
                remaining=[row for row in ctx['articles'] if row['id'] not in excluded_articles]
                remaining_series=[row for row in ctx['official_series'] if row['id'] not in excluded_series]
                # Do not discard a usable data-backed subject simply because
                # it has only one RSS source and two independent official series.
                if len(remaining)+len(remaining_series)>=2:
                    work_ctx=dict(ctx)
                    work_ctx['articles']=remaining
                    work_ctx['official_series']=remaining_series
                    from seafood_story_selection import build_story_clusters
                    work_ctx['story_candidates']=build_story_clusters(remaining,remaining_series,[])
                    remaining_ids={row['id'] for row in remaining+remaining_series}
                    work_ctx['editorial_outline']=[p for p in ctx.get('editorial_outline',[])
                       if len(set(p.get('evidence_ids',[]))&remaining_ids)>=2]
                    work_ctx['topic_candidates']=[t for t in ctx.get('topic_candidates',[])
                       if not t.get('article_ids') or len(set(t['article_ids'])&remaining_ids)>=2]
                    work_ctx['previous_headlines']=list(ctx.get('previous_headlines',[]))+[r['headline'] for r in accepted]
                    print('SEAFOOD second-report evidence: %d remaining articles, %d series' %
                          (len(remaining),len(remaining_series)),flush=True)
            output=_call(MAIN_PROMPT,work_ctx,MAIN_SCHEMA,'seafood_deep_research_v1',note)
            good,reasons=_validate_main(output,work_ctx)
            cited_already={x for r in accepted for x in r.get('article_ids',[])}
            kept=[]
            for report in good:
                new_ids=set(report.get('article_ids',[]))-cited_already
                # Allow a different report about the same product/category,
                # but never publish one source event twice under new headings.
                if not new_ids or any(report['headline']==r['headline'] for r in accepted+kept):
                    continue
                if accepted and any(len(set(report.get('article_ids',[])) & set(r.get('article_ids',[]))) >=
                                    len(set(report.get('article_ids',[]))) for r in accepted+kept):
                    continue
                kept.append(report)
                cited_already.update(report.get('article_ids',[]))
            accepted.extend(kept)
            if len(accepted)>=2:
                return accepted[:3],f'AI 리서치 {len(accepted[:3])}편 · 서로 다른 공개 뉴스와 수치 검증 통과'
            last_reason=' / '.join(dict.fromkeys(reasons))[:200] or '두 번째 독립 소재·근거 부족'
            remaining_articles={a['id'] for a in ctx['articles']}-cited_already
            remaining_series={f['id'] for f in ctx['official_series']}-{x for r in accepted for x in r.get('feature_ids',[])}
            if len(remaining_articles)+len(remaining_series)<2:
                break
            already_titles=[x['headline'] for x in accepted]
            already_ids=[id for r in accepted for id in r.get('article_ids',[])]
            note=('현재 승인된 원고는 '+json.dumps(already_titles,ensure_ascii=False)+
                  '. 이미 사용한 기사 ID '+json.dumps(already_ids,ensure_ascii=False)+
                  '를 핵심 근거로 되풀이하지 마라. *다른 실제 사건*을 중심으로 '
                  '가능하면 남은 주제 1~2편을 작성하라. 원문의 수치, 날짜, 대상, '
                  '시장의 영향과 전망을 독립 출처로 입증하라. 사실이 부족하면 reports=[]. '
                  '검수 사유: '+last_reason)
        except requests.HTTPError as e:
            return accepted,('AI 요청 실패 HTTP '+str(e.response.status_code if e.response is not None else 'unknown')+
                              ' · 이전에 검증한 분석 '+str(len(accepted))+'편 보존')
        except requests.RequestException as e:
            return accepted,f'AI 요청 실패: {type(e).__name__} · 이전에 검증한 분석 {len(accepted)}편 보존'
        except (ValueError,KeyError,TypeError) as e:
            last_reason=type(e).__name__
            note='JSON 출력 구조를 바로잡고 이전 자료에 없는 숫자를 추가하지 말 것. '+note[:400]
    if accepted:
        return accepted, f'근거를 확보한 심층 분석 {len(accepted)}편 · 추가 소재 근거 미달 ({last_reason[:80]})'
    print('SEAFOOD analysis validation: '+last_reason)
    return [],'새로운 종합 분석을 작성하지 못했습니다. '+last_reason[:80]


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
    return {'now_kst':now.isoformat(),'features':[{'id':f['id'],'name':f['name'],'title':f['title'],
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
            from seafood_editorial_quality import strong_editorial_claim
            if not strong_editorial_claim(r.get('headline',''),r.get('structural_insight','')):
                reasons.append('상식적 주의사항을 시장 결론으로 제출');continue
            lengths={'headline':12,'conclusion':42,'market_observation':40,'structural_insight':50,
                     'alternative':25,'limits':20}
            if any(not isinstance(r.get(k),str) or len(r[k].strip())<lengths[k] for k in fields):
                reasons.append('완결된 설명 부족');continue
            outlook=r.get('outlook')
            if outlook is not None:
                if not isinstance(outlook,dict) or outlook.get('direction') not in (
                        '상승','하락','횡보','확대','축소','제한적 회복','혼조','전망 제외'):
                    reasons.append('전망 판단이 불분명함');continue
                if any(len(str(outlook.get(k,'')))<n for k,n in (
                    ('horizon',3),('judgment',30),('basis',35),('revision_trigger',15))):
                    reasons.append('방향·근거·예상 시점 부족');continue
            else:
                old_fields=('scenario_support','scenario_challenge','investor_meaning')
                if any(len(str(r.get(k,'')))<25 for k in old_fields):
                    reasons.append('기존 전망 항목 누락');continue
                fields+=old_fields
            if not isinstance(r['transmission'],list) or len(r['transmission'])<2 or any(len(x.strip())<40 for x in r['transmission']):
                reasons.append('전파 경로 두 문단 미충족');continue
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


# v5.27: news-led briefs are separate from the deep statistical research lane.
NEWS_BRIEF_SCHEMA=obj({'briefs':{'type':'array','items':obj({
    'issue_id':{'type':'string'},
    'headline':{'type':'string'},
    'observed_change':{'type':'string'},
    'interpretation':{'type':'string'},
    'conclusion':{'type':'string'},
    'next_check':{'type':'string'},
    'evidence_ids':{'type':'array','items':{'type':'string'}},
    'confidence':{'type':'string','enum':['보도 기반 해석','복수 근거로 교차 확인']},
})}})

NEWS_BRIEF_PROMPT='''너는 한국 경제신문의 식품·수산업 담당 기자다. 독자는 산업 현장에서 일하는 한국인이다.
뉴스를 열심히 조사했다는 설명이 아니라, 중요한 사건에 대한 **완성된 판단**을 제공하라.

[먼저 이슈를 고른다]
- 모든 뉴스를 의무적으로 분석하지 않는다. 중요도는 변화율 숫자의 크기가 아니라 시장에 미친 실제 영향, 영향을 받는 업체·소비자 범위, 공급·판매·규제의 실질적 변화를 기준으로 정한다.
- 지역의 어획 통계 한 건이 전국 산업을 뒤흔드는 사건보다 중요하다는 근거가 없다면 후자를 우선한다.
- 작은 통계 발표나 낱개 수출단가는 기사 아카이브에 남기고, 독립적인 추가 근거가 없으면 심층 분석으로 부풀리지 않는다.
- 하나의 사건을 다룬 기사끼리만 연결한다. 단순히 같은 품종이나 유통 분야라고 연결하지 않는다.
- 출처에 기사 제목과 RSS 요약만 있다면 그 범위에서 판단한다. 전문을 읽었다고 가장하지 않는다.

[기사 문장]
- headline: 단순 발표 제목을 복사하지 말고 **어떤 일이 일어났고 어떤 변화가 생겼는지** 자연스러운 한국어 제목으로 적는다. 내용이 확인된 범위를 벗어나면 안 된다.
- observed_change: 누가, 언제, 무엇을 바꿨는지. 숫자나 조건은 원문에 있는 것만 쓴다.
- interpretation: 그 결과 실제 거래·공급·소비·유통의 어느 부분이 바뀌는지를 설명한다. 인과가 증명되지 않은 경우 새로운 원인을 지어내지 않는다.
- conclusion: 핵심 판단을 **하나의 분명한 문장**으로 적는다. 독자가 이것만 읽어도 시장의 변화를 이해해야 한다.
- next_check: 실질적인 후속 사건이 확정된 경우에만 쓰고, 없으면 빈 문자열로 둔다.
- 한 문단에 새로운 사실이나 판단이 없으면 문단을 없앤다. 같은 말을 바꿔 두 번 설명하지 않는다.
- 한국어 모국어 화자가 읽는 경제 기사처럼 쓴다. '-에 대한','-의 측면에서','-이 작용할 전망','수요가 뒷받침되며 물량을 흡수' 등의 번역투를 피한다.
- 부실한 해석의 예: '어획량 회복과 수출량 증가는 오징어 가격 상승을 뜻하지 않는다', '원양 생산과 연근해 생산은 다르다', '환율 때문에 통화별 가격 흐름은 다르다'. 누구에게 어떤 일이 발생했는지 말하지 못하는 기사는 요약만 남긴다.
- 자료에 물량, 금액, 증감률이 있으면 단위와 기준기간을 붙여 구체적으로 적고 '늘었다/줄었다'만 반복하지 않는다.
- 숫자 없이도 중요한 시행·규제·공급 차질은 사건 자체의 직접적인 결과를 적는다.
- 금지: '확인해야 한다', '살펴볼 필요가 있다', '단정하기 어렵다', '지표만으로 판단하면 안 된다', '시사한다', '핵심 변수가 된다', '구조적 통찰', '추가 자료 확인', '전망이 강화된다'. 자료 조사 방식과 면책성 문장을 본문에 쓰지 않는다.
- 제품 형태(필렛, 슬라이스, 초밥용 네타 등), 업체 영업전략, 국내 가공업체 영향은 이번 사건의 원인·결과와 직접 연결되는 경우에만 쓴다.
- 불확실성을 억지로 없애서는 안 된다. 입증되지 않은 효과는 제외하고, 중요한 규제 시행 여부처럼 독자의 판단을 좌우하는 불확실성만 구체적으로 밝힌다.

[검증]
- 허위 숫자·인용·출처·가격 전망을 만들지 않는다. 실제 주어진 자료가 설명하지 않는 결론은 쓰지 않는다.
- evidence_ids는 실제 입력의 ID만 사용하고, 최소 한 개 기사 ID를 포함한다.
- source_status가 보도 1건이면 confidence='보도 기반 해석'으로 둔다.
- 분석 가치가 없거나 사실을 넘어 해석해야만 그럴듯해지는 사건은 briefs에서 제외한다.
- 결과는 제공된 JSON 스키마 그대로 작성한다.

[산업 기사로서 읽을 가치]
- 구매·영업·유통 현장에 실제로 영향을 미치는 변화라면 그 영향까지 설명한다. 다만 모든 사건을 구매·영업의 행동지침으로 끝내지 않는다.
- 독자의 판단을 바꿀 만한 새로운 사실 또는 예측을 우선한다. 단순 통계 증감, 환율 상식, 어종 분류, 형식적 방법론 안내는 시장 결론이 아니다.
- 해외 시세는 확인 가능한 USD/kg와 기준기간·변화폭을 우선 제시한다. 검증되지 않은 USD 환산값을 만들어내거나 환율 환산의 일반론을 본문에 붙이지 않는다.
- 다른 기사·공식 발표·업종 실적에서 연결 근거가 있다면 실제 작용 경로와 파급효과를 구체적으로 밝히고 가장 개연성 높은 전망을 선택한다.
- 한국 산업·경제 전문지에서 자연스럽게 읽히는 제목과 문장을 사용한다. 지표는 주장을 뒷받침하는 증거이지 그 자체가 통찰이 아니다.
- 구체적인 사실이 뒷받침되지 않는 단어('경쟁점', '소비 이전', '구조적 의미', '관측 사실을 종합하면')로 글을 포장하지 않는다.
'''

def analyze_news_digest(issues, articles, features, now):
    """Optional evidence-checked interpretation. No API key => never fake a conclusion."""
    if not issues or not os.getenv('OPENAI_API_KEY','').strip() or os.getenv('SEAFOOD_NEWS_BRIEF','1')=='0':
        return {},'뉴스 이슈 원문 정리만 표시 · AI 해석 없음'
    article_by_id={a['id']:a for a in articles if a.get('id')}
    feature_by_id={f['id']:f for f in features if f.get('id')}
    context=[];allowed_by_issue={}
    for issue in issues[:6]:
        article_ids=[x for x in issue.get('article_ids',[]) if x in article_by_id]
        feature_ids=[x for x in issue.get('feature_ids',[]) if x in feature_by_id]
        if not article_ids:continue
        allowed_by_issue[issue['id']]=set(article_ids+feature_ids)
        context.append({'issue_id':issue['id'],'headline':issue['headline'],
            'subject':issue['subject'],'source_status':issue['status'],
            'articles':[{'id':x,'title':article_by_id[x]['title'],
                'summary':article_by_id[x].get('summary',''),
                'source':article_by_id[x].get('source',''),
                'published':article_by_id[x].get('published','')}
                for x in article_ids],
            'related_official_series':[{'id':x,'observed':feature_by_id[x].get('observed',''),
                'period_end':feature_by_id[x].get('period_end',''),
                'name':feature_by_id[x].get('name','')} for x in feature_ids]})
    if not context:return {},'해석 가능한 최신 뉴스 없음'
    try:
        payload=_call(NEWS_BRIEF_PROMPT,{'date':now.date().isoformat(),'news_issues':context},
                      NEWS_BRIEF_SCHEMA,'seafood_news_digest_v1')
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        return {},f'뉴스 해석 생성 미완료: {type(exc).__name__}'
    accepted={}
    for item in payload.get('briefs',[]):
        iid=item.get('issue_id')
        if iid not in allowed_by_issue or iid in accepted:continue
        refs=item.get('evidence_ids')
        if not isinstance(refs,list) or not refs or not set(refs).issubset(allowed_by_issue[iid]):continue
        permitted_sources=[article_by_id.get(x) or feature_by_id.get(x) for x in refs]
        if not any(x in article_by_id for x in refs):continue
        evidence=json.dumps(permitted_sources,ensure_ascii=False)
        required=('observed_change','interpretation','conclusion')
        if any(not isinstance(item.get(k),str) or len(item[k].strip())<22 for k in required):continue
        next_check=item.get('next_check','')
        if not isinstance(next_check,str):next_check=''
        if not _supported(' '.join(item[k] for k in required)+' '+next_check+' '+str(item.get('headline','')),evidence):continue
        from seafood_editorial_quality import substantive_news_analysis
        if not substantive_news_analysis(item):continue
        from seafood_editorial_quality import important_numeric_evidence, quantified_change
        if important_numeric_evidence(permitted_sources) and not quantified_change(item['observed_change']):continue
        # Avoid a response that looks precise while being merely a set of disclaimers.
        if all(any(w in item[k] for w in ('확인 필요','판단할 수 없','추가 자료','지켜봐야')) for k in ('interpretation','conclusion')):continue
        claimed='복수 근거로 교차 확인' if item.get('confidence')=='복수 근거로 교차 확인' else '보도 기반 해석'
        origins={_public_source_family(article_by_id[x]) for x in refs if x in article_by_id}
        if len(origins)<2:claimed='보도 기반 해석'
        accepted[iid]={k:item[k].strip() for k in required}
        accepted[iid]['headline']=str(item.get('headline','')).strip() or next(x['headline'] for x in issues if x['id']==iid)
        accepted[iid]['next_check']=next_check.strip()
        accepted[iid].update(evidence_ids=refs,confidence=claimed)
    return accepted,f'뉴스 이슈 해석 {len(accepted)}/{len(context)}편 검증 통과'
