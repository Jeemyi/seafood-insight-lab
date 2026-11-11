"""Evidence-first market dossiers. Topics are selected dynamically every run.

There are no mandatory salmon/squid/retail slots. Original publisher material,
quantified observations and the day's ranked event leads determine draft order.
"""
from __future__ import annotations

import re
from seafood_research_depth import (ANCHORS, LABELS, MARKET_AXES, facets,
                                    numeric_observations, anchor_for,
                                    record_text, MEASURE, source_family)


def _words(theme):
    ignore={'시장','시세','국내','국외','관련','현황','변화','동향','전망','주요','해외',
            '수급','가격','동향과','산업','글로벌','국내외','수출입'}
    return [x.lower() for x in re.findall(r'[a-zA-Z가-힣0-9]+',str(theme))
            if len(x)>1 and x.lower() not in ignore]


def track_for_report(report):
    if report.get('market_anchor'):
        return str(report['market_anchor'])
    text=' '.join(str(report.get(k,'') or '') for k in ('headline','thesis','kind')).lower()
    for anchor,terms in ANCHORS.items():
        if any(x.lower() in text for x in terms):return anchor
    # Unfamiliar topics still need stable identity for archive de-duplication.
    return 'topic:'+re.sub(r'\s+','',str(report.get('headline',''))[:42]).lower()


def records_for_track(anchor,articles,features,topic=None):
    topic=topic or {}
    direct=set(topic.get('article_ids',[]))|set(topic.get('feature_ids',[]))
    words=ANCHORS.get(anchor) or _words(topic.get('theme') or anchor)
    def relevant(row):
        if row.get('id') in direct:return True
        title=' '.join(str(row.get(k,'') or '') for k in ('title','name')).lower()
        summary=str(row.get('summary') or row.get('observed') or '').lower()
        if anchor in ANCHORS:
            return any(w.lower() in title or w.lower() in summary for w in words)
        # A combined lead such as "Japan/US exports" must not discard a
        # Japan-only or US-only original report. Those are candidate evidence,
        # not proof that the two countries share a causal mechanism.
        matching=sum(w in title or w in summary[:500] for w in words)
        theme=str(topic.get('theme') or anchor)
        required=1 if len(words)<=2 or ('·' in theme or '/' in theme) else 2
        return matching>=required if words else False
    return ([a for a in articles if relevant(a)],
            [f for f in features if relevant(f)])


def _observations(rows,anchor):
    if anchor in ANCHORS:
        return numeric_observations(rows,anchor)
    # The general topic is built using its direct article IDs; numeric facts
    # need not contain a predeclared commodity name.
    found=[];seen=set()
    for row in rows:
        text=record_text(row)
        matches=list(MEASURE.finditer(text))
        if not matches:continue
        dims=set()
        for match in matches[:14]:
            near=text[max(0,match.start()-100):match.end()+60]
            dims.update(x for x in facets(near) if x!='fx')
        rid=str(row.get('id') or '')
        if rid and rid not in seen and dims:
            seen.add(rid)
            found.append({'id':rid,'source':source_family(row),'facets':sorted(dims),
                          'quantities':[m.group(0) for m in matches[:7]]})
    return found


def _candidate_topics(articles,features,topics):
    if topics:
        return list(topics)
    # Fallback when there is no editorial candidate: rank measured public
    # coverage, never force topics by position or stable fixed labels.
    result=[]
    for anchor in ANCHORS:
        a,f=records_for_track(anchor,articles,features)
        observed=_observations(a+f,anchor)
        if not a and not f:continue
        independent={x['source'] for x in observed if x['source']}
        score=len(observed)*7+len(independent)*6+min(len(a),5)
        result.append({'theme':anchor,'anchor':anchor,'score':score,
                       'article_ids':[x['id'] for x in a[:8] if x.get('id')],
                       'feature_ids':[x['id'] for x in f[:5] if x.get('id')]})
    return sorted(result,key=lambda x:x['score'],reverse=True)


def coverage_tracks(articles,features,topics=(),maximum=9):
    ordered=_candidate_topics(articles,features,topics)
    tracks=[];used=set()
    for topic in ordered:
        theme=str(topic.get('theme') or topic.get('subject') or '').strip()
        if not theme:continue
        anchor=topic.get('anchor') or anchor_for(topic) or 'topic:'+re.sub(r'\s+','',theme).lower()[:45]
        if anchor in used:continue
        a,f=records_for_track(anchor,articles,features,topic)
        observed=_observations(a+f,anchor)
        sources={r['source'] for r in observed if r['source']}
        dims={facet for r in observed for facet in r['facets']}
        available=len(observed)>=2 and len(sources)>=2 and len(dims)>=2
        if not a and not f:continue
        used.add(anchor)
        axes=MARKET_AXES.get(anchor,('supply','trade','price','demand','distribution','policy'))
        tracks.append({'anchor':anchor,'label':theme,'articles':a,'features':f,
            'observations':observed,'sources':len(sources), 'dimensions':sorted(dims),
            'ready':available,'numeric_records':len(observed),
            'missing':[LABELS.get(x,x) for x in axes if x not in dims],
            'score':float(topic.get('score') or 0),
            'headline_ids':[x['id'] for x in a[:8] if x.get('id')],
            'feature_ids':[x['id'] for x in f[:6] if x.get('id')]})
        if len(tracks)>=maximum:break
    return tracks


def research_targets(articles,features,base_topics=(),maximum=7):
    """Prioritize ranked events; use measured-data fallback only if none ranked."""
    tracks=coverage_tracks(articles,features,base_topics,maximum=maximum)
    leads=[]
    for t in tracks:
        leads.append({'theme':t['label'],'category':'원물 수급/시세',
            'anchor':t['anchor'],'article_ids':t['headline_ids'],
            'feature_ids':t['feature_ids'],
            'score':t['score'],
            'research_question':'관련 사건의 실제 공급·가격·수요·정책 수치를 비교'})
    for topic in base_topics:
        if len(leads)>=maximum:break
        if topic.get('theme') not in {t['theme'] for t in leads}:
            leads.append(topic)
    return leads[:maximum]
