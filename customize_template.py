from pathlib import Path
import re
p=Path(__file__).resolve().parent/'template.html'
s=p.read_text(encoding='utf-8')
repl={
'MARKET INSIGHT LAB v6.1 — 결론부터 읽는 시장 리서치':'SEAFOOD INSIGHT LAB — 결론부터 읽는 수산 시장 리서치',
'뉴스를 시장 구조·금리·환율·수급·포트폴리오 위험의 연결고리로 읽는 자산운용 취업 준비용 인사이트 대시보드':'공개 수산 뉴스와 공식 시세를 묶어 원물가·납품가·채널별 수익성으로 연결해 읽는 수산 가공·유통 리서치 대시보드',
'<span class="brand-symbol">M/</span>MARKET INSIGHT <span class="header-label">CONNECT THE DOTS</span>':'<span class="brand-symbol">S/</span>SEAFOOD INSIGHT <span class="header-label">FROM SEA TO SHELF</span>',
'FOR FUTURE ASSET MANAGEMENT PROFESSIONALS':'SEAFOOD SUPPLY · RETAIL · COST STRUCTURE',
'시장의 큰 변화에서,<br>숨은 구조를 찾기.':'원물 시세의 변화가,<br>채널 수익에 닿기까지.',
'무엇이 변했고, 왜 지금이며, 다른 변수에 어떤 경로로 번지는가?<br>매일 중요한 뉴스와 지표를 연결해 가설과 반론을 함께 읽습니다.':'공개 뉴스와 공식 지표를 묶어 원물가·납품가·채널별 이익률의 전달 경로를 읽습니다.<br>근거와 반론을 함께 보며 10분 안에 확인할 실무 판단을 정리합니다.',
'기사 묶음 · 근거 확인':'공식 지표 · 원가 전파 경로',
'CONNECTED BRIEF':'SEAFOOD BRIEF',
'중요도 · 근거 · 인과 · 반론':'수급 · 채널 · 비용 · 근거 · 반론',
'오늘의 시장을 읽는 핵심 인사이트':'이번 주 수산 시장의 핵심 인사이트',
'핵심 결론을 먼저 읽고, 관심 있는 주제의 근거·인과관계·구조적 해석·조건부 전망을 펼쳐보세요. 질문이 아닌 완성된 분석만 게시합니다.':'공개 자료에서 확인된 변화가 원물가·납품가·채널별 이익에 어떤 조건으로 연결될지 완성된 분석으로 제시합니다. 결론부터 읽고 필요하면 근거와 반론을 펼쳐보세요.',
'숫자에서 출발하는 구조적 시장 해석':'실제 가격·환율에서 출발하는 데이터 리서치',
'같은 관측일의 실제 FRED 수치를 계산한 뒤, AI가 전달 경로·반대 가설·조건부 결론을 분석합니다. <strong>01번과 주제가 겹치지 않는 데이터 리서치를 우선합니다.</strong> 숫자의 동행만으로 인과관계는 확정하지 않습니다.':'SSB·한국은행 ECOS의 공식 공개 수치를 비교 가능한 기간에 맞춰 계산합니다. <strong>01번과 다른 주제를 우선하며, 수출가격과 실제 국내 매입단가는 구분합니다.</strong> 3년 비교 자료가 없으면 표시하지 않습니다.',
'추가 참고 · 같은 주제의 기사 묶음 보기 (자동 생성된 검증 질문이며 분석 결론은 아님)':'03 / 추가로 읽을 것 · 출처 비교 질문 (AI 분석 결론 아님)',
'추가 기사 묶음과 검증 메모':'출처별 보도 차이와 검증 질문',
'여러 출처가 다룬 변화를 묶어 <strong>무엇을 비교해야 인과관계를 판단할지</strong> 제시합니다. 이 목록은 AI가 내린 결론이 아니라 증거를 검증할 문제 목록입니다.':'같은 수산 이슈를 서로 다른 출처로 확인합니다. 이곳은 결론이 아닌 <strong>후속 자료 확인용 질문</strong>입니다.',
'주요 기사 · 원자료 확인':'이번 주 중요한 수산·유통 기사',
'리서치의 참고 근거 및 추가 기사':'채널 영향·원가 방향·후속 지표와 원문을 함께 표시',
'참고 기사 전체 목록':'전체 기사 검색·필터',
'연결해서 읽을 소재를 직접 찾아보기 · 읽음 · 저장':'10개 카테고리 · 읽음 · 저장 · 검색',
'인사이트 카드 2개':'핵심 인사이트 카드 읽기',
'현상 → 연결 구조를 읽고, 일단 가설로 두기':'원물 수급 → 원가 → 판매 조건의 연결 읽기',
'기사·수치 교차 확인':'관련 기사와 원자료 확인',
'기사와 공식 데이터를 확인해 지표의 기준일 맞추기':'가격의 단위·기준일·규격과 채널을 구분',
'어떤 조건에서 해석이 틀릴 수 있는지 덧붙이기':'환율·재고·행사 조건을 반론으로 기록',
'중요한 변화를 볼 때':'수산 원가·유통 변화 분석 프레임',
'① 기준선</b> 이전 기간·시장 예상과 비교<br><b>② 비교집단</b> 다른 나라·업종·자산과 대조<br><b>③ 전달 경로</b> 누가 사고팔고, 현금흐름·금리가 어떻게 연결되는가<br><b>④ 반대 가설</b> 환율·구성효과·계절성·제도 효과를 구분<br><b>⑤ 후속 변화</b> 다음에 확인할 지표와 시점':'① 기준점</b> 전주·전년·3년 동기 평균과 비교<br><b>② 비교군</b> 수입/국산·규격·어종·유통채널 구분<br><b>③ 전파 경로</b> 시세·환율 → 제조원가 → 납품가 → 채널별 이익률<br><b>④ 반가설</b> 재고 단가·행사비·물류비·규격 차이 검토<br><b>⑤ 후속 지표</b> 위판가·실매입가·재고 회전·납품가 갱신',
'기계적인 하나의 화살표로 모든 현상을 설명하지 않습니다.':'가격 인하·인상은 계약 시점과 채널별 조건에 따라 다르게 전달됩니다.',
'확인된 가격·금리·환율 변화와 그것을 설명하는 인과 가설은 다릅니다. 숫자의 기준일이 일치하는지, 다른 해석이 가능한지, 이후 어떤 관측이 결론을 바꾸는지까지 함께 제시합니다.':'관측된 수출 FOB 가격·환율과 기업의 실제 매입단가·납품가·이익률은 다릅니다. 관측 가격의 단위·발표시점을 표시하고, 인과 설명은 검증이 필요한 가설로 남깁니다.',
'주 1회 깊게 읽을 곳':'수산 원자료·정책 깊게 읽기',
'기사 출처 및 요약 표시':'자료 이용과 투명성',
'MARKET INSIGHT LAB</strong> · 개인 학습용 금융기사 읽기 대시보드':'SEAFOOD INSIGHT LAB</strong> · 개인 학습용 수산 가공·유통 리서치 대시보드',
'ⓘ 즐겨찾기·읽음은 현재 브라우저에만 저장 · 푸시 알림 없음':'ⓘ AI의 인과 분석은 검증 가설 · 공개자료만 사용 · 브라우저별 읽음/저장',
"['전체','금리·통화정책','거시·경기','환율·외환','채권·유동성','증시·수급','자산운용·ETF','제도·운용산업']":"['전체','원물 수급/시세','코스트코','대형마트/SSM','매장 운영','온라인','B2B/급식','식품안전/소비심리','시즌/트렌드','비용/거시','해외']",
"mb_2026_":"sil_2026_",
'실제 FRED 수치 기반':'실제 공식 시세·환율 기반',
'수치는 FRED의 관측자료이며 AI의 해석은 인과관계 입증이 아닙니다. 데이터의 발표 시차·수정 가능성 및 기사 발췌의 한계를 고려해야 합니다.':'수치는 공개 SSB·ECOS 관측자료입니다. 수출 FOB 가격은 실제 매입단가가 아니며 AI의 인과 설명은 가설입니다.',
'관측 지표':'공식 관측 지표',
'수치의 출처 · 관련 기사':'공식 원자료 · 관련 보도',
'FRED 원자료':'공식 원자료',
'측정 구간:':'비교 구간:',
' · 공통 관측일 기준 비교':' · 각 지표의 발표·관측 시점 기준',
'실제 관측 숫자 · 공통 관측일 기준':'공식 관측 숫자 · 비교 기간 확인',
'금융시장과 투자 판단에 남는 의미':'원물 소싱·판매 채널 판단에 남는 의미',
'투자 환경에서 달라지는 의미':'수산 구매·채널 운영 판단에 남는 의미',
'숫자를 연결할 수 있는 최신 FRED 시계열 자료가 부족합니다.':'현재 자동 접근 가능한 공식 수산·환율 시계열이 부족합니다.',
'아래 금융지표와 기사 목록':'아래 공식 지표와 기사 목록',
'아래 실제 기사 목록과 데이터 출처':'아래 실제 기사 목록과 데이터 출처',
'최근 7일 이내 게시물':'최근 14일 이내 게시물',
}
for a,b in repl.items():
    if a not in s:print('NOT FOUND:',a[:90])
    s=s.replace(a,b)
