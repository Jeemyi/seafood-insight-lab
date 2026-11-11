# SEAFOOD INSIGHT LAB v5.33 — 기존 GitHub 사이트 업데이트

## 이번 버전의 목표

뉴스 RSS·검색 수집 경로를 118개로 넓히고(실제 응답 경로 수는 실행일에 따라 다름), **서로 다른 주요 사건의 심층분석 2편 이상 발행을 목표**로 1편 생성 후에도 다른 사건을 추가 검토합니다. 공개 근거가 부족하거나 AI 호출/검수가 실패하면 2편을 조작해 채우지 않고, 실제 발행 편수를 경고로 남깁니다.

수치·통계는 가격·공급·유통·시장 전망을 뒷받침할 때만 사용합니다. '영업·구매에서 활용할 점' 등 억지 소제목은 제거하고 주요 동향/시장 분석/시장 전망 등 자연스러운 기사 문체로 작성합니다.

## 주의 — 데이터 파일 보존

이 ZIP은 **기존 사이트에 덮어쓰는 소스코드**입니다. 아래 사용 중인 데이터는 ZIP에 포함하지 않았습니다.

- `site/data.json` — 마지막 생성된 사이트 내용
- `site/news_archive.json` — 기존 30일 기사 기록
- `site/report_archive.json` — 날짜별 심층분석 기록
- `site/index.html` — 현재 공개 중인 사이트 페이지

**위 파일과 `site` 폴더를 GitHub 저장소에서 삭제하지 마세요.** ZIP 자체를 GitHub에 올리는 것이 아니라 압축 안의 파일들을 같은 경로로 반영해야 합니다. 기존 GitHub Pages 주소와 API Secret은 유지합니다.

## 적용 순서

1. ZIP을 내려받아 압축을 풉니다.
2. GitHub 저장소 `Jeemyi/seafood-insight-lab`의 소스코드와 같은 경로에 반영합니다. 최소한 `build.py`, `seafood_ai.py`, `seafood_newsroom.py`, `seafood_story_selection.py`, `template.html`, `health_check.py`, 그리고 함께 들어 있는 `seafood_*.py` 모듈을 모두 반영합니다. 누락된 모듈이 있으면 빌드에 실패할 수 있습니다.
3. **`.github/workflows/daily.yml`도 포함해서** 업데이트합니다. GitHub의 `.github`는 숨김 폴더입니다. 웹 업로드 과정에서 숨김 폴더가 빠지지 않았는지 확인하세요.
4. GitHub Actions의 **Daily SEAFOOD INSIGHT LAB → Run workflow**를 실행합니다. `.github/workflows/daily.yml` 안의 `OPENAI_API_KEY` Secret 연결을 유지하세요. API가 연결되지 않으면 심층 AI 원고는 생성되지 않습니다.
5. Actions의 `build`와 `deploy` 성공을 확인하고 `site/data.json`의 `deep_reports` 개수, 실제 RSS 성공 경로(`sources_ok`), `news_collection.seen_this_run` 및 `site/report_archive.json` 누적 여부를 확인합니다. 녹색 체크는 **문서 내용의 품질을 보증하지 않습니다.**
6. 갱신된 사이트에서 상단 주제 카드, 주요 뉴스, 기사 검색·더 보기, 하단 날짜별 분석 아카이브를 확인합니다. 오래된 화면이면 강력 새로고침합니다.

## 중요한 제한

- 118개는 **설정된 RSS/검색 경로 수**이지, 매일 118개 모두 정상 응답한다는 뜻이 아닙니다. 일부 Google/Bing 검색은 지역·접근 제한으로 차단될 수 있습니다.
- ‘매일 심층 2편 이상’은 **편집 목표**입니다. 서로 다른 사건을 뒷받침하는 근거가 없거나 OpenAI API가 실패할 경우 0–1편으로 발행하고, GitHub Actions에 **2편 미달 경고**를 표시합니다. 같은 사건을 둘로 쪼개거나 수치를 지어내지 않습니다.
- 미리보기 HTML과 스크린샷은 **과거 공개자료 시연본**입니다. 이번 세션에서 GitHub 실제 RSS 실행·OpenAI 리서치 원고의 최종 품질을 실측한 것은 아닙니다.
- 수집 결과가 많아져도 뉴스 목록은 기본 36개씩 불러오며, 24시간/7일/30일 필터와 검색·저장은 유지됩니다.
- AI 분석 호출이 여러 번 이루어질 수 있어 종전 버전보다 **API 사용량과 실행 시간**이 늘 수 있습니다. GitHub Actions 로그와 OpenAI API 사용량을 확인하세요.

## 검증

`python -m unittest discover -s tests -q` — 93개 테스트 통과. 브라우저 데스크톱(1440px)·모바일(390px) 로딩, 기사 카드, 읽기 크기, 30일 필터, 90건 더 보기/검색 리셋 검증. 실시간 네트워크 수집 테스트는 별개입니다.
