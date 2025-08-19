# SOT News Bot (RU) → Discord

Демон для Ubuntu: парсит русскую страницу новостей Sea of Thieves (`/ru/news`) и публикует новые статьи в Discord через webhook.

## Возможности
- Парсит карточки новостей без RSS (устойчивые селекторы).
- Постит в Discord embed с заголовком и ссылкой.
- Хранит состояние в SQLite, чтобы не дублировать публикации.
- Логирование с ротацией (RotatingFileHandler).
- Корректное завершение по SIGTERM/SIGINT (systemd-friendly).
- Ограничение количества публикаций при первом запуске (антиспам).

## Быстрый старт (Ubuntu 20.04+/22.04+/24.04+)
1. Скачайте и распакуйте архив, перейдите в папку проекта.
2. Установите (создаст пользователя `sotbot`, venv, unit, конфиг):
   ```bash
   sudo ./install.sh
   ```
3. Отредактируйте конфиг:
   ```bash
   sudo nano /etc/sot-news-bot/bot.env
   ```
   Установите реальный `DISCORD_WEBHOOK_URL`.
4. Проверьте статус:
   ```bash
   systemctl status sot-news-bot.service --no-pager
   journalctl -u sot-news-bot.service -n 100 --no-pager
   ```

## Ручная установка (без install.sh)
```bash
# Пользователь и каталоги
sudo useradd -r -s /usr/sbin/nologin sotbot || true
sudo mkdir -p /opt/sot-news-bot /var/log/sot-news-bot /var/lib/sot-news-bot /etc/sot-news-bot
sudo chown -R sotbot:sotbot /opt/sot-news-bot /var/log/sot-news-bot /var/lib/sot-news-bot /etc/sot-news-bot

# venv и зависимости
sudo apt-get update -y
sudo apt-get install -y python3-venv
python3 -m venv /opt/sot-news-bot/venv
/opt/sot-news-bot/venv/bin/pip install --upgrade pip
/opt/sot-news-bot/venv/bin/pip install requests beautifulsoup4

# файлы
sudo cp sot_news_bot.py /opt/sot-news-bot/
sudo cp bot.env.example /etc/sot-news-bot/bot.env
sudo cp sot-news-bot.service /etc/systemd/system/sot-news-bot.service
sudo chown -R sotbot:sotbot /opt/sot-news-bot /etc/sot-news-bot
sudo chmod 600 /etc/sot-news-bot/bot.env
sudo chmod +x /opt/sot-news-bot/sot_news_bot.py

# запуск
sudo systemctl daemon-reload
sudo systemctl enable --now sot-news-bot.service
```

## Конфигурация (`/etc/sot-news-bot/bot.env`)
```ini
NEWS_URL=https://www.seaofthieves.com/ru/news
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXX/YYY
CHECK_INTERVAL_SECONDS=900
REQUEST_TIMEOUT_SECONDS=15
USER_AGENT=SOTNewsBot/1.0 (+https://discord.com/)
BOT_NAME=Sea of Thieves Новости
LOG_FILE=/var/log/sot-news-bot/bot.log
LOG_LEVEL=INFO
STATE_DB_PATH=/var/lib/sot-news-bot/state.db
POST_ONLY_FIRST_N=8
```

### Важные заметки
- **DISCORD_WEBHOOK_URL** — обязателен.
- При первом запуске бот найдёт много публикаций; ограничение `POST_ONLY_FIRST_N` поможет не заспамить канал.
- База `state.db` хранит только список уже опубликованных ссылок.
- Логи пишутся в `/var/log/sot-news-bot/bot.log` и ротируются.

## Эксплуатация
```bash
sudo systemctl status sot-news-bot.service --no-pager
sudo journalctl -u sot-news-bot.service -n 100 --no-pager
sudo systemctl restart sot-news-bot.service
sudo systemctl stop sot-news-bot.service
```

## Обновление
```bash
sudo systemctl stop sot-news-bot.service
sudo cp sot_news_bot.py /opt/sot-news-bot/
sudo systemctl start sot-news-bot.service
```

## Траблшутинг
- **В логах HTTP 403/404** — сайт мог временно меняться; подождите цикл или увеличьте таймаут.
- **Пусто/ничего не парсится** — в редких случаях изменилась вёрстка. Увеличьте интервал и дайте знать — можно добавить альтернативные селекторы.
- **429 в Discord** — бот сам подождёт `retry_after` и повторит отправку.
- **Нет записей в SQLite** — проверьте права на `/var/lib/sot-news-bot/`, пользователя `sotbot` и путь `STATE_DB_PATH`.

## Безопасность
- Конфиг хранит webhook — держите файл `/etc/sot-news-bot/bot.env` с правами `600` и владельцем `sotbot`.
- Логи не содержат webhook; при отладке не публикуйте его в открытых местах.

## Лицензия
MIT
