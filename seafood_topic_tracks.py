"""Coverage tracks are research priorities, never a licence to fabricate stories."""
from __future__ import annotations

from seafood_research_depth import numeric_observations, LABELS, MARKET_AXES

TRACKS=(
    ('연어','글로벌 연어시장',('연어','salmon','mowi','salmar','노르웨이')),
    ('오징어','오징어 국내외 수급',('오징어','대왕오징어','squid','pota','dosidicus')),
    ('대형마트','대형마트·유통시장',('홈플러스','대형마트','이마트','롯데마트','트레이더스','코스트코')),
)

def track_for_report(report):
    text=' '.join(str(report.get(k,'') or '') for k in ('headline','thesis','kind')).lower()
    for anchor,_,words in TRACKS:
        if any(w.lower() in text for w in words):return anchor
    return None

def records_for_track(anchor,articles,features):
    words=next((words for label,_,words in TRACKS if label==anchor),())
    def relevant(row):
        # Headlines and named series are much more reliable than broad category.
        title=' '.join(str(row.get(k,'') or '') for k in ('title','name')).lower()
        summary=str(row.get('summary') or row.get('observed') or '').lower()
        return any(w.lower() in title for w in words) or any(w.lower() in summary for w in words)
    matched_a=[a for a in articles if relevant(a)]
    matched_f=[f for f in features if relevant(f)]
    # Preserve research citations and originating primary data even when its
    # RSS category was incorrectly assigned (e.g. salmon classified as overseas).
    return matched_a,matched_f

def coverage_tracks(articles,features):
    result=[]
    for anchor,label,_ in TRACKS:
        matched_a,matched_f=records_for_track(anchor,articles,features)
        measured=numeric_observations(matched_a+matched_f,anchor)
        sources={r['source'] for r in measured if r['source']}
        axes={facet for r in measured for facet in r['facets']}
        # Official measurements count as meaningful but do not automatically
        # prove an independent second market fact.
        available=len(measured)>=2 and len(sources)>=2 and len(axes)>=2
        result.append({'anchor':anchor,'label':label,'articles':matched_a,
           'features':matched_f,'observations':measured,'sources':len(sources),
           'dimensions':sorted(axes),'ready':available,'numeric_records':len(measured),
           'missing':[LABELS[x] for x in MARKET_AXES[anchor] if x not in axes],
           'headline_ids':[a['id'] for a in matched_a[:8] if a.get('id')],
           'feature_ids':[f['id'] for f in matched_f[:6] if f.get('id')]})
    return result

def research_targets(articles,features,base_topics=()):
    """Maintain three distinct research leads without treating them as output articles."""
    wanted=coverage_tracks(articles,features)
    leads=[]
    for track in wanted:
        if not track['headline_ids'] and not track['feature_ids']:continue
        leads.append({'theme':track['label'],'category':
           '대형마트/SSM' if track['anchor']=='대형마트' else '원물 수급/시세',
           'anchor':track['anchor'], 'article_ids':track['headline_ids'],
           'feature_ids':track['feature_ids'],'score':100 if track['ready'] else 35,
           'research_question':'공급·가격·수요·정책 중 비교 가능한 별도 시장자료 확보'})
    for topic in base_topics:
        if len(leads)>=7:break
        if any(topic.get('theme')==x['theme'] for x in leads):continue
        leads.append(topic)
    return leads[:7]
