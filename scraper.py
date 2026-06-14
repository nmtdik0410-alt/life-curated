#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
scraper.py  —  LIFE CURATED フィード更新スクリプト
12媒体からインテリア・建築・カフェ・イベント・ガジェット・カルチャー記事を収集し、
life_curated_feed.csv をスクリプトと同じディレクトリに保存する。
GitHub Actions / ローカル両対応。
"""

import subprocess
import sys
import os

def install_packages():
    required = ['requests', 'beautifulsoup4', 'feedparser', 'lxml']
    for pkg in required:
        import_name = pkg.replace('-', '_')
        try:
            __import__(import_name)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])

install_packages()

import time
import csv
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import feedparser

# ─── 設定 ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV   = os.path.join(BASE_DIR, 'life_curated_feed.csv')
ERROR_LOG    = os.path.join(BASE_DIR, 'life_curated_errors.txt')
MAX_ARTICLES = 5
DELAY        = 2  # 秒

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
}

# ─── 媒体定義 ─────────────────────────────────────────────────────────────────
MEDIA_LIST = [
    {
        'category': 'インテリア',
        'source':   'Casa BRUTUS Web',
        'base_url': 'https://casabrutus.com',
        'rss_urls': [
            'https://casabrutus.com/feed/',
            'https://casabrutus.com/feed',
            'https://casabrutus.com/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'インテリア',
        'source':   'Elle Decor Japan',
        'base_url': 'https://www.elle.com/jp/decor/',
        'rss_urls': [
            'https://www.elle.com/jp/decor/feed/',
            'https://www.elle.com/jp/decor/rss/',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(article|item|card|post)'},
        ],
    },
    {
        'category': '建築',
        'source':   'AXIS Web',
        'base_url': 'https://www.axismag.jp',
        'rss_urls': [
            'https://www.axismag.jp/feed/',
            'https://www.axismag.jp/feed',
            'https://www.axismag.jp/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|entry|article|item)'},
        ],
    },
    {
        'category': 'カフェ・スポット',
        'source':   'Hanako Web',
        'base_url': 'https://hanako.tokyo',
        'rss_urls': [
            'https://hanako.tokyo/feed/',
            'https://hanako.tokyo/feed',
            'https://hanako.tokyo/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card)'},
        ],
    },
    {
        'category': 'カフェ・スポット',
        'source':   '&Premium Web',
        'base_url': 'https://www.machikado-creative.jp',
        'rss_urls': [
            'https://www.machikado-creative.jp/feed/',
            'https://www.machikado-creative.jp/feed',
            'https://www.machikado-creative.jp/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|entry|article|item|card)'},
        ],
    },
    {
        'category': 'イベント',
        'source':   'POPEYE Web',
        'base_url': 'https://popeyemagazine.jp',
        'rss_urls': [
            'https://popeyemagazine.jp/feed/',
            'https://popeyemagazine.jp/feed',
            'https://popeyemagazine.jp/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|entry|article|item|card)'},
        ],
    },
    {
        'category': 'イベント',
        'source':   'Time Out Tokyo',
        'base_url': 'https://www.timeout.com/tokyo',
        'rss_urls': [
            'https://www.timeout.com/tokyo/feed/',
            'https://www.timeout.com/tokyo/rss.xml',
            'https://www.timeout.com/feed/',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(article|card|tile|item|post)'},
        ],
    },
    {
        'category': 'ガジェット・プロダクト',
        'source':   'Pen Online',
        'base_url': 'https://pen-online.com',
        'rss_urls': [
            'https://pen-online.com/feed/',
            'https://pen-online.com/feed',
            'https://pen-online.com/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'ガジェット・プロダクト',
        'source':   'WIRED Japan',
        'base_url': 'https://wired.jp',
        'rss_urls': [
            'https://wired.jp/feed/',
            'https://wired.jp/feed',
            'https://wired.jp/rss/',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|story)'},
        ],
    },
    {
        'category': 'ガジェット・プロダクト',
        'source':   'ギズモード・ジャパン',
        'base_url': 'https://www.gizmodo.jp',
        'rss_urls': [
            'https://www.gizmodo.jp/index.xml',
            'https://www.gizmodo.jp/feed/',
            'https://www.gizmodo.jp/feed',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|js-post)'},
        ],
    },
    {
        'category': 'カルチャー・アート',
        'source':   'BRUTUS.jp',
        'base_url': 'https://brutus.jp',
        'rss_urls': [
            'https://brutus.jp/feed/',
            'https://brutus.jp/feed',
            'https://brutus.jp/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'カルチャー・アート',
        'source':   '美術手帖',
        'base_url': 'https://bijutsutecho.com',
        'rss_urls': [
            'https://bijutsutecho.com/feed/',
            'https://bijutsutecho.com/feed',
            'https://bijutsutecho.com/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|news)'},
        ],
    },
]


# ─── ユーティリティ ───────────────────────────────────────────────────────────

def clean_text(text, max_len=200):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]


def parse_date(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d')
        except Exception:
            pass
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        try:
            return datetime(*entry.updated_parsed[:6]).strftime('%Y-%m-%d')
        except Exception:
            pass
    for attr in ('published', 'updated', 'created'):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val).strftime('%Y-%m-%d')
            except Exception:
                return val[:10] if len(val) >= 10 else val
    return ''


def get_excerpt(entry):
    for attr in ('summary', 'description', 'subtitle'):
        val = getattr(entry, attr, None)
        if val:
            return clean_text(val)
    if hasattr(entry, 'content') and entry.content:
        return clean_text(entry.content[0].get('value', ''))
    return ''


def wait():
    time.sleep(DELAY)


# ─── OGP 画像取得 ────────────────────────────────────────────────────────────

def get_ogp_image(url):
    wait()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        for selector in [
            {'property': 'og:image'},
            {'name': 'twitter:image'},
            {'name': 'twitter:image:src'},
        ]:
            tag = soup.find('meta', attrs=selector)
            if tag:
                content = tag.get('content', '').strip()
                if content:
                    return content
    except Exception:
        pass
    return ''


# ─── RSS 取得 ────────────────────────────────────────────────────────────────

def fetch_via_rss(media):
    for rss_url in media.get('rss_urls', []):
        wait()
        try:
            feed = feedparser.parse(
                rss_url,
                request_headers=HEADERS,
                agent=HEADERS['User-Agent'],
            )
            if feed.bozo and not feed.entries:
                continue
            if not feed.entries:
                continue

            articles = []
            for entry in feed.entries[:MAX_ARTICLES]:
                url   = entry.get('link', '').strip()
                title = clean_text(entry.get('title', ''))
                if not url or not title:
                    continue
                articles.append({
                    'category':  media['category'],
                    'source':    media['source'],
                    'title':     title,
                    'url':       url,
                    'excerpt':   get_excerpt(entry),
                    'date':      parse_date(entry),
                    'thumbnail': '',
                })
            if articles:
                return articles, rss_url
        except Exception:
            continue
    return [], None


# ─── HTML フォールバック ───────────────────────────────────────────────────────

def fetch_via_html(media):
    wait()
    resp = requests.get(media['base_url'], headers=HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')

    seen = set()
    articles = []
    base = media['base_url']
    base_host = urlparse(base).netloc

    def looks_like_article(href):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_host:
            return False
        path = parsed.path
        if not path or path in ('/', '#'):
            return False
        if re.search(r'/(article|news|post|topics|column|feature|story|event|blog)/', path, re.I):
            return True
        if re.search(r'/\d{4,}', path):
            return True
        return len(path.strip('/').split('/')) >= 2

    containers = soup.find_all('article')
    if len(containers) < 3:
        for sel in media.get('article_selectors', []):
            tag      = sel.get('tag', 'div')
            class_re = sel.get('class_re', r'(post|article|item|card|entry)')
            pattern  = re.compile(class_re, re.I) if class_re else None
            if pattern:
                containers += soup.find_all(tag, class_=pattern)
            else:
                containers += soup.find_all(tag)

    for container in containers:
        a_tag = container.find('a', href=True)
        if not a_tag:
            continue
        href = a_tag['href'].strip()
        full_url = urljoin(base, href)
        if full_url in seen or not looks_like_article(full_url):
            continue
        seen.add(full_url)

        heading = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
        title = (heading.get_text(strip=True) if heading
                 else a_tag.get_text(strip=True))
        title = clean_text(title)
        if not title or len(title) < 4:
            continue

        p = container.find('p')
        excerpt = clean_text(p.get_text()) if p else ''

        articles.append({
            'category':  media['category'],
            'source':    media['source'],
            'title':     title,
            'url':       full_url,
            'excerpt':   excerpt,
            'date':      '',
            'thumbnail': '',
        })
        if len(articles) >= MAX_ARTICLES:
            break

    if not articles:
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            full_url = urljoin(base, href)
            if full_url in seen or not looks_like_article(full_url):
                continue
            seen.add(full_url)
            title = clean_text(a_tag.get_text())
            if not title or len(title) < 8:
                continue
            articles.append({
                'category':  media['category'],
                'source':    media['source'],
                'title':     title,
                'url':       full_url,
                'excerpt':   '',
                'date':      '',
                'thumbnail': '',
            })
            if len(articles) >= MAX_ARTICLES:
                break

    return articles


# ─── メイン処理 ──────────────────────────────────────────────────────────────

def main():
    errors       = []
    all_articles = []

    print('=' * 60)
    print('  LIFE CURATED scraper.py  記事収集開始')
    print(f'  対象: {len(MEDIA_LIST)} 媒体 / 各最大 {MAX_ARTICLES} 記事')
    print(f'  出力: {OUTPUT_CSV}')
    print('=' * 60)

    for media in MEDIA_LIST:
        source = media['source']
        print(f'\n[{source}] ({media["category"]}) 取得中...')

        articles = []
        method   = ''

        try:
            articles, used_rss = fetch_via_rss(media)
            if articles:
                method = f'RSS: {used_rss}'
                print(f'  RSS 成功 ({len(articles)} 件)')
            else:
                print('  RSS 失敗 → HTML スクレイピング')
                articles = fetch_via_html(media)
                method   = 'HTML scraping'
                if articles:
                    print(f'  HTML 成功 ({len(articles)} 件)')
                else:
                    raise ValueError('記事が 1 件も取得できませんでした')

        except Exception as e:
            msg = f'[{source}] {method or "取得"} エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)
            continue

        print('  OGP 画像取得中...')
        for article in articles:
            if article['url']:
                article['thumbnail'] = get_ogp_image(article['url'])
                status = '✓' if article['thumbnail'] else '–'
                print(f'    [{status}] {article["title"][:45]}')
            all_articles.append(article)

    fieldnames = ['category', 'source', 'title', 'url', 'excerpt', 'date', 'thumbnail']
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_articles)

    print('\n' + '=' * 60)
    print(f'  完了: {len(all_articles)} 件 → {OUTPUT_CSV}')

    if errors:
        with open(ERROR_LOG, 'w', encoding='utf-8') as f:
            f.write(f'LIFE CURATED エラーログ\n')
            f.write(f'実行日時: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write('=' * 60 + '\n')
            for err in errors:
                f.write(err + '\n')
        print(f'  エラー: {len(errors)} 件 → {ERROR_LOG}')
    else:
        print('  エラーなし')

    print('=' * 60)
    return all_articles


if __name__ == '__main__':
    main()
