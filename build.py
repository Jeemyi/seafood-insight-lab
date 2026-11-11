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
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from urllib.parse import quote, urlparse, parse_qs, unquote
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from seafood_data import make_features, SSB_LINK
from seafood_ai import analyze, analyze_data, balanced_article_pool, research_public_sources, analyze_news_digest
from seafood_editorial import (select_market_topics, connect_evidence,
                              deterministic_data_report)
from seafood_newsroom import (retain_archive,split_archive,make_issue_digest,
                              ARCHIVE_DAYS,WINDOW_DAYS,MAX_ARCHIVE)

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site';SITE.mkdir(exist_ok=True)
KST=timezone(timedelta(hours=9))
HEADERS={'User-Agent':'SeafoodInsightLab/1.0 (public RSS research dashboard)'}
CATEGORIES=[
 ('원물 수급/시세',['salmon','squid','fisheries','aquaculture','seafood prices','fishery','crab','shrimp','mackerel','pollock','광어','넙치','우럭','방어','연어','오징어','꽃게','문어','새우','장어','과메기','건어물','수산물 시세','어획','어황','양식','적조','고수온','금어기','수산물 가격','생연어','출하량','위판'],8,'어획량·양식 생산·수입량 변화 가운데 무엇이 최근 시세 변화를 설명하는가'),
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
SEAFOOD_HINTS=['seafood','salmon','squid','fisheries','aquaculture','fishery','crab','shrimp','mackerel','pollock','catch','exports','imports','수산','해산','어업','어획','어류','양식','수산물','활어','회','광어','우럭','연어','새우','오징어','꽃게','방어','고등어','갈치','명태','멸치','참치','굴','가리비','주꾸미','전복','낙지','장어','건어물','식품','유통','급식','마트','홈플러스','롯데슈퍼','트레이더스','코스트코','수협','해양수산','KMI','쿠팡','컬리','물류','환율','냉장','냉동','포장재','수입','수출','안전','위생']

# Broad topic queries rather than long AND keyword strings. Date relevance is
# assessed separately so a single Google RSS search does not overconstrain recall.
SEARCH_QUERIES=[
 # Independent, short searches. Do not combine many unrelated words with OR:
 # Google News may return no RSS items for such compound queries.
 ('원물 수급/시세','수산물 가격',True),
 ('원물 수급/시세','오징어 어획',True),
 ('원물 수급/시세','광어 산지가',True),
 ('원물 수급/시세','고등어 어획량',True),
 ('원물 수급/시세','연어 수입',True),
 ('원물 수급/시세','수산물 양식',True),
 ('원물 수급/시세','수산물 수입량',True),
 ('코스트코','코스트코 식품',True),
 ('대형마트/SSM','홈플러스 납품',True),
 ('대형마트/SSM','대형마트 신선식품',True),
 ('대형마트/SSM','이마트 트레이더스',True),
 ('매장 운영','수산물 매장',True),
 ('온라인','온라인 수산물',True),
 ('온라인','신선식품 배송',True),
 ('B2B/급식','급식 수산물',True),
 ('B2B/급식','식자재 유통',True),
 ('식품안전/소비심리','수산물 검역',True),
 ('식품안전/소비심리','수산물 원산지',True),
 ('시즌/트렌드','제철 수산물',True),
 ('시즌/트렌드','수산물 소비',True),
 ('비용/거시','냉동 수산물 운임',True),
 ('비용/거시','수산물 수입 가격',True),
 ('해외','노르웨이 연어',True),
 ('해외','일본 수산물 수출',True),
 ('해외','미국 수산물 관세',True),
 ('해외','한국 수산물 수출',True),
 # New official releases can be weeks/months ahead of the legacy MOF tables.
 # They are research leads only; claimed quantities still need verified sources.
 ('원물 수급/시세','site:mods.go.kr 어업생산동향조사',True),
 ('원물 수급/시세','site:foc.re.kr 수산업관측 생산량 가격',True),
 ('원물 수급/시세','site:kmi.re.kr 수산관측 주요 품목',True),
 ('해외','site:mof.go.kr 수산물 수출입 실적',True),
 ('원물 수급/시세','수산물 도매가격',True),
 ('원물 수급/시세','수산물 위판 실적',True),
 ('원물 수급/시세','수산물 공급 부족',True),
 ('원물 수급/시세','수산업 고수온 양식 피해',True),
 ('원물 수급/시세','넙치 출하량',True),
 ('원물 수급/시세','우럭 양식 가격',True),
 ('원물 수급/시세','고등어 수입 가격',True),
 ('원물 수급/시세','명태 수급',True),
 ('원물 수급/시세','꽃게 어획',True),
 ('원물 수급/시세','새우 수입 관세',True),
 ('원물 수급/시세','참치 어획 규제',True),
 ('원물 수급/시세','갈치 산지가',True),
 ('원물 수급/시세','양식장 폐사 피해',True),
 ('원물 수급/시세','생굴 수급',True),
 ('원물 수급/시세','fresh salmon export price Norway',True),
 ('원물 수급/시세','global fishmeal prices',True),
 ('원물 수급/시세','squid catches Peru China Korea',True),
 ('원물 수급/시세','seafood wholesale prices Korea',True),
 ('대형마트/SSM','홈플러스 회생 폐점',True),
 ('대형마트/SSM','대형마트 매출 점포',True),
 ('대형마트/SSM','이마트 식품 매출',True),
 ('대형마트/SSM','롯데마트 신선식품',True),
 ('대형마트/SSM','슈퍼마켓 SSM 매출',True),
 ('코스트코','코스트코 신규 출점',True),
 ('코스트코','코스트코 매출 식품',True),
 ('온라인','컬리 신선식품',True),
 ('온라인','쿠팡 신선식품',True),
 ('온라인','SSG닷컴 식품',True),
 ('B2B/급식','식자재 가격 급식',True),
 ('B2B/급식','CJ프레시웨이 식자재',True),
 ('B2B/급식','학교급식 식재료 수산',True),
 ('식품안전/소비심리','수입수산물 부적합',True),
 ('식품안전/소비심리','수산물 원산지 위반',True),
 ('식품안전/소비심리','수산물 검역 금지',True),
 ('식품안전/소비심리','seafood import ban regulation',True),
 ('시즌/트렌드','수산물 소비 추세',True),
 ('비용/거시','수산물 냉동 물류비',True),
 ('해외','한국 수산식품 수출 실적',True),
 ('해외','수산물 수입 통관',True),
 ('해외','Japan seafood imports Korea',True),
 ('해외','Norway Seafood Council exports',True),
 ('해외','NOAA seafood imports MMPA',True),
 ('해외','EU seafood trade regulation',True),
 ('해외','Russia pollock export supply',True),
 ('해외','US seafood tariff',True),
 ('해외','China seafood imports prices',True),
 ('해외','site:newsis.com 수산물 유통',True),
 ('해외','site:yna.co.kr 수산물 수입',True),
 ('원물 수급/시세','site:fishnews.co.kr 수산',True),
]

NEWS_LOOKBACK_DAYS=30

# The 30 Google News feeds share one provider. Pace requests to avoid an
# accidental 7-request burst, while retaining parallelism for other feeds.
_GOOGLE_LOCK=Lock()
_GOOGLE_NEXT_AT=0.0
_GOOGLE_UNAVAILABLE_COUNT=0
_GOOGLE_MIN_INTERVAL=0.85

def _pace_google_request():
    global _GOOGLE_NEXT_AT
    with _GOOGLE_LOCK:
        wait=max(0.0,_GOOGLE_NEXT_AT-monotonic())
        if wait:sleep(wait)
        _GOOGLE_NEXT_AT=monotonic()+_GOOGLE_MIN_INTERVAL

def _google_unavailable():
    with _GOOGLE_LOCK:
        return _GOOGLE_UNAVAILABLE_COUNT>=3

def _record_google_result(success=False,status=None):
    global _GOOGLE_UNAVAILABLE_COUNT
    with _GOOGLE_LOCK:
        if success:_GOOGLE_UNAVAILABLE_COUNT=0
        elif status in (403,429):_GOOGLE_UNAVAILABLE_COUNT+=1

def google_feed(q,lookback_days=NEWS_LOOKBACK_DAYS):
    # Google News supports OR. The period concerns collection, not an article's
    # publication date, and older items are never relabeled as new today.
    return 'https://news.google.com/rss/search?q='+quote(q+f' when:{lookback_days}d')+'&hl=ko&gl=KR&ceid=KR:ko'

def bing_feed(q):
    # Bing's public news RSS is an independent fallback. Its format is
    # unofficial, so failures are logged as such rather than hidden.
    return 'https://www.bing.com/news/search?q='+quote(q)+'&format=rss&setmkt=ko-KR'

# Direct publisher feeds are kept even when BOTH search aggregators fail.
# The limited Bing portfolio covers broad sectors without 30 extra requests.
BING_QUERIES=[
    ('원물 수급/시세','수산물 생산 가격'),
    ('원물 수급/시세','Norway salmon exports'),
    ('원물 수급/시세','Peru squid fishing quota'),
    ('원물 수급/시세','aquaculture seafood prices'),
    ('원물 수급/시세','오징어 어획 수출'),
    ('원물 수급/시세','연어 노르웨이 가격'),
    ('원물 수급/시세','광어 양식 출하'),
    ('대형마트/SSM','홈플러스 이마트 유통'),
    ('코스트코','코스트코 식품 유통'),
    ('온라인','온라인 신선식품'),
    ('B2B/급식','급식 식자재 수산'),
    ('식품안전/소비심리','수산물 안전 검역'),
    ('식품안전/소비심리','seafood import inspection recall'),
    ('해외','수산물 수출 관세'),
    ('해외','Japan seafood import tariff'),
    ('원물 수급/시세','fish prices Norway salmon'),
    ('원물 수급/시세','fisheries catch quota Japan'),
    ('원물 수급/시세','수산물 위판가격'),
    ('대형마트/SSM','대형마트 영업 점포 폐점'),
    ('B2B/급식','식자재 식품 수급'),
    ('해외','seafood exports Korea trade'),
    ('해외','China seafood import policy'),
    ('식품안전/소비심리','수산물 수입 검사 부적합'),
]
SOURCES=[(f'Bing 뉴스 검색·{cat}·{q}',bing_feed(q),'search',cat)
         for cat,q in BING_QUERIES] + [

    ('한국경제·경제','https://www.hankyung.com/feed/economy','news',None),
    ('한국경제·국제','https://www.hankyung.com/feed/international','news',None),
    ('한국경제·증권','https://www.hankyung.com/feed/finance','news',None),
    ('매일경제·경제','https://www.mk.co.kr/rss/30100041/','news',None),
    ('매일경제·국제','https://www.mk.co.kr/rss/30300018/','news',None),
    ('매일경제·증권','https://www.mk.co.kr/rss/50200011/','news',None),
    ('뉴시스·산업','https://www.newsis.com/RSS/industry.xml','news',None),
    ('뉴시스·경제','https://www.newsis.com/RSS/economy.xml','news',None),
    ('뉴시스·국제','https://www.newsis.com/RSS/international.xml','news',None),
    ('연합뉴스·전체','https://www.yna.co.kr/rss/news.xml','news',None),
    ('동아일보·전체','https://rss.donga.com/total.xml','news',None),
    ('매일경제·전체','https://www.mk.co.kr/rss/30000001/','news',None),
    ('뉴시스·속보','https://www.newsis.com/RSS/sokbo.xml','news',None),
    ('국가데이터처·보도자료','https://mods.go.kr/menu.es?mid=a10301010000&act=rss','news',None),
    ('KOSIS·주요 월간동향','https://kosis.kr/rss/trend_rss.jsp','news',None),
    ('KOSIS·최근 수록 통계','https://kosis.kr/rss/themes_rss.jsp','news',None),
] + [(f'Google 뉴스 검색·{cat}·{q}',google_feed(q),'search',cat) for cat,q,_ in SEARCH_QUERIES]


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
            if key in ('title','link','summary','published','updated','source') and value:
                result.setdefault(key,value)
        if result.get('title') and result.get('link'):
            entries.append(result)
    return entries


def fetch_feed(src):
    label,url,kind,category=src
    is_google=urlparse(url).netloc.lower()=='news.google.com'
    if is_google and _google_unavailable():
        return src,[],f'{label}: Google News temporary access failure (3 HTTP 403/429 responses; remaining queries skipped)'
    for attempt in range(2):
        try:
            if is_google:
                if _google_unavailable():
                    return src,[],f'{label}: Google News temporary access failure (provider circuit open)'
                _pace_google_request()
            r=requests.get(url,timeout=(7,18),headers=HEADERS)
            r.raise_for_status()
            if is_google:_record_google_result(success=True)
            items=parse_feed(r.content)
            if not items:
                content_type=str(r.headers.get('Content-Type',''))[:70]
                root_tag='unknown'
                try:root_tag=ET.fromstring(r.content).tag.rsplit('}',1)[-1]
                except ET.ParseError:pass
                return src,[],f'{label}: empty RSS (status={r.status_code}, type={content_type}, root={root_tag})'
            return src,items[:100],None
        except requests.HTTPError as exc:
            # Do not emit request URLs (which can contain private parameters).
            status=exc.response.status_code if exc.response is not None else None
            if attempt==0 and status in (429,500,502,503,504):
                sleep(1.2)
                continue
            if is_google:_record_google_result(status=status)
            return src,[],f'{label}: HTTP {status if status is not None else "unknown"} ({"Google News" if is_google else "publisher RSS"})'
        except requests.RequestException as exc:
            return src,[],f'{label}: {type(exc).__name__} (request/network failure)'
        except (ValueError,ET.ParseError) as exc:
            return src,[],f'{label}: {type(exc).__name__}: {str(exc)[:90]}'
    return src,[],f'{label}: request exhausted'


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


def feed_to_articles(source, entries, now, diagnostics=None):
    label,_,kind,forced=source
    out=[]
    dropped={'date':0,'link_or_title':0,'topic':0}
    for row in entries:
        title=clean(row.get('title'))
        title,publisher=extract_publisher(title,label)
        if (label.startswith('Bing 뉴스') or label.startswith('Google 뉴스')) and row.get('source'):
            publisher=clean(row['source'])[:90]
        url=valid_url(str(row.get('link','')).strip())
        if url and urlparse(url).netloc.lower().endswith('bing.com'):
            inner=parse_qs(urlparse(url).query).get('url',[''])[0]
            url=valid_url(unquote(inner)) or url
        published=stamp(row)
        if not title or not url or not published:
            dropped['link_or_title']+=1
            continue
        if not now-timedelta(days=NEWS_LOOKBACK_DAYS)<=published<=now+timedelta(hours=2):
            dropped['date']+=1
            continue
        summary=clean(row.get('summary') or row.get('description'))
        category,tags,score=classify(title,summary,forced)
        if not category:
            dropped['topic']+=1
            continue
        if not any(k in title.lower()+' '+summary.lower()[:320] for k in SEAFOOD_HINTS):
            dropped['topic']+=1
            continue
        if 'Google 뉴스' in summary[:25]:
            summary=''
        # Retain an accurate headline-only record when publisher RSS has no abstract.
        # Never synthesize a summary from the headline and call it article content.
        if (now-published).total_seconds() < 48*3600:score+=2.5
        channels,impact,follow=impact_fields(title,category)
        out.append({'id':hashlib.sha1(url.encode()).hexdigest()[:16],
                    'title':title[:220], 'url':url, 'source':publisher,'published':published.isoformat(timespec='minutes'),
                    'timestamp':int(published.timestamp()),'category':category,'tags':tags,
                    'score':score,'summary':summary[:330],'summary_type':'공개 RSS 소개문' if summary else '',
                    'question':CATS[category]['question'],'official':False,
                    'channels':channels, 'impact':impact,'followup':follow})
    if diagnostics is not None:
        diagnostics.update(raw=len(entries),accepted=len(out),**dropped)
    return out


def _event_duplicate(a,b):
    """Consolidate multiple headlines about the same company/quarter/metric.

    This is a display filter, not a claim that two publications are
    independent evidence. Keep separate releases when entities or quantities
    differ, even if they concern the same company.
    """
    left=re.sub(r'[^0-9a-z가-힣]','',a['title'].lower())
    right=re.sub(r'[^0-9a-z가-힣]','',b['title'].lower())
    if SequenceMatcher(None,left,right).ratio()>=.80:return True
    numbers_a=set(re.findall(r'\d{3,}',a['title']))
    numbers_b=set(re.findall(r'\d{3,}',b['title']))
    # A distinctive three-digit figure combined with the same company
    # is a strong indicator of repeated coverage of one results release.
    entities=('컬리','코스트코','홈플러스','롯데마트','이마트','쿠팡','CJ프레시웨이','노르웨이')
    if numbers_a & numbers_b and any(ent.lower() in a['title'].lower() and ent.lower() in b['title'].lower() for ent in entities):
        return True
    return False


def dedup(rows,maximum=90):
    result=[];urls=set()
    for item in sorted(rows,key=lambda x:(x.get('score',0),x.get('timestamp',0)),reverse=True):
        if item['url'] in urls or any(_event_duplicate(item,other) for other in result):
            continue
        urls.add(item['url']);result.append(item)
    buckets={c:[] for c in CATS}
    for item in result:buckets[item['category']].append(item)
    chosen=[]
    while len(chosen)<maximum and any(buckets.values()):
        round_entries=[]
        for c in CATS:
            if buckets[c]:round_entries.append(buckets[c].pop(0))
        round_entries.sort(key=lambda x:(x.get('score',0),x.get('timestamp',0)),reverse=True)
        chosen.extend(round_entries[:maximum-len(chosen)])
    return chosen


def keep_recent_archive(current,previous,now,max_age_days=14):
    """Retain genuinely recent verified RSS records on feed outage days.

    Their original dates, source URLs and descriptions are preserved;
    archive records are not relabeled as today's news.
    """
    previous_articles=previous.get('articles',[]) if previous else []
    retain=[]
    for a in previous_articles:
        try:
            pub=datetime.fromisoformat(a['published'].replace('Z','+00:00'))
            if pub.tzinfo is None:continue
            if not now-timedelta(days=max_age_days)<=pub<=now+timedelta(hours=2):continue
            if not valid_url(a.get('url','')) or a.get('category') not in CATS:continue
            retain.append(a)
        except (ValueError,TypeError,KeyError,AttributeError):
            pass
    return dedup(list(current)+retain)


def load_news_archive():
    """Separate persistent news history, independent of rolling AI report copies."""
    try:
        payload=json.loads((SITE/'news_archive.json').read_text(encoding='utf-8'))
        rows=payload.get('articles',[]) if isinstance(payload,dict) else payload
        return rows if isinstance(rows,list) else []
    except (OSError,ValueError,TypeError,AttributeError):
        return []


def issues_from_articles(articles):
    candidates=[]
    for cat in CATS:
        matches=[a for a in articles if a['category']==cat and len(a['summary'])>=40]
        distinct={a['source'] for a in matches}
        if len(matches)<2 or len(distinct)<2:continue
        # The same copied press headline at two outlets is not two market events.
        headline_forms={re.sub(r'[^a-z0-9\uac00-\ud7a3]','',a.get('title','').lower())
                        for a in matches}
        if len(headline_forms)<2:continue
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
    # The same numeric facts can produce an article with a concrete business result.
    r.update({
       'headline':'홈플러스 폐점 인근 이마트 매출 +11.4%…거래업체 72%는 피해',
       'thesis':'홈플러스 폐점 인근 이마트 두 곳의 매출은 11.4%, 롯데마트 인근 매장은 평균 9% 증가했다. 반면 홈플러스 거래 중소기업 100곳 중 72곳은 피해를 겪었고, 해당 72곳 모두 정산 지연을 호소했다. 고객은 경쟁점으로 옮겨갔지만 기존 공급업체의 미수금은 남았다.',
       'lead':'홈플러스 기존 104개 점포 중 37곳이 폐점했다. 폐점 인근 경쟁점에는 고객이 몰렸지만, 해당 유통사와 거래했던 중소기업의 대금 회수는 별개로 진행됐다.',
       'market_change':'홈플러스는 기존 점포 104곳 가운데 37곳을 폐점했다. 폐점 인근 이마트 창동·묵동점 매출은 2026년 5월 10~31일 전년 동기보다 11.4% 증가했다. 같은 시기 서울 지역 인근 롯데마트는 평균 9% 늘었다.',
       'mechanism':[
          '일부 경쟁점은 폐점 점포의 고객을 확보하면서 매출이 늘었다. 하지만 산업통상부의 2026년 상반기 전체 대형마트 매출은 오히려 7.3% 감소했고, 기업형 슈퍼마켓(SSM)도 6.6% 줄었다. 특정 상권의 고객 이동이 업태 전체의 매출 회복으로 이어진 것은 아니었다.',
          '11월 중소기업중앙회 조사에서는 홈플러스 거래 중소기업 100곳 중 72곳이 피해를 경험했다. 피해를 본 72곳 모두 정산 지연을 꼽았고, 조사 대상 100곳 중 63곳은 매출 감소도 겪었다. 인근 마트의 판매가 늘어도 홈플러스가 지급해야 할 기존 납품대금은 해결되지 않았다.'
       ],
       'structural_insight':'홈플러스 점포 축소는 인근 경쟁점에 매출 증가를 가져왔지만, 기존 납품업체에는 정산 지연과 거래 감소를 남겼다. 일부 매장의 반사이익과 납품망의 손실이 동시에 발생한 것이다.',
       'what_changes':'',
       'one_sentence':'폐점 인근 매출 +11.4%, 홈플러스 거래업체 피해 72%…소비 이전에도 미수금 문제는 계속됐다.',
       'limitations':'경쟁점 매출은 5월 일부 점포, 납품업체 피해는 11월 설문, 전체 업태 매출은 상반기 통계다.'
    })
    return [source_1,source_2,source_3],r


def squid_demo():
    """Independent historical public official datasets, explicitly marked DEMO."""
    t1=datetime(2026,2,26,11,0,tzinfo=KST)
    t2=datetime(2026,2,18,10,0,tzinfo=KST)
    a={'id':'mof-2025-squid-production','source':'해양수산부 · 국가데이터처 어업생산동향',
       'title':'2025년 국내 연근해 오징어 생산 31,006톤·전년 대비 128.5% 증가',
       'url':'https://www.mof.go.kr/doc/ko/selectDoc.do?bbsSeq=10&docSeq=65372&menuSeq=971',
       'published':t1.isoformat(),'timestamp':int(t1.timestamp()),'category':'원물 수급/시세',
       'tags':['원물 수급/시세'],'score':16,'official':True,'channels':[],
       'summary':'해양수산부 2026.2.26 발표. 2025 연근해 오징어 31,006톤으로 2024년 13,568톤 대비 128.5% 증가. 최근 5년 평균 38,278톤보다 18.9% 적다. 같은 해 원양 오징어류는 약 5.2만 톤, 전년 대비 17.4% 감소. 연근해와 원양어업의 생산 방향이 다르다.',
       'summary_type':'공식 연간 어업생산동향 통계','impact':'연근해 회복·원양 감소','followup':'2026년 연근해 생산 및 원양어업 물량'}
    b={'id':'mof-2025-squid-exports','source':'해양수산부 · 2025년 수산식품 수출통계',
       'title':'2025년 오징어 수출물량 3.1만 톤·87.8% 증가',
       'url':'https://www.fsis.go.kr/front/api/totalView.do?cnts_id=38261&select_list_no=5&title=',
       'published':t2.isoformat(),'timestamp':int(t2.timestamp()),'category':'해외',
       'tags':['해외'],'score':15,'official':True,'channels':['수출'],
       'summary':'2025년 오징어 수출 물량은 2024년 1.7만 톤에서 2025년 3.1만 톤으로 87.8% 증가했다. 수출액은 0.8억 달러에서 1.1억 달러로 48.7% 증가. 공식 성장률을 사용한 대략적 단가 변화 계산 (1.487/1.878-1)은 약 -20.8%. 물량과 금액 증가율은 별도 기준이다.',
       'summary_type':'공식 수산식품 수출통계 · 단가 변화율 별도 계산','impact':'수출액보다 빠른 물량 성장','followup':'2026년 오징어 수출단가·물량'}
    report={'depth':'핵심','kind':'원물 수급/시세','time_frame':'2025년 연간 통계 · 2026년 2월 발표 · 시연',
      'headline':'오징어 어획 반등에도 5년 평균 미달…수출 성장은 물량이 주도',
      'thesis':'2025년 국내 연근해 오징어 어획량은 전년보다 128.5% 늘었다. 그러나 최근 5년 평균에는 18.9% 못 미쳤고, 원양 오징어 생산은 오히려 줄었다. 같은 해 오징어 수출도 물량이 금액보다 빠르게 증가했다. 어획량 급증과 수출 호조라는 두 수치만으로 오징어값의 강세를 판단하기 어려운 이유다.',
      'lead':'오징어 공급이 반등했다는 뉴스는 사실이지만 무엇을 기준으로 회복이라고 부를 것인지는 다르다. 연근해 생산량을 전년과 비교하면 급증이고, 최근 5년 평균과 비교하면 여전히 낮은 수준이다. 여기에 원양 생산과 수출단가까지 놓으면 시장의 모습은 달라진다.',
      'facts':[{'text':'해양수산부에 따르면 2025년 연근해 오징어 생산량은 31,006톤으로 2024년 13,568톤보다 128.5% 많았지만 최근 5년 평균 38,278톤보다 18.9% 적었다.','refs':['mof-2025-squid-production']},
               {'text':'같은 발표에서 2025년 원양 오징어류 생산량은 약 5.2만 톤으로 전년보다 17.4% 줄었다. 연근해 생산과 원양 생산이 서로 반대 방향으로 움직였다.','refs':['mof-2025-squid-production']},
               {'text':'수산식품 수출통계에 따르면 2025년 오징어 수출물량은 약 3.1만 톤으로 87.8%, 수출액은 약 1.1억 달러로 48.7% 각각 늘었다.','refs':['mof-2025-squid-exports']}],
      'market_change':'2024년 역대 최저 수준이었던 연근해 오징어 생산은 2025년에 31,006톤으로 반등했다. 하지만 비교 기준을 최근 5년 평균으로 바꾸면 회복 폭은 충분하지 않다. 더구나 원양 오징어류 생산은 전년 대비 감소했다. 어획이 늘었다는 한 문장에 서로 다른 조업 해역의 수급 상황이 모두 담기지 않는다.',
      'mechanism':['연근해 생산의 증가는 기저효과를 빼고 읽어야 한다. 2024년 어획량이 13,568톤으로 매우 낮았던 만큼 전년 대비 128.5% 증가라는 높은 성장률이 나타났다. 그 결과 2025년의 31,006톤도 최근 5년 평균 38,278톤보다 적었다. 전년 대비 증가율 하나만으로 장기 생산력을 회복했다고 판단할 수 없다.',
                   '원양 생산과 연근해 생산은 같은 오징어 공급이라는 이름 아래 있지만 조업 해역과 품목 구성이 다르다. 해양수산부는 2025년 원양 오징어류 생산이 17.4% 감소했다고 발표했다. 국내 연근해 어획은 늘었는데 원양 물량은 줄었으므로, 가공·외식·소매시장에서 실제로 활용하는 원료의 공급여건을 한 가지 연근해 통계로 일반화할 수 없다.',
                   '수출 통계도 가격과 물량을 분리해야 한다. 오징어 수출물량 증가율 87.8%는 수출액 증가율 48.7%를 크게 웃돌았다. 공식 발표된 반올림 증가율을 이용해 계산하면 수출 평균단가는 약 20.8% 낮아진 셈이다. 판매량은 늘었지만 평균단가가 높아져서 수출이 성장한 것은 아니었다. 다만 수출 상품의 가공 형태와 세부 품목 구성 변화가 평균단가에 반영됐는지는 추가 자료로 확인해야 한다.'],
      'structural_insight':'연근해 어획 반등, 원양 생산 감소, 수출물량 확대와 수출 평균단가 하락이 같은 해에 나타났다. 오징어시장 전체를 단일한 가격 흐름으로 설명하기 어렵다는 증거다. 국내 연근해 생산량이 전년 대비 크게 늘었다는 소식만으로 국산·원양산·수입산 원료의 공급이 모두 넉넉해졌다고 볼 수 없고, 수출 증가만으로 가격 강세를 주장할 수도 없다.',
      'scenario_up':{'condition':'2026년 연근해 오징어 생산이 5년 평균 이상으로 회복되고 원양 생산도 반등한다면','interpretation':'전체 공급 회복 판단에 필요한 두 생산 축이 함께 개선되는 것이다. 품목·규격이 같은 시장에서 가격 흐름을 추가 확인해야 한다.'},
      'scenario_down':{'condition':'연근해 어획이 다시 줄거나 원양 생산 감소가 이어지고 수입단가가 상승한다면','interpretation':'2025년 반등은 일시적이었을 수 있으며, 시장별 원료 공급의 차이가 더 커질 수 있다.'},
      'what_changes':'다음에는 2026년 월별 오징어 국내 어획량과 원양 생산량을 분리해 보고, 페루 등 국가별 냉동 오징어 HSK 수입량·평균단가를 추가로 확인해야 한다. 수출에서 물량 증가율이 금액 증가율을 웃도는 현상도 다음 연간 통계에서 지속되는지 확인해야 한다.',
      'one_sentence':'역대 최저치에서 회복된 연근해 어획과 감소한 원양 생산, 가격보다 물량이 앞선 수출은 동시에 나타날 수 있다.',
      'limitations':'2025년 연간 공식 통계의 시연이며, 연근해 살오징어와 원양 오징어류, 수출 오징어는 세부 품목·집계 범위가 달라 물량을 합산하거나 동일 상품 가격으로 비교하지 않았다. 평균 수출단가 -20.8%는 반올림 증가율에 근거한 근삿값이다.',
      'article_ids':['mof-2025-squid-production','mof-2025-squid-exports'],'feature_ids':[],'policy_ids':[],
      'confidence':'중간','channels':['수출'],'impact':'어획·수출 물량과 단가의 엇갈림',
      'followup':'국산 연근해 어획·원양 생산·냉동 오징어 수입량·단가',
      'status':'공식 과거 통계로 만든 시연 · 오늘의 자동 분석 아님'}
    report.update({
      'headline':'2025년 연근해 오징어 3만1,006톤…5년 평균보다 18.9% 적어',
      'thesis':'2025년 연근해 오징어 생산량은 3만1,006톤으로 전년보다 128.5% 증가했다. 다만 최근 5년 평균 3만8,278톤에는 18.9% 못 미쳤다. 2024년 생산이 1만3,568톤에 그쳤던 영향이 컸다.',
      'lead':'2024년의 매우 낮은 어획량이 2025년 증가율을 키웠다. 생산량 자체는 여전히 최근 5년 평균보다 7,272톤 적다.',
      'market_change':'2025년 연근해 오징어 어획은 전년 1만3,568톤에서 3만1,006톤으로 증가했다. 원양 오징어류 생산은 같은 기간 17.4% 감소했다.',
      'mechanism':['2024년 생산량이 1만3,568톤에 불과했던 만큼 전년 대비 128.5%라는 증가율이 크게 나타났다. 2025년 생산량도 최근 5년 평균보다 7,272톤 적었다.',
                   '2025년 오징어 수출물량은 3.1만 톤으로 87.8% 늘었고 수출액은 1.1억 달러로 48.7% 증가했다. 공표된 증가율 기준 평균 수출단가는 약 20.8% 낮아졌다.'],
      'structural_insight':'국내 연근해 오징어는 2024년의 급감에서 일부 회복됐지만, 5년 평균 생산량에는 미치지 못했다. 수출에서는 물량 증가가 금액 증가를 앞섰고, 평균 수출단가는 약 20.8% 낮아졌다.',
      'what_changes':'',
      'one_sentence':'연근해 오징어 생산량은 5년 평균에 못 미쳤고, 수출 평균단가는 약 20.8% 하락했다.',
      'limitations':'2025년 연간 공개자료로 구성한 과거 시연이며 2026년 최신 뉴스가 아니다.'
    })
    return [a,b],report


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
       'summary':'2026년 10월 노르웨이 연어 수출은 159,810톤, 수출액 약 130억 NOK를 기록했다. 전년 동월 대비 수출물량은 9%, 수출액은 6% 증가했다. 폴란드향 물량은 15% 증가했고 현지 소비와 재수출도 늘었다.',
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
    # The example below demonstrates editorial style and illustrates USD conversion;
    # it is not an up-to-date price feed or a verified historical model forecast.
    f['facts'].insert(0,{'label':'달러 환산가격 · 시연','value':'$8.07/kg','detail':'2026년 44주차 · 기존 샘플 환산값'})
    f['title']='연어 수출량 14.3% 증가 · 달러 환산가격은 전년 수준'
    f['observed']+=' · 기존 시연용 달러 환산가격은 약 $8.07/kg, 전년 동기와 비슷한 수준. NOK 수출가격과 달러 환산가격은 환율에 따라 방향이 달라질 수 있다.'
    report={'depth':'핵심','kind':'원물 수급/시세','time_frame':'2026년 10월·44주차 · 공개자료 시연',
      'headline':'노르웨이 연어 수출 역대 최대…공급 늘었지만 달러 가격은 유지',
      'thesis':'노르웨이 연어 수출량이 늘었지만 달러로 환산한 가격은 지난해와 비슷하다. 유럽의 판매 증가가 수출 확대에 기여했고, 연말에는 계절적 수요에 따라 가격이 완만하게 반등할 것으로 예상된다.',
      'lead':'10월 노르웨이 연어 수출액은 사상 최대였다. 44주차 수출물량도 지난해보다 크게 늘었지만 달러 기준 가격은 거의 변하지 않았다.',
      'facts':[{'text':'노르웨이 수산물위원회에 따르면 2026년 10월 연어 수출량은 159,810톤으로 전년 동월보다 9% 증가했다.','refs':['nsc-public-sample']},
               {'text':'SSB 2026년 44주차 신선·냉장 연어 수출물량은 28,444톤으로 전년보다 14.3% 증가했다. 당시 달러 환산가격 시연값은 약 $8.07/kg이다.','refs':['ssb-public-sample','salmon_export_price']}],
      'market_change':'10월 연어 수출량은 159,810톤으로 전년보다 9% 늘었다. 44주차 수출물량은 28,444톤으로 14.3% 증가했다. 수출량 증가에 비해 달러로 환산한 가격은 전년 수준을 유지했다.',
      'mechanism':['유럽에서는 연어 판매가 늘었다. 10월 폴란드향 수출물량은 전년보다 15% 증가했고, 폴란드의 가정 내 소비와 재수출도 확대됐다. 가공·유통 수요뿐 아니라 현지 소비가 함께 증가했다.',
                   '한편 노르웨이 수출통계에 표시되는 크로네 가격과 달러 환산가격은 서로 다른 방향으로 움직일 수 있다. 이번에는 크로네 기준 가격이 낮아졌지만 달러로 환산한 가격은 전년과 비슷했다.'],
      'structural_insight':'유럽 시장에서 소비가 늘어나는 동안 노르웨이의 출하량도 확대됐다. 공급이 증가했는데도 달러 기준 가격이 유지된 점은 이번 수출 확대가 판매량에만 의존한 것은 아니라는 점을 보여준다.',
      'what_changes':'이후 주차 수출물량과 달러 환산가격의 방향, 유럽 주요국의 실제 소비 추이를 관측한다.',
      'one_sentence':'연어 수출물량은 늘었지만 달러 환산가격은 유지돼, 연말에는 완만한 반등이 예상된다.',
      'limitations':'시연용 원고. 달러 가격은 기존 화면 예시 환산값으로, 새 실행에서는 Norges Bank 공식 환율이 수집된 경우에만 자동 환산한다.',
      'article_ids':['nsc-public-sample','ssb-public-sample'],'feature_ids':['salmon_export_price'],'policy_ids':[],
      'confidence':'중간','status':'과거 공개자료 기반 시연 · 실제 AI 생성 결과 아님',
      'channels':[],'impact':'유럽 수요 증가 · 달러 기준 가격 유지',
      'followup':'주간 출하량과 달러 환산 수출가격'}
    # Historical USD conversion was supplied in the prior editorial sample.
    # It is a *demonstration* figure, not the result of a new live ECB request.
    f['facts']=[{'label':'연어 수출가 · 달러 환산 시연','value':'$8.07/kg',
                 'detail':'2026년 44주차 · 과거 샘플 값'},
                {'label':'달러 환산가격 전년 동주 대비','value':'+0.5%',
                 'detail':'이전 샘플에서 사용한 값'},
                {'label':'수출량','value':'28,444톤','detail':'44주차 · 전년 대비 +14.3%'}]
    f['title']='연어 수출량 +14.3% · 달러 가격 시연 +0.5%'
    f['observed']='2026년 44주차 노르웨이 신선·냉장 연어 수출량 28,444톤(+14.3%). 과거 편집 시연에서 제시된 달러 환산 수출가 $8.07/kg(+0.5%). 이 환산가격은 새 ECB 조회로 다시 확인한 수치는 아니다.'
    f['measurements']={'species':'연어','tonnes':28444,'yoy_qty_pct':14.3,'price_usd_kg':8.07,'yoy_price_pct':0.5}
    f['data_links'].append({'url':'https://data.ecb.europa.eu/data/datasets/EXR','label':'유럽중앙은행 · 환율 기준 자료'})
    a['title']='노르웨이 연어 주간 수출량 28,444톤…전년보다 14.3% 증가'
    a['summary']='2026년 44주차 신선·냉장 연어 수출량은 28,444톤으로 전년 같은 주보다 14.3% 증가했다. 가격은 별도 ECB 환율 환산이 가능한 경우에만 달러로 표시한다.'
    a2['summary']+=' 10월 전체 수산물 수출액은 전년과 거의 같았다. 양식어류 수출비중은 전년 72%에서 76%로 높아졌고, 대구·고등어 등 자연산 어종은 낮은 어획쿼터로 수출물량이 줄었다. 폴란드향 수출은 32,664톤(+15%), 폴란드 가정 내 연어 소비는 19%, 재수출물량은 10% 증가했다.'
    report.update({
      'headline':'노르웨이 연어 수출량 14.3% 증가…달러 환산가는 8달러대 유지',
      'thesis':'2026년 44주차 노르웨이 신선·냉장 연어 수출량은 28,444톤으로 전년 동주보다 14.3% 증가했다. 기존 시연의 달러 환산가격은 kg당 8.07달러로 전년보다 약 0.5% 높았다. 유럽 소비가 증가한 가운데 출하량도 확대됐다.',
      'lead':'10월 노르웨이 연어 수출량은 159,810톤으로 전년 대비 9% 증가했다. 폴란드향 수출은 32,664톤으로 15% 늘었다.',
      'market_change':'10월 연어 수출량은 159,810톤(+9%)이었다. 44주차에는 28,444톤(+14.3%)을 기록했고 달러 환산가격 시연값은 kg당 8.07달러(+0.5%)였다.',
      'mechanism':[
          '유럽의 주요 유통·가공 거점인 폴란드향 수출량은 10월 32,664톤으로 지난해 같은 달보다 15% 증가했다. 폴란드의 가정 내 연어 소비는 19%, 재수출량은 10% 늘었다.',
          '연말을 앞두고 노르웨이의 주간 수출물량이 전년보다 14.3% 많은 수준을 유지했다. 계절적인 소비 증가가 나타나더라도 공급이 크게 줄지 않는다면 가격 상승 폭은 제한될 전망이다.'
      ],
      'structural_insight':'노르웨이 연어는 공급과 유럽 판매가 동시에 확대됐다. 44주차 수출물량이 14.3% 증가한 가운데 달러 환산가격 시연값은 전년보다 0.5% 높았고, 폴란드의 내수 소비와 재수출도 증가했다.',
      'what_changes':'',
      'one_sentence':'노르웨이 연어 수출량 +14.3%, 달러 환산가격 시연 +0.5%…연말에는 완만한 반등이 예상된다.',
      'limitations':'환산가격 8.07달러는 이전 대화에서 사용한 과거 시연값이며, 이번 실행에서 ECB 조회로 검증한 수치는 아니다.'
    })
    # Official annual data illustrated separately from auto-fetched live indicators.
    # These are actual published 2025 figures, NOT mock API observations.
    squid_public_feature={'id':'squid_official_2025_benchmark',
        'name':'오징어 생산·수출 비교',
        'title':'연근해 어획 반등, 원양 생산 감소…수출은 물량 중심 증가',
        'subtitle':'2025년 공식 연간 통계 · 과거 자료 시연',
        'period_start':'2024년','period_end':'2025년',
        'facts':[{'label':'연근해 오징어 생산량','value':'31,006톤','detail':'전년 대비 +128.5%'},
                 {'label':'최근 5년 평균 대비','value':'-18.9%','detail':'5년 평균 38,278톤'},
                 {'label':'원양 오징어 생산','value':'-17.4%','detail':'전년 대비'},
                 {'label':'오징어 수출 물량','value':'+87.8%','detail':'수출액 +48.7%'}],
        'observed':'2025년 연근해 오징어 생산 31,006톤(+128.5% YoY, 5년 평균 대비 -18.9%); 원양 오징어류 생산 -17.4%; 오징어 수출물량 +87.8%, 수출액 +48.7%, 이를 이용한 평균 수출단가 증감률 약 -20.8%. 각 통계의 상품 범위는 다름.',
        'data_links':[{'url':'https://www.mof.go.kr/doc/ko/selectDoc.do?bbsSeq=10&docSeq=65372&menuSeq=971', 'label':'해양수산부 2025년 어업생산동향 발표'},
                      {'url':'https://www.fsis.go.kr/front/api/totalView.do?cnts_id=38261&select_list_no=5&title=', 'label':'해양수산부 2025년 수산식품 수출 발표'}],
        'article_ids':['mof-2025-squid-production','mof-2025-squid-exports'],
        'category':'원물 수급/시세','channels':[],
        'impact':'국내 연근해·원양 생산 차이와 수출 물량·금액의 역행',
        'limitations':'연근해 오징어, 원양 오징어류, 수출 오징어의 범위와 가공상태가 달라 물량을 더하거나 동일 어종의 가격으로 간주하면 안 됩니다. 2025년 연간 관측이며 실시간 관측이 아닙니다.'}
    squid_public_report={
        'feature_id':'squid_official_2025_benchmark',
        'headline':'오징어 어획 급증에도 장기 평균엔 못 미쳐…수출단가도 하락',
        'conclusion':'2025년 연근해 오징어 생산은 전년보다 128.5% 늘었지만 5년 평균보다 18.9% 적었다. 원양 생산은 17.4% 감소했고 수출은 물량 증가율이 금액 증가율을 크게 웃돌았다. 오징어 시장의 회복을 한 가지 어획 통계로 판단할 수 없는 이유다.',
        'market_observation':'해양수산부의 2025년 어업생산동향에 따르면 연근해 오징어 31,006톤, 최근 5년 평균 38,278톤이며 원양 오징어류 생산은 전년 대비 17.4% 감소했다. 별도의 연간 수산식품 수출자료에서는 오징어 수출물량 +87.8%, 수출액 +48.7%가 확인된다.',
        'transmission':['전년 대비 어획 증가율 +128.5%만 보면 공급이 정상화된 것 같지만, 비교기간을 최근 5년 평균으로 바꾸면 18.9% 부족하다. 전년도 생산이 극히 낮았던 데 따른 기저효과를 구분해야 한다.',
                        '같은 해 수출물량 증가율 +87.8%는 수출액 증가율 +48.7%를 웃돌았다. 두 비율로 계산한 평균 수출단가 변화율은 약 -20.8%다. 이는 수출량 증가가 수출액 확대의 주요 요인이었다는 뜻이지만, 세부 수출 제품의 구성 변화 가능성은 남는다.'],
        'structural_insight':'국내 연근해 조업은 크게 반등했지만 장기 평균에 못 미쳤고, 원양 오징어 생산은 오히려 줄었다. 수출은 물량 중심으로 성장하면서 평균단가가 하락했다. 따라서 국내 어획 회복, 원료 공급 여건, 수출가격을 하나의 상승·하락 신호로 합쳐 해석하면 시장별 차이를 놓친다.',
        'alternative':'연근해 오징어와 원양 오징어류는 조업 해역과 세부 품목이 다르고, 수출 통계에는 가공·규격별 구성 변화가 포함될 수 있다. 따라서 세 숫자가 서로 직접적인 원인·결과 관계라고 볼 수 없다.',
        'scenario_support':'2026년에도 연근해 오징어 생산이 5년 평균을 웃돌고 원양 생산까지 개선되면 국내 전체 공급의 회복 근거가 강해진다.',
        'scenario_challenge':'연근해 어획이 다시 줄거나 수출 평균단가가 회복하면서 수출물량이 감소한다면 2025년의 물량 중심 성장세가 지속된다는 해석을 수정해야 한다.',
        'investor_meaning':'2026년 월별 국내 어획과 원양 생산을 나눠 확인하고, 냉동 오징어 HSK 수입량·수입단가를 국가별로 비교해야 한다. 특히 남미산 대왕오징어와 국산 살오징어의 용도·규격이 다르다는 점을 고려해야 한다.',
        'limits':'2025년 연간 공식 발표에 근거한 시연용 수치 해설. 자동 AI 생성도, 2026년 최신 현황 분석도 아닙니다. 수출 평균단가 -20.8%는 공식 발표의 반올림 성장률을 이용한 근사치입니다.',
        'article_ids':['mof-2025-squid-production','mof-2025-squid-exports'],
        'confidence':'중간','status':'공식 공개통계 과거 시연 · AI 실시간 생성 아님'}
    distribution_articles,distribution_report=homeplus_demo()
    latest_hypermarket={'id':'homeplus-local-retail-nov9-2026',
       'source':'한국경제 · 유통시장 취재',
       'title':'똑같이 반값 한우 내걸었는데…이마트 매출 급증, 홈플러스는 제자리',
       'url':'https://www.hankyung.com/article/202611093646g',
       'published':datetime(2026,11,9,12,9,tzinfo=KST).isoformat(),
       'timestamp':int(datetime(2026,11,9,12,9,tzinfo=KST).timestamp()),
       'category':'대형마트/SSM','tags':['대형마트/SSM'],
       'score':20,'official':False,'channels':['마트'],
       'summary':'2026년 11월 9일 보도. 10월 말 할인행사 기간 이마트의 추정 카드 결제액은 비교기간(10월 16~19일)보다 132% 증가했으나 홈플러스는 거의 변하지 않았다. 별도 집계에서 홈플러스 폐점 주변 이마트 창동·묵동점의 5월 10~31일 매출은 전년보다 11.4% 늘었다. 같은 기간 이마트 전체 기존점은 5.2% 증가해 증가율 차이는 6.2%포인트였다(단순 계산).',
       'summary_type':'대형마트 점포별 판매 실적 취재','impact':'폐점 지역 판매 점포의 매출 변화',
       'followup':'매출이 증가한 상권의 품목별 매장 발주 변화'}
    distribution_report['article_ids']=[distribution_articles[0]['id'],latest_hypermarket['id'],distribution_articles[1]['id']]
    distribution_report['facts'][1]={'text':'2026년 11월 9일 보도에 따르면 홈플러스 폐점 인근 이마트 창동·묵동점의 5월 10~31일 매출은 전년 대비 11.4% 증가했다. 같은 기간 이마트 전체 기존점 증가율은 5.2%였다.','refs':[latest_hypermarket['id']]}
    distribution_articles.insert(1,latest_hypermarket)
    distribution_report.update({
       'headline':'홈플러스 폐점 인근 이마트 매출 11.4% 증가…납품업체는 판로 확보 경쟁 심화',
       'thesis':'홈플러스가 문을 닫은 지역의 이마트 창동·묵동점 매출은 전년보다 11.4% 늘었다. 같은 기간 이마트 전체 기존점 증가율 5.2%를 6.2%포인트 웃돌았다. 한편 홈플러스 거래 중소기업 100곳 중 63곳은 매출 감소를 겪었다. 일부 유통사의 매출 확대와 기존 납품업체의 판로 축소가 동시에 나타나면서 신규 납품처를 둘러싼 경쟁이 심해질 가능성이 있다.',
       'lead':'폐점 인근 이마트의 매출 증가율은 기존점 평균보다 높았다. 그러나 홈플러스 거래업체의 63%는 매출 감소를 경험했다.',
       'market_change':'홈플러스가 37개 점포를 폐점한 뒤, 폐점 인근 이마트 창동·묵동점의 2026년 5월 10~31일 매출이 11.4% 증가했다. 같은 기간 이마트 전체 기존점 증가율은 5.2%, 인근 롯데마트 매장의 평균 증가율은 9%였다. 11월 중소기업중앙회 조사에서는 홈플러스 거래 중소기업의 72%가 피해를 경험했고, 63%가 매출 감소를 답했다.',
       'mechanism':[
          '대형마트 전체 매출은 2026년 상반기 7.3% 감소했지만, 홈플러스가 빠진 일부 지역에서는 기존 이마트와 롯데마트의 매출이 늘었다. 새 점포를 열지 않은 유통사가 기존 매장으로 매출을 가져온 만큼, 추가 매출이 고정비 증가를 크게 동반하지 않는다면 수익성 개선에 유리할 수 있다. 다만 매출 증가에 따른 이익 규모는 공개되지 않았다.',
          '반면 홈플러스 거래업체 100곳 가운데 63곳은 매출 감소를 겪었다. 홈플러스 납품량이 줄어든 업체들이 다른 유통사로 판매를 늘리려 할 경우 신규 입점과 판촉 조건을 둘러싼 경쟁은 더 치열해질 수 있다. 판매가 늘어난 유통사는 매입처 선택지가 넓어지는 반면, 납품업체의 가격 협상력은 상대적으로 약해질 여지가 있다.'
       ],
       'structural_insight':'홈플러스 점포 축소가 장기화되면 이마트·롯데마트는 일부 지역에서 신규 출점 없이 매출을 늘릴 수 있다. 반대로 납품업체들은 줄어든 판매처를 대체하기 위해 남은 유통망의 입점과 발주량을 놓고 경쟁할 가능성이 크다. 지역별 판매 실적과 거래업체 피해조사가 함께 보여주는 변화는 유통사와 납품업체의 협상력 차이다.',
       'one_sentence':'폐점 인근 이마트 매출 +11.4%, 홈플러스 거래업체 63% 매출 감소…판로 확보 경쟁이 심화될 수 있다.',
       'what_changes':'',
       'outlook':{'direction':'확대','horizon':'향후 홈플러스 점포 축소가 이어지는 기간',
                  'judgment':'기존 점포를 보유한 다른 대형마트는 일부 지역의 매출을 추가로 확보할 수 있고, 홈플러스 납품업체들은 다른 유통망을 확보하기 위한 경쟁이 심해질 가능성이 크다.',
                  'basis':'폐점 주변 점포의 매출 증가율은 이마트 기존점 평균을 웃돈 반면 홈플러스 거래업체 63%가 매출 감소를 경험했다.',
                  'revision_trigger':'경쟁 유통사의 지역별 매출 확대가 줄어들거나 홈플러스 거래업체의 매출 감소가 뚜렷하게 개선되는 경우',
                  'numeric_estimate':'','forecast_method':'','backtest':'','evidence_ids':['homeplus-kbiz-nov-2026','homeplus-rival-july-2026']},
       'limitations':'5월 일부 점포의 매출과 11월 거래업체 설문을 연결한 시연 원고이며, 실제 납품단가 변화와 기업별 이익 증감은 확인되지 않았다.',
       'status':'과거 공개자료로 만든 편집 시연 · 실제 AI 자동 발행 아님'
    })
    squid_articles,squid_report=squid_demo()
    salmon_public_report=deterministic_data_report(dict(f,series_type='salmon_joint',measurements={'yoy_price_pct':-6.9,'yoy_qty_pct':14.3}))
    if salmon_public_report:
        salmon_public_report['status']='공식 공개통계 과거 시연 · AI 실시간 생성 아님'
    # No illustrative forecasts on the homepage: business action must follow observed evidence.
    distribution_report['status']='과거 공개자료로 만든 분석 시연'
    # Historical mock should look like the real production time filter:
    # older news stays out of the 7-day homepage. Evidence may be older.
    # Second independent editorial demonstration: Norway's export mix changed
    # as wild-caught quotas restricted raw materials while farmed salmon volume grew.
    # Based on two independently published original sources; not an AI-live report.
    a3={'id':'ssb-salmon-week45-2026','source':'노르웨이 통계청 SSB',
        'title':'노르웨이 신선 연어 45주차 수출 28,277톤…전년보다 17.3% 증가',
        'url':'https://www.ssb.no/en/utenriksokonomi/utenrikshandel/statistikk/eksport-av-laks/artikler/salmon-price',
        'published':datetime(2026,11,11,8,0,tzinfo=KST).isoformat(),
        'timestamp':int(datetime(2026,11,11,8,0,tzinfo=KST).timestamp()),
        'category':'원물 수급/시세','tags':['원물 수급/시세'],'score':17,
        'official':True,'channels':['수출'],
        'summary':'2026년 45주차 노르웨이 신선·냉장 연어 수출은 28,277톤. 전년 동주 24,111톤보다 17.3% 증가했고 전주 28,444톤보다 0.6% 감소했다. 가격은 수출통계 원문에 별도로 제공된다.',
        'summary_type':'SSB 주간 원자료','impact':'연어 주간 수출량 증가','followup':'11월 이후 출하 변화'}
    salmon_report={
        'depth':'핵심','kind':'원물 수급/시세',
        'time_frame':'2026년 10~11월 공개자료 · 시연',
        'headline':'노르웨이 수산물 수출 정체에도 양식 비중 76%…연어가 성장 떠받쳐',
        'thesis':'10월 노르웨이 수산물 수출액은 전년과 거의 같았지만, 양식어류가 차지하는 비중은 72%에서 76%로 높아졌다. 대구·고등어 등 자연산 어종은 어획쿼터 축소로 수출물량이 줄어든 반면 연어 수출량은 9%, 수출액은 6% 증가했다. 수산물 수출 실적이 양식 생산에 더 크게 좌우되는 방향으로 바뀌고 있다.',
        'lead':'노르웨이 수산물위원회는 2026년 10월 수산물 총수출액이 전년 동월과 사실상 비슷했다고 발표했다. 같은 기간 양식어류 수출 비중은 76%까지 높아졌다.',
        'facts':[
            {'text':'노르웨이 수산물위원회에 따르면 2026년 10월 전체 수산물 수출액은 전년 동월과 거의 같았고, 양식어류 수출 비중은 전년 72%에서 76%로 높아졌다. 대구·고등어의 수출량은 어획쿼터 감소와 함께 줄었다.','refs':['nsc-public-sample']},
            {'text':'10월 연어 수출은 159,810톤으로 전년 동월보다 9% 늘었고 수출액도 6% 증가했다. 11월 2~8일 신선·냉장 연어 수출은 28,277톤으로 전년 동주보다 17.3% 많았다.','refs':['nsc-public-sample','ssb-salmon-week45-2026']},
            {'text':'10월 폴란드향 연어 수출량은 32,664톤으로 전년 대비 15% 증가했다. 현지 가정 내 연어 소비는 올해 들어 19%, 재수출물량은 10% 증가했다.','refs':['nsc-public-sample']}
        ],
        'market_change':'10월 노르웨이 연어 수출량은 159,810톤(+9%), 수출액은 전년 대비 +6%였다. 반면 어획쿼터가 축소된 대구·고등어 등 자연산 어종은 수출물량이 감소했다. 그 결과 양식어류의 수출액 비중은 72%에서 76%로 4%p 상승했다.',
        'mechanism':[
            '대구와 고등어는 정해진 어획쿼터가 원료 공급을 제한한다. 올해는 수출가격이 높아진 어종도 있었지만 물량 감소를 상쇄하지 못했다. 반면 연어는 출하량이 늘면서 전체 수산물 수출실적을 지탱했다. 총수출액이 정체돼도 양식어류 비중이 높아진 이유다.',
            '연어 수출 확대는 유럽 가공·유통 물량뿐 아니라 실제 소비 증가와도 연결돼 있다. 노르웨이의 폴란드향 연어 수출은 10월 32,664톤(+15%)을 기록했고, 폴란드의 가정 내 소비는 올해 들어 19% 증가했다. 폴란드에서 다른 국가로 보내는 재수출물량도 10% 늘었다.'
        ],
        'structural_insight':'노르웨이 수산업의 수출 성적을 결정하는 무게중심이 양식어류 쪽으로 옮겨가고 있다. 자연산은 어획쿼터가 제한되면 높은 판매가격에도 공급량을 늘리기 어렵지만, 연어 수출물량 확대는 전체 실적의 감소를 완충했다. 앞으로 자연산 어획제한이 유지된다면 노르웨이 수산물 수출의 성장과 변동성은 연어 출하량과 주요 유럽 판매시장의 수요에 더 크게 좌우될 가능성이 높다.',
        'scenario_up':{'condition':'자연산 어획쿼터 제한이 유지되고 연어 출하가 확대된다면',
                       'interpretation':'연어를 포함한 양식어류의 수출 비중은 당분간 높은 수준을 유지할 가능성이 크다.'},
        'scenario_down':{'condition':'자연산 어종의 어획쿼터가 확대되고 수출물량이 회복된다면',
                         'interpretation':'자연산 수출 회복에 따라 양식어류의 비중 상승은 둔화할 수 있다.'},
        'what_changes':'올해 말까지는 노르웨이 전체 수산물 수출에서 양식어류가 차지하는 비중이 높은 수준을 유지할 것으로 예상된다. 11월 첫째 주에도 신선 연어의 수출량은 전년 동주보다 17.3% 많았다.',
        'one_sentence':'양식어류 비중 72%→76%…자연산 어획 제한 속 연어가 노르웨이 수출 실적을 지탱했다.',
        'limitations':'2026년 10월 월간 수출 실적과 11월 첫째 주 수출량을 각각 제시했다. 두 기간의 수치를 직접 합산하지 않았다.',
        'article_ids':['nsc-public-sample','ssb-salmon-week45-2026'],
        'feature_ids':[],'policy_ids':[],'confidence':'중간',
        'channels':['수출'],'impact':'노르웨이 수산물 수출의 양식어류 의존도 확대',
        'followup':'연어 월별 출하량·대구와 고등어의 어획쿼터·수출 실적',
        'status':'과거 공개자료로 만든 분석 시연 · 자동 AI 생성 아님'
    }
    demo_recent=[a3,latest_hypermarket,distribution_articles[0]]
    demo_older=[a,a2]
    demo_sources=distribution_articles[2:]+squid_articles+[a2]
    demo_issues=make_issue_digest(demo_recent,[],now)
    return {'generated_at':now.isoformat(timespec='minutes'),'articles':demo_recent,'features':[],
            'issue_digest':demo_issues,'archived_articles':demo_older,
            'news_collection':{'fresh_24h':0,'fresh_7d':len(demo_recent),'archive_8_30d':len(demo_older)},
            'deep_reports':[distribution_report,salmon_report],'deep_status':'서로 다른 두 소재의 과거 공개자료 분석 시연',
            'research_sources':demo_sources,'report_factual_brief':False,'report_archived':False,
            'fresh_deep_count':0,'content_state':'demo',
            'last_report_updated_at':datetime(2026,11,5,10,39,tzinfo=KST).isoformat(),
            'data_reports':[],'data_ai_status':'샘플 전용 — 자동 AI 생성 아님',
            'issue_candidates':[],'analysis_status':'2026년 과거 공개자료를 사용한 시연 · 실시간 자료 아님',
            'sources_ok':0,'sources_total':len(SOURCES),'errors':[],
            'metric_errors':[],'demo':True, 'policy_sources':[], 'deep_links':DEEP_LINKS,
            'report_archive':[{'id':'demo-homeplus-20261105','published_at':'2026-11-05T10:39:00+09:00',
               'headline':distribution_report['headline'], 'kind':distribution_report['kind'],
               'report':distribution_report, 'sources':distribution_articles, 'features':[]},
                {'id':'demo-salmon-20261111','published_at':'2026-11-11T08:00:00+09:00',
                 'headline':salmon_report['headline'],'kind':salmon_report['kind'],
                 'report':salmon_report,'sources':[a2,a3],'features':[]}] }


def load_previous_report():
    """Read repository-persisted last valid analysis, not yesterday's unverified fallback."""
    try:
        data=json.loads((SITE/'data.json').read_text(encoding='utf-8'))
        reports=data.get('deep_reports',[])
        if not isinstance(reports,list):return None
        # Archiving a report does not make it fresh again.
        date=data.get('last_report_updated_at') or data.get('generated_at')
        if not isinstance(date,str) or len(date)<10 or data.get('demo'):return None
        sources=data.get('research_sources',[])
        return {'reports':[dict(r) for r in reports[:3]],'date':date,
                'sources':sources,'articles':data.get('articles',[]),'features':data.get('features',[])}
    except (OSError,ValueError,TypeError,AttributeError):return None


def make_factual_brief(articles, features, now, focus_topics=None):
    """Truthful fact-based fallback. Not marketed as a comprehensive AI report."""
    best=[];used_sources=set()
    focus_ids=next((t['article_ids'] for t in (focus_topics or []) if t['article_ids']),[])
    focused=[a for a in articles if a['id'] in focus_ids]
    eligible=focused if focused else articles
    if eligible:
        lead_category=eligible[0]['category']
        eligible=[a for a in eligible if a['category']==lead_category]
    for a in eligible:
        if len(a.get('summary',''))<55 or a['source'] in used_sources:continue
        best.append(a);used_sources.add(a['source'])
        if len(best)==3:break
    if not best and not features:return []
    category=best[0]['category'] if best else features[0]['category']
    title=best[0]['title'] if best else features[0]['title']
    observations=[f"{a['source']}의 {a['published'][:10]} 보도: {a['title']} — {a['summary'][:250]}" for a in best]
    if features and (not best or features[0]['category']==category): observations.append(features[0]['observed'])
    desc=' '.join(observations)
    if not desc:return []
    fact_refs=[{'text':x['summary'][:350], 'refs':[x['id']]} for x in best]
    if features and (not best or features[0]['category']==category):fact_refs.append({'text':features[0]['observed'],'refs':[features[0]['id']]})
    evidence_statement=' '.join(o[:280] for o in observations[:2])
    return [{'depth':'보조','kind':category,'time_frame':now.date().isoformat()+' 기준',
        'headline':'공개자료로 확인된 시장 변화 · '+title[:70],
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
        'article_ids':[x['id'] for x in best], 'feature_ids':[features[0]['id']] if features and (not best or features[0]['category']==category) else [],
        'policy_ids':[],'confidence':'낮음','channels':[],'impact':'공개 자료로 확인한 현황',
        'followup':'해당 분야의 후속 공식 통계','status':'공개 자료 요약 · 심층 분석 미완료'}]


def collect():
    now=datetime.now(KST)
    all_articles=[];errors=[];ok=0;feed_stats=[]
    with ThreadPoolExecutor(max_workers=9) as pool:
        futures=[pool.submit(fetch_feed,s) for s in SOURCES]
        for future in as_completed(futures):
            src,entries,err=future.result()
            if err:errors.append(err)
            else:
                ok+=1
                diagnostic={}
                accepted=feed_to_articles(src,entries,now,diagnostic)
                all_articles.extend(accepted)
                feed_stats.append((src[0],diagnostic))
    previous=load_previous_report()
    observed_this_run=retain_archive(all_articles,[],now,maximum=MAX_ARCHIVE)
    previous_items=load_news_archive()+(previous.get('articles',[]) if previous else [])
    full_archive=retain_archive(observed_this_run,previous_items,now)
    observed_urls={item['url'] for item in observed_this_run}
    archive_retained=sum(item['url'] not in observed_urls for item in full_archive)
    articles,archived_articles=split_archive(full_archive,now)
    for article in articles+archived_articles:
        article['collection_status']='이번 실행 재수집' if article['url'] in observed_urls else '이전 수집 보존'
    google_ok=sum(label.startswith('Google 뉴스') for label,_ in feed_stats)
    google_total=sum(urlparse(src[1]).netloc.lower()=='news.google.com' for src in SOURCES)
    bing_ok=sum(label.startswith('Bing 뉴스') for label,_ in feed_stats)
    bing_total=sum(urlparse(src[1]).netloc.lower()=='www.bing.com' for src in SOURCES)
    news_collection={'seen_this_run':len(observed_this_run),'archive_retained':archive_retained,
                     'google_ok':google_ok,'google_total':google_total,
                     'bing_ok':bing_ok,'bing_total':bing_total,
                     'publisher_ok':ok-google_ok-bing_ok,'publisher_total':len(SOURCES)-google_total-bing_total,
                     'fresh_24h':sum((now-datetime.fromisoformat(x['published'])).total_seconds()<86400 for x in articles),
                     'observed_fresh_24h':sum(0<=(now-datetime.fromisoformat(x['published'])).total_seconds()<86400 for x in observed_this_run),
                     'fresh_7d':len(articles),'archive_8_30d':len(archived_articles),
                     'archive_days':ARCHIVE_DAYS,'window_days':WINDOW_DAYS}
    fresh_news=len(articles)
    print(f'SEAFOOD feeds: {ok}/{len(SOURCES)} succeeded, '
          f'{len(full_archive)} dated stories (last 7d={fresh_news}; max lookback={NEWS_LOOKBACK_DAYS}d)',flush=True)
    print('SEAFOOD RSS CURRENT RUN: observed='+str(news_collection['seen_this_run'])+
          ' archive_reused='+str(archive_retained)+
          ' GoogleNews='+str(google_ok)+'/'+str(google_total)+
          ' Bing='+str(bing_ok)+'/'+str(bing_total)+
          ' publisher='+str(news_collection['publisher_ok'])+'/'+str(news_collection['publisher_total']),flush=True)
    for item in errors:
        print('SEAFOOD RSS FAILED:',item[:200],flush=True)
    for label,stat in sorted(feed_stats):
        if stat['accepted']==0 or stat['raw']>=15 and stat['accepted']/stat['raw']<.10:
            print(f"SEAFOOD RSS FILTERED: {label}: parsed={stat['raw']} kept={stat['accepted']} "
                  f"missing_title_date_link={stat['link_or_title']} old={stat['date']} unrelated={stat['topic']}",flush=True)
    # Keep macro-market commentary only when it actually mentions seafood or
    # food distribution; a stock-market/FX table is not a seafood headline.
    def market_news(a):
        title=(a.get('title') or '').lower()
        if a.get('category')=='비용/거시':
            return any(k in title for k in ('수산','수입수산','연어','오징어','광어','어획','어업','냉동','냉장','물류','해운','식품','식자재','양식'))
        if a.get('category')=='온라인' and any(k in title for k in ('배달의민족','배민','쿠팡이츠')):
            return any(k in title for k in ('수산','신선','식품','식자재','수산물'))
        return True
    articles=[a for a in articles if market_news(a)]
    archived_articles=[a for a in archived_articles if market_news(a)]
    # News remains the primary product, regardless of statistical API availability.
    features,metric_errors=make_features(now)
    print(f'SEAFOOD official series: {len(features)} items; diagnostics: {len(metric_errors)}',flush=True)
    for item in metric_errors:
        print('SEAFOOD API:',str(item)[:220],flush=True)
    connect_evidence(features,articles)
    issue_digest=make_issue_digest(articles,features,now)
    print('SEAFOOD NEWSROOM: recent='+str(len(articles))+' issue_digest='+str(len(issue_digest))+' archives='+str(len(archived_articles)),flush=True)
    previous_headlines=[r.get('headline','') for r in (previous or {}).get('reports',[])]
    # Research comes BEFORE final topic selection. Keyword-matched RSS headlines
    # no longer predetermine what the analysis will discuss.
    issues=issues_from_articles(articles)
    provisional_topics=select_market_topics(articles,features,previous_headlines,max_topics=7)
    print('SEAFOOD DISCOVERY - provisional research leads:',
          [(t['theme'],t['score']) for t in provisional_topics[:5]],flush=True)
    discovered,discovery_status=research_public_sources(articles,features,now,focus_topics=None)
    broad_pool=articles+discovered
    from seafood_topic_tracks import research_targets, coverage_tracks
    focus_for_research=research_targets(broad_pool,features,
        select_market_topics(broad_pool,features,previous_headlines,max_topics=7))
    print('SEAFOOD RESEARCH - focused targets:',
          [(t['theme'],len(t.get('article_ids',[])),len(t.get('feature_ids',[])))
           for t in focus_for_research[:4]],flush=True)
    targeted=[];focus_status='후속 조사 대상 없음'
    if focus_for_research and os.getenv('SEAFOOD_RESEARCH_ROUNDS','2')!='1':
        targeted,focus_status=research_public_sources(
            broad_pool,features,now,focus_topics=focus_for_research[:4])
    # The two passes may cite the same original URL. Neither is independent
    # evidence when the source is the same press release.
    search_sources=list({a['id']:a for a in discovered+targeted}.values())
    # The newly cited research must be linked back to actual commodity data;
    # previously this only ran before discovery, so data comparisons were lost.
    connect_evidence(features,articles+search_sources)
    from seafood_research_depth import evidence_profiles
    depth_profiles=evidence_profiles(focus_for_research,articles+search_sources,features)
    tracks=coverage_tracks(articles+search_sources,features,focus_for_research)
    print('SEAFOOD TRACKS - coverage:',[(t['anchor'],t['numeric_records'],
        t['sources'],t['dimensions'],t['ready']) for t in tracks],flush=True)
    print('SEAFOOD DEPTH - measured coverage:',[(p['anchor'],p['numeric_records'],
        p['independent_sources'],p['dimensions_present']) for p in depth_profiles],flush=True)
    focus_topics=research_targets(articles+search_sources,features,
        select_market_topics(articles+search_sources,features,previous_headlines))
    # An old public dataset or retrieved background page is NOT a current news
    # event. A deep topic needs an actual recent RSS anchor from this run/archive.
    current_article_ids={a['id'] for a in articles}
    focus_topics=[t for t in focus_topics
                  if current_article_ids.intersection(t.get('article_ids',[]))]
    tracks=coverage_tracks(articles+search_sources,features,focus_topics)
    research_status=f'1차: {discovery_status} / 주제별 재조사: {focus_status}'
    print('SEAFOOD RESEARCH - sources:',len(discovered),'discovery +',len(targeted),
          'focused =>',len(search_sources),'unique citations',flush=True)
    print('SEAFOOD research:',research_status,
          'final themes:',[(t['theme'],t['score']) for t in focus_topics[:4]],flush=True)
    print('SEAFOOD report: composing and checking evidence-led articles',flush=True)
    print('SEAFOOD REPORT LANES - ready for draft:',
          [t['anchor'] for t in tracks if t['ready']],flush=True)
    reports,deep_status=(analyze(articles+search_sources,features,now,issues,focus_topics,previous_headlines=previous_headlines)
      if focus_topics and articles else ([], '최근 7일 뉴스에 연결된 심층 분석 후보가 없어 신규 원고를 작성하지 않았습니다.'))
    news_analysis,news_analysis_status=analyze_news_digest(issue_digest,articles,features,now)
    for item in issue_digest:
        if item['id'] in news_analysis:
            item['analysis']=news_analysis[item['id']]
    print('SEAFOOD NEWS ANALYSIS:',news_analysis_status,flush=True)
    print(f'SEAFOOD report: {len(reports)} new deep reports; checking multi-source data analysis',flush=True)
    # New reports can cover ANY evidenced market; archive by derived subject.
    from seafood_topic_tracks import track_for_report
    fresh_count=len(reports)
    current_anchors={track_for_report(r) for r in reports}
    for r in reports:
        r['archived_source']=False
        r['published_at']=now.isoformat(timespec='minutes')
    # Previous work is stored in report_archive.json, never promoted to today's main analysis.
    if reports and fresh_count==0 and all(r.get('archived_source') for r in reports):
        print('SEAFOOD publish: no fresh report; all displayed reports retain original date',flush=True)
    # Official figures are back-data: do not turn unrelated indicators into standalone reports.
    cited_ids=set(fid for issue in issue_digest for fid in issue.get('feature_ids',[]))
    cited_ids.update(fid for r in reports for fid in r.get('feature_ids',[]))
    relevant_features=[f for f in features if f.get('id') in cited_ids and not f.get('id','').startswith('fx_')]
    data_reports,data_status=(analyze_data(relevant_features,articles+search_sources,reports,now)
                              if relevant_features else ([], '관련 뉴스에 연결된 공식 자료가 없어 독립 통계 분석을 생성하지 않았습니다.'))
    # Single-source official observations stay concise source-linked cards.
    # No scripted 7-section pseudo-analysis when research lacks independent evidence.
    last_report_updated_at=now.isoformat(timespec='minutes') if reports else None
    archive=False
    factual_brief=False
    if not reports:
        # Keep the news list useful; do not fill the main analysis with an old report.
        deep_status='새 분석 없음'
    print(f'SEAFOOD publish: {len(reports)} report(s), {len(data_reports)} data analyses, archive={archive}',flush=True)
    mixed=False
    content_state='fresh_research' if reports else 'no_report'
    return {'generated_at':now.isoformat(timespec='minutes'),'articles':articles,'features':features,
            'archived_articles':archived_articles,'issue_digest':issue_digest,
            'news_analysis_status':news_analysis_status,
            'archive_span_days':ARCHIVE_DAYS,
            'issue_candidates':[],'focus_topics':focus_topics,'deep_reports':reports,'deep_status':deep_status,
            'research_sources':search_sources,'archived_features':[],
            'report_archived':archive,'report_factual_brief':factual_brief,
            'fresh_deep_count':fresh_count,'content_state':content_state,
            'last_report_updated_at':last_report_updated_at,
            'data_reports':data_reports,'data_ai_status':data_status,
            'analysis_status':f'실제 공식 관측 {len(features)}종 · SSB/ECOS 및 연결된 국내 공공통계 기준',
            'sources_ok':ok,'sources_total':len(SOURCES),'errors':errors,
            'news_collection':news_collection,
            'research_status':research_status,
            'research_coverage':{'discovery_citations':len(discovered),
                                 'focused_citations':len(targeted),
                                 'unique_citations':len(search_sources),
                                 'topic_candidates':len(focus_topics),
                                 'tracked_topics':[{'anchor':t['anchor'],
                                    'numeric_records':t['numeric_records'],
                                    'independent_sources':t['sources'],
                                    'dimensions':t['dimensions'], 'ready':t['ready']}
                                    for t in tracks],
                                 'topic_measurement_depth':[{k:p[k] for k in ('anchor','numeric_records','independent_sources','dimensions_present','dimensions_missing')} for p in depth_profiles],
                                 'accepted_report_evidence':[{ 'headline':r.get('headline',''), **r.get('evidence_depth',{}) } for r in reports if r.get('evidence_depth') and not archive],
                                 'feed_parsed':sum(row['raw'] for _,row in feed_stats),
                                 'feed_kept':sum(row['accepted'] for _,row in feed_stats)},
            'metric_errors':metric_errors,'demo':False,'policy_sources':[], 'deep_links':DEEP_LINKS}


def publish(data):
    from seafood_report_archive import read_archive, merge_archive, write_archive
    from datetime import datetime
    if not data.get('demo'):
        previous_data = None
        try:
            previous_data=json.loads((SITE/'data.json').read_text(encoding='utf-8'))
        except (OSError,ValueError,TypeError):
            pass
        when=datetime.fromisoformat(data['generated_at'])
        old_archive=read_archive(SITE/'report_archive.json')
        sources=data.get('articles',[])+data.get('archived_articles',[])+data.get('research_sources',[])
        features=data.get('features',[])+data.get('archived_features',[])
        entries=merge_archive(data.get('deep_reports',[]),sources,features,previous_data,old_archive,when)
        data['report_archive']=entries
        data['deep_reports']=[r for r in data.get('deep_reports',[]) if not r.get('archived_source')]
        write_archive(SITE/'report_archive.json',entries,when)
    else:
        data.setdefault('report_archive',[])
    output=json.dumps(data,ensure_ascii=False,indent=2)
    (SITE/'data.json').write_text(output,encoding='utf-8')
    # The archive survives an RSS outage or a day with no new deep analysis.
    if not data.get('demo'):
        archive=retain_archive(data.get('articles',[])+data.get('archived_articles',[]),
                               load_news_archive(),datetime.fromisoformat(data['generated_at']))
        (SITE/'news_archive.json').write_text(json.dumps({'updated_at':data['generated_at'],
            'retention_days':ARCHIVE_DAYS,'articles':archive},ensure_ascii=False,indent=2),encoding='utf-8')
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
