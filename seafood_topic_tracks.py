"""Compatibility layer for v5.26's research-topic coverage diagnostics.

Only descriptors of evidence availability; never invents citations or statistics.
"""
from __future__ import annotations
from seafood_story_selection import SUBJECTS, SIGNALS


def _anchor(text):
    text=str(text).lower()
    for label,terms in SUBJECTS:
        if any(w in text for w in terms):return label
    return ''


def research_targets(articles,features,topics):
    """Focus web research on real headline-backed subjects before data-only ones."""
    articles_by_id={a.get('id'):a for a in articles}
    result=[]
    for topic in topics:
        news=[articles_by_id[x] for x in topic.get('article_ids',[]) if x in articles_by_id]
        if not news:continue
        item=dict(topic)
        item['anchor']=_anchor(' '.join(x.get('title','') for x in news)) or topic['theme']
        result.append(item)
    return result[:7]


def coverage_tracks(articles,features,topics):
    articles_by_id={a.get('id'):a for a in articles}
    features_by_id={f.get('id'):f for f in features}
    rows=[]
    for t in topics:
        relevant=[articles_by_id[i] for i in t.get('article_ids',[]) if i in articles_by_id]
        measurements=[features_by_id[i] for i in t.get('feature_ids',[]) if i in features_by_id]
        text=' '.join(' '.join(str(x.get(k,'')) for k in ('title','summary','observed','name')) for x in relevant+measurements).lower()
        dimensions=[k for k,words in SIGNALS.items() if any(w in text for w in words)]
        sources={x.get('source') for x in relevant if x.get('source')}
        numeric=sum(any(char.isdigit() for char in str(x.get('observed',''))+' '+str(x.get('summary',''))) for x in relevant+measurements)
        rows.append({'anchor':t.get('anchor') or t.get('theme'),'numeric_records':numeric,
                     'sources':len(sources),'dimensions':dimensions,
                     'ready':bool(relevant and len(sources)>=2 and len(dimensions)>=2)})
    return rows


def track_for_report(report):
    return _anchor(' '.join(str(report.get(k,'')) for k in ('headline','thesis','lead'))) or str(report.get('kind',''))
