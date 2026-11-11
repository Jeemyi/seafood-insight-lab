"""Persistent dated research archive. Prior reports are never silently re-published as new."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

MAX_AGE_DAYS = 730
MAX_REPORTS = 360


def _dated(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d if d.tzinfo else None
    except (ValueError, TypeError):
        return None


def _entry(report, sources, features, published_at):
    if not isinstance(report, dict) or not report.get('headline'):
        return None
    if report.get('kind') == 'NEWS' or report.get('report_factual_brief'):
        return None
    date = report.get('published_at') or published_at
    if not _dated(date):
        return None
    content = str(report.get('headline', '')) + '\n' + str(report.get('thesis', '')) + '\n' + str(report.get('market_change', ''))
    code = hashlib.sha256(content.encode('utf-8')).hexdigest()[:20]
    source_map = {x.get('id'): x for x in sources if isinstance(x, dict) and x.get('id')}
    feature_map = {x.get('id'): x for x in features if isinstance(x, dict) and x.get('id')}
    cited_sources = [source_map[i] for i in report.get('article_ids', []) if i in source_map]
    cited_features = [feature_map[i] for i in report.get('feature_ids', []) if i in feature_map]
    return {'id': 'report-' + code, 'published_at': date, 'headline': report['headline'],
            'kind': report.get('kind', ''), 'report': dict(report),
            'sources': cited_sources[:12], 'features': cited_features[:8]}


def read_archive(path):
    try:
        blob = json.loads(Path(path).read_text(encoding='utf-8'))
        items = blob.get('reports', []) if isinstance(blob, dict) else blob
        return items if isinstance(items, list) else []
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def merge_archive(new_reports, new_sources, new_features, previous_data, old_entries, now):
    """Keep dated original report and its source snapshot; never invent an archive date."""
    candidates = []
    for r in new_reports or []:
        if r.get('archived_source'):
            continue
        row = _entry(r, new_sources, new_features, now.isoformat(timespec='minutes'))
        if row:
            candidates.append(row)
    if isinstance(previous_data, dict) and not previous_data.get('demo'):
        prior_sources = (previous_data.get('articles', []) + previous_data.get('archived_articles', [])
                         + previous_data.get('research_sources', []))
        prior_features = previous_data.get('features', []) + previous_data.get('archived_features', [])
        for r in previous_data.get('deep_reports', []):
            if not isinstance(r, dict):
                continue
            timestamp = r.get('published_at') or previous_data.get('last_report_updated_at') or previous_data.get('generated_at')
            row = _entry(r, prior_sources, prior_features, timestamp)
            if row:
                candidates.append(row)
    candidates.extend(old_entries or [])
    unique = {}
    for row in candidates:
        if not isinstance(row, dict) or not row.get('id') or not isinstance(row.get('report'), dict):
            continue
        d = _dated(row.get('published_at'))
        if not d:
            continue
        elapsed = now - d
        if elapsed < timedelta(hours=-2) or elapsed > timedelta(days=MAX_AGE_DAYS):
            continue
        existing = unique.get(row['id'])
        # Stable first-publication date wins; keep the fullest source snapshot.
        if existing:
            if len(row.get('sources', [])) > len(existing.get('sources', [])):
                row['published_at'] = existing['published_at']
                unique[row['id']] = row
            continue
        unique[row['id']] = row
    return sorted(unique.values(), key=lambda x: x['published_at'], reverse=True)[:MAX_REPORTS]


def write_archive(path, entries, now):
    Path(path).write_text(json.dumps({'updated_at': now.isoformat(timespec='minutes'),
        'reports': entries, 'retention_days': MAX_AGE_DAYS}, ensure_ascii=False, indent=2), encoding='utf-8')
