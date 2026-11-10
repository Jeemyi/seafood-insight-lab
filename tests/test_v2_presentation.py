import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build import demo_data

class PresentationTests(unittest.TestCase):
    def test_compact_brief_replaces_hero(self):
        t=(Path(__file__).resolve().parents[1]/'template.html').read_text(encoding='utf-8')
        self.assertNotIn('<section class="hero"',t)
        self.assertIn('id="dailyBrief"',t)
        self.assertIn('id="brief-heading"',t)
        self.assertIn("$('#briefLead').textContent=topReport?topReport.thesis",t)
        self.assertIn('id="allNews"',t)
        self.assertNotIn('핵심 인사이트',t)
    def test_demo_has_two_publicly_linked_sources(self):
        d=demo_data()
        self.assertTrue(d['demo'])
        self.assertEqual(d['articles'][0]['source'],'노르웨이 통계청 SSB')
        self.assertEqual(len({a['source'] for a in d['articles']}),2)
        self.assertEqual(set(d['deep_reports'][0]['article_ids']),set(a['id'] for a in d['articles']))

if __name__=='__main__':unittest.main()
