"""News-led daily briefing and bounded rolling archive.

Only use dated RSS titles/short descriptions and linked public observations.
Never turn a statistical snapshot into a 'news' event or infer causation.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

WINDOW_DAYS=7
ARCHIVE_DAYS=30
MAX_RECENT=850
MAX_ARCHIVE=2500

SUBJECTS=(
 ('오징어 수급·수출입',('오징어','대왕오징어','squid','calamari'),'원물 수급/시세',
  '어획량이나 쿼터 변화가 실제 수입 가능 물량·국내 원가로 이어지는 시점이 다른지 확인'),
 ('광어·우럭 양식시장',('광어','넙치','우럭','조피볼락'),'원물 수급/시세',
  '출하량과 산지가가 같은 방향인지, 양성물량 변화가 언제 출하에 반영되는지 확인'),
 ('연어 원료시장',('연어','salmon','노르웨이 수산'),'원물 수급/시세',
  '현지 수출가격과 물량을 함께 보고 환율·운송비·국내 통관 시차를 분리'),
 ('꽃게·갑각류',('꽃게','대게','새우','크랩'),'원물 수급/시세',
  '산지 위판과 수입산 공급을 분리하고 냉장·냉동·규격별 가격을 대조'),
 ('고등어·기타 어획',('고등어','방어','참치','문어','낙지','주꾸미'),'원물 수급/시세',
  '품목별 어획·출하와 실제 도매·소매 판매가격을 같은 시점에 맞춰 비교'),
 ('대형마트·창고형 유통',('홈플러스','이마트','롯데마트','트레이더스','코스트코','대형마트'),'대형마트/SSM',
  '점포 변화가 수산물 판매처와 납품 경로에 어떤 영향을 주는지는 점포·품목별 수치로 점검'),
 ('수산 식품안전·통상규제',('수산물 검역','수산물 원산지','수산물 검사','mmpa','수입 금지','수입금지'),'식품안전/소비심리',
  '시행일·대상국·어종·검사 결과를 대조해 실제 거래 제한 범위를 확인'),
 ('회·초밥·수산 가공식품',('회초밥','횟감','초밥','필렛','수산 밀키트','수산 간편식'),'시즌/트렌드',
  '행사·신제품 발표와 반복 매출, 실제 소비 확대를 구분해 확인'),
 ('수산물 온라인·급식',('온라인 수산','수산물 배송','수산물 온라인','급식 수산물','수산물 식자재'),'온라인',
  '채널 성장 지표가 전체 식품인지 수산물 품목인지 구분하고 수요처별 단가를 확인'),
 ('수산업 정책·수급',('수산업','수산물 가격','수산물 수출','수산물 수입','어획량','양식 피해'),'원물 수급/시세',
  '발표 시점과 실물 시장의 반영 시점이 다른지 후속 거래·어획·소비 자료로 확인'),
)

SIGNAL_WORDS=(
 ('공급·어획',('어획','쿼터','생산','조업','출하','위판','양식','고수온','금어기','공급')),
 ('가격·비용',('가격','시세','단가','물류비','운임','가격인상','가격하락')),
 ('수출입·규제',('수출','수입','관세','검역','규제','원산지','인증','허가')),
 ('판매·유통',('판매','점포','폐점','입점','인수','마트','급식','온라인','소비')),
)


def _when(row):
    try:
        dt=datetime.fromisoformat(str(row['published']).replace('Z','+00:00'))
        return dt if dt.tzinfo is not None else None
    except (KeyError,ValueError,TypeError):
        return None


def _canonical_url(url):
    """Ignore tracking keys for deduplication, not for the public link itself."""
    try:
        p=urlparse(url)
        params=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
                if not (k.lower().startswith('utm_') or k.lower() in ('fbclid','gclid'))]
        return urlunparse((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),'',urlencode(params),''))
    except (ValueError,TypeError):
        return ''


def retain_archive(observed, old_rows, now, days=ARCHIVE_DAYS, maximum=MAX_ARCHIVE):
    """Keep each publication's date and link; never mark retained rows newly fetched."""
    pool={}; ordered=list(observed)+list(old_rows)
    for item in ordered:
        if not isinstance(item,dict) or not str(item.get('url','')).startswith(('https://','http://')):continue
        dt=_when(item)
        if dt is None or dt < now-timedelta(days=days) or dt > now+timedelta(hours=2):continue
        key=_canonical_url(item['url']) or str(item.get('id',''))
        if not key:continue
        previous=pool.get(key)
        candidate=dict(item)
        # The first verified current-run entry wins; never rewrite publication dates.
        if not previous or (not previous.get('summary') and candidate.get('summary')):
            pool[key]=candidate
    entries=sorted(pool.values(),key=lambda a:(int(a.get('timestamp',0)),float(a.get('score',0))),reverse=True)
    return entries[:maximum]


