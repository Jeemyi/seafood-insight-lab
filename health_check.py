"""Audit generated static content; no private API values printed."""
import json
from pathlib import Path


def audit(path=Path('site/data.json')):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data.get('articles'),list) or not isinstance(data.get('features'),list):
        raise ValueError('Generated data payload is missing required collections')
    if not Path('site/index.html').exists():
        raise FileNotFoundError('site/index.html was not built')
    articles=data['articles']; feats=data['features']; reports=data.get('deep_reports',[])
    print('SEAFOOD AUDIT - news-first issue digest:',len(data.get('issue_digest',[])))
    print('SEAFOOD AUDIT - rolling archive (older than 7d):',len(data.get('archived_articles',[])))
    print('SEAFOOD AUDIT - news articles:',len(articles))
    stats=data.get('news_collection',{})
    print('SEAFOOD AUDIT - actually observed this run:',stats.get('seen_this_run','unavailable'))
    print('SEAFOOD AUDIT - preserved from archive:',stats.get('archive_retained','unavailable'))
    print('SEAFOOD AUDIT - Google/Bing:',stats.get('google_ok',0),'/',stats.get('google_total',0),'|',stats.get('bing_ok',0),'/',stats.get('bing_total',0))
    print('SEAFOOD AUDIT - official observations:',len(feats))
    print('SEAFOOD AUDIT - deep reports:',len(reports),'archived:',data.get('report_archived',False))
    print('SEAFOOD AUDIT - primary feeds:',data.get('sources_ok'), '/', data.get('sources_total'))
    print('SEAFOOD AUDIT - data source families:',sorted({f.get('series_type','other') for f in feats}))
    for err in data.get('metric_errors',[]):
        print('::warning::Official data source:',str(err)[:240])
    if not data.get('issue_digest'):
        print('::warning::No article-led news events found for current 7-day window. Check filter/retrieval logs.')
    if len(reports)<2:
        print(f'::warning::Deep analysis target not met: {len(reports)}/2. Diagnose source coverage, evidence clusters, API configuration and validation; never pad with unsupported statistics.')
    if data.get('sources_total') and data.get('sources_ok',0)/max(1,data['sources_total'])<.35:
        print('::warning::Most live RSS sources did not respond. Recent archived articles, if any, retain original dates.')
    return True

if __name__=='__main__':audit()
