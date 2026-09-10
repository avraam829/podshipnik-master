# Руководство по развертыванию Django проекта на Ubuntu

Это руководство поможет вам развернуть ваш Django проект (`bearings_shop`) на сервере под управлением Ubuntu с использованием Gunicorn в качестве WSGI-сервера и Nginx в качестве обратного прокси-сервера. Предполагается, что у вас уже есть домен с настроенными DNS-записями, указывающими на IP-адрес вашего сервера Ubuntu.

## 1. Подготовка сервера

### 1.1. Обновление системы
Подключитесь к вашему серверу по SSH и обновите список пакетов:
```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2. Создание нового пользователя (рекомендуется)
Не рекомендуется запускать приложения под пользователем `root`. Создайте нового пользователя (например, `webuser`):
```bash
sudo adduser webuser
sudo usermod -aG sudo webuser
```
Выйдите из текущей сессии SSH и войдите снова под новым пользователем `webuser`.

### 1.3. Установка необходимых пакетов
Установите Python, pip, virtualenv, Nginx и Gunicorn:
```bash
sudo apt install python3 python3-pip python3-venv nginx -y
```

## 2. Развертывание кода проекта

### 2.1. Клонирование репозитория
Перейдите в домашний каталог пользователя и клонируйте ваш Git-репозиторий. Замените `[ВАШ_РЕПОЗИТОРИЙ_GIT]` на URL вашего репозитория.
```bash
cd ~
git clone [ВАШ_РЕПОЗИТОРИЙ_GIT] bearings_shop
```

### 2.2. Настройка виртуального окружения
Перейдите в каталог проекта и создайте виртуальное окружение:
```bash
cd bearings_shop
python3 -m venv .venv
```
Активируйте виртуальное окружение:
```bash
source .venv/bin/activate
```

### 2.3. Установка зависимостей
Установите все зависимости проекта из `requirements.txt`:
```bash
pip install -r requirements.txt
```
После установки деактивируйте виртуальное окружение:
```bash
deactivate
```

### 2.4. Сбор статических файлов и миграции
Вернитесь в каталог проекта и соберите статические файлы. Убедитесь, что `STATIC_ROOT` настроен в `config/settings.py`.
```bash
cd ~/bearings_shop
source .venv/bin/activate
python manage.py collectstatic --noinput
python manage.py makemigrations # Если есть новые миграции
python manage.py migrate
deactivate
```
**Важно:** Убедитесь, что в `config/settings.py` установлен `DEBUG = False` для продакшн-среды и правильно настроен `ALLOWED_HOSTS` для вашего домена.

## 3. Настройка базы данных (PostgreSQL рекомендуется)

Для продакшн-среды рекомендуется использовать PostgreSQL. Если вы используете SQLite (как в вашем проекте), убедитесь, что файл `db.sqlite3` находится в безопасном месте и имеет правильные права доступа.

### 3.1. Установка PostgreSQL (если вы переходите с SQLite)
```bash
sudo apt install postgresql postgresql-contrib -y
```
Создайте нового пользователя базы данных и базу данных для вашего проекта:
```bash
sudo -u postgres psql
CREATE DATABASE bearings_shop;
CREATE USER bearings_user WITH PASSWORD 'вашнадежныйпароль';
GRANT ALL PRIVILEGES ON DATABASE bearings_shop TO bearings_user;
\q
```
Затем обновите настройки базы данных в `config/settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'bearings_shop',
        'USER': 'bearings_user',
        'PASSWORD': 'вашнадежныйпароль',
        'HOST': 'localhost',
        'PORT': '',
    }
}
```
После изменения `settings.py`, не забудьте снова выполнить `python manage.py migrate`.

## 4. Настройка Gunicorn

### 4.1. Тестирование Gunicorn
Перейдите в каталог проекта и запустите Gunicorn для теста:
```bash
cd ~/bearings_shop
source .venv/bin/activate
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```
Если Gunicorn запустился без ошибок, вы можете проверить его, открыв в браузере `http://ВАШ_IP_АДРЕС_СЕРВЕРА:8000`. Нажмите `Ctrl+C`, чтобы остановить Gunicorn.