def split_archive(archive,now):
    threshold=now-timedelta(days=WINDOW_DAYS)
    recent=[r for r in archive if (_when(r) or now-timedelta(days=999))>=threshold]
    older=[r for r in archive if (_when(r) or now-timedelta(days=999))<threshold]
    return recent[:MAX_RECENT],older


def _signals(rows):
    text=' '.join((r.get('title','')+' '+r.get('summary','')[:200]).lower() for r in rows)
    return [label for label,words in SIGNAL_WORDS if any(word in text for word in words)]


def _choose_topic(article):
    text=(article.get('title','')+' '+article.get('summary','')[:160]).lower()
    for title,terms,_,followup in SUBJECTS:
        if any(term in text for term in terms):return title,followup
    cat=article.get('category') or '수산 유통'
    return cat,article.get('followup') or '관련 발표의 대상·시점·수치를 후속 자료로 검증'


def _headline_tokens(text):
    """Keep distinct events separate: the species name is not an event ID."""
    tokens=re.findall(r"[a-z0-9\uac00-\ud7a3]+",str(text).lower())
    stop={"the","and","for","with","from","this","that"}
    return {t for t in tokens if len(t)>=2 and t not in stop}


def _same_event(a,b):
    """A narrow matching rule prevents unrelated commodity stories being merged.

    Source name, generic category and species similarity alone never suffice.
    A syndication rewrite may group with its original only if the distinctive
    headline terms also match. Articles remain separate in the reading archive.
    """
    ta=_headline_tokens(a.get('title',''));tb=_headline_tokens(b.get('title',''))
    if not ta or not tb:return False
    common=ta&tb
    if len(common)<2:return False
    overlap=len(common)/max(1,len(ta|tb))
    left=re.sub(r"[^0-9a-z\uac00-\ud7a3]",'',a.get('title','').lower())
    right=re.sub(r"[^0-9a-z\uac00-\ud7a3]",'',b.get('title','').lower())
    similarity=SequenceMatcher(None,left,right).ratio()
    if overlap<.58 and similarity<.78:return False
    # Avoid merging conflicting quantitative reports by relying on a species.
    nums_a=set(re.findall(r"\d+(?:[.,]\d+)?",a.get('title','')))
    nums_b=set(re.findall(r"\d+(?:[.,]\d+)?",b.get('title','')))
    if nums_a and nums_b and not nums_a.intersection(nums_b) and overlap<.78:
        return False
    return True


