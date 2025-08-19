#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import json
import html
import signal
import sqlite3
import logging
import requests
from urllib.parse import urljoin, urlparse
from logging.handlers import RotatingFileHandler
from bs4 import BeautifulSoup

DEFAULT_NEWS_URL = "https://www.seaofthieves.com/ru/news"

class GracefulKiller:
    stop = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
    def exit_gracefully(self, *_):
        self.stop = True

def setup_logging(log_file: str, level: str = "INFO"):
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(lvl)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

def ensure_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def is_new(conn, url: str) -> bool:
    cur = conn.execute("SELECT 1 FROM posted WHERE url = ?", (url,))
    return cur.fetchone() is None

def mark_posted(conn, url: str, title: str):
    conn.execute("INSERT OR IGNORE INTO posted (url, title) VALUES (?,?)", (url, title))
    conn.commit()

def fetch(url: str, timeout: int, user_agent: str) -> str:
    headers = {
        "User-Agent": user_agent or "Mozilla/5.0 (compatible; SOTNewsBot/1.0; +https://discord.com/)"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text

def parse_news_list(html_text: str, base_url: str):
    """
    Ищем карточки новостей на /ru/news.
    На сайте бывает разная вёрстка, поэтому делаем парсинг «с запасом»:
    - любые <a> со ссылкой вида /ru/news/...
    - вытягиваем заголовок из <a> либо родительских элементов
    """
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    seen = set()

    # 1) try typical cards
    for a in soup.select('a[href^="/ru/news/"], a[href*="/ru/news/"]'):
        href = a.get("href")
        if not href:
            continue
        # игнорируем якоря и повторные
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if not re.search(r"/ru/news/", parsed.path):
            continue
        if full in seen:
            continue

        # заголовок
        title = a.get_text(strip=True)
        if not title:
            # пытаемся вытащить из соседних тегов
            parent = a.find_parent()
            if parent:
                h = parent.find(["h1", "h2", "h3"])
                if h and h.get_text(strip=True):
                    title = h.get_text(strip=True)

        if not title:
            # ещё попытка глубже
            h = a.find(["h1", "h2", "h3"])
            if h and h.get_text(strip=True):
                title = h.get_text(strip=True)

        # убираем совсем короткие/мусорные заголовки
        if title and len(title) < 3:
            title = None

        # dedupe и сбор
        seen.add(full)
        items.append({"url": full, "title": title or full})

    return items

def discord_post(webhook_url: str, title: str, url: str, username: str, timeout: int):
    payload = {
        "username": username or "Sea of Thieves News",
        "embeds": [{
            "title": title,
            "url": url,
            "description": "Новая публикация на официальном сайте.",
        }]
    }
    r = requests.post(webhook_url, json=payload, timeout=timeout)
    # обработка rate limit
    if r.status_code == 429:
        try:
            retry_after = r.json().get("retry_after", 5)
        except Exception:
            retry_after = 5
        logging.warning("Discord rate limited. Sleeping for %ss", retry_after)
        time.sleep(float(retry_after))
        r = requests.post(webhook_url, json=payload, timeout=timeout)
    r.raise_for_status()

def load_config(path: str) -> dict:
    cfg = {
        "NEWS_URL": DEFAULT_NEWS_URL,
        "DISCORD_WEBHOOK_URL": "",
        "CHECK_INTERVAL_SECONDS": "900",
        "REQUEST_TIMEOUT_SECONDS": "15",
        "USER_AGENT": "",
        "STATE_DB_PATH": "/var/lib/sot-news-bot/state.db",
        "LOG_FILE": "/var/log/sot-news-bot/bot.log",
        "LOG_LEVEL": "INFO",
        "POST_ONLY_FIRST_N": "8",
        "BOT_NAME": "Sea of Thieves Новости"
    }
    if not path or not os.path.exists(path):
        return cfg

    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in cfg.keys():
            if k in data and data[k] is not None:
                cfg[k] = str(data[k])
        return cfg

    # .env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in cfg:
                cfg[k] = v
    return cfg

def main():
    config_path = os.environ.get("SOT_BOT_CONFIG", "bot.env")
    cfg = load_config(config_path)

    # Логи
    os.makedirs(os.path.dirname(cfg["LOG_FILE"]), exist_ok=True)
    setup_logging(cfg["LOG_FILE"], cfg.get("LOG_LEVEL", "INFO"))

    # Проверки
    webhook = cfg["DISCORD_WEBHOOK_URL"].strip()
    if not webhook:
        logging.error("DISCORD_WEBHOOK_URL не задан в конфиге. Завершаюсь.")
        sys.exit(1)

    news_url = cfg.get("NEWS_URL", DEFAULT_NEWS_URL).strip() or DEFAULT_NEWS_URL
    interval = int(cfg.get("CHECK_INTERVAL_SECONDS", "900"))
    req_timeout = int(cfg.get("REQUEST_TIMEOUT_SECONDS", "15"))
    user_agent = cfg.get("USER_AGENT", "")
    bot_name = cfg.get("BOT_NAME", "Sea of Thieves Новости")

    # DB
    os.makedirs(os.path.dirname(cfg["STATE_DB_PATH"]), exist_ok=True)
    conn = ensure_db(cfg["STATE_DB_PATH"])

    killer = GracefulKiller()
    first_run_limit = int(cfg.get("POST_ONLY_FIRST_N", "8"))

    logging.info("Запущен SOT News Bot. Источник: %s, интервал: %ss", news_url, interval)

    first_cycle = True

    while not killer.stop:
        try:
            html_text = fetch(news_url, timeout=req_timeout, user_agent=user_agent)
            items = parse_news_list(html_text, base_url=news_url)

            # Собираем новые
            to_post = []
            for item in items:
                if is_new(conn, item["url"]):
                    to_post.append(item)

            if to_post:
                logging.info("Найдено новых публикаций: %d", len(to_post))

                if first_cycle and first_run_limit > 0:
                    to_post = to_post[:first_run_limit]

                # Постим от старых к новым
                for item in reversed(to_post):
                    title = html.unescape(item["title"]).strip()
                    url = item["url"]
                    try:
                        discord_post(webhook, title=title, url=url, username=bot_name, timeout=req_timeout)
                        mark_posted(conn, url, title)
                        logging.info("Опубликовано: %s", url)
                        time.sleep(1.2)
                    except Exception as e:
                        logging.exception("Ошибка публикации '%s': %s", url, e)
            else:
                logging.debug("Новых публикаций нет.")

            first_cycle = False

        except requests.HTTPError as e:
            logging.error("HTTP %s при запросе %s: %s", getattr(e.response, "status_code", "?"), news_url, e)
        except Exception as e:
            logging.exception("Неожиданная ошибка цикла: %s", e)

        # сон цикла
        for _ in range(interval):
            if killer.stop:
                break
            time.sleep(1)

    logging.info("Останавливаюсь по сигналу. До встречи.")

if __name__ == "__main__":
    main()
