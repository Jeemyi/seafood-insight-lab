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
    print('SEAFOOD AUDIT - news articles:',len(articles))
    print('SEAFOOD AUDIT - official observations:',len(feats))
    print('SEAFOOD AUDIT - deep reports:',len(reports),'archived:',data.get('report_archived',False))
    print('SEAFOOD AUDIT - NEW evidence-validated research:',data.get('fresh_deep_count',0))
    print('SEAFOOD AUDIT - content state:',data.get('content_state','legacy'))
    print('SEAFOOD AUDIT - primary feeds:',data.get('sources_ok'), '/', data.get('sources_total'))
    print('SEAFOOD AUDIT - research coverage:',data.get('research_coverage',{}))
    print('SEAFOOD AUDIT - data source families:',sorted({f.get('series_type','other') for f in feats}))
    google_errors=sum(str(e).startswith('Google 뉴스 검색') for e in data.get('errors',[]))
    if google_errors>=10:
        print(f'::warning::Google News RSS: {google_errors} searches failed. This reduces market coverage even if the other publisher feeds are healthy.')
    families={f.get('series_type','other') for f in feats}
    if not ({'trade','kamis'} & families) and not data.get('demo'):
        print('::warning::No MOF trade or KAMIS price observations were available. Check dated API response diagnostics.')
    for err in data.get('metric_errors',[]):
        print('::warning::Official data source:',str(err)[:240])
    if not data.get('demo') and data.get('fresh_deep_count',0)==0:
        print('::warning::No NEW evidence-validated research published. Workflow success is NOT an editorial success; archived/summary work must be labeled.')
    if not reports:
        print('::warning::No displayed deep report in this run. See research logs; do not infer quality from green checks.')
    if not data.get('demo') and data.get('sources_total') and data.get('sources_ok',0)/max(1,data['sources_total'])<.35:
        print('::warning::Most live RSS sources did not respond. Recent archived articles, if any, retain original dates.')
    return True

if __name__=='__main__':audit()
