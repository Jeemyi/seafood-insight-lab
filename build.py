#!/usr/bin/env python3
"""SEAFOOD INSIGHT LAB: public RSS and official seafood indicators -> GitHub Pages.

No internal trade values, private company data, or invented live prices.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from seafood_data import make_features, SSB_LINK
from seafood_ai import analyze, analyze_data, balanced_article_pool, research_public_sources

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site';SITE.mkdir(exist_ok=True)
KST=timezone(timedelta(hours=9))
HEADERS={'User-Agent':'SeafoodInsightLab/1.0 (public RSS research dashboard)'}
CATEGORIES=[
 ('원물 수급/시세',['광어','넙치','우럭','방어','연어','오징어','꽃게','문어','새우','장어','과메기','건어물','수산물 시세','어획','어황','양식','적조','고수온','금어기','수산물 가격','생연어','출하량','위판'],8,'어획량·양식 생산·수입량 변화 가운데 무엇이 최근 시세 변화를 설명하는가'),
 ('코스트코',['코스트코','costco','커클랜드','kirkland','회원제 창고형','코스트코코리아'],8,'신규 출점·PB·소싱 정책 변화가 경쟁사와 전체 유통시장 구조를 어떻게 바꾸는가'),
 ('대형마트/SSM',['이마트','트레이더스','롯데마트','롯데슈퍼','홈플러스','서원유통','에브리데이','gs더프레시','대형마트','ssm','노브랜드','의무휴업','새벽배송 규제','유통사 소싱','비딩'],7,'대형마트와 SSM 간 소비 이동을 확인할 수 있는 매출·점포·점유율 근거는 무엇인가'),
 ('매장 운영',['최저임금','매장 운영','수산코너','영업신고','식품위생법','리뉴얼','폐점','신규 출점','입점','수산 매장','매장 인건비','백화점 식품'],5,'점포 확장·폐점과 노동·위생 기준 변화가 수산 유통 형태를 어떻게 바꾸는가'),
 ('온라인',['쿠팡','컬리','마켓컬리','ssg','스마트스토어','이커머스','온라인 수산','수산대전','로켓프레시','플랫폼 수수료','무료배송','온라인 PB'],6,'온라인 신선식품 시장의 상품·배송·가격 경쟁은 어느 방향으로 이동하는가'),
 ('B2B/급식',['급식','군납','군 급식','조달청','방위사업청','편의점 신선','프랜차이즈','외식업','식자재','급식기업','학교급식','단체급식'],6,'급식·외식·편의점의 수산물 수요가 어떻게 달라지고 있는가'),
 ('식품안전/소비심리',['비브리오','식중독','항생제','방사능','오염수','원산지 표시','표시기준','위생','수산물 안전','MSC','ASC','검역','식약처','수산물 검사'],7,'안전성 통계와 제도 변화가 실제 소비 행동·유통 가능 품목에 어떤 영향을 주는가'),
 ('시즌/트렌드',['설 명절','추석','김장','제수','과메기','대방어','밀키트','완성회','1인 가구','횟감','겨울 수산','명절 수산','절임','제철 수산'],5,'제철 수산물 소비가 전년 같은 기간 및 대체 어종과 비교해 어떻게 달라졌는가'),
 ('비용/거시',['원달러','원/달러','엔화','노르웨이 크로네','환율','물류비','냉동창고','냉장운송','전기요금','포장재','컨테이너 운임','해상운임','수입 단가','금리','냉동비'],5,'환율·운임·에너지 변화와 수입단가 변화의 시차는 얼마나 다른가'),
 ('해외',['일본 수출','일본 스시','스시로','겐키스시','미국 수출','mmpa','대미 수산','관세','수출지원','수산 수출','해외 수산','미국 한인','해외 통관'],5,'국가별 수출입 물량·규제 변화가 수산시장 경쟁에 어떤 차이를 만드는가')
]
CATS={x[0]:{'terms':x[1],'boost':x[2],'question':x[3]} for x in CATEGORIES}
SEAFOOD_HINTS=['수산','해산','어업','어획','어류','양식','수산물','활어','회','광어','우럭','연어','새우','오징어','꽃게','방어','건어물','식품','유통','급식','마트','코스트코','쿠팡','컬리','물류','환율','냉장','냉동','포장재','수입','수출','안전','위생']

SEARCH_QUERIES=[
 ('원물 수급/시세','광어 우럭 연어 오징어 꽃게 수산 시세 어획 양식',True),
 ('원물 수급/시세','수산물 산지가 출하량 고수온 양식 피해',True),
 ('코스트코','코스트코 수산물 납품 공급사 PB 출점 가격',True),
 ('대형마트/SSM','이마트 롯데마트 홈플러스 트레이더스 유통 수산',True),
 ('매장 운영','수산코너 유통매장 영업신고 식품위생 인건비',True),
 ('온라인','쿠팡 컬리 SSG 수산물 수수료 유통',True),
 ('B2B/급식','군 급식 식자재 수산물 조달 편의점',True),
 ('식품안전/소비심리','수산물 비브리오 원산지 식품안전 검역',True),
 ('시즌/트렌드','대방어 과메기 제철 수산물 소비 트렌드',True),
 ('비용/거시','수입 연어 환율 물류비 냉동 수산물',True),
 ('해외','수산물 일본 스시 체인 미국 수출 관세',True),
]

def google_feed(q):
    return 'https://news.google.com/rss/search?q='+quote(q+' when:14d')+'&hl=ko&gl=KR&ceid=KR:ko'

SOURCES=[(f'Google 뉴스 검색·{cat}',google_feed(q),'search',cat) for cat,q,_ in SEARCH_QUERIES] + [
    ('한국경제·경제','https://www.hankyung.com/feed/economy','news',None),
    ('매일경제·경제','https://www.mk.co.kr/rss/30100041/','news',None),
]

DEEP_LINKS=[
 {'title':'KMI 수산업관측센터 · 어종별 관측','url':'https://www.foc.re.kr/'},
 {'title':'수협중앙회 · 위판 정보 확인','url':'https://www.suhyup.co.kr/'},
 {'title':'해양수산부 · 보도자료','url':'https://www.mof.go.kr/'},
 {'title':'관세청 · 수출입무역통계','url':'https://unipass.customs.go.kr/ets/'},
 {'title':'aT KATI · 해외 식품시장 정보','url':'https://www.kati.net/'},
 {'title':'한국수산회','url':'https://www.korfish.or.kr/'},
 {'title':'노르웨이 수산물위원회','url':'https://en.seafood.no/market-insight/'},
 {'title':'노르웨이 통계청 SSB 연어 수출통계','url':SSB_LINK},
 {'title':'한국은행 ECOS','url':'https://ecos.bok.or.kr/'},
]

def clean(x):
    return re.sub(r'\s+',' ',html.unescape(BeautifulSoup(str(x or ''),'html.parser').get_text(' ',strip=True))).strip()


def stamp(entry):
    for field in ('published','updated','pubDate','date'):
        raw=entry.get(field,'')
        if not raw:continue
        try:
            from email.utils import parsedate_to_datetime
            d=parsedate_to_datetime(raw)
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(KST)
        except Exception:pass
        try:
            d=datetime.fromisoformat(raw.replace('Z','+00:00'))
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(KST)
        except Exception:pass
    return None


def parse_feed(content):
    root=ET.fromstring(content)
    entries=[]
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1] not in ('item','entry'):continue
        result={}
        for child in node:
            tag=child.tag.rsplit('}',1)[-1]
            value=''.join(child.itertext()).strip()
            if tag=='link':
                value=child.attrib.get('href') or value
            key={'pubDate':'published','description':'summary','date':'published'}.get(tag,tag)
            if key in ('title','link','summary','published','updated') and value:
                result.setdefault(key,value)
        if result.get('title') and result.get('link'):
            entries.append(result)
    return entries


def fetch_feed(src):
    label,url,kind,category=src
    try:
        r=requests.get(url,timeout=(7,18),headers=HEADERS)
        r.raise_for_status()
        items=parse_feed(r.content)
        if not items:raise ValueError('empty feed')
        return src,items[:65],None
    except Exception as e:
        return src,[],f'{label}: {type(e).__name__}'


def classify(title,desc,forced=None):
    text=title.lower()+' '+desc.lower()[:320]
    scored=[]
    for cat,info in CATS.items():
        matches=sum(3 for kw in info['terms'] if kw.lower() in title.lower())
        matches+=sum(.7 for kw in info['terms'] if kw.lower() in desc.lower()[:300])
        if forced==cat:matches+=2
        scored.append((matches+info['boost']/4,cat,matches))
    scored.sort(reverse=True)
    best=scored[0]
    if best[2]<2.5:return None,[],0
    cat=best[1]
    # Broad finance feeds are accepted only with clearly seafood / distribution-relevant terms.
    if forced is None and not any(kw in title.lower() for kw in SEAFOOD_HINTS):
        return None,[],0
    tags=[c for _,c,m in scored if m>=2.5][:3]
    score=best[2]+CATS[cat]['boost']
    score+=2 if any(x in title for x in ('급등','급락','폐점','관세','인상','인하','공급','수급','위판','가격','규제','금어기','인수','진출')) else 0
    return cat,tags,round(score,1)


def valid_url(url):
    parsed=urlparse(url)
    return url if parsed.scheme in ('http','https') and parsed.netloc else ''


def extract_publisher(title, source):
    if source.startswith('Google 뉴스') and ' - ' in title:
        a,b=title.rsplit(' - ',1)
        if a.strip() and 2<=len(b.strip())<=55:
            return a.strip(),b.strip()
    return title,source


def impact_fields(title,cat):
    """Public market context. Do not infer private margins or force channel effects."""
    text=title.lower()
    channels=[]
    rules=[('코스트코',['코스트코','costco']),('마트',['이마트','롯데마트','홈플러스','마트','트레이더스','ssm']),
           ('매장',['매장','수산코너','백화점','리뉴얼','최저임금']),('온라인',['쿠팡','컬리','ssg','온라인','이커머스']),
           ('B2B',['급식','군납','편의점','프랜차이즈','식자재']),('수출',['수출','일본','미국','스시로','mmpa'])]
    for channel,terms in rules:
        if any(term in text for term in terms):channels.append(channel)
    if any(t in text for t in ('급등','급락','가격 상승','가격 하락','산지가','위판가','인상','인하')):
        label='가격 변화 보도 · 비교 확인'
    elif any(t in text for t in ('어획','출하량','수입량','수출량','생산량','공급','금어기','비축')):
        label='수급·물량 변화 보도'
    elif any(t in text for t in ('폐점','출점','점포','인수','매각','pb','경쟁')):
        label='유통시장 구조 변화'
    elif any(t in text for t in ('규제','검사','인증','위생','법','기준')):
        label='정책·식품안전 변화'
    else:
        label='시장 동향 · 후속 근거 확인'
    follow={'원물 수급/시세':'산지가·위판량·어종별 규격·수출입 물량',
            '코스트코':'신규 출점·경쟁 상품 가격·시즌 행사 편성',
            '대형마트/SSM':'점포 수·동일점 매출·PB 상품 변화',
            '매장 운영':'출점·폐점 일정·영업 규정·인건비 변화',
            '온라인':'온라인 식품 판매통계·수수료·경쟁 상품 가격',
            'B2B/급식':'공개 조달 통계·급식 식자재 수요·상품 규격',
            '식품안전/소비심리':'공식 검사 결과·기준 시행일·소비조사',
            '시즌/트렌드':'전년 동기 수산물 판매·행사·가계 구매자료',
            '비용/거시':'원화 환산 수입단가·환율·운임·동일 기간 가격',
            '해외':'무역통계·원산지별 가격·규제 시행일'}[cat]
    return channels,label,follow


def feed_to_articles(source, entries, now):
    label,_,kind,forced=source
    out=[]
    for row in entries:
        title=clean(row.get('title'))
        title,publisher=extract_publisher(title,label)
        url=valid_url(str(row.get('link','')).strip())
        published=stamp(row)
        if not title or not url or not published:continue
        if not now-timedelta(days=14)<=published<=now+timedelta(hours=2):continue
        summary=clean(row.get('summary') or row.get('description'))
        category,tags,score=classify(title,summary,forced)
        if not category:continue
        if not any(k in title.lower()+' '+summary[:120].lower() for k in SEAFOOD_HINTS):continue
        if len(summary)<44 or 'Google 뉴스' in summary[:25]:
            summary='' if len(summary)<44 else summary
        if (now-published).total_seconds() < 48*3600:score+=2.5
        channels,impact,follow=impact_fields(title,category)
        out.append({'id':hashlib.sha1(url.encode()).hexdigest()[:16],
                    'title':title[:220], 'url':url, 'source':publisher,'published':published.isoformat(timespec='minutes'),
                    'timestamp':int(published.timestamp()),'category':category,'tags':tags,
                    'score':score,'summary':summary[:330],'summary_type':'공개 RSS 소개문' if summary else '제목만 확인',
                    'question':CATS[category]['question'],'official':False,
                    'channels':channels, 'impact':impact,'followup':follow})
    return out


def dedup(rows,maximum=90):
    result=[];titles=[];urls=set()
    for item in sorted(rows,key=lambda x:(x['score'],x['timestamp']),reverse=True):
        key=re.sub(r'[^0-9a-z가-힣]','',item['title'].lower())
        if item['url'] in urls or any(SequenceMatcher(None,key,t).ratio()>.89 for t in titles):continue
        urls.add(item['url']);titles.append(key);result.append(item)
    # Guarantee diversity of category among the highest-priority stories.
    buckets={c:[] for c in CATS}
    for item in result:buckets[item['category']].append(item)
    chosen=[]
    while len(chosen)<maximum and any(buckets.values()):
        round_entries=[]
        for c in CATS:
            if buckets[c]:round_entries.append(buckets[c].pop(0))
        round_entries.sort(key=lambda x:(x['score'],x['timestamp']),reverse=True)
        chosen.extend(round_entries[:maximum-len(chosen)])
    return chosen


def issues_from_articles(articles):
    candidates=[]
    for cat in CATS:
        matches=[a for a in articles if a['category']==cat and len(a['summary'])>=40]
        distinct={a['source'] for a in matches}
        if len(matches)<2 or len(distinct)<2:continue
        selected=[];sources=set()
        for a in matches:
            if a['source'] in sources and len(sources)<2:continue
            selected.append(a);sources.add(a['source'])
            if len(selected)==4:break
        if len(sources)<2:continue
        candidates.append({'id':'issue-'+hashlib.md5(cat.encode()).hexdigest()[:8],
                           'theme':cat,'priority':sum(a['score'] for a in selected)/len(selected),
                           'headline':cat+' 관련 보도에서 어떤 시장 변화가 공통으로 확인되는가?',
                           'question':CATS[cat]['question'],
                           'check':selected[0]['followup'],
                           'bridge_terms':['수급','가격','유통 구조'],
                           'article_ids':[a['id'] for a in selected],
                           'feature_ids':[],'publisher_count':len(sources),
                           'article_count':len(selected),'evidence_level':'출처 비교 질문 · 분석 결론 아님'})
    return sorted(candidates,key=lambda x:x['priority'],reverse=True)[:6]


def homeplus_demo():
    """Historical public-source editorial example, never marked as a live AI report."""
    from datetime import datetime
    date=datetime(2026,11,5,10,39,tzinfo=KST)
    source_1={'id':'homeplus-kbiz-nov-2026','source':'뉴스핌 · 중소기업중앙회 조사',
       'title':'홈플러스 거래업체 피해 72%…대금 정산 지연과 매출 감소 집중',
       'url':'https://ir.newspim.com/news/view/20261105000417',
       'published':date.isoformat(),'timestamp':int(date.timestamp()),'category':'대형마트/SSM','tags':['대형마트/SSM'],
       'summary':'2026년 11월 발표된 중소기업중앙회 2026년 오프라인 대규모유통업체 거래 실태조사. 홈플러스 거래 중소기업 100곳 중 72.0%가 점포 축소·폐점 등으로 피해를 경험했고 이 72곳 모두 정산 지연을 피해 유형으로 답했다. 홈플러스 거래업체 63.0%는 매출 감소, 전체 대형마트 거래업체 매출 감소 응답은 37.0%, 이마트 28.0%, 롯데마트 31.0%, 하나로마트 26.0%. 전년 홈플러스 피해 경험 응답 12.9%.',
       'summary_type':'공개 기사에 인용된 중소기업중앙회 조사','score':18,'official':False,'channels':['마트'],
       'impact':'거래업체 피해 집중','followup':'표본 구성·시계열별 거래여건 비교'}
    source_2={'id':'homeplus-rival-july-2026','source':'조선비즈 · 매장별 판매 실적 취재',
       'title':'홈플러스 폐점 인근 이마트·롯데마트 판매 증가',
       'url':'https://biz.chosun.com/distribution/channel/2026/07/06/I4IYRRRE2ZA7DE3ZE6XQWGHS4E/?outputType=amp',
       'published':datetime(2026,7,6,10,0,tzinfo=KST).isoformat(),'timestamp':int(datetime(2026,7,6,10,0,tzinfo=KST).timestamp()),
       'category':'대형마트/SSM','tags':['대형마트/SSM'],
       'summary':'2026년 7월 보도. 홈플러스 기존 104개 점포 가운데 37곳 폐점, 67곳 운영. 홈플러스 폐점 점포 인근 이마트 창동·묵동점은 2026년 5월 10~31일 매출 전년동기 대비 11.4% 증가. 서울 지역 인근 롯데마트 매장은 평균 9% 증가, 일부 점포 20% 초과.',
       'summary_type':'개별 경쟁매장 매출을 확인한 보도','score':17,'official':False,'channels':['마트'],
       'impact':'상권 내 수요 이동','followup':'폐점 인근·비인근 점포 비교'}
    source_3={'id':'retail-half-2026','source':'뉴스핌 · 산업통상부 주요 유통업체 매출 동향',
       'title':'2026년 상반기 대형마트 매출 -7.3%…SSM도 -6.6%',
       'url':'https://mobile2.newspim.com/news/view/20260803001174',
       'published':datetime(2026,8,3,15,0,tzinfo=KST).isoformat(),'timestamp':int(datetime(2026,8,3,15,0,tzinfo=KST).timestamp()),
       'category':'대형마트/SSM','tags':['대형마트/SSM'],
       'summary':'산업통상부 2026년 상반기 주요 유통업체 매출 동향에 따르면, 대형마트 매출은 전년 상반기 대비 7.3% 감소하고 SSM은 6.6% 감소했다. 같은 기간 백화점 매출은 20.1% 증가. 유통업태 전체 매출 중 대형마트 비중은 전년 상반기 10.3%에서 올해 상반기 8.5%로 하락.',
       'summary_type':'공식 유통 매출 동향을 인용한 기사','score':16,'official':False,'channels':['마트'],
       'impact':'대형마트 업태 둔화','followup':'업태별 동일점 매출과 신규 점포 영향'}
    r={'depth':'핵심','kind':'대형마트/SSM','time_frame':'2026년 7~11월 공개자료 · 시연',
       'headline':'홈플러스 납품업체 72% 피해…인근 경쟁점 매출 증가와는 다른 문제',
       'thesis':'홈플러스 점포 축소 이후 인근 이마트·롯데마트 일부 매장의 매출은 증가했다. 그러나 홈플러스와 거래하는 중소기업은 72%가 피해를 경험했고, 피해 업체 모두 대금 정산 지연을 꼽았다. 소비자의 구매처 이동과 기존 납품업체의 거래 정상화는 별개의 문제라는 사실이 드러난다.',
       'lead':'점포가 문을 닫으면 소비자는 다른 매장으로 이동할 수 있다. 하지만 유통업체가 사라진 자리에 다른 매장의 매출이 늘었다고 해서 기존 납품업체의 매출과 대금 회수가 자동으로 회복되는 것은 아니다. 경쟁 점포의 매출, 거래업체 설문, 대형마트 전체 매출을 나눠 보면 이런 차이가 선명해진다.',
       'facts':[{'text':'중소기업중앙회 조사에서 홈플러스 거래 중소기업 100곳 중 72.0%가 피해를 경험했고, 해당 72곳 모두 정산 지연을 피해 유형으로 답했다. 63.0%는 매출 감소를 응답했다.','refs':[source_1['id']]},
                {'text':'홈플러스 폐점 인근 이마트 창동·묵동점의 2026년 5월 10~31일 매출은 전년 동기보다 11.4% 늘었고, 서울 지역 인근 롯데마트는 평균 9% 증가했다.','refs':[source_2['id']]},
                {'text':'산업통상부 집계에서는 2026년 상반기 전체 대형마트 매출이 전년 동기보다 7.3% 감소하고 SSM도 6.6% 줄었다.','refs':[source_3['id']]}],
       'market_change':'서로 다른 세 통계가 보여주는 시장은 하나가 아니다. 홈플러스 거래업체의 피해 경험률은 전년 조사 12.9%에서 올해 72.0%로 높아졌고, 인근 경쟁점에서는 매출이 늘었다. 그러나 대형마트 업태 전체는 상반기 7.3% 역성장했다. 홈플러스 점포 이탈이 특정 상권의 고객 이동을 만들었더라도 업태 전체의 소비 증가로 해석할 수는 없다.',
       'mechanism':['고객 이동과 납품망 회복 사이에 시차가 있다. 영업을 중단한 점포 인근의 소비자는 같은 장보기 수요를 다른 매장에서 해결할 수 있다. 7월 보도에 나타난 경쟁점 매출 상승은 이러한 국지적 이동과 맞닿아 있다. 다만 해당 수치는 폐점 인근의 일부 매장에서 관찰된 결과이므로, 전국 모든 이마트·롯데마트 점포가 같은 폭으로 성장했다는 의미는 아니다.',
                    '납품업체는 소비자와 다른 문제에 직면한다. 11월 중소기업중앙회 조사에서 피해를 경험한 홈플러스 거래업체가 모두 정산 지연을 답한 점이 중요하다. 구매처가 경쟁 유통사로 바뀌어도 기존 계약과 채권은 이전되지 않기 때문이다. 신규 유통망 확보와 이미 납품한 상품의 대금 회수는 각각 다른 절차를 거친다. 따라서 소비자 판매가 다른 점포로 이전되는 속도와 공급업체의 정상화 속도는 일치하지 않을 수 있다.',
                    '업태 전체의 흐름은 경쟁점 몇 곳의 매출만으로 설명되지 않는다. 산업통상부의 상반기 대형마트 매출 감소율 7.3%는 폐점 인근 점포 매출 증가와 동시에 나타났다. 집계 범위와 기준 시점이 다르므로 두 수치를 직접 빼거나 더할 수는 없다. 다만 경쟁점의 부분적 반사이익을 대형마트 산업 전체의 회복으로 일반화하기 어렵다는 점은 분명하다.'],
       'structural_insight':'이번 변화는 상권의 경쟁과 유통망의 거래 안정성이 별도로 움직일 수 있음을 보여준다. 고객은 근처 다른 매장으로 이동하지만 기존 공급업체에는 정산 지연, 매출 감소, 판로 재편이 동시에 발생했다. 홈플러스에서 빠진 소비가 어디로 갔는지와 홈플러스에 공급하던 기업들이 거래를 어떻게 회복하는지는 서로 다른 질문이다. 산업 전체의 성장 여부도 독립적으로 확인해야 한다.',
       'scenario_up':{'condition':'폐점 인근뿐 아니라 경쟁사 전국 기존점 매출과 실제 구매객 수까지 함께 개선된다면',
                      'interpretation':'국지적 소비 이동을 넘어 경쟁 유통망의 회복으로 해석할 근거가 늘어난다.'},
       'scenario_down':{'condition':'인근 점포의 매출만 오르고 업태 전체 매출 감소와 납품업체의 정산 지연이 지속된다면',
                        'interpretation':'소비가 일부 점포에 집중되는 현상과 거래망 손상은 함께 이어지고 있다는 해석이 더 설득력 있다.'},
       'what_changes':'앞으로는 폐점 인근과 비인근 점포의 동일점 매출을 구분해서 비교해야 한다. 거래업체 피해 조사는 전년과 표본·질문 구성이 같은지도 확인할 필요가 있다. 특히 식품·수산물처럼 납품 주기가 짧은 상품은 유통망 변화의 영향을 별도 품목 통계로 확인해야 하며, 이 조사만으로 수산물 업체의 피해 규모를 계산할 수는 없다.',
       'one_sentence':'경쟁 매장 매출이 늘어나는 것과 기존 납품업체가 회복되는 것은 같은 사건이 아니다.',
       'limitations':'납품업체 조사는 2026년 11월 발표된 설문이고, 경쟁점 매출은 2026년 5월 일부 점포의 실적이며, 업태 매출은 상반기 전체 기준이다. 같은 기간·동일 표본의 비교가 아니며, 수산물 공급업체만 분리한 수치는 없다.',
       'article_ids':[source_1['id'],source_2['id'],source_3['id']],'feature_ids':[],'policy_ids':[],
       'confidence':'중간','channels':['마트'],'impact':'소비 이동과 거래망 피해의 차이',
       'followup':'업태별 동일점 매출·폐점 주변 상권·납품업체 정산 지연',
       'status':'공개자료 기반 분석 시연 · 자동 생성 결과 아님'}
    return [source_1,source_2,source_3],r


def demo_data():
    """A clearly labeled historical demonstration using two distinct public datasets."""
    now=datetime.now(KST)
    sample_date=datetime(2026,11,4,8,0,tzinfo=KST)
    a={'id':'ssb-public-sample','title':'SSB: 2026년 44주차 연어 수출단가 74.98 NOK/kg, 물량 28,444톤',
       'url':'https://www.ssb.no/en/utenriksokonomi/utenrikshandel/statistikk/eksport-av-laks',
       'source':'노르웨이 통계청 SSB','published':sample_date.isoformat(),'timestamp':int(sample_date.timestamp()),
       'category':'원물 수급/시세','tags':['원물 수급/시세'],'score':17,
       'summary':'SSB 공식 통계에서 2026년 44주차 신선·냉장 연어 수출가격은 74.98 NOK/kg으로 전년 동기 대비 6.9% 하락했다. 반면 수출량은 28,444톤으로 전년 동기 대비 14.3% 증가했다.',
       'summary_type':'공식 주간 통계','question':'동일 주차의 가격과 물량을 함께 비교',
       'official':True,'channels':[],'impact':'물량 증가·단가 하락 동시 관측','followup':'다음 주 수출량·가격·원산지별 수요'}
    a2={'id':'nsc-public-sample','title':'노르웨이 수산물위원회: 10월 연어 수출액 사상 최대, 물량 증가율은 더 높아',
       'url':'https://en.seafood.no/news-and-media/news-archive/norwegian-seafood-exports-remained-stable-in-october/',
       'source':'Norwegian Seafood Council','published':sample_date.isoformat(),'timestamp':int(sample_date.timestamp())-600,
       'category':'원물 수급/시세','tags':['원물 수급/시세'],'score':16,
       'summary':'2026년 10월 노르웨이 연어 수출은 159,810톤, 수출액 약 130억 NOK를 기록했다. 전년 동월 대비 수출물량은 9%, 수출액은 6% 증가해 평균단가는 하락한 것으로 계산된다.',
       'summary_type':'공식 월간 수출 발표','question':'금액 증가를 가격과 물량 효과로 분해',
       'official':True,'channels':[],'impact':'수출액 성장보다 빠른 물량 증가','followup':'월별 물량·평균단가·국가별 수출구성'}
    f={'id':'salmon_export_price','name':'노르웨이 생연어 수출가격·물량',
       'title':'노르웨이 연어 수출은 물량이 늘었지만 단가는 낮아졌다',
       'subtitle':'SSB 공식 통계 · 2026년 44주차 시연','period_start':'2026년 43주','period_end':'2026년 44주',
       'facts':[{'label':'신선·냉장 연어 수출가','value':'74.98 NOK/kg','detail':'44주차 · SSB'},
                {'label':'전년 동주 가격','value':'-6.9%','detail':'전년 동주 대비'},
                {'label':'전년 동주 수출물량','value':'+14.3%','detail':'28,444톤 · SSB'}],
       'observed':'2026년 44주차 신선·냉장 연어 수출가격 74.98 NOK/kg · 전년 동주 -6.9%; 같은 주 수출량 28,444톤 · 전년 동주 +14.3% (SSB 공식 발표)',
       'data_links':[{'url':a['url'],'label':'SSB 연어 공식 가격·물량 통계'}],
       'article_ids':['ssb-public-sample'],'category':'원물 수급/시세','channels':[],
       'impact':'수출물량 증가와 단가 하락이 동시에 발생',
       'limitations':'44주 수치는 주간 통계, 10월 수치는 월간 통계로 직접 혼합해 변화율 계산 불가'}
    report={'depth':'핵심','kind':'원물 수급/시세','time_frame':'2026년 10월·44주차 · 공개자료 시연',
      'headline':'노르웨이 연어 수출액 사상 최대…가격보다 물량이 성장 이끌어',
      'thesis':'2026년 10월 노르웨이 연어 수출액은 사상 최고치를 기록했지만, 수출액 증가율보다 물량 증가율이 높았다. 월간 수출액을 가격과 물량으로 분해하면 성장을 주도한 것은 가격 인상이 아니라 더 많은 물량의 판매였다. 같은 시기 공식 주간 통계 역시 전년 대비 물량 증가와 단가 하락을 보여준다.',
      'lead':'수출액이 늘었다고 연어값까지 오른 것은 아니다. 10월 수출액과 물량을 나눠 살펴보면 물량 증가가 성장을 이끌었다. 44주차 가격 통계도 같은 방향을 보여주지만, 월간 수치와 주간 수치를 하나로 계산하지는 않았다.',
      'facts':[{'text':'노르웨이 수산물위원회에 따르면 2026년 10월 연어 수출량은 159,810톤으로 전년 동월보다 9% 증가했고, 수출액은 약 130억 NOK로 6% 증가했다.','refs':['nsc-public-sample']},
               {'text':'SSB의 2026년 44주차 통계에서 신선·냉장 연어 수출단가는 74.98 NOK/kg으로 전년 동주보다 6.9% 낮았고, 같은 주 수출물량은 28,444톤으로 14.3% 증가했다.','refs':['ssb-public-sample','salmon_export_price']}],
      'market_change':'2026년 10월 연어 수출액 증가율(+6%)이 수출량 증가율(+9%)보다 낮다는 것은 월간 평균 판매단가가 낮아졌음을 의미한다. 약 1.06을 1.09로 나누면 월간 평균단가 변화율은 약 -2.8%다. 이 계산은 월간 집계의 반올림 수치를 사용한 근삿값이다.',
      'mechanism':['첫 번째 근거는 월간 수출액과 물량의 차이다. 수출액만 보면 시장의 가격 경쟁력이 강화됐다는 결론을 내릴 수 있지만, 수출물량 증가가 더 빨라 평균단가는 오히려 하락했다. 수출액 기록이 판매단가 상승의 증거가 아닌 이유다.',
                   '두 번째 근거는 SSB의 주간 통계다. 44주차의 신선·냉장 연어 수출량은 전년 동주 대비 늘고 가격은 하락했다. 월간 통계와 관측 빈도는 달라 완전히 동일한 계산에 합칠 수 없지만, 두 자료는 물량 확대와 가격 약세가 공존한다는 동일한 방향을 독립적으로 지지한다.'],
      'structural_insight':'노르웨이의 연어 수출 기록은 가격보다 물량이 늘면서 만들어졌다. 공급이 확대되면 판매량이 늘어도 평균단가는 내려갈 수 있다. 따라서 수출액만 보고 연어 가격이 강세라고 해석해서는 안 된다. 수출량과 평균단가를 나눠 보고 주요 수입국의 소비 흐름까지 확인해야 이번 확대가 얼마나 오래 이어질지 판단할 수 있다.',
      'scenario_up':{'condition':'향후 주요 수출시장에서 소비와 재수출 물량이 동반 확대되고, 공급 증가분을 계속 흡수한다면',
                     'interpretation':'가격을 억지로 끌어올리지 않아도 물량 중심 수출 확대가 유지될 여지가 생긴다.'},
      'scenario_down':{'condition':'수출물량은 계속 증가하는데 주요 시장의 소비·재수출이 둔화되고 단가 하락이 확대된다면',
                       'interpretation':'수출액 기록 뒤에 공급 압력과 가격 경쟁이 심화되는 구조를 더 의심해야 한다.'},
      'what_changes':'다음 분석에서는 월별 전체 연어 수출물량과 평균단가를 분리해 추적하고, 폴란드 등 가공·재수출 거점과 최종 소비국의 수요를 비교해야 한다. 한국 시장과 연결하려면 같은 시점의 관세청 수입단가와 환율을 별도로 확인해야 한다.',
      'one_sentence':'사상 최대 수출액이라는 성적표는 가격의 호황이 아니라 물량 확대가 만든 기록일 수 있다.',
      'limitations':'시연용 원고로, 2026년 10월 수산물위원회 월간 발표와 44주차 SSB 통계만 비교한다. 월간과 주간 수치를 직접 합산하지 않았고, 한국 수입단가나 기업별 손익은 분석 대상이 아니다.',
      'article_ids':['nsc-public-sample','ssb-public-sample'],'feature_ids':['salmon_export_price'],'policy_ids':[],
      'confidence':'중간','status':'시연 전용 · 2026년 10월 공개 공식자료 기반 · 자동 생성 결과 아님',
      'channels':[],'impact':'수출물량 주도형 성장 · 가격 약세 동반',
      'followup':'월간 연어 수출량과 단가, 국가별 수요·재수출 물량'}
    distribution_articles,distribution_report=homeplus_demo()
    return {'generated_at':now.isoformat(timespec='minutes'),'articles':[a,a2]+distribution_articles,'features':[f],
            'deep_reports':[distribution_report,report],'deep_status':'샘플 전용 — 자동 AI 생성 아님',
            'research_sources':[],'report_factual_brief':False,'report_archived':False,'last_report_updated_at':datetime(2026,11,5,10,39,tzinfo=KST).isoformat(),
            'data_reports':[],'data_ai_status':'샘플 전용 — 자동 AI 생성 아님',
            'issue_candidates':[],'analysis_status':'2026년 10월 공식 과거 통계로 만든 시연 · 실시간 자료 아님',
            'sources_ok':0,'sources_total':len(SOURCES),'errors':[],
            'metric_errors':[],'demo':True, 'policy_sources':[], 'deep_links':DEEP_LINKS}


def load_previous_report():
    """Read repository-persisted last valid analysis, not yesterday's unverified fallback."""
    try:
        data=json.loads((SITE/'data.json').read_text(encoding='utf-8'))
        reports=data.get('deep_reports',[])
        if not isinstance(reports,list) or not reports:return None
        # Archiving a report does not make it fresh again.
        date=data.get('last_report_updated_at') or data.get('generated_at')
        if not isinstance(date,str) or len(date)<10:return None
        sources=data.get('research_sources',[])
        return {'reports':[dict(r) for r in reports[:3]],'date':date,
                'sources':sources,'articles':data.get('articles',[]),'features':data.get('features',[])}
    except (OSError,ValueError,TypeError,AttributeError):return None


