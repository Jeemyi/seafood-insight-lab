"""Observed-only support coverage for topic diagnostics (not causal proof)."""
from seafood_topic_tracks import coverage_tracks
from seafood_story_selection import SIGNALS


def evidence_profiles(topics,articles,features):
    tracks=coverage_tracks(articles,features,topics)
    output=[]
    for t in tracks:
        output.append({'anchor':t['anchor'],'numeric_records':t['numeric_records'],
                       'independent_sources':t['sources'],
                       'dimensions_present':t['dimensions'],
                       'dimensions_missing':[x for x in SIGNALS if x not in t['dimensions']]})
    return output
