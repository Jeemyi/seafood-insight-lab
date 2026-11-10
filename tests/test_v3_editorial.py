import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build import balanced_article_pool, CATS
from seafood_ai import _main_context,MAIN_PROMPT

class EditorialTests(unittest.TestCase):
    def test_diversity_candidates_without_forced_reports(self):
        cats=list(CATS)
        articles=[]
        # Salmon-heavy pool should not hide non-salmon stories from AI.
        for i in range(35):
            cat=cats[0] if i<28 else cats[(i-28)+1]
            articles.append(dict(id=str(i),score=100-i,timestamp=100-i,category=cat,
                                 source='agency'+str(i%2),summary='공식 시장 관련 기사 요약'*6,
                                 title='기사 '+str(i),published='2026-11-10'))
        pool=balanced_article_pool(articles,20)
        self.assertGreaterEqual(len({a['category'] for a in pool}),8)
        ctx=_main_context(articles,[],datetime.now(timezone.utc),[])
        self.assertGreaterEqual(len({a['category'] for a in ctx['articles']}),8)
    def test_plain_ui_labels(self):
        txt=(Path(__file__).resolve().parents[1]/'template.html').read_text(encoding='utf-8')
        self.assertIn('주요 시장 분석',txt)
        self.assertIn('가격·수급 동향',txt)
        self.assertIn('id="demoTopics" hidden',txt)
        self.assertNotIn('기억할 한 문장',txt)
        self.assertNotIn('중간 확신',txt)
        self.assertIn('자세히 읽기',txt)
    def test_editorial_direction(self):
        self.assertIn('한국 경제지',MAIN_PROMPT)
        self.assertIn('특정 수산물을 우대하지 않는다',MAIN_PROMPT)

if __name__=='__main__':unittest.main()
