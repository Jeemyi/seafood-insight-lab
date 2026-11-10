"""Public-source topic scoring and rigorous numeric explanatory fallback.

No proprietary customers, sales, margins, contracts, confidential numbers or
internal strategy documents are present here or sent to any model.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import re

TOPICS=(
 ('대형마트·창고형 유통 변화','대형마트/SSM', ('홈플러스','이마트','롯데마트','트레이더스','코스트코','ssm','마트','폐점','점포','대형마트'),20),
 ('광어·우럭 양식 수급','원물 수급/시세',('광어','넙치','우럭','조피볼락','양성물량','양식','산지가','출하'),18),
 ('오징어·대체 수입시장','원물 수급/시세',('오징어','대왕오징어','원양','페루','에콰도르','수입량','어획'),19),
 ('연어·해외 원료시장','원물 수급/시세',('연어','노르웨이','생연어','훈제연어','salmon'),12),
 ('회·초밥과 가공식품','시즌/트렌드',('회초밥','초밥','필렛','네타','밀키트','숙성회','간편식','즉석조리','생선구이','h mr'),14),
 ('식품안전·규제','식품안전/소비심리',('검사','식약처','원산지','검역','비브리오','haccp','오염','mmpa','수입금지','규제'),18),
 ('일본·미국 수출시장','해외',('일본','미국','수출','통관','관세','스시','수출국','쿼터'),15),
 ('온라인·급식 수요','온라인',('쿠팡','컬리','ssg','온라인','급식','식자재','외식','프랜차이즈'),12),
 ('해양수산 공급변동','원물 수급/시세',('고등어','꽃게','새우','문어','장어','낙지','수산','위판','금어기','수온'),8),
)
IMPACT_WORDS={'폐점':12,'매각':12,'부도':13,'구조조정':14,'중단':11,'수입금지':13,
              '급감':9,'급증':9,'급등':8,'급락':8,'어획량':5,'수출량':5,'폐쇄':12,
              '고수온':7,'검역':7,'규제':7,'관세':9,'생산량':5,'위판':5,'전년':4,'공급':4}
SOFT_WORDS={'행사':-5,'할인':-5,'레시피':-6,'맛집':-7,'선물세트':-4,'홍보':-6,'광고':-8,'신제품 출시':-1}

def _hits(text,keywords):
    return sum(1 for word in keywords if word in text)

def evaluate_article(article):
    title=str(article.get('title','')).lower()
    summary=str(article.get('summary','')).lower()
    score=5 + sum(value for word,value in IMPACT_WORDS.items() if word in title)
    score+=sum(value for word,value in SOFT_WORDS.items() if word in title)
    score+=min(8,len(re.findall(r'\d+(?:\.\d+)?\s*(?:%|톤|억원|개점|곳|원)',title))*4)
    if article.get('official'):score+=7
    if len(summary)>=90:score+=2
    if article.get('timestamp',0):score+=2
    article['editorial_score']=score
    return score

def select_market_topics(articles,features,previous_headlines=None,max_topics=5):
    """Choose public market changes, not a rigid species/news quota."""
    previously=' '.join(previous_headlines or []).lower()
    ranked=[]
    for name,category,terms,weight in TOPICS:
        matched=[];publishers=set();species_features=[]
        for a in articles:
            text=(str(a.get('title',''))+' '+str(a.get('summary',''))[:230]).lower()
            n=_hits(text,terms)
            if n==0:continue
            article_score=evaluate_article(a)
            if n>=2:article_score+=4
            matched.append((article_score+min(8,n*2),a))
        matched.sort(key=lambda x:x[0],reverse=True)
        unique=[];seen_ids=set()
        for score,a in matched:
            if a.get('id') in seen_ids:continue
            if not a.get('summary') and score<18:continue
            unique.append(a);seen_ids.add(a.get('id'));publishers.add(a.get('source',''))
            if len(unique)>=7:break
        for f in features:
            txt=(str(f.get('name',''))+' '+str(f.get('observed',''))[:200]).lower()
            if _hits(txt,terms):species_features.append(f)
        if not unique and not species_features:continue
        news_strength=max((evaluate_article(a) for a in unique),default=0)
        feature_strength=min(18, max((f.get('significance',0) for f in species_features),default=0)*.6)
        score=weight+news_strength+feature_strength+min(7,len(publishers)*2)+min(5,len(unique))
        if any(term in previously for term in terms if len(term)>3):score-=9
        # Do not force a report if only a weak generic mention exists.
        if score<23:continue
        ranked.append({'theme':name,'category':category,'score':round(score,1),
             'article_ids':[a['id'] for a in unique[:6]],
             'feature_ids':[f['id'] for f in sorted(species_features,key=lambda x:x.get('significance',0),reverse=True)[:4]],
             'source_count':len(publishers),
             'research_question':_question_for(name),
             'news_titles':[a['title'] for a in unique[:4]]})
    ranked.sort(key=lambda x:x['score'],reverse=True)
    # Distinct topics where possible; e.g. don't publish four copies of the same salmon story.
    chosen=[];used=set()
    for r in ranked:
        fresh=set(r['article_ids'])-used
        if r['article_ids'] and not fresh and not r['feature_ids']:continue
        chosen.append(r);used.update(r['article_ids'])
        if len(chosen)>=max_topics:break
    return chosen

def _question_for(name):
    return {
      '대형마트·창고형 유통 변화':'매출과 점포 변화는 같은 방향인가? 소비 이동과 공급망 영향은 어떻게 다른가?',
      '광어·우럭 양식 수급':'출하·양성물량·산지가를 함께 보면 앞으로 공급은 늘어나는가, 줄어드는가?',
      '오징어·대체 수입시장':'국내 생산, 원양산, 남미산 수입과 가격이 서로 다른 방향으로 움직이는가?',
      '연어·해외 원료시장':'수출액 성장에 물량과 단가가 각각 얼마나 기여했으며 한국 수입 통계와 같은가?',
      '회·초밥과 가공식품':'신선회, 조리용 필렛, 냉동 간편식 중 어떤 상품 형태가 늘고 있는가?',
      '식품안전·규제':'실제 검사 통계, 규제 발효일, 품목 범위가 유통 제한과 일치하는가?',
      '일본·미국 수출시장':'국가별 수출액과 물량을 분해하면 판매량 성장과 단가 변화가 어떻게 다른가?',
      '온라인·급식 수요':'온라인 판매와 외식·급식 수요는 같은 품목에서 동일한 흐름인가?',
      '해양수산 공급변동':'산지 생산·위판·수입 및 소비자가격에 일관된 변화가 있는가?',
    }[name]

def connect_evidence(features,articles):
    """Link related primary measures but never equate incomparable series."""
    for f in features:
        species=f.get('measurements',{}).get('species') or f.get('measurements',{}).get('item','')
        if not species:
            species=next((k for k in ('광어','우럭','오징어','연어','꽃게','고등어','새우','문어') if k in f.get('name','')), '')
        related=[]
        for other in features:
            if other['id']==f['id']:continue
            othertype=other.get('series_type','')
            if species and species in other.get('name','') and (othertype!=f.get('series_type') or othertype=='trade'):
                related.append({'id':other['id'],'name':other['name'],'observed':other['observed'][:550],
                   'period_end':other['period_end'],'limits':other['limitations'][:220]})
        f['related_observations']=related[:3]
        # Title-driven matching only: link not proof of causality.
        terms=[species] if species else ['환율','수입','수산']
        f['article_ids']=[a['id'] for a in articles if any(t in a['title'] for t in terms)][:4]
    return features

def deterministic_data_report(f):
    """Statistical reading for a valid measure if model output fails; never an AI story."""
    measure=f.get('measurements',{})
    kind=f.get('series_type')
    if kind=='trade':
        qty,unit,val=[measure.get(k) for k in ('yoy_qty_pct','yoy_unit_pct','yoy_value_pct')]
        if None in (qty,unit,val):return None
        species=measure['species'];direction=measure['direction'];form=measure['form']
        direction_word='늘었' if qty>0 else '줄었' if qty<0 else '유지됐'
        unit_word='상승' if unit>0 else '하락' if unit<0 else '보합'
        conclusion=(f'{species} {form} {direction} 물량은 전년 동월보다 {abs(qty):.1f}% {direction_word}고 '
             f'평균단가는 {abs(unit):.1f}% {unit_word}했다. '
             f'{direction}액은 {val:+.1f}% 변해 물량과 단가가 서로 다른 방향으로 움직였는지 확인할 수 있다.')
        if qty*unit<0:
            title=f'{species} {form} {direction}물량과 단가, 반대 방향으로 움직여'
        else:title=f'{species} {form} {direction}물량 {qty:+.1f}% · 평균단가 {unit:+.1f}%'
        main=(f'{f["observed"]}. 같은 HSK 코드를 전년 동월과 비교했고, '
               '금액을 중량으로 나눈 단가는 통관 통계의 평균단가이지 개별 계약 가격은 아니다.')
        bridge1=(f'{direction}액은 물량과 단가의 곱으로 결정된다. 금액 변화율 {val:+.1f}%를 '
                 f'물량 {qty:+.1f}%와 단가 {unit:+.1f}%로 나눠 보면, '
                 '금액의 증감이 단가 변화만으로 설명되지 않는다는 점이 확인된다.')
        bridge2=(f'다만 {form} {species}라고 해도 HSK 하위 코드·포장·규격별 거래구성이 달라질 수 있다. '
                 f'같은 코드 {len(measure["hsk_codes"])}개를 비교했지만 품질 차이, 원산지별 수입 비중, '
                 '통관과 소매 판매 간 시차는 이 통계에 포함되지 않는다.')
        insight=(f'동일 분류의 {species} {form}에서 물량 변화 {qty:+.1f}%와 평균단가 변화 {unit:+.1f}%가 '
                 f'함께 관측됐다. 전체 {direction}액 {val:+.1f}%만으로 가격 강세나 수요 변화를 판단하면 '
                 '이 두 요인의 방향을 놓칠 수 있다.')
        alt='거래상대국, 세부 규격 또는 고가·저가 상품의 구성 변화가 평균단가에 반영됐을 수 있다. 원산지·규격별 분포를 확인하기 전에는 수급 원인으로 단정할 수 없다.'
        support='다음 발표에서도 같은 HSK 코드의 물량과 단가 변화가 같은 방향으로 반복되는지 확인한다.'
        challenge='다음 달 금액과 물량의 증가율 차이가 좁혀지거나 평균단가 흐름이 반전되면 이번 패턴은 일시적일 수 있다.'
        later=f'KMI 산지·출하량과 KAMIS {species} 도소매 가격을 같은 규격·기준기간으로 확인해 통관가격과 국내가격 변화를 구분해야 한다.'
    elif kind=='salmon_joint':
        p=measure.get('yoy_price_pct');q=measure.get('yoy_qty_pct')
        if p is None or q is None:return None
        implied=((1+p/100)*(1+q/100)-1)*100
        title=f'노르웨이 연어 수출가격 {p:+.1f}% · 수출량 {q:+.1f}%'
        conclusion=(f'SSB의 같은 주차 신선·냉장 연어 수출가격은 전년 동주 대비 {p:+.1f}%, '
                    f'수출량은 {q:+.1f}% 움직였다. 물량과 가격을 함께 보면 수출 확대가 가격 상승을 동반했는지 구분할 수 있다.')
        main=f'{f["observed"]}. 같은 통화·같은 수산물 형태·같은 주차를 비교했다.'
        bridge1=(f'수출가격과 물량의 변화율을 같은 주차에서 결합하면 '
                 f'가격×물량에 따른 수출가치 증감은 약 {implied:+.1f}%로 계산된다. '
                 '이는 반올림한 두 성장률로 구한 근삿값이며 공식 발표된 수출액과 완전히 같다는 뜻은 아니다.')
        bridge2=('신선·냉장 연어의 국제 수출가격은 한국의 통관단가나 소비자가격과 집계 단계가 다르다. '
                 '한국 수입가격으로 이어지는지 확인하려면 해당 월의 HSK 수입량과 금액, NOK 및 결제통화 환율을 함께 살펴야 한다.')
        insight=(f'동일 주차의 연어 물량 {q:+.1f}%와 수출가격 {p:+.1f}%가 동시에 관측됐다. '
                 '이 때문에 수출액 증가 또는 가격 변화 한 가지 지표만으로 연어 수요와 공급을 설명하면 안 된다.')
        alt='주차별 출하 시기, 수출국별 제품 규격과 등급 구성 차이가 평균가격에 영향을 줄 수 있다. 현재 통계만으로 인과관계를 확정할 수 없다.'
        support='이후 주차에도 같은 방향의 물량·가격 관계가 반복되고 월간 수출액·물량 비교도 뒷받침하는지 확인한다.'
        challenge='이후 주차에 수출물량과 가격의 관계가 역전되면 공급 주도형 해석을 재검토한다.'
        later='노르웨이 수산물위원회의 국가별 월간 수출자료와 한국의 연어 HSK 수입량·평균단가를 기간별로 비교해야 한다.'
    elif kind=='kamis':
        item=measure['item'];cls=measure['channel'];week=measure.get('week_pct');year=measure.get('yoy_pct')
        title=f'{item} {cls}가격, 전년 동기와 최근 일주일 움직임 비교'
        recent=f'{week:+.1f}%' if week is not None else '비교 불가'
        annual=f'{year:+.1f}%' if year is not None else '비교 불가'
        conclusion=f'{item} {cls}가격은 최근 조사에서 {measure["current_price"]:,.0f}원/{measure["unit"]}이다. 1주 전 대비 {recent}, 전년 조사 대비 {annual}로 나타났다.'
        main=f'{f["observed"]}. 같은 품목·품종·등급·단위의 조사값을 비교했다.'
        bridge1='전주 비교는 최근 가격의 방향을, 전년 동기 비교는 계절성을 일부 고려한 가격 수준의 차이를 보여준다. 두 값의 기준기간이 달라 서로 대체할 수 없다.'
        bridge2='도매와 소매는 조사 대상·포장·단위·유통단계가 다를 수 있다. 이 지표만으로 산지가나 수입단가가 변한 원인, 소매상의 마진을 계산할 수 없다.'
        insight=(f'{item} {cls}가격의 최근 변화와 전년 동기 비교가 함께 제공된다. '
                 '특히 두 비교의 방향이 다르다면 단기적인 반등·조정과 계절적 가격 수준을 구분해야 한다.')
        alt='조사 규격·지역별 공급 차이, 판촉 행사, 신선·냉동 구성 차이 등이 가격 변화에 영향을 주었을 수 있지만 현재 통계만으로 비중을 정할 수 없다.'
        support='동일 품종과 규격에 대한 후속 조사가 같은 흐름을 보이는지 관찰한다.'
        challenge='동일 기준의 후속 조사에서 가격 변화 방향이 반전되면 일시적 등락으로 판단해야 한다.'
        later='같은 품목의 KMI 산지가·위판량과 관세청 수입량을 함께 확인하면 어느 유통단계에서 가격 변화가 시작됐는지 비교할 수 있다.'
    else:
        # Never fabricate a comprehensive essay from a single FX or price observation.
        return None
    return {'feature_id':f['id'],'headline':title,'conclusion':conclusion,'market_observation':main,
            'transmission':[bridge1,bridge2], 'structural_insight':insight,'alternative':alt,
            'scenario_support':support,'scenario_challenge':challenge,
            'investor_meaning':later,'limits':f['limitations'], 'article_ids':[],
            'confidence':'낮음','status':'공식 통계 계산 해설 · AI 심층 분석 아님'}