def _feature_match(headline,subject,features,now):
    """Attach official back-data only when species AND observation age match.

    Do not quietly attach a broad exchange rate or an annual sector total to
    an unrelated price/supply event.
    """
    terms=next((terms for title,terms,*_ in SUBJECTS if title==subject),())
    species=[t.lower() for t in terms if len(t)>=3 and t.lower() in headline.lower()]
    if not species:return []
    answer=[]
    for f in features or []:
        if f.get('role')=='context' or str(f.get('id','')).startswith('fx_'):continue
        text=(str(f.get('name',''))+' '+str((f.get('measurements') or {}).get('species',''))).lower()
        if not any(t in text for t in species):continue
        date=str(f.get('period_end') or f.get('observed_at') or '')[:10]
        stamp=None
        for fmt in ('%Y-%m-%d','%Y%m%d','%Y%m'):
            try:stamp=datetime.strptime(date[:{'%Y-%m-%d':10,'%Y%m%d':8,'%Y%m':6}[fmt]],fmt);break
            except ValueError:pass
        if stamp is None or abs((now.date()-stamp.date()).days)>110:continue
        answer.append(f['id'])
        if len(answer)>=2:break
    return answer


def make_issue_digest(articles,features=None,now=None,maximum=8):
    """Article-led individual events, not one omnibus report per species.

    No model-generated conclusions are filled in by this deterministic step.
    A failed analysis leaves the real linked article visible to the reader.
    """
    if now is None:raise ValueError('now required')
    eligible=[x for x in articles if (_when(x) or now-timedelta(days=999))>=now-timedelta(days=7)
              and x.get('summary_type') not in ('\uacf5\uc2dd \uc8fc\uac04 \ud1b5\uacc4','\uacf5\uc2dd \uc6d4\uac04 \ud1b5\uacc4')
              and not str(x.get('title','')).startswith(('SSB:', 'KOSIS:'))]
    eligible.sort(key=lambda x:(float(x.get('score',0))+
                  (5 if (_when(x) or now-timedelta(days=999))>=now-timedelta(hours=48) else 0),
                  int(x.get('timestamp',0))),reverse=True)
    groups=[]
    for row in eligible:
        group=next((g for g in groups if _same_event(g[0],row)),None)
        if group is None:groups.append([row])
        else:group.append(row)
    results=[]
    for rows in groups:
        lead=rows[0]
        subject,_=_choose_topic(lead)
        picked=[];urls=set();publishers=set()
        for item in rows:
            if item.get('url') in urls:continue
            urls.add(item.get('url'))
            publisher=str(item.get('source','')).strip().lower()
            if publisher in publishers and len(picked)>=2:continue
            publishers.add(publisher)
            picked.append(item)
            if len(picked)>=5:break
        dt=_when(lead)
        feature_ids=_feature_match(lead['title'],subject,features,now)
        results.append({'id':'news-'+str(lead.get('id','')),
            'subject':subject,'headline':lead.get('title',''),
            'summary':lead.get('summary','')[:400],
            'reading':'','why_it_matters':'','followup':'',
            'article_ids':[x['id'] for x in picked],
            'feature_ids':feature_ids,
            'publisher_count':len({str(r.get('source','')).lower() for r in picked if r.get('source')}),
            'article_count':len(rows),
            'independent_confirmation':False,
            'status':'RSS \uae30\uc0ac\ub85c \ud655\uc778',
            'signals':_signals(picked)[:2],
            'lead_published':dt.isoformat(timespec='minutes') if dt else '',
            'newest_ts':int(lead.get('timestamp',0)),
            'score':float(lead.get('score',0)) + min(5,len(rows)*1.5)
                     + (3 if len(publishers)>=2 else 0)})
    from seafood_editorial_quality import event_priority
    index={a.get('id'):a for a in articles}
    for issue in results:
        sources=[index[a] for a in issue['article_ids'] if a in index]
        issue['editorial_priority']=event_priority(issue,sources,now)
    # Soft diversity, not category quotas: a more important event can still
    # outrank every other subject. This prevents one feed from swallowing the
    # entire top-eight display while retaining EVERY story in the archive.
    selected=[];used_subjects={}
    while results and len(selected)<maximum:
        chosen=max(results,key=lambda r:(r['editorial_priority']-2*used_subjects.get(r['subject'],0),r['newest_ts']))
        results.remove(chosen)
        selected.append(chosen)
        used_subjects[chosen['subject']]=used_subjects.get(chosen['subject'],0)+1
    return selected
