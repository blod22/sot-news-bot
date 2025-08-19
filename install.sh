#!/usr/bin/env bash
set -euo pipefail

# Параметры
APP_DIR="/opt/sot-news-bot"
ETC_DIR="/etc/sot-news-bot"
VAR_LOG="/var/log/sot-news-bot"
VAR_LIB="/var/lib/sot-news-bot"
UNIT="/etc/systemd/system/sot-news-bot.service"

# Пользователь
id -u sotbot &>/dev/null || sudo useradd -r -s /usr/sbin/nologin sotbot

# Папки
sudo mkdir -p "$APP_DIR" "$ETC_DIR" "$VAR_LOG" "$VAR_LIB"
sudo chown -R sotbot:sotbot "$APP_DIR" "$ETC_DIR" "$VAR_LOG" "$VAR_LIB"

# Виртуальное окружение и зависимости
sudo apt-get update -y
sudo apt-get install -y python3-venv
sudo python3 -m venv "$APP_DIR/venv"
sudo "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/venv/bin/pip" install requests beautifulsoup4

# Копируем файлы
sudo cp sot_news_bot.py "$APP_DIR/"
sudo cp sot-news-bot.service "$UNIT"
sudo cp bot.env.example "$ETC_DIR/bot.env"
sudo chown -R sotbot:sotbot "$APP_DIR" "$ETC_DIR"
sudo chmod 600 "$ETC_DIR/bot.env"
sudo chmod +x "$APP_DIR/sot_news_bot.py"

# Запуск
sudo systemctl daemon-reload
sudo systemctl enable --now sot-news-bot.service

echo "Готово. Отредактируйте конфиг: sudo nano $ETC_DIR/bot.env"
echo "Статус: systemctl status sot-news-bot.service --no-pager"
