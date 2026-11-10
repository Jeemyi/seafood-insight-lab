import sys,unittest
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seafood_data import _pct,_jsonstat_values,_choose_salmon_codes,_series_feature
from seafood_ai import _supported,_validate_main,_validate_data
from build import classify,impact_fields,parse_feed,issues_from_articles,demo_data,feed_to_articles,CATS

class SeafoodTests(unittest.TestCase):
 def test_categories(self):
  self.assertEqual(len(CATS),10)
  self.assertEqual(classify('광어 산지 가격 상승','')[0],'원물 수급/시세')
  self.assertEqual(classify('미국 국채시장 상승','')[0],None)
 def test_impact(self):
  channels,impact,follow=impact_fields('코스트코 수산물 납품 확대','코스트코')
  self.assertIn('코스트코',channels)
  self.assertIn('행사',follow)
 def test_sanitize_source(self):
  xml=b'<rss><channel><item><title>\xed\x95\x9c\xea\xb5\xad \xec\x97\xb0\xec\x96\xb4 \xeb\x89\xb4\xec\x8a\xa4</title><link>https://example.com/seafood</link><pubDate>Mon, 09 Nov 2026 10:00:00 GMT</pubDate><description>\xec\x97\xb0\xec\x96\xb4 \xea\xb0\x80\xea\xb2\xa9 \xec\x83\x81\xec\x8a\xb9</description></item></channel></rss>'
  self.assertEqual(len(parse_feed(xml)),1)
 def test_pct(self):
  self.assertAlmostEqual(_pct(100,90),-10)
 def test_ssb_dimensions(self):
  metadata={'id':['Product','ContentsCode','Tid'],'dimension':{
    'Product':{'label':'Commodity group','category':{'index':{'01':0,'02':1},'label':{'01':'Fresh or chilled salmon','02':'Frozen salmon'}}},
    'ContentsCode':{'label':'Contents','category':{'index':{'Q':0,'P':1},'label':{'Q':'Weight (tonnes)','P':'Price per kg (NOK)'}}},
    'Tid':{'label':'Week','category':{'index':{'2026U43':0,'2026U44':1},'label':{'2026U43':'2026U43','2026U44':'2026U44'}}}}}
  self.assertEqual(_choose_salmon_codes(metadata),{'Product':'01','ContentsCode':'P','Tid':'top(190)'})
  payload={'id':['Product','ContentsCode','Tid'],'size':[1,1,2],
    'dimension':{'Tid':metadata['dimension']['Tid']},'value':[76.04,74.98]}
  self.assertEqual(_jsonstat_values(payload)[(2026,44)],74.98)
 def test_actual_three_year(self):
  now=date(2026,11,10)
  d={date(2026,11,9):1300,date(2026,11,2):1320,date(2025,11,9):1250,date(2024,11,9):1240,date(2023,11,9):1200}
  f=_series_feature('fx_usd','USD 환율','환율',d,'원/USD','https://example.com','ECOS',now,'비용/거시',['마트'],'환율 상승')
  self.assertTrue(any('3년' in x['label'] for x in f['facts']))
  d.pop(date(2023,11,9))
  f=_series_feature('fx_usd','USD 환율','환율',d,'원/USD','https://example.com','ECOS',now,'비용/거시',['마트'],'환율 상승')
  self.assertFalse(any('3년' in x['label'] for x in f['facts']))
 def test_numeric_guard(self):
  self.assertTrue(_supported('가격 74.98 NOK/kg, 2026년 44주','관측 가격 74.98 NOK/kg 2026년 44주'))
  self.assertFalse(_supported('가격 89.99 NOK/kg','가격 74.98 NOK/kg'))
 def test_demo_public_data_only(self):
  data=demo_data()
  self.assertTrue(data['demo'])
  self.assertEqual(data['deep_reports'][0]['feature_ids'],['salmon_export_price'])
  self.assertEqual(data['articles'][0]['source'],'노르웨이 통계청 SSB')
 def test_issue_requires_multiple_publishers(self):
  a=demo_data()['articles'][0].copy()
  a2=a.copy();a2['id']='two';a2['source']='노르웨이 통계청 SSB';a2['score']=12
  self.assertEqual(issues_from_articles([a,a2]),[])
 def test_news_filter(self):
  self.assertIsNone(classify('미국 나스닥 지수 상승','경제 증권')[0])

if __name__=='__main__':unittest.main()

class FlowTests(unittest.TestCase):
 def test_collect_without_network_avoids_fake_data(self):
  from unittest.mock import patch
  import build
  fake=lambda src:(src,[], 'blocked feed')
  with patch.object(build,'fetch_feed',side_effect=fake), patch.object(build,'make_features',return_value=([],['SSB: unavailable'])), patch.object(build,'analyze',return_value=([],'근거 부족')), patch.object(build,'analyze_data',return_value=([],'공식 시계열 부족')):
   data=build.collect()
  self.assertEqual(data['articles'],[])
  self.assertEqual(data['deep_reports'],[])
  self.assertFalse(data['demo'])
  self.assertEqual(data['sources_ok'],0)
  self.assertEqual(len(data['errors']),len(build.SOURCES))
 def test_json_safe_script_injection(self):
  from unittest.mock import patch
  import build
  example=build.demo_data()
  example['articles'][0]['title']='break </script><script>alert(1)</script>'
  with patch.object(build,'SITE',Path('/tmp/seafood-site-test')):
   build.SITE.mkdir(exist_ok=True)
   build.publish(example)
   s=(build.SITE/'index.html').read_text(encoding='utf-8')
  self.assertNotIn('break </script><script>',s)
  self.assertIn('<\\/script>',s)
