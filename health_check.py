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
    print('SEAFOOD AUDIT - data source families:',sorted({f.get('series_type','other') for f in feats}))
    for err in data.get('metric_errors',[]):
        print('::warning::Official data source:',str(err)[:240])
    if not data.get('demo') and data.get('fresh_deep_count',0)==0:
        print('::warning::No NEW evidence-validated research published. Workflow success is NOT an editorial success; archived/summary work must be labeled.')
    if not reports:
        print('::warning::No displayed deep report in this run. See research logs; do not infer quality from green checks.')
    if data.get('sources_total') and data.get('sources_ok',0)/max(1,data['sources_total'])<.35:
        print('::warning::Most live RSS sources did not respond. Recent archived articles, if any, retain original dates.')
    return True

if __name__=='__main__':audit()
