# SBA — каталог и заявки на подшипники

Django 5.2 LTS, Python 3.12, SQLite, серверные шаблоны, локальный Bootstrap CSS, WhiteNoise и Gunicorn. Каталог загружается **из Excel через админку**. Цены сравниваются численно по возрастанию; 9999 означает «Наличие уточняйте». Заказ — заявка на согласование наличия и условий.

## Запуск в Ubuntu / WSL через Docker

Из корня репозитория `podshipnik-master`:

```sh
cp -n .env.example .env
sh scripts/docker_check.sh
```

Скрипт собирает образ, запускает сайт, ждёт healthcheck, выполняет тесты, проверку миграций и HTTP/статики. Сайт: http://localhost:8000. Нужен работающий Docker Engine с Compose и доступом к Docker Hub/PyPI при первой сборке. Если порт занят, задайте `WEB_PORT` и соответствующий `PRIMARY_DOMAIN` в `.env`.

```sh
docker compose exec web python manage.py createsuperuser
docker compose logs --tail=100 web
docker compose stop
```

При первом запуске создаётся пустая БД в именованном volume; загрузите каталог в админке. Локальная `db.sqlite3` автоматически не подключается. Копирование существующей базы, production, обновление и backup описаны в **[единой инструкции deployment](docs/DEPLOYMENT.md)**. Старые systemd/nginx-скрипты и дублирующие руководства удалены.

## Разработка без Docker

```sh
python3 -m venv .venv-wsl
.venv-wsl/bin/python -m pip install -r requirements-dev.txt
cp -n .env.example .env
.venv-wsl/bin/python manage.py migrate
.venv-wsl/bin/python manage.py runserver 127.0.0.1:8000
```

Windows `.venv` не используется из Ubuntu. Проверки: `python manage.py test`, `python manage.py makemigrations --check --dry-run`. Browser-проверки находятся в `scripts/`; результаты — `docs/evidence/`. Приватная БД, Excel, секреты и окружения исключены из Git и Docker image.

- [Excel: формат, проверка и обновление](docs/IMPORT.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Домены и DNS](docs/DOMAIN_SETUP.md)
- [SEO](docs/SEO.md)
- [Первичный аудит](docs/AUDIT.md)
- [Журнал и состояние работ](docs/WORKLOG.md)

Telegram-бот в `tg_bot/` — отдельный необязательный процесс; веб-контейнер его не запускает. Production/DNS автоматически не изменяются.