def make_factual_brief(articles, features, now):
    """Truthful fact-based fallback. Not marketed as a comprehensive AI report."""
    best=[];used_sources=set()
    for a in articles:
        if len(a.get('summary',''))<55 or a['source'] in used_sources:continue
        best.append(a);used_sources.add(a['source'])
        if len(best)==3:break
    if not best and not features:return []
    category=best[0]['category'] if best else features[0]['category']
    title=best[0]['title'] if best else features[0]['title']
    observations=[f"{a['source']}의 {a['published'][:10]} 보도: {a['title']} — {a['summary'][:250]}" for a in best]
    if features: observations.append(features[0]['observed'])
    desc=' '.join(observations)
    if not desc:return []
    fact_refs=[{'text':x['summary'][:350], 'refs':[x['id']]} for x in best]
    if features:fact_refs.append({'text':features[0]['observed'],'refs':[features[0]['id']]})
    evidence_statement=' '.join(o[:280] for o in observations[:2])
    return [{'depth':'보조','kind':category,'time_frame':now.date().isoformat()+' 기준',
        'headline':'주요 수산·유통 동향: '+title[:70],
        'thesis':evidence_statement,'lead':'관련 공개 기사와 공식 통계에서 직접 확인되는 내용을 정리했습니다. 여러 자료로 검증되지 않은 원인이나 수익성은 추정하지 않았습니다.',
        'facts':fact_refs,'market_change':desc[:900],
        'mechanism':['현재 공개된 자료만으로는 서로 다른 변화가 같은 원인에서 비롯됐다고 단정할 수 없습니다. 각 출처의 날짜와 지표를 구분해 읽어야 합니다.',
                     '관측된 시세나 공급 변화가 유통 판매가격에 얼마나 반영되는지는 같은 기간의 거래규격과 환율, 판매 통계로 별도로 확인해야 합니다.'],
        'structural_insight':'이번 자료에서 확인되는 변화는 기사와 공식 관측치에 한정됩니다. 수급과 유통채널 전체의 방향을 판단하려면 비교 대상 기간과 품목이 일치하는 별도 통계가 필요합니다.',
        'scenario_up':{'condition':'같은 기준의 후속 통계에서 변화가 반복 확인될 때','interpretation':'단발성 사건보다 지속적인 시장 변화로 볼 수 있습니다.'},
        'scenario_down':{'condition':'후속 자료에서 다른 흐름이 확인될 때','interpretation':'현재 보도만으로 방향을 단정할 수 없습니다.'},
        'what_changes':'자료별 기준일·대상·규격을 확인하고 같은 기간의 수출입·소비 및 산지 통계와 대조해야 합니다.',
        'one_sentence':'공개 자료에서 확인된 주요 현황을 정리했습니다.',
        'limitations':'심층 AI 분석에 필요한 독립 근거가 충분하지 않아, 검증된 기사와 공식 지표만 정리한 자료입니다.',
        'article_ids':[x['id'] for x in best], 'feature_ids':[features[0]['id']] if features else [],
        'policy_ids':[],'confidence':'낮음','channels':[],'impact':'공개 자료로 확인한 현황',
        'followup':'해당 분야의 후속 공식 통계','status':'공개 자료 요약 · 심층 분석 미완료'}]