# Replace sidebar source links as one self-contained block; do not auto-collect unverified source pages.
start=s.index('   <section class="sidebar-card"><div class="side-label">DEEP READING')
end=s.index('  </aside>',start)
s=s[:start]+'''   <section class="sidebar-card"><div class="side-label">DEEP READING</div><h2 class="side-title">공식 자료 확인할 곳</h2>
   <div class="sources"><a class="source-link" href="https://www.foc.re.kr/" target="_blank" rel="noopener noreferrer">KMI 수산업관측센터 · 어종별 수급</a><br>
   <a class="source-link" href="https://www.mof.go.kr/" target="_blank" rel="noopener noreferrer">해양수산부 · 보도자료</a><br>
   <a class="source-link" href="https://unipass.customs.go.kr/ets/" target="_blank" rel="noopener noreferrer">관세청 · 무역통계</a><br>
   <a class="source-link" href="https://www.kati.net/" target="_blank" rel="noopener noreferrer">aT KATI · 해외 식품시장 정보</a><br>
   <a class="source-link" href="https://www.korfish.or.kr/" target="_blank" rel="noopener noreferrer">한국수산회</a><br>
   <a class="source-link" href="https://en.seafood.no/market-insight/" target="_blank" rel="noopener noreferrer">Norwegian Seafood Council</a><br>
   <a class="source-link" href="https://www.ssb.no/en/statbank/table/03024/" target="_blank" rel="noopener noreferrer">SSB · 연어 수출가격·물량</a><br>
   <a class="source-link" href="https://ecos.bok.or.kr/" target="_blank" rel="noopener noreferrer">한국은행 ECOS · 환율</a></div>
   <div class="side-divider"></div><div class="footnote">KMI·수협·관세청 등 API/RSS 연결을 확인하지 못한 지표는 링크만 제공합니다. 자동 수집·3년 평균 계산을 하는 공식 지표는 해당 섹션에 출처가 명시됩니다.</div></section>
   <section class="sidebar-card side-wide"><div class="side-label">SOURCES & TRANSPARENCY</div><h2 class="side-title">뉴스 출처와 계산 방식</h2>
   <div class="sources">Google 뉴스의 공개 검색 RSS 및 한국경제·매일경제의 공개 RSS 제목/소개문을 이용합니다. 기사 본문을 우회해 수집하지 않습니다. 원문 링크는 게시자가 제공하는 URL이며 일부는 Google 뉴스 경유 링크일 수 있습니다.</div>
   <div class="side-divider"></div><div class="footnote">공식 데이터: SSB PxWeb 통계 / 한국은행 ECOS(별도 인증키). 변동률은 수집값으로 계산하며, 전주·전년 동기·3년 동기 평균 중 기초값이 없는 비교는 생략합니다. AI는 수치 계산을 하지 않고 공개 근거에 대한 가능한 해석을 작성합니다. 실제 기업의 구매가격·납품가·이익률을 알고 있는 것으로 표현하지 않습니다. 개인 학습용이며 AI 인과 해석은 확정 사실이 아닙니다.</div></section>
''' +s[end:]
# Fix empty deep notice double punctuation and language of no features.
s=s.replace("${esc(data.deep_status||'원고 생성에 필요한 근거 부족')}.","${esc(data.deep_status||'원고 생성에 필요한 근거 부족')}")
s=s.replace('공통 관측일 기준','공식 발표 기준')
# 'role' tags for article effects and followup: no fake hard-code claim.
s=s.replace('<div class="question"><span class="q-mark">읽을 때 볼 것</span>',
'''<div class="impact-strip"><span class="effect-tag">영향 채널 · ${esc((a.channels||[]).join(' / ')||'확인 필요')}</span><span class="effect-tag">${esc(a.impact||'방향 미확정')}</span></div><div class="question"><span class="q-mark">후속 확인</span> ${esc(a.followup||'관련 채널 실데이터')} · ''')
# previous replace inserted a duplicated expression before the original interpolation; repair the entire question tail.
s=s.replace("${esc(a.followup||'관련 채널 실데이터')} ·  ${esc(a.question||'이 뉴스가 시장에 어떤 영향을 주는지 확인')}","${esc(a.followup||'관련 채널 실데이터')}")
# Add small tags for list cards; show channels and impact without expanded clutter.
s=s.replace('<p class="list-summary">${summary(a)}</p>',
'''<p class="list-summary">${summary(a)}</p><div class="item-meta" style="margin-top:6px">채널: ${esc((a.channels||[]).join(' / ')||'확인 필요')} · ${esc(a.impact||'방향 미확정')} · 후속: ${esc(a.followup||'자료 확인')}</div>''')
# Make deep report lead operationally tagged.
s=s.replace('<h3>${esc(r.headline)}</h3><div class="deep-thesis">',
'''<h3>${esc(r.headline)}</h3><div class="impact-strip"><span class="effect-tag">채널 · ${esc((r.channels||[]).join(' / ')||'근거에 따라 확인')}</span><span class="effect-tag">${esc(r.impact||'원가·매출 영향 미확정')}</span></div><div class="deep-thesis">''')
s=s.replace('<p class="report-lead">${esc(r.lead)}</p>',
'''<p class="report-lead">${esc(r.lead)}</p><p class="report-lead"><b>후속 지표:</b> ${esc(r.followup||'매입단가·납품가·행사비 등 실제 자료 확인')}</p>''')
# update f.j data face and detect conditional % comparisons
s=s.replace('<h3>${esc(title)}</h3><div class="fact-row">',
'''<h3>${esc(title)}</h3><div class="impact-strip"><span class="effect-tag">관련 채널 · ${esc((ins.channels||[]).join(' / '))}</span><span class="effect-tag">${esc(ins.impact||'실제 원가 확인 필요')}</span></div><div class="fact-row">''')
# Theme override as last CSS rules for consistency, not brittle many replace of existing CSS.
extra='''\n/* SEAFOOD palette and operational impact tags */
:root{--ink:#17312d;--ink2:#5c6d69;--ink3:#879b93;--paper:#f4f8f6;--line:#e0ebe7;--accent:#087c70;--pale:#e1f6ef;--strong:#173d36;--shadow:0 12px 36px rgba(11,67,57,.06)}
.brand-symbol{background:#0d665a}.hero-left{background:linear-gradient(120deg,#103b36,#0d6b61 67%,#16827b)}.eyebrow{color:#b8e5dc}.hero-desc{color:#d5f5ed}.hero-pill{color:#e1faf4}.rank{background:#e5f4ee;color:#246d5e}.featured-card:first-child .rank{background:#ccece1;color:#0d665a}.category-pill{color:#116e62;background:#e4f6ef}.question{background:#f0f9f5;color:#326b5e}.q-mark{color:#167265}.tab.active{background:#0a6559}.side-label,.chain b,.open-link,.source-link{color:#087c70}.routine-num,.study-example{background:#e6f5ef;color:#0c7264}.study-example{border-color:#56b29a}.issue-card:first-child{background:linear-gradient(130deg,#e9faf3,#fff)}.issue-eyebrow,.issue-check>b{color:#087c70}.deep-cover{background:linear-gradient(135deg,#e8f8f1,#fff 78%)}.deep-report.primary .deep-cover{border-top-color:#0d7769}.deep-thesis,.data-report-cover,.research-body .deep-memo{border-left-color:#0b8272;background:#e9f7f2;color:#225648}.deep-section-label,.data-expand>summary,.report-expand>summary,.data-research-body h4{color:#0c7063}.insight-card,.deep-report{overflow:hidden}.impact-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:10px 0}.effect-tag{font-size:10.5px;font-weight:750;padding:4px 8px;border-radius:6px;background:#e9f7f1;color:#237465;border:1px solid #d9eae2}.deep-notice{background:#f1f8f4;border-color:#cfe3da}.source-note{line-height:1.7}.tab{border:1px solid #e2eee8}.tab:hover{background:#e5f4ed}.featured-card,.list-article,.insight-card,.deep-report{overflow-wrap:anywhere}
'''
s=s.replace('</style>',extra+'</style>')
p.write_text(s,encoding='utf-8')