### 4.2. Создание сервиса Systemd для Gunicorn
Создайте файл сервиса Systemd для Gunicorn:
```bash
sudo nano /etc/systemd/system/gunicorn.service
```
Вставьте следующее содержимое, заменив `webuser` на имя вашего пользователя, `/home/webuser/bearings_shop` на путь к вашему проекту и `[ВАШ_ДОМЕН]` на ваш домен:
```ini
[Unit]
Description=Gunicorn daemon for Django project
After=network.target

[Service]
User=webuser
Group=www-data
WorkingDirectory=/home/webuser/bearings_shop
ExecStart=/home/webuser/bearings_shop/.venv/bin/gunicorn --workers 3 --bind unix:/run/gunicorn.sock config.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
```
Сохраните и закройте файл (`Ctrl+X`, `Y`, `Enter`).

Запустите и активируйте сервис Gunicorn:
```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```
Проверьте статус сервиса:
```bash
sudo systemctl status gunicorn
```
Если есть ошибки, проверьте логи:
```bash
sudo journalctl -u gunicorn --since "10 minutes ago"
```

## 5. Настройка Nginx

### 5.1. Создание конфигурации Nginx
Создайте файл конфигурации Nginx для вашего домена:
```bash
sudo nano /etc/nginx/sites-available/[ВАШ_ДОМЕН]
```
Вставьте следующее содержимое, заменив `[ВАШ_ДОМЕН]` на ваш домен и `webuser` на имя вашего пользователя:
```nginx
server {
    listen 80;
    server_name [ВАШ_ДОМЕН] www.[ВАШ_ДОМЕН];

    location = /favicon.ico { access_log off; log_not_found off; }
    location /static/ {
        root /home/webuser/bearings_shop; # Путь к вашему проекту
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}
```
Сохраните и закройте файл.

### 5.2. Активация конфигурации
Создайте символическую ссылку на файл конфигурации в `sites-enabled`:
```bash
sudo ln -s /etc/nginx/sites-available/[ВАШ_ДОМЕН] /etc/nginx/sites-enabled/
```
Удалите дефолтную конфигурацию Nginx:
```bash
sudo rm /etc/nginx/sites-enabled/default
```
Проверьте конфигурацию Nginx на наличие синтаксических ошибок:
```bash
sudo nginx -t
```
Перезапустите Nginx, чтобы применить изменения:
```bash
sudo systemctl restart nginx
```

## 6. Настройка переменных окружения

Для хранения чувствительных данных, таких как `SECRET_KEY` и `TG_BOT_TOKEN`, используйте переменные окружения. Вы можете задать их в файле `/etc/systemd/system/gunicorn.service` в секции `[Service]` с помощью `Environment` или `EnvironmentFile`.

Пример с `Environment`:
```ini
[Service]
# ...
Environment="DJANGO_SECRET_KEY=ВАШ_СЕКРЕТНЫЙ_КЛЮЧ"
Environment="TG_BOT_TOKEN=ВАШ_ТОКЕН_БОТА"
# ...
```
После изменения файла сервиса Gunicorn, не забудьте перезагрузить конфигурацию Systemd и перезапустить Gunicorn:
```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

## 7. Устранение неполадок

-   **Nginx 502 Bad Gateway:** Проверьте, запущен ли Gunicorn (`sudo systemctl status gunicorn`) и правильно ли указан путь к сокету в конфигурации Nginx и Gunicorn.
-   **Nginx 403 Forbidden:** Проверьте права доступа к каталогу `static/` и файлам проекта. Пользователь Nginx (обычно `www-data`) должен иметь к ним доступ.
-   **Django Internal Server Error:** Проверьте логи Gunicorn и Django. Логи Gunicorn можно посмотреть через `sudo journalctl -u gunicorn`. Логи Django можно настроить в `config/settings.py`.
-   **Сброс настроек:** Если вы застряли, попробуйте удалить файл конфигурации Nginx (`sudo rm /etc/nginx/sites-enabled/[ВАШ_ДОМЕН]`) и сервис Gunicorn (`sudo rm /etc/systemd/system/gunicorn.service`), а затем начать заново.

Удачи с развертыванием!
