# Единое развёртывание: Docker Compose

Все команды выполняются из корня Git-репозитория `podshipnik-master`. Рабочая папка над ним — только контейнер проекта. Единственный набор конфигурации: `Dockerfile`, `compose.yaml`, `.env.example`, `deploy/Caddyfile`. `deploy/` содержит только конфигурацию HTTPS-прокси; это не второй deployment. Старые `deploy.sh`, `update.sh`, `DEPLOYMENT_GUIDE.md` и устаревший `PROJECT_SUMMARY.md` удалены; история доступна в Git.

## Локально: Ubuntu / WSL

```sh
cd /mnt/c/Users/Veronika/Documents/Artem/sitepodsahipnikv2/podshipnik-master
docker version
docker compose version
cp -n .env.example .env
sh scripts/docker_check.sh
```

Открыть http://localhost:8000. Для другого порта согласованно задайте `WEB_PORT=8080` и `PRIMARY_DOMAIN=localhost:8080`. Локальный `.env`: `DJANGO_DEBUG=True`, `TRUST_PROXY=False`. Web публикуется только на loopback. Секрет для development необязателен; production без секрета не стартует.

Повторная проверка: `sh scripts/docker_check.sh`. Тесты используют отдельную тестовую БД. Скрипт не сбрасывает volume и не перезаписывает `.env`. Скрипт предназначен для локального debug env; проверку production выполняйте через настроенный HTTPS-прокси.

## Каталог и существующая база

Обычный путь: `docker compose exec web python manage.py createsuperuser`, затем Excel-импорт в `/admin/catalog/product/`. Формат и ограничения — [IMPORT.md](IMPORT.md).

Для **первого** заполнения пустого volume копией локальной `db.sqlite3`, до запуска web:

```sh
docker compose build web
docker compose run --rm --no-deps \
  -v "$PWD/db.sqlite3:/source/db.sqlite3:ro" \
  web python scripts/backup_database.py /source/db.sqlite3 /data/db.sqlite3
docker compose up -d --wait web
```

Скрипт использует SQLite online backup и проверяет integrity. Исходник открыт read-only; существующий файл назначения не перезаписывается. Если контейнер уже создал БД, обновляйте каталог через импорт; не удаляйте volume ради этой команды.

## Production с HTTPS

Подготовьте сервер с Docker/Compose, DNS A/AAAA на его IP и входящие 80/443. В `.env`:

```dotenv
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<случайный секрет не короче 50 символов>
PRIMARY_DOMAIN=<основной домен без схемы и пути>
ADDITIONAL_DOMAINS=<алиасы через запятую>
SITE_DOMAINS=<основной домен и все алиасы через запятую>
TRUST_PROXY=True
WEB_PORT=8000
```

Секрет можно получить командой `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`. Сохраните его только в `.env`/менеджере секретов. Caddy получает сертификаты и передаёт запросы Gunicorn; Django перенаправляет алиасы на основной домен. Не открывайте Gunicorn внешнему интернету. `TRUST_PROXY=True` допустим только за доверенным прокси.

```sh
docker compose --profile production up -d --build --wait
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py createsuperuser
docker compose logs --tail=100 web proxy
```

Образ собирает manifest/compressed статику заранее; WhiteNoise обслуживает её без отдельного nginx. Процесс web — UID 10001. SQLite хранится в volume `database`, сертификаты — `caddy_data`. Healthcheck проверяет доступность БД. Миграции применяются при старте. Это конфигурация для одного экземпляра web; масштабирование требует пересмотра БД и миграций.

## Обновление, backup и восстановление

Перед обновлением работающей БД:

```sh
docker compose exec web python scripts/backup_database.py /data/db.sqlite3 /data/backup-before-update.sqlite3
mkdir -p backups
docker compose cp web:/data/backup-before-update.sqlite3 backups/backup-before-update.sqlite3
docker compose --profile production up -d --build --wait
```

Каждый backup должен иметь новое имя: существующий не перезаписывается. Храните копию вне хоста. Восстановление сначала проверяйте на отдельном Compose project/volume. Для rollback остановите web, сохраните текущую БД, восстановите согласованную пару прежнего образа/кода и backup. Не заменяйте открытую SQLite простым копированием. Не запускайте `docker compose down -v`: команда удаляет данные.

## Проверки и границы

- `scripts/docker_check.sh`: build, healthy startup, Django tests, отсутствие недостающих миграций, реальные HTTP и CSS через Gunicorn.
- `scripts/browser_check.py`: каталог, цены, клавиатура и пять размеров экрана.
- `scripts/seo_check.py --all`: страницы/301/metadata всех товаров и sitemap.
- `scripts/migration_check.py db.sqlite3 --roundtrip`: проверка обратимости старой миграции каталога на отдельной копии.
- `python -m pip_audit -r requirements.txt`: аудит закреплённых зависимостей при доступном сервисе уязвимостей.

`check --deploy` оставляет предупреждения HSTS include_subdomains/preload: их не включаем без проверки всех поддоменов. Поисковый limiter пока действует внутри одного процесса; для публичной нагрузки нужен общий limiter на edge/Redis. Запуск и проверки на локальном Docker не подтверждают внешние DNS/сертификаты или состояние production-сервера.

Проверка production-настроек в приватном контейнере, без выпуска сертификатов: `sh scripts/docker_production_check.sh` после локального запуска. Проверяет manifest CSS и HTTP с заголовками доверенного HTTPS-прокси; внешний TLS это не проверяет.

Проверка полного Excel roundtrip: `docker compose exec -T web python scripts/import_roundtrip_check.py /data/db.sqlite3`. Создаёт временную копию SQLite, выгружает товары, импортирует выгрузку, сравнивает идентичность, содержимое, цены и остатки. Рабочая база открывается только для чтения.
