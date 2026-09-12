# SEO
Товары имеют серверные страницы /podshipniki/<saved-slug>/; slug содержит исходное обозначение в URL-форме и устойчивый код. Старый /product/<id>/ возвращает HTTP 301 сразу на сохранённый адрес. Несуществующий товар и недопустимая страница каталога возвращают 404.

Title/H1/description используют реальные designation/brand/price. Оригинальное обозначение в контенте не нормализуется. Один canonical; OpenGraph URL использует SITE_URL. Product JSON-LD сериализуется с экранированием <; отзывы/ratings/availability не выдуманы. Offer сознательно не добавлен: заказ требует подтверждения менеджера и наличие условное.

sitemap.xml — индекс, товары разбиты по 5000 URL; sitemap-pages.xml содержит главную, каталог, контакты. Поиск, filters, users/cart/API имеют noindex. Crawlable пагинация ?page=N. Manufacturer filter выводит только реальные значения manufacturer; Excel владельца содержит пустую колонку, поэтому выдуманные бренды/SEO-страницы не создаются.

Для проверки:
```sh
python manage.py test catalog
python scripts/browser_check.py
```
JSON-LD проверяется JSON-парсером и соответствием видимому обозначению; внешние Google Rich Results/Schema Validator требуют отдельной проверки опубликованного HTTPS URL. Автоматические тесты не равны подтверждению индексации Google/Яндекс.

После публикации: проверить canonical/301/404, отправить sitemap в Search Console и Яндекс Вебмастер, проверить индексируемость на реальных product URL. Первые места и упоминания LLM не гарантируются. llms.txt не заменяет серверный HTML и полезные страницы.
