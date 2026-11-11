# SEAFOOD INSIGHT LAB v5.28 - 뉴스 수집/아카이빙 및 사건 중심 분석

## 이 업데이트의 기준

이 버전은 단순 통계 요약 생성기가 아니라 **최근에 실제로 발표된 기사**를 먼저 수집하고, 개별 사건을 구분한 뒤, 근거가 있는 사건에만 해석을 붙이는 데 중점을 둡니다.

- 첫 화면: **주요 이슈와 시장 전망** / 최근 7일 주요 사건
- 기사 목록: **최근 24시간 / 7일 / 30일**, 제목 검색, 분야 필터, 읽음/저장
- 분석: 수집된 실제 보도를 기반으로 사건별 판단을 생성합니다. API가 실패하거나 수치가 틀리면 기사는 남기되 근거 없는 분석은 표시하지 않습니다.
- 통계: 개별 뉴스 사건과 연결된 경우에만 보조 근거로 제공하며 기본 화면 아래에 접어둡니다.

## GitHub 적용

1. ZIP 압축을 푼 다음, 기존 **seafood-insight-lab 저장소 루트**에 모든 코드/설정 파일을 **동일한 경로로 덮어쓰기** 합니다. 기존 파일을 모두 삭제하는 방식이 아닙니다.
2. **중요: 기존 `site/data.json`, `site/news_archive.json`, `site/index.html`은 삭제하거나 이 패키지로 덮어쓰지 마세요.** 이 파일들은 기존 실운영 결과이며, 새 ZIP에는 넣지 않았습니다.
3. 기존 GitHub Secrets(OPENAI_API_KEY, ECOS_API_KEY, MOF_API_KEY, KAMIS_API_KEY, KAMIS_API_ID)는 유지합니다. 이 ZIP에 개인 인증키를 넣지 않았습니다.
4. 변경사항 Commit 후 **Actions -> Daily SEAFOOD INSIGHT LAB -> Run workflow**를 실행합니다.
5. Actions가 정상 완료되면 공개 사이트가 재생성되고 기존 뉴스 기록이 다음 실행으로 이어집니다.

## 확인할 로그

- `SEAFOOD RSS CURRENT RUN: observed=... archive_reused=... GoogleNews=... Bing=... publisher=...`
- `SEAFOOD NEWSROOM: recent=... issue_digest=... archives=...`
- `SEAFOOD NEWS ANALYSIS: 뉴스 이슈 해석 N/M편 검증 통과`
- `SEAFOOD report: N new deep reports`는 별도 심층 분석 건수입니다. **이 수치가 0이더라도 RSS 기사 수집 자체가 실패한 것은 아닙니다.**

`observed`는 **이번 실행에서 실제로 다시 확인한 기사 URL 수**이며, `archive_reused`는 기존 기록 중 보존한 기사 수입니다. 숫자를 합쳐 새 기사라고 부르지 않습니다.

## 변경된 수집원

- 직접 언론사 RSS 16종(기존 유지)
- Google 뉴스 검색 30종(접근 제한 발생 시 오류 표시)
- Bing 뉴스 검색 15종(별도 공개 검색 RSS, 비공식 인터페이스로 공급자 측 변경 가능)

여러 RSS가 같은 기사를 가리킬 수 있으므로, **61개 피드 = 61개 기사**가 아닙니다. URL 중복은 기사 원장에서 제거하고, 서로 다른 언론사의 실제 보도는 원문을 보존합니다.

## 알고 있어야 할 제한

- GitHub에서 실제 RSS에 연결한 통합 검증은 이 패키지를 작성한 실행 환경의 네트워크 제한으로 수행하지 못했습니다.
- 언론사 기사 본문을 우회 복제하지 않습니다. RSS 제목·공개 소개문·게시일·원문 링크를 저장합니다.
- AI 해석은 제공된 제목·소개문·연결된 공식 데이터 범위에서만 허용합니다. 보도 근거가 얕다면 **원문 기사만 게시**할 수 있습니다.
- 기존 통계 기반 심층 연구 파이프라인은 유지했습니다. 이번 업데이트는 그 품질을 자동으로 보장하지 않습니다.
- 실제 기사 수와 새 분석 건수는 GitHub Actions 실행 로그에서 확인해야 합니다.

## 로컬 검증 명령

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -q
python build.py --demo
```

`--demo`는 과거 공개자료를 사용한 **화면 검증용**이며, 실시간 기사 수집이나 AI 분석 성공을 입증하지 않습니다. 운영 실행은 `python build.py`입니다.