def collect():
    now=datetime.now(KST)
    all_articles=[];errors=[];ok=0
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures=[pool.submit(fetch_feed,s) for s in SOURCES]
        for future in as_completed(futures):
            src,entries,err=future.result()
            if err:errors.append(err)
            else:
                ok+=1
                all_articles.extend(feed_to_articles(src,entries,now))
    articles=dedup(all_articles)
    features,metric_errors=make_features(now)
    # Articles are not proof of changes to private buying costs or channel profit.
    for f in features:
        terms=['연어','노르웨이'] if f['id']=='salmon_export_price' else ['환율','수입','외화']
        f['article_ids']=[a['id'] for a in articles if any(t in a['title'] for t in terms)][:3]
    issues=issues_from_articles(articles)
    search_sources,research_status=research_public_sources(articles,features,now)
    print('SEAFOOD research:',research_status)
    reports,deep_status=analyze(articles+search_sources,features,now,issues)
    data_reports,data_status=analyze_data(features,articles,reports,now)
    last_report_updated_at=now.isoformat(timespec='minutes') if reports else None
    archive=False
    factual_brief=False
    if not reports:
        old=load_previous_report()
        if old:
            reports=old['reports']
            last_report_updated_at=old['date']
            archive=True
            # Keep linked cited sources even when today's feed no longer includes them.
            by_id={a['id']:a for a in articles+search_sources}
            for source in old['articles']+old['sources']:
                if source.get('id') not in by_id:
                    search_sources.append(source);by_id[source['id']]=source
            deep_status='지난 시장 분석 · '+last_report_updated_at[:10]+' 작성'
        elif articles or features:
            reports=make_factual_brief(articles,features,now)
            if reports:
                factual_brief=True
                last_report_updated_at=now.isoformat(timespec='minutes')
                deep_status='공개 자료를 바탕으로 정리한 주요 동향 · 심층 분석과 구분'
        if not reports:
            # Clearly marked historical editorial, never presented as today's news.
            sample=demo_data()
            reports=sample['deep_reports']
            for report in reports:
                report['status']='지난 분석 · 공개된 2026년 10월 통계 · 신규 분석 아님'
            last_report_updated_at='2026-11-05T10:39:00+09:00'
            archive=True
            deep_status='지난 시장 분석 · 2026년 10~11월 자료' 
            search_sources=search_sources+sample['articles']
    if not reports:raise RuntimeError('An on-screen research article is always required')
    return {'generated_at':now.isoformat(timespec='minutes'),'articles':articles,'features':features,
            'issue_candidates':issues,'deep_reports':reports,'deep_status':deep_status,
            'research_sources':search_sources,'archived_features':old['features'] if archive and 'old' in locals() and old else [],
            'report_archived':archive,'report_factual_brief':factual_brief,
            'last_report_updated_at':last_report_updated_at,
            'data_reports':data_reports,'data_ai_status':data_status,
            'analysis_status':f'공식 자동 지표 {len(features)}개 · ECOS·SSB 공개 데이터 · 비교불가 수치 제외',
            'sources_ok':ok,'sources_total':len(SOURCES),'errors':errors,
            'metric_errors':metric_errors,'demo':False,'policy_sources':[], 'deep_links':DEEP_LINKS}


def publish(data):
    output=json.dumps(data,ensure_ascii=False,indent=2)
    (SITE/'data.json').write_text(output,encoding='utf-8')
    templ=(ROOT/'template.html').read_text(encoding='utf-8')
    js='const NEWS_DATA='+json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+';'
    if '/*__INITIAL_DATA__*/' not in templ:raise RuntimeError('template injection marker absent')
    html_page=templ.replace('/*__INITIAL_DATA__*/',js)
    (SITE/'index.html').write_text(html_page,encoding='utf-8')
    print(json.dumps({'articles':len(data['articles']),'features':len(data['features']),
                      'deep_reports':len(data['deep_reports']),'data_reports':len(data['data_reports']),
                      'sources_ok':data['sources_ok'],'sources_total':data['sources_total'],
                      'deep_status':data['deep_status'],'data_ai_status':data['data_ai_status'],
                      'metric_errors':data['metric_errors']},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--demo',action='store_true',help='clearly labeled public-SSB historical sample, not live data')
    options=parser.parse_args()
    publish(demo_data() if options.demo else collect())

if __name__=='__main__':main()
