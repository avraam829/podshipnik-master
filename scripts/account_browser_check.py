"""Real-browser local account/checkout journey. Creates one uniquely named QA account."""
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright

base = os.getenv('BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
output = Path('docs/evidence')
output.mkdir(exist_ok=True, parents=True)
username = 'qa_' + uuid4().hex[:12]
password = secrets.token_urlsafe(24)
checks = []
errors = []
with sync_playwright() as playwright:
    options = {'headless': True}
    channel = os.getenv('BROWSER_CHANNEL', 'msedge' if os.name == 'nt' else '')
    if channel:
        options['channel'] = channel
    browser = playwright.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.on('pageerror', lambda error: errors.append(str(error)))
    axe = Path('.npm-cache/axe.min.js')
    if axe.exists():
        page.route('**/static/qa-axe.js', lambda route: route.fulfill(path=str(axe), content_type='application/javascript'))

    def inspect(name):
        page.wait_for_load_state('networkidle')
        if axe.exists():
            page.add_script_tag(url=base + '/static/qa-axe.js')
            violations = page.evaluate("async () => (await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v => ({id:v.id,impact:v.impact}))")
            assert not violations, (name, violations)
        for width, height in ((1440, 900), (768, 1024), (390, 844)):
            page.set_viewport_size({'width': width, 'height': height})
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (name, width)
            assert page.locator('h1').count() == 1
            page.screenshot(path=str(output / f'account-{name}-{width}.png'), full_page=True)
            checks.append({'page': name, 'width': width, 'overflow': False})
        page.set_viewport_size({'width': 1440, 'height': 900})

    page.goto(base + '/users/login/')
    inspect('login')
    page.goto(base + '/users/register/')
    inspect('register')
    page.locator('[name=username]').fill(username)
    page.locator('[name=email]').fill(username + '@example.test')
    page.locator('[name=password1]').fill(password)
    page.locator('[name=password2]').fill(password)
    page.get_by_role('button', name='Создать аккаунт', exact=True).click()
    page.wait_for_url('**/users/account/')
    inspect('account-empty')
    page.get_by_role('button', name='Выйти', exact=True).click()
    page.goto(base + '/users/login/?next=/users/account/')
    page.locator('[name=username]').fill(username)
    page.locator('[name=password]').fill(password)
    page.get_by_role('button', name='Войти', exact=True).click()
    page.wait_for_url('**/users/account/')
    page.goto(base + '/search/?q=7212')
    page.locator('.designation').first.click()
    page.locator('[name=quantity]').fill('2')
    page.locator('form[action*="/cart/add/"] button').click()
    page.goto(base + '/cart/')
    inspect('cart')
    page.goto(base + '/cart/checkout/')
    inspect('checkout')
    page.locator('[name=contact_name]').fill('Проверка интерфейса')
    page.locator('[name=email]').fill(username + '@example.test')
    page.locator('[name=comment]').fill('Локальная автоматическая проверка. Не обрабатывать.')
    page.get_by_role('button', name='Отправить заявку', exact=True).click()
    page.wait_for_url('**/confirmation/')
    inspect('confirmation')
    page.goto(base + '/users/account/')
    inspect('account-orders')
    assert page.locator('.order-card').count() == 1
    assert not errors, errors
    browser.close()
output.joinpath('account-browser-results.json').write_text(
    json.dumps({'qa_username': username, 'checks': checks, 'js_errors': errors}, ensure_ascii=False, indent=2),
    encoding='utf-8',
)
print('PASS: registration, logout/login, account, cart, checkout and order history at three viewports.')
