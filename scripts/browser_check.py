"""Browser regression + repeatable local lab measurements, not field CWV."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT=Path('docs/evidence')
OUTPUT.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel='msedge',headless=True)
    for width,height in [(1920,1080),(1440,900),(1366,768),(768,1024),(390,844)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.add_init_script("""window.lab={lcp:0,cls:0};new PerformanceObserver(l=>{for(const e of l.getEntries())window.lab.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.lab.cls+=e.value}).observe({type:'layout-shift',buffered:true});""")
        for name,url in [('home','/'),('catalog','/catalog/'),('search','/search/?q=7212')]:
            response=page.goto('http://127.0.0.1:8000'+url,wait_until='networkidle')
            assert response.status==200,(name,response.status)
            assert page.locator('h1').count()==1
            overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow,(name,width,'overflow')
            page.screenshot(path=str(OUTPUT/f'final-{name}-{width}.png'),full_page=True)
            results.append({'page':name,'width':width,**page.evaluate('({...window.lab, duration:performance.getEntriesByType("navigation")[0].duration,resources:performance.getEntriesByType("resource").length})')})
        links=page.locator('.designation')
        assert links.count()>0
        labels=links.all_text_contents()
        assert '7212BEP SKF' in labels[0],labels[:3]
        url=links.first.get_attribute('href')
        links.first.click()
        page.wait_for_load_state('networkidle')
        assert '/podshipniki/' in page.url
        assert '7212' in page.locator('h1').inner_text()
        assert page.locator('link[rel=canonical]').count()==1
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(OUTPUT/f'final-product-{width}.png'),full_page=True)
        results.append({'page':'product','width':width,**page.evaluate('window.lab')})
        page.get_by_role('link',name='Вернуться в каталог').click()
        assert '/catalog/' in page.url
        page.locator('#search-input').fill('7212')
        page.get_by_role('button',name='Найти',exact=True).click()
        page.wait_for_load_state('networkidle')
        assert page.locator('.designation').count()>0
        assert not errors,errors
        page.close()
    browser.close()
OUTPUT.joinpath('browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 5 viewports, home/catalog/search/product, navigation, numeric price order, no overflow or JS errors.')
