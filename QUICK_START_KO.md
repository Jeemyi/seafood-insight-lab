# 기존 SEAFOOD INSIGHT LAB GitHub 사이트에 v5 적용하기

**금융 MARKET INSIGHT LAB 저장소에는 절대 올리지 마세요.**

1. `seafood-insight-lab-v5-update-only.zip` 압축 풀기.
2. GitHub → `Jeemyi/seafood-insight-lab` → Code → Add file → Upload files.
3. 아래 **7개 파일**을 저장소 맨 위(root)에 업로드해서 덮어쓰고 Commit changes:
   - `build.py`
   - `seafood_ai.py`
   - `seafood_data.py`
   - `seafood_editorial.py` **(새 파일)**
   - `seafood_public.py` **(새 파일)**
   - `template.html`
   - `requirements.txt` (기존과 같아도 문제 없음)
4. `.github/workflows/daily.yml`은 숨김 폴더라 GitHub 웹에서 놓칠 수 있습니다. 저장소에서 **Code → .github → workflows → daily.yml → 연필(Edit)**을 눌러 **v5 ZIP에 포함된 `.github/workflows/daily.yml` 전체 내용**으로 교체하고 Commit. 기존 파일이 없다면 Add file → Create new file에서 `.github/workflows/daily.yml` 경로로 작성하세요.
5. 저장소 Settings → Secrets and variables → Actions → New repository secret에서 `OPENAI_API_KEY`, `ECOS_API_KEY` 확인. 기존 값을 다시 넣을 필요는 없습니다.
6. 추가 데이터 연결을 원하면 다음 Secrets도 등록:
   - `MOF_API_KEY` : [공공데이터포털 해양수산부 HSK API](https://www.data.go.kr/data/15056602/openapi.do) 활용 신청 후 서비스 키
   - `KAMIS_API_KEY`와 `KAMIS_API_ID` : [KAMIS Open API](https://www.kamis.or.kr/customer/reference/openapi_list.do?action=detail&boardno=1)에서 발급한 인증키와 등록 ID
   - 새 키가 없더라도 사이트 자체는 실행됩니다. **단, 국내 수출입·도소매 자동 통계는 표시되지 않습니다.**
7. Actions → Daily SEAFOOD INSIGHT LAB → Run workflow → main → Run workflow.
8. `build`와 `deploy`가 모두 녹색인지 확인하고 https://jeemyi.github.io/seafood-insight-lab/ 에 접속.

기존 사이트의 `site/data.json`은 **업데이트 ZIP에 넣지 않았습니다**. 과거 보고서를 보존하기 위해서입니다.

## 실행 설정
- 한국시간 매일 오전 **6:00**, 하루 **1회** (`0 21 * * *`, UTC 기준). GitHub Actions 예약 작업은 몇 분 늦게 시작할 수 있습니다.
- AI 모델 `gpt-6.1-sol`, 웹 검색 켬. AI 검색·재작성 비용이 발생할 수 있습니다.
- 모델이나 외부 API 오류가 나더라도 공식 수치만 이용해 산출 가능한 해설을 표시할 수 있습니다. 이 해설은 AI 심층 분석과 구분됩니다.

## 자주 묻는 질문
- **KMI 광어/우럭 자료는 이미 직접 자동 수집?** 아직 아닙니다. 공개 원문과 최신 기사를 조사하도록 했지만, API 기반 월간 수치 연결은 향후 과제입니다.
- **키를 안 넣었는데 뉴스만 보이나요?** 네. RSS 뉴스와 접근 가능한 SSB 통계, ECOS 키가 있다면 환율은 표시됩니다. 국내 HSK와 KAMIS 숫자는 각 인증키를 등록해야 시작합니다.
- **금융 사이트도 영향받나요?** 아닙니다. SEAFOOD 저장소의 코드만 바뀝니다.
- **어떻게 실패 원인을 보나요?** Actions → 해당 실행 → `Research, write, and verify today's report` 로그와 사이트 `site/data.json`의 `errors`,`metric_errors`를 확인하세요. 절대 API 키를 공개하지 마세요.
