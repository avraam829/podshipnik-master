#!/bin/bash
# Скрипт для обновления Django-приложения после git pull.
# Запускать от имени пользователя, который может выполнять sudo,
# так как перезапуск systemd сервиса требует прав администратора.

set -e # Выход, если любая команда завершится с ошибкой

echo ">>> [START] Запуск скрипта обновления приложения..."

echo ">>> [1/4] Активация виртуального окружения..."
# Активация не обязательна, если мы указываем полные пути, но это хорошая практика
source .venv/bin/activate

echo ">>> [2/4] Установка/обновление зависимостей Python..."
pip install -r requirements.txt

echo ">>> [3/4] Выполнение команд Django (миграции и сбор статики)..."
python manage.py migrate --noinput
python manage.py collectstatic --noinput

echo ">>> [4/4] Перезапуск Gunicorn для применения изменений в коде..."
sudo systemctl restart gunicorn

deactivate
echo ">>> [COMPLETE] Обновление завершено!"
