"""Compare statistical *observation periods*, not publication dates.

Annual figures become historical context when two or more calendar years old;
monthly observations older than four calendar months likewise must not be
mistaken for the current market. None of these thresholds changes the numbers.
"""
from __future__ import annotations

from datetime import datetime, date
import re

TRACKED = {'mof_stats', 'kosis_stats', 'enara_fisheries'}


def status(period, as_of):
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    value = str(period or '').strip().replace('.', '').replace('-', '')
    if re.fullmatch(r'20\d{2}', value):
        age = as_of.year - int(value)
        if age < 0:
            return 'future'
        return 'current' if age <= 1 else 'historical'
    if re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])', value):
        age = 12 * (as_of.year - int(value[:4])) + as_of.month - int(value[4:])
        if age < 0:
            return 'future'
        return 'current' if age <= 4 else 'historical'
    if re.fullmatch(r'20\d{2}Q[1-4]', str(period or '')):
        year, quarter = int(value[:4]), int(value[-1])
        age = 4 * (as_of.year - year) + ((as_of.month - 1) // 3 + 1) - quarter
        if age < 0:
            return 'future'
        return 'current' if age <= 2 else 'historical'
    return 'unknown'


def label_features(features, now):
    result = []
    for feature in features:
        item = dict(feature)
        if item.get('series_type') in TRACKED:
            freshness = status(item.get('period_end'), now)
            item['data_freshness'] = freshness
            if freshness in ('historical', 'future', 'unknown'):
                item['role'] = 'historical_context'
                item['significance'] = min(3.0, float(item.get('significance') or 0))
                item['limitations'] = (str(item.get('limitations') or '').strip() +
                    f' 수록시점 {item.get("period_end", "미확인")}: 현재 시장의 직접 관측치가 아닌 과거·미확인 시점 자료.')
        result.append(item)
    return result
