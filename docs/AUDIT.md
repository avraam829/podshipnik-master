# Первоначальный аудит, 2026-09-10

Аудит исходников выполнен до изменений функциональности. Передана распакованная папка без .git. Python 3.12.6, Node 22.19.0; requirements фиксирует Django 5.0.6, openpyxl 3.1.5, python-telegram-bot 22.6, Gunicorn без версии. Frontend: Django templates, Bootstrap 5.3.3 CDN, Google Fonts, собственный CSS 25 395 байт. Сборщика frontend нет.

## Архитектура

Browser → Django templates/views → Django ORM → SQLite.
Excel → admin import → Product/Price/Stock; JSON → management command → те же модели.
Telegram bot → ORM → отдельные TelegramOrder. Сайт: session cart → Order/OrderItem.

Product содержит уникальный code, designation, manufacturer, description, weight, length/width/height, category и price. Price отдельно хранит retail/wholesale. Stock связан со складом, amount/reserved/free. Валютного поля нет, интерфейс выводит рубли. Семейство товара не моделируется. Пользователи, админка и CSRF существуют; изображения продукции отсутствуют. Кеширование приложения отсутствует. Поиск icontains по маркировке, бренду и описанию; 24 товара на страницу. URL товара /product/<id>/. Deployment: shell → systemd/Gunicorn/nginx, домены gpz5.ru и www.gpz5.ru; состояние сервера не проверено.

## Исходный запуск и baseline

- Обычный check/test/migrate на Windows падает files.E001: FILE_UPLOAD_TEMP_DIR=/tmp не существует.
- После временного переопределения только в процессе на tempfile.gettempdir(): check и миграции проходят, найдено 0 тестов.
- Исходный сервер запущен на 127.0.0.1:8000; screenshots главной desktop/mobile: docs/evidence/baseline-home-*.png.
- Производственная БД изначально не передана в проект. Позже владелец указал D:/podshipnik: Excel «03.03 НА САЙТ.xlsx», 18 438 строк, и отдельную SQLite с 15 950 товарами. Источники читаются без изменения.
- Excel: все 18 438 code пустые, все manufacturer пустые, все amount=9999; 11 413 положительных розничных цен; 1 857 повторов designation после strip. Повторы не означают тождество товара.
- 7212BEP SKF: 6800; 7212-B-XL-MP-UA FAG: 7124. Бренды находятся в designation, оригинальные строки нельзя незаметно переписывать.
- Полноценные CWV и screenshots каталога/товара пока не измерены. Нельзя представлять отсутствие измерения как нулевое значение.

## Проблемы

| Уровень | Проблема и место | Последствие | Исправление | Риск |
|---|---|---|---|---|
| CRITICAL | admin._process_import_row: при пустом code всегда create | Повтор Excel дублирует весь каталог | Стабильная идентификация, dry-run, транзакции, отказ на неоднозначности | Нельзя склеивать разные товары |
| HIGH | config/settings.py: известный fallback SECRET_KEY | Небезопасная production-конфигурация | Обязательный секрет вне debug | Настроить env перед запуском |
| HIGH | base.html innerHTML + сырые designation/manufacturer из suggestions | Stored XSS через импорт | DOM textContent, JSON без HTML | Проверить подсказки |
| HIGH | admin custom URLs проверяют staff, но не model permissions | Staff без прав может импортировать/удалять | Проверка add/change/delete | Проверить роли |
| HIGH | cart quantity int без валидации, remove/logout GET, referer redirect | 500, отрицательные количества, CSRF/open redirect | Формы/POST/безопасный redirect | Обновить шаблоны |
| HIGH | cart.__iter__ мутирует session объектами ORM и Decimal | Ошибка JSON session при отображении корзины | Отдельные копии элементов | Тесты корзины |
| HIGH | order_create без transaction и с session price | Частичный заказ и устаревшая цена | Атомарность, текущие цены | Согласовать поведение цены по запросу |
| HIGH | Product.price и Price расходятся при JSON import | Неверные цены каталога и корзины | Единая политика розничной цены | Не менять оптовые цены |
| HIGH | amount вместо free; Excel везде 9999 | Недостоверное наличие | Уточнить смысл 9999 у владельца | Не придумывать stock |
| HIGH | Нет canonical/sitemap/robots/JSON-LD | Слабая индексируемость, дубли доменов | Постоянные URL, 301, SEO | Проверка всех старых URL |
| MEDIUM | Поиск без нормализации; sorting designation | Варианты пробелов/дефисов не находятся | Отдельный поисковый ключ и проверенная сортировка | Не объединять товары |
| MEDIUM | Счётчики категорий не учитывают всех потомков | Несогласованность каталога | Единая иерархия | Циклы категорий |
| MEDIUM | /tmp hardcoded; uploads 100/200 MB расходятся | Windows не запускается; ресурсоёмкий импорт | Portable temp и ограничение xlsx | Проверить большой файл |
| MEDIUM | Нет тестов, CI; gunicorn без pin; Django старой ветки | Регрессии, невоспроизводимость | Аудит зависимостей и совместимое обновление | Не делать слепой major upgrade |
| MEDIUM | Подсказки не отменяют устаревшие ответы, inputs без label | Race и недоступность | AbortController, label, клавиатура | E2E |
| LOW | Demo Oil, фиктивный переключатель EN/USD, marquee | Непоследовательный бренд и отвлечение | SBA и единые tokens | Сохранить полезный контент |

SQL: ORM параметризует пользовательский поиск; явной SQL injection не найдено. Raw delete использует константы, но имена products_* не совпадают с catalog_*. Командного выполнения входа пользователя, SSRF и public debug API не найдено в просмотренных web routes. CORS не нужен same-origin приложению. Полная проверка зависимостей и production headers ещё предстоит.

## Коммерческие заявления владельца

Сохранять предоставленный текст. «Альтернативные решения уровня SKF», «без потери надежности», квалификация инженеров, базовая гарантия 12 месяцев и расширенная 36 месяцев требуют подтверждения владельцем и соответствующих договорных условий. Не подменять их выдуманными доказательствами. Старое «10 000+ позиций на складе» не подтверждено количеством 9999 в Excel.
