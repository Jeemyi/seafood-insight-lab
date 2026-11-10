# GitHub에 SEAFOOD INSIGHT LAB 올리는 순서

> 기존 `Jeemyi/market-insight-lab`은 그대로 둡니다. 새 저장소를 만듭니다.

1. [GitHub 새 저장소](https://github.com/new)를 열어 이름에 **seafood-insight-lab** 입력 → Public 선택 → Create repository.
2. 다운받은 ZIP을 압축 해제하고 내부의 `build.py`, `seafood_ai.py`, `seafood_data.py`, `template.html`, `requirements.txt`, `README.md`, `QUICK_START_KO.md` 및 `site` 폴더 등을 **ZIP이 아니라 압축 풀린 파일로** 새 저장소에 업로드. 프로젝트 최상위 경로에 코드가 있어야 함.
3. 폴더 `.github/workflows/daily.yml`을 GitHub 웹 업로드에서 누락했다면 [GitHub 새 파일 화면](https://github.com/Jeemyi/seafood-insight-lab/new/main)에 경로 `.github/workflows/daily.yml` 입력한 뒤 ZIP의 같은 파일 내용을 붙여넣고 Commit. 이 단계는 자동 배포에 반드시 필요.
4. 새 저장소의 **Settings → Pages → Build and deployment → Source: GitHub Actions** 선택.
5. 새 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 다음 값 설정:
   - `OPENAI_API_KEY`: MARKET INSIGHT LAB에서 쓰던 OpenAI API 키를 이 저장소에도 *별도로* 등록할 수 있음(발급한 키의 프로젝트 권한/사용량 확인). GitHub Secret은 저장소 간 자동 공유되지 않음.
   - `ECOS_API_KEY`: 한국은행 ECOS 발급 키. **FRED_API_KEY와 다릅니다.** 아직 없으면 생략(환율 자동 수집 비활성).
6. 새 저장소 **Actions → Daily SEAFOOD INSIGHT LAB → Run workflow** 클릭.
7. `build`와 `deploy`가 초록 체크면 `https://Jeemyi.github.io/seafood-insight-lab/` 주소를 열어 확인. 실제 배포 후에 주소가 열림. 첫 화면은 큰 소개 배너 대신 **오늘의 브리핑 → 핵심 분석 → 데이터 분석 → 주요 뉴스** 순서.
8. 실패하면 Actions의 빨간 항목을 눌러 오류 내용 확인. `site/data.json`에도 기사 수집 및 지표 상태가 기록됨.

## 데이터 범위

- 자동 수집: Google 뉴스 검색 RSS + 공개 언론 RSS / 공식 SSB 연어 수출 가격 / ECOS 환율(키 등록 시)
- 링크만: KMI, 수협 위판 정보, 관세청 수출입단가, Norwegian Seafood Council 일부 로그인 필요 통계 등 공개 API를 확인하지 못한 자료
- `3년 평균`: 실제 동일 주차/동일 날짜 3개 연도가 모두 있을 때만 계산. 일부 시계열은 비교 생략.
- 거래조건/가격/이익률은 내부자료에 해당하므로 이 사이트가 수치로 추정하지 않음.

## GitHub에서 잘못된 저장소에 업로드하지 않기

업데이트할 때 URL이 `Jeemyi/seafood-insight-lab`인지 확인하세요. 기존 금융 사이트인 `Jeemyi/market-insight-lab`의 `build.py`를 바꾸면 안 됩니다.


## v3에서 바뀐 점
- 화면과 리포트의 한국어를 자연스럽게 고쳤습니다.
- AI 입력 기사 후보를 분야별로 분산합니다. 수산물만이 아니라 유통·온라인·해외·안전 규정도 함께 검토합니다. 실제 분석은 근거가 충분한 주제만 게시합니다.
- 시연 화면의 기타 3개 주제 카드는 실제 뉴스가 아니라 **분석 범위 예시**로 표시합니다.
- 공식 자동 가격 통계는 여전히 연어(SSB)와 환율(ECOS) 중심입니다. 새 가격 통계가 자동으로 추가된 것은 아닙니다.


## v4 적용 시 필수 확인
1. 저장소 루트의 `build.py`, `seafood_ai.py`, `seafood_data.py`, `template.html`, `requirements.txt`를 v4 파일로 교체한다.
2. `.github/workflows/daily.yml`도 v4로 교체한다. 기존에 직접 작성한 파일이 있다면 **꼭 편집한다.** 안 바꾸면 보고서 아카이브 저장 기능과 모델 설정이 반영되지 않는다.
3. Settings > Secrets and variables > Actions의 `OPENAI_API_KEY`를 확인한다. `ECOS_API_KEY`는 환율용이다. 추가 키 없음.
4. Actions > Daily SEAFOOD INSIGHT LAB > Run workflow > main > Run workflow로 수동 실행한다.
5. `build`와 `deploy`가 모두 초록 체크인지 확인한다. 화면에 새 분석이 아닌 '지난 분석'이라고 표시되면 자료 부족/모델 실패 등으로 현재 보고서 생성에 실패한 것이다.

**비용:** v4는 기본적으로 `gpt-6.1-sol`와 웹 검색을 사용하며 v3보다 OpenAI API 사용량이 늘어날 수 있다.
