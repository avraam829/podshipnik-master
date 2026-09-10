#!/bin/bash

# Скрипт для автоматического развертывания Django проекта с Gunicorn и Nginx
# ПРЕДУПРЕЖДЕНИЕ: Запускать с правами sudo! (например, sudo ./deploy.sh)

# --- Конфигурация ---
DOMAIN="gpz5.ru www.gpz5.ru"
PROJECT_NAME="bearings_shop"
# --- Конец Конфигурации ---

set -e # Выход, если любая команда завершится с ошибкой

echo ">>> [START] Запуск скрипта развертывания для $DOMAIN"

# --- Проверка на root права ---
if [ "$EUID" -ne 0 ]; then
  echo "!!! ОШИБКА: Пожалуйста, запустите этот скрипт с правами sudo."
  exit 1
fi

# --- Системные переменные ---
PROJECT_DIR=$(pwd) # Абсолютный путь к директории проекта
CURRENT_USER=$(logname) # Имя пользователя, от которого запущен скрипт

echo "Путь проекта: $PROJECT_DIR"
echo "Пользователь: $CURRENT_USER"

# --- Установка зависимостей ---
echo ">>> [1/9] Обновление пакетов и установка зависимостей (nginx, python3-venv)..."
apt-get update
apt-get install -y nginx python3-venv

# --- Настройка виртуального окружения Python ---
echo ">>> [2/9] Создание и настройка виртуального окружения..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate # Деактивируем, так как сервис systemd будет использовать абсолютный путь

# --- Настройка Django ---
echo ">>> [3/9] Сбор статических файлов и применение миграций..."
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py migrate --noinput

# --- Настройка прав доступа для Nginx ---
echo ">>> [4/9] Настройка прав доступа для статических файлов..."
# Убедимся, что директории существуют
mkdir -p $PROJECT_DIR/staticfiles
mkdir -p $PROJECT_DIR/media
# Устанавливаем владельца www-data на папки со статикой и медиа
chown -R www-data:www-data $PROJECT_DIR/staticfiles
chown -R www-data:www-data $PROJECT_DIR/media
# Даем права на выполнение для всех родительских директорий, чтобы nginx мог "пройти" к файлам
chmod 755 $PROJECT_DIR/staticfiles
chmod 755 $PROJECT_DIR/media
chmod o+x $PROJECT_DIR
# Если проект в /root, то нужно дать права и на /root. Будьте осторожны с этим.
if [[ "$PROJECT_DIR" == /root/* ]]; then
    chmod o+x $(dirname "$PROJECT_DIR")
fi

# --- Создание сервиса Gunicorn для systemd ---
echo ">>> [5/9] Создание systemd сервиса для Gunicorn..."

# Сначала создаем socket-файл
cat > /etc/systemd/system/gunicorn.socket << EOF
[Unit]
Description=gunicorn socket for bearings_shop

[Socket]
ListenStream=/run/gunicorn.sock

[Install]
WantedBy=sockets.target
EOF

# Затем создаем service-файл
cat > /etc/systemd/system/gunicorn.service << EOF
[Unit]
Description=gunicorn daemon for bearings_shop
Requires=gunicorn.socket
After=network.target

[Service]
User=$CURRENT_USER
Group=www-data
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --bind unix:/run/gunicorn.sock \
          config.wsgi:application

[Install]
WantedBy=multi-user.target
EOF

# --- Запуск сервиса Gunicorn ---
echo ">>> [6/9] Запуск и включение автозагрузки сервиса Gunicorn..."
systemctl daemon-reload
systemctl start gunicorn.socket
systemctl enable gunicorn.socket
echo "Статус Gunicorn Socket:"
systemctl status gunicorn.socket --no-pager

# --- Генерация самоподписанного SSL сертификата ---
echo ">>> [7/9] Создание самоподписанного SSL сертификата..."
# Создаем директорию, если она не существует
mkdir -p /etc/ssl/private
# Генерируем сертификат (неинтерактивно)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/nginx-selfsigned.key \
    -out /etc/ssl/certs/nginx-selfsigned.crt \
    -subj "/C=RU/ST=Moscow/L=Moscow/O=GPZ5/OU=IT/CN=$DOMAIN"

# --- Настройка Nginx ---
echo ">>> [8/9] Создание конфигурационного файла Nginx с HTTPS..."
cat > /etc/nginx/sites-available/$PROJECT_NAME << EOF
# Редирект с HTTP на HTTPS
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

# Основная конфигурация HTTPS
server {
    listen 443 ssl;
    server_name $DOMAIN;

    # Пути к SSL сертификатам
    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;

    access_log /var/log/nginx/${PROJECT_NAME}_access.log;
    error_log /var/log/nginx/${PROJECT_NAME}_error.log;

    location = /favicon.ico { access_log off; log_not_found off; }

    # Правильная раздача статических файлов
    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
    }
    
    # Правильная раздача медиа файлов
    location /media/ {
        alias $PROJECT_DIR/media/;
    }

    # Перенаправление запросов на Gunicorn
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}
EOF

# --- Активация сайта Nginx ---
echo ">>> [9/9] Активация сайта и перезапуск Nginx..."
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi
ln -sfn /etc/nginx/sites-available/$PROJECT_NAME /etc/nginx/sites-enabled/

# Проверка синтаксиса и перезапуск
nginx -t
systemctl restart nginx

echo ">>> [COMPLETE] Развертывание завершено!"
echo "Ваш сайт должен быть доступен по адресу https://gpz5.ru"
echo "Для проверки статуса сервисов используйте:"
echo "sudo systemctl status gunicorn.service"
echo "sudo systemctl status nginx.service"
