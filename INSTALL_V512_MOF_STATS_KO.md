# SEAFOOD INSIGHT LAB v5.12: 해양수산통계 추가 연동

## 어떤 API를 추가했나

- 기존 `MOF_API_KEY`: **공공데이터포털**의 「해양수산부_수산물 HSK품목별 수출입 현황」 API에 사용. **변경하거나 지우지 않는다.**
- 신규 `MOF_STATS_API_KEY`: **해양수산통계시스템**에서 별도로 발급한 오픈API 인증키에 사용.
- 신규 `MOF_STATS_TABLE_URLS`: 해양수산통계시스템에서 **원하는 통계표를 선택해 생성한 조회 URL 목록**에 사용.
- KAMIS 도·소매가격과 SSB 연어 통계 등 기존 수집원은 계속 사용한다.

공식 신청 화면: https://www.mof.go.kr/statPortal/api/idx/main.do

2024-12-13에 해양수산통계 OPEN API가 이전되었으므로 **신규 시스템 발급 키·URL**을 사용해야 한다. (과거 `statsportal` 소문자 주소 사용 금지.)

## GitHub 올릴 파일

압축을 풀고 저장소 구조 그대로 업로드:

1. `seafood_mof_statistics.py` (새로 추가)
2. `seafood_public.py` (기존 파일 덮어쓰기)
3. `seafood_data.py` (기존 파일 덮어쓰기)
4. `.github/workflows/daily.yml` (워크플로 환경변수 연결)

테스트와 설명 문서는 참고용으로 선택 업로드. `site/data.json`과 `site/index.html`은 덮어쓰지 않는다.

## 설정: GitHub Actions Secrets 2개

GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret

### A. `MOF_STATS_API_KEY`

해양수산통계 OPEN API 사이트에서 새로 발급받은 **해양수산통계 인증키**를 넣는다.
`MOF_API_KEY`와 완전히 별개다. 이 키를 README, 코드, 공개 GitHub 커밋에 기록하지 않는다.

### B. `MOF_STATS_TABLE_URLS`

해양수산통계 OPEN API 페이지에서 원하는 **실제 통계표를 선택하여 제공하는 요청 URL을 생성**한다. 그 URL의 인증키 값만 `{API_KEY}`로 치환한다.

예를 들어 URL 안에 `apiKey=본인의실제키`가 있다면 `apiKey={API_KEY}`로 교체한다. 키가 다른 이름의 매개변수에 들어있어도 값 부분만 `{API_KEY}`로 바꾸면 된다.

실제 URL을 **JSON 배열**로 만들어 등록한다. 아래는 형식 설명용이며 `URL_...` 자리는 포털에서 생성한 URL로 교체해야 한다. 원문 그대로 넣어도 동작하지 않는다.

```json
[
  {"name":"어업생산량", "url":"URL_어업생산량_통계표_실제조회주소_키값은_{API_KEY}"},
  {"name":"양식생산량", "url":"URL_양식생산량_통계표_실제조회주소_키값은_{API_KEY}"}
]
```

처음에는 **1~3개 통계표**로 작동 확인을 권장한다. 시스템은 최대 12개를 받아들이며, 공백 배열 또는 한쪽 설정만 있으면 데이터를 발행하지 않는다.

추천 통계표: 품목별 어업생산량, 양식 생산량, 연근해·원양 생산량, 가능하다면 월별 품목 생산량. 단, **통계표 실제 제공 여부와 분류 코드는 포털에서 확인**해야 한다.

**주의:** 공공데이터포털의 「연도별 총괄 어업생산통계」는 또 다른 독립 API이다. 여기서 등록하는 URL은 **해양수산통계시스템에서 생성한 조회 URL**이어야 한다.

## 어느 단계에 반영되나

매일 `seafood_public.make_public_features`가 다음을 병렬로 호출한다.

- HSK 품목별 수출입 통계 (기존)
- KAMIS 가격 통계 (기존)
- **해양수산통계 통계표들 (신규)**

서로 다른 통계표나 단위(톤 vs 천톤), 종·세부 품목을 합산하지 않는다. 최근 관측과 전년 동일기간을 우선 비교하고, 없으면 직전 관측을 비교한다. 비교 가능한 관측이 1건밖에 없으면 발행하지 않고 로그에 기록한다.

실행 로그에서 `SEAFOOD MOF STATS table=` 및 `SEAFOOD MOF STATS tables=... features=...`를 확인한다.

## 검증 범위

- 코드 자동테스트 **126개 통과** (모의 JSON 응답 포함)
- 실제 인증키와 사용자가 생성한 통계표 조회 URL은 아직 제공받지 않아 **실제 연결 성공 여부는 확인하지 못했다.**
- 포털의 응답 구조가 문서상 형식과 달라지면 파서에 조정이 필요할 수 있다. `ValueError`가 뜨더라도 URL·인증키를 로그에 출력하지 않도록 했다.
