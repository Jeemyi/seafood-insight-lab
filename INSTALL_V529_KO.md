# SEAFOOD INSIGHT LAB v5.29 — 이전 화면 복원 + v5.28 수집 개선 유지

## 이번 파일에서 바뀐 것

2026-11-11 대화 내보내기 ZIP에 포함된 `SEAFOOD_INSIGHT_LAB_v5.26_RSS_COLLECTION_FIX.zip`의 `template.html`을 실제 기준으로 사용해 v5.26 UI를 복원했습니다.

- 메인 제목 **주요 이슈와 시장 전망** 복원
- v5.26의 요약 → 주제 선택 카드 → 선택한 분석/근거 → 공식 데이터 → 주요 기사/검색/읽음/저장 레이아웃 복원
- v5.28의 신규 뉴스 수집, 중복 제거, 개별 사건 분리, 아카이빙, AI 해석 검증 코드는 그대로 유지
- 신규 사건은 v5.26 주제 카드와 심층 읽기 패널로 표시하며, 분석에 근거가 없으면 원문 뉴스 요약만 표기
- 24시간 / 7일 / 30일 **기간 선택은 전체 기사 영역의 작은 필터로만** 제공
- 문제로 지적된 '최근 7일, 무슨 일이 있었나' 제목, 별도의 v5.28 newsroom 카드 섹션 제거

## 적용 방법

1. 다운로드한 업데이트 ZIP의 파일을 GitHub `seafood-insight-lab` 저장소의 같은 경로에 **덮어쓰기** 하세요.
2. **기존 저장소 파일 전체를 삭제하지 마세요.** 특히 `site/data.json`, `site/news_archive.json`, `site/index.html`은 기존 운영 데이터입니다. ZIP에 포함하지 않았습니다.
3. GitHub Secrets 키값은 유지하고 외부 공개 저장소에 노출하지 마세요.
4. Commit 뒤 `Actions` → `Daily SEAFOOD INSIGHT LAB` → `Run workflow` 실행.
5. 사이트에서 메인 제목, 주제 카드 클릭, 기사 원문 링크, 24시간/7일/30일 전환을 확인하세요.

## 검증 범위

- Python unit tests 71개 통과
- `python build.py --demo`로 HTML 출력 성공
- Chromium 데스크톱/모바일 동작 확인, 브라우저 JS 에러 없음
- 데모의 5개 주제 카드 전환, 기사 날짜 필터 정상 작동 확인

**미검증:** 실제 GitHub 환경에서의 RSS/API 실시간 연결과 OpenAI 기반 뉴스 해석 원고의 품질. 화면의 과거 공개자료를 바탕으로 만든 데모는 실시간 수집 결과가 아닙니다.
