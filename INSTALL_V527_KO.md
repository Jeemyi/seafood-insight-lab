# SEAFOOD INSIGHT LAB v5.27 — 뉴스 중심 아카이빙

## 이번 버전의 우선순위

**최근 뉴스 수집 → 최근 7일 이슈 선정 → 보도별 사실 → 시장 영향 해석과 잠정 결론 → 공식 통계로 검증 → 기사 아카이브** 순서입니다.

v5.26 RSS 안정화 패치와 전체 저장소(v5.4 계열)를 통합했고, 패치에만 있던 `seafood_topic_tracks`, `seafood_research_depth` 의존 모듈도 포함했습니다. 기존 ZIP 위에 `build.py`나 `template.html`만 부분 덮어쓰기하지 말고, **이번 ZIP의 전체 파일**을 GitHub 저장소에 올리세요.

## GitHub 적용 방법

1. 이 ZIP을 압축 해제하고 GitHub `seafood-insight-lab` 저장소의 파일을 같은 경로로 교체하세요. `.github/workflows/daily.yml`도 빠뜨리지 마세요.
2. GitHub `Actions` → `Daily SEAFOOD INSIGHT LAB` → `Run workflow`를 실행하세요. 예약 실행은 기존과 같이 매일 **한국시간 오전 6시**입니다.
3. 실행 로그에서 `SEAFOOD RSS CURRENT RUN`, `SEAFOOD NEWSROOM`, `SEAFOOD NEWS ANALYSIS`를 확인하세요.
4. GitHub Pages 배포 완료 후 사이트를 새로고침하세요. ZIP에 들어 있는 `site/index.html`은 **과거 공개자료로 만든 데모**이며, 수동 실행으로 실시간 데이터로 교체됩니다.

기존 GitHub Secrets는 그대로 사용합니다. `OPENAI_API_KEY`가 있으면 기사별 근거에 기반해 확인된 변화·시장 영향·잠정 결론·후속 변수를 구성하고, 검증되지 않은 해석은 게시하지 않습니다. 추가 설정 `SEAFOOD_NEWS_BRIEF=0`은 AI 뉴스 해석만 끄는 선택값입니다. 기본은 켜짐입니다.

## 데이터 보존

- 메인 최신 뉴스: 게시일 기준 최근 **7일**, 최대 350건
- 기간 선택의 이전 기사: 최근 **8~30일**, 최대 총 800건 저장 (과거 게시일 유지)
- 이전 아카이브 파일: `site/news_archive.json`, Actions가 **다음 실행을 위해 커밋**
- `site/data.json`은 최신 홈페이지 데이터와 심층 분석을 위한 자료이며 별도 뉴스 원장은 위 파일이 담당합니다.
- 동일 URL의 추적 파라미터만 제거하여 중복 등록을 줄이며, 서로 다른 매체 보도는 근거 확인을 위해 보존합니다. 매체가 둘이라도 원발표가 같으면 독립 검증이라고 단정하지 않습니다.
- 수집에 실패한 날도 이전 게시물의 날짜를 오늘 날짜로 바꾸지 않습니다.

## 수집 범위 및 한계

- 기존 Google News RSS 주제별 검색과 재시도/차단 진단을 유지하고, 연합뉴스/뉴시스/동아일보/매일경제 등 공개 RSS를 추가해 대체 경로를 확보했습니다. 각 매체의 RSS 주소는 운영 중 변경되거나 차단될 수 있습니다.
- 기사 본문 전체를 크롤링하거나 유료벽을 우회하지 않습니다. **기사 제목·공개 소개문·발행시각·출처·원문 링크**를 사용합니다.
- 공식 API 수치는 관련 뉴스의 뒷받침 자료로만 사용하고, 연결 근거가 없는 공식 데이터만으로 새로운 '주요 이슈'를 생성하지 않습니다.
- AI 해석의 품질은 공개 원문 수집량과 API 응답에 의존합니다. 기사만으로 결론을 뒷받침하기 어려운 경우 '시장 영향 · 확인할 변수'만 표시하고 **강한 결론을 만들지 않습니다**.
- 이 개발 환경은 외부 RSS/실제 OpenAI API 인증 호출이 제한돼 있어서 실제 일일 리포트의 기사 수나 AI 원고 품질을 보장할 수 없습니다. 실제 GitHub Actions 로그를 통한 운영 검증이 추가로 필요합니다.

## 로컬 확인

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python build.py --demo  # 데모 데이터: 배포 전 화면 확인용
python build.py         # 실시간 RSS, 공식 API, 선택적 AI 분석
python health_check.py
```

UI는 `최근 7일 이슈 → 주요 기사/검색 → 근거 검증된 심층 해석 → 접혀 있는 공식 통계` 순서입니다. 공식 데이터 영역은 펼쳐서 볼 수 있고, 기사는 **최근 7일 / 지난 30일 포함**으로 전환할 수 있습니다.
