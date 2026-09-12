import json
from pathlib import Path
from statistics import median
from playwright.sync_api import sync_playwright

output=Path('docs/evidence')
results=[]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(channel='msedge',headless=True)
    for version,port in [('baseline',8001),('final',8000)]:
        for width,height in [(1440,900),(390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height},bypass_csp=True)
            if version=='baseline':
                # Reproducible old CSS/JS even when the external CDN is unavailable.
                page.route('**/bootstrap@5.3.3/dist/css/bootstrap.min.css',lambda route: route.fulfill(path='static/vendor/bootstrap.min.css',content_type='text/css',headers={'Access-Control-Allow-Origin':'*'}))
                page.route('**/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',lambda route: route.fulfill(path='.npm-cache/bootstrap.bundle.min.js',content_type='application/javascript',headers={'Access-Control-Allow-Origin':'*'}))
                page.route('https://fonts.googleapis.com/**',lambda route: route.fulfill(body='',content_type='text/css'))
            page.add_init_script("""window.lab={lcp:0,cls:0,interactions:[]};new PerformanceObserver(l=>{for(const e of l.getEntries())window.lab.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.lab.cls+=e.value}).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(e.interactionId)window.lab.interactions.push(e.duration)}).observe({type:'event',durationThreshold:16,buffered:true});""")
            page.goto(f'http://127.0.0.1:{port}/search/?q=7212',wait_until='networkidle')
            if version=='baseline' and width==1440:
                assert page.locator('.container').first.evaluate('(e)=>getComputedStyle(e).maxWidth')=='1320px','Baseline Bootstrap did not load'
            selector='.designation' if version=='final' else '.p-card-title a'
            product_url=page.locator(selector).first.get_attribute('href')
            catalog_url='/catalog/' if version=='final' else '/category/1/'
            for name,url in [('home','/'),('catalog',catalog_url),('product',product_url)]:
                measurements=[]
                for attempt in range(3):
                    response=page.goto(f'http://127.0.0.1:{port}'+url,wait_until='networkidle')
                    assert response.status==200
                    page.locator('#search-input').click()
                    page.wait_for_timeout(100)
                    measurements.append(page.evaluate('({...window.lab,bytes:performance.getEntriesByType("resource").reduce((s,r)=>s+r.encodedBodySize,0),requests:performance.getEntriesByType("resource").length})'))
                record={'version':version,'page':name,'width':width,'lcp_median_ms':median(m['lcp'] for m in measurements),'cls_max':max(m['cls'] for m in measurements),'resource_bytes':measurements[-1]['bytes'],'requests':measurements[-1]['requests'],'interaction_events_ms':measurements[-1]['interactions']}
                if version=='final':
                    page.add_script_tag(path='.npm-cache/axe.min.js')
                    axe=page.evaluate("async () => {const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))}")
                    record['axe_violations']=axe
                else:
                    page.screenshot(path=str(output/f'baseline-reconstructed-{name}-{width}.png'),full_page=True)
                results.append(record)
            page.close()
    browser.close()
output.joinpath('quality-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
