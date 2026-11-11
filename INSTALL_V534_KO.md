# SEAFOOD INSIGHT LAB v5.34 — 심층분석 2편 시연·독립 소재 재선정 수정

## 무엇을 고쳤나

v5.33의 미리보기에는 심층분석이 **1편만** 들어 있었으며, 두 번째 분석을 만들 때 첫 번째 글의 근거를 AI 입력에서 제거하지 않았습니다. 이로 인해 새 소재를 분석하지 못하고 기존 주제를 반복할 가능성이 있었습니다.

- `python build.py --demo` 시연 화면에 **홈플러스 유통업계 분석 + 노르웨이 수산물 수출구조 분석 2편**을 넣었습니다. 서로 다른 원자료를 사용하며 상단의 두 주제 카드를 누르면 각 본문으로 이동합니다.
- 실제 AI 발행에서 첫 번째 분석이 검증되면 그 글에 사용한 기사와 공식 시계열을 두 번째 분석의 입력에서 제외하고, 남은 근거로 다시 주제를 선정합니다.
- 그 결과가 여전히 부족하면 원고를 조작해 2편을 채우지 않습니다. 모델/API/원문 수집 문제로 실발행이 1편일 수 있으며 그 상태를 로그에 남깁니다.
- 지난 분석 아카이브, 118개로 설정된 기사 수집 경로, 24시간/7일/30일 필터, 읽음·저장, 기존 UI 구조는 유지합니다.

## GitHub 업데이트 순서

1. ZIP 압축을 풀고 내용물을 GitHub 저장소 `Jeemyi/seafood-insight-lab`의 동일 경로로 업로드합니다. **ZIP 자체를 올리면 동작하지 않습니다.**
2. `build.py`, `seafood_ai.py` 외에도 모든 `.py`, `template.html`, `.github/workflows/daily.yml`, 테스트 파일을 같은 경로에 반영합니다. 기존 파일에 덮어써야 하는 경우 GitHub 웹 편집 또는 Git을 사용합니다.
3. 기존 `site` 폴더의 **`data.json`, `news_archive.json`, `report_archive.json`, `index.html`을 삭제하지 마세요.** 업데이트 ZIP에는 이들 데이터 파일을 포함하지 않았습니다.
4. `Actions` → `Daily SEAFOOD INSIGHT LAB` → `Run workflow`를 누릅니다. `OPENAI_API_KEY` GitHub Secret 연결을 유지합니다.
5. Actions 로그와 배포된 `site/data.json`에서 `deep_reports` 배열 개수를 확인합니다. **`build/deploy` 초록 체크는 2편 발행 성공을 의미하지 않습니다.**

## 검증 범위

- 자동화 코드 및 역사적 시연 데이터에 대한 테스트 94개 통과.
- 데스크톱·모바일 Chromium에서 **분석 카드 2개와 분석 본문 2개**, 2번째 카드 선택/본문 표시를 확인했습니다.
- 시연의 노르웨이 자료: Norwegian Seafood Council의 2026년 10월 발표(양식 비중 72→76%, 연어 물량 +9%) 및 SSB의 2026년 45주차 통계(28,277톤, 전년 대비 +17.3%). 공식 원문은 각각 `https://en.seafood.no/news-and-media/news-archive/norwegian-seafood-exports-remained-stable-in-october/`, `https://www.ssb.no/en/utenriksokonomi/utenrikshandel/statistikk/eksport-av-laks/artikler/salmon-price`입니다.
- 실제 GitHub 환경의 118개 수집 경로 응답률 및 라이브 AI 원고 생성은 **별도 검증이 필요**합니다. 시연 원고는 자동 AI가 생성한 최신 보고서가 아닙니다.
