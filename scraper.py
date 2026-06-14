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
    required = [
        ('requests',      'requests'),
        ('beautifulsoup4','bs4'),
        ('feedparser',    'feedparser'),
        ('lxml',          'lxml'),
        ('python-dotenv', 'dotenv'),
    ]
    for pkg, import_name in required:
        try:
            __import__(import_name)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])

install_packages()

from dotenv import load_dotenv
load_dotenv()   # .env があれば環境変数に読み込む（ローカル開発用）

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
    'Accept-Language': 'ja,ja-JP;q=0.9,en;q=0.3',
}

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

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
        'base_url': 'https://www.timeout.com/tokyo/ja/',
        'rss_urls': [],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(article|card|tile|item|post)'},
        ],
        'require_japanese': True,
    },
    {
        'category': 'ガジェット・プロダクト',
        'source':   'GetNavi Web',
        'base_url': 'https://getnavi.jp',
        'rss_urls': [
            'https://getnavi.jp/gadgets/feed/',
            'https://getnavi.jp/feed/',
            'https://getnavi.jp/feed',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'インテリア',
        'source':   'Casa BRUTUS Design',
        'base_url': 'https://casabrutus.com',
        'rss_urls': [
            'https://casabrutus.com/category/design/feed/',
            'https://casabrutus.com/feed/?cat=design',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
        'url_path_filter': '/categories/design',
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

# ─── YouTube チャンネル定義 ──────────────────────────────────────────────────
MAX_YT_VIDEOS = 5

YOUTUBE_CHANNELS = [
    {'handle': '@Actuskikaku',        'name': 'ACTUS'},
    {'handle': '@CONNECT-Design',     'name': 'CONNECT北欧'},
    {'handle': '@TOKYOROOMS',         'name': 'TOKYOROOMS'},
    {'handle': '@c.uragawa',          'name': 'クリエイティブの裏側'},
    {'handle': '@hyggescape',         'name': 'HYGGESCAPE'},
    {'handle': '@y_interior',         'name': 'ゆっくりインテリア(カジマグ)'},
    {'handle': '@McGuffin2017',       'name': 'McGuffin'},
    {'handle': '@HOUYHNHNM_OFFICIAL', 'name': 'HOUYHNHNM'},
    {'handle': '@itm_project',        'name': 'IN THE MAKING'},
    {'handle': '@kiokutekisansaku',   'name': 'キオク的サンサク'},
    {'handle': '@GQJapan',            'name': 'GQ JAPAN'},
    {'handle': '@ellejapan',          'name': 'ELLE Japan'},
]


# ─── ユーティリティ ───────────────────────────────────────────────────────────

JAPANESE_RE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')


def has_japanese_chars(title):
    """タイトルに、ひらがな・カタカナ・漢字が1文字以上含まれるか判定する。"""
    return bool(title and JAPANESE_RE.search(title))


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


def normalize_url(url):
    """URL内のデフォルトポート表記など、CSV上で不要な揺れを整える。"""
    return url.replace(':443/', '/')


def get_meta_content(soup, selectors):
    for selector in selectors:
        tag = soup.find('meta', attrs=selector)
        if tag:
            content = tag.get('content', '').strip()
            if content:
                return content
    return ''


def normalize_date(value):
    if not value:
        return ''
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except Exception:
        pass
    try:
        return parsedate_to_datetime(value).strftime('%Y-%m-%d')
    except Exception:
        return value[:10] if len(value) >= 10 else value


# ─── カテゴリ自動分類 ─────────────────────────────────────────────────────────
KEYWORD_RULES_PY = [
    ('art',      ['美術', 'アート', 'ギャラリー', '個展', '美術館', 'アーティスト', '展覧会', '写真集', 'インスタレーション', '展示']),
    ('fashion',  ['ファッション', '洋服', 'ブランド', 'コーデ', 'スタイル', 'アパレル', 'ウェア', 'コレクション', 'Tシャツ', 'シューズ', 'スニーカー', 'バッグ', '着こなし']),
    ('travel',   ['旅行', '海外', '旅先', '観光', '宿', 'ホテル宿泊', '世界', '国', '都市', '街歩き', 'ツーリスト', 'トラベル']),
    ('event',    ['フェア', 'デザインウィーク', 'サローネ', 'イベント', '開催', 'セール', '週末', 'フェスティバル', 'キャンペーン']),
    ('food',     ['カフェ', 'コーヒー', 'レストラン', 'グルメ', 'フード', 'メニュー', 'ランチ', 'ディナー', '料理', '食', 'スイーツ', 'ベーカリー', '喫茶']),
    ('product',  ['ガジェット', '掃除機', '家電', 'プロダクト', 'デバイス', 'スマート', 'アプリ', 'テック', 'AI', '新モデル', '発売', 'ギア', '道具', '車', 'ベンツ', 'メルセデス', '自動車', 'バイク', '自転車', '傘', '雨具', '子供', 'キッズ']),
    ('culture',  ['カルチャー', '映画', '音楽', '書籍', '出版', '写真', '文化', 'マンガ', 'ゲーム', 'ポップ', '作品', '読書', '宇宙', 'テレビ', '放送', 'デジタル', 'テクノロジー']),
    ('interior', ['インテリア', '家具', '雑貨', 'チェア', 'ソファ', 'テーブル', '照明', 'ルームツアー', '部屋', '収納', '空間', '建築', 'リノベーション', '建物', '住宅', '設計', '建築家', 'パビリオン', '邸宅', 'ハウス', 'デザイン']),
]


def classify_category(title, excerpt=''):
    """タイトルと説明文からカテゴリを推定する（index.html の KEYWORD_RULES と同一ルール）。"""
    text = (title or '') + ' ' + (excerpt or '')
    for cat, keywords in KEYWORD_RULES_PY:
        for kw in keywords:
            if kw in text:
                return cat
    return 'interior'


# ─── OGP 画像取得 ────────────────────────────────────────────────────────────

def get_ogp_image(url):
    wait()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        return get_meta_content(soup, [
            {'property': 'og:image'},
            {'name': 'twitter:image'},
            {'name': 'twitter:image:src'},
        ])
    except Exception:
        pass
    return ''


# ─── YouTube 動画取得 ─────────────────────────────────────────────────────────

def fetch_youtube_channel(channel):
    """YouTube Data API v3 でチャンネルの最新動画を取得する。"""
    handle = channel['handle']
    name   = channel['name']

    # チャンネルのアップロード再生リストIDを取得
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/channels',
        params={
            'part':      'contentDetails',
            'forHandle': handle,
            'key':       YOUTUBE_API_KEY,
        },
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get('items', [])
    if not items:
        raise ValueError(f'チャンネルが見つかりません: {handle}')
    uploads_id = items[0]['contentDetails']['relatedPlaylists']['uploads']

    wait()

    # アップロード再生リストから最新動画を取得
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/playlistItems',
        params={
            'part':       'snippet',
            'playlistId': uploads_id,
            'maxResults': MAX_YT_VIDEOS,
            'key':        YOUTUBE_API_KEY,
        },
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()

    articles = []
    for item in resp.json().get('items', []):
        snippet  = item['snippet']
        video_id = snippet.get('resourceId', {}).get('videoId', '')
        if not video_id:
            continue

        title    = snippet.get('title', '').strip()
        desc_raw = snippet.get('description', '')
        excerpt  = desc_raw[:100].replace('\n', ' ').strip()
        pub_date = snippet.get('publishedAt', '')[:10]   # YYYY-MM-DD

        thumbs = snippet.get('thumbnails', {})
        thumb  = (
            thumbs.get('maxres') or
            thumbs.get('high')   or
            thumbs.get('medium') or
            thumbs.get('default') or {}
        ).get('url', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg')

        articles.append({
            'category':    classify_category(title, excerpt),
            'source':      name,
            'source_type': 'YouTube',
            'title':       title,
            'url':         f'https://www.youtube.com/watch?v={video_id}',
            'excerpt':     excerpt,
            'date':        pub_date,
            'thumbnail':   thumb,
        })

    return articles


# ─── RSS 取得 ────────────────────────────────────────────────────────────────

def fetch_via_rss(media):
    for rss_url in media.get('rss_urls', []):
        wait()
        try:
            # feedparser 自身の HTTP リクエストはタイムアウト不可のため
            # requests で先にフェッチしてバイト列を渡す
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
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
                if media.get('require_japanese') and not has_japanese_chars(title):
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
        except Exception as e:
            print(f'    RSS スキップ ({rss_url[:50]}): {e}')
            continue
    return [], None


# ─── HTML フォールバック ───────────────────────────────────────────────────────

def fetch_via_html(media):

    page_urls = media.get('start_urls') or [media['base_url']]
    seen = set()
    articles = []
    base = media['base_url']
    base_host = urlparse(base).netloc

    for page_url in page_urls:
        page_articles = fetch_html_page(media, page_url, base_host, seen)
        articles.extend(page_articles)
        if len(articles) >= MAX_ARTICLES:
            break
    return articles[:MAX_ARTICLES]


def fetch_html_page(media, page_url, base_host, seen):
    wait()
    resp = requests.get(page_url, headers=HEADERS, timeout=15, allow_redirects=True)
    resp.raise_for_status()
    effective_page_url = resp.url
    # resp.content（バイト列）を渡すことで BeautifulSoup が
    # <meta charset> を参照して正しいエンコーディングを自動判定する
    soup = BeautifulSoup(resp.content, 'lxml')

    articles = []

    def normalize_host(host):
        return host.lower().removeprefix('www.')

    allowed_hosts = {
        normalize_host(base_host),
        normalize_host(urlparse(effective_page_url).netloc),
    }

    url_path_filter = media.get('url_path_filter', '')

    def looks_like_article(href):
        parsed = urlparse(href)
        if parsed.netloc and normalize_host(parsed.netloc) not in allowed_hosts:
            return False
        path = parsed.path
        if not path or path in ('/', '#'):
            return False
        if url_path_filter and url_path_filter not in path:
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
        full_url = urljoin(effective_page_url, href)
        if full_url in seen or not looks_like_article(full_url):
            continue
        seen.add(full_url)

        heading = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
        title = (heading.get_text(strip=True) if heading
                 else a_tag.get_text(strip=True))
        title = clean_text(title)
        if not title or len(title) < 4:
            continue
        if media.get('require_japanese') and not has_japanese_chars(title):
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
            full_url = urljoin(effective_page_url, href)
            if full_url in seen or not looks_like_article(full_url):
                continue
            seen.add(full_url)
            title = clean_text(a_tag.get_text())
            if not title or len(title) < 8:
                continue
            if media.get('require_japanese') and not has_japanese_chars(title):
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

MAX_STORED  = 1000   # CSVに保持する最大記事数
FIELDNAMES  = ['category', 'source', 'source_type', 'title', 'url', 'excerpt', 'date', 'thumbnail']


def load_existing_csv():
    """既存CSVを読み込んでリストで返す。ファイルがなければ空リストを返す。"""
    if not os.path.exists(OUTPUT_CSV):
        return []
    articles = []
    try:
        with open(OUTPUT_CSV, newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                articles.append(dict(row))
    except Exception as e:
        print(f'  ⚠ 既存CSV読み込みエラー: {e}')
    return articles


def main():
    errors      = []
    new_fetched = []

    print('=' * 60)
    print('  LIFE CURATED scraper.py  記事収集開始')
    print(f'  対象: {len(MEDIA_LIST)} 媒体 / 各最大 {MAX_ARTICLES} 記事')
    print(f'  出力: {OUTPUT_CSV}')
    print('=' * 60)

    # ── 既存CSV読み込み ───────────────────────────────────────────
    existing   = load_existing_csv()
    exist_urls = {a['url'] for a in existing}
    print(f'\n既存件数: {len(existing)} 件')

    # ── 各媒体から新着取得 ────────────────────────────────────────
    for media in MEDIA_LIST:
        source = media['source']
        print(f'\n[{source}] ({media["category"]}) 取得中...')

        try:
            articles = []
            method   = ''

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

            # require_japanese フラグが立っている媒体は日本語タイトル以外を除外
            if media.get('require_japanese'):
                before   = len(articles)
                articles = [a for a in articles if has_japanese_chars(a['title'])]
                dropped  = before - len(articles)
                if dropped:
                    print(f'  日本語タイトル以外を除外: {dropped} 件 → 残 {len(articles)} 件')

            print('  OGP 画像取得中...')
            for article in articles:
                try:
                    if article['url'] and not article.get('thumbnail'):
                        article['thumbnail'] = get_ogp_image(article['url'])
                except Exception:
                    article['thumbnail'] = ''
                status = '✓' if article.get('thumbnail') else '–'
                print(f'    [{status}] {article["title"][:45]}')
                new_fetched.append(article)

        except Exception as e:
            msg = f'[{source}] {method or "取得"} エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ── YouTube 動画取得 ──────────────────────────────────────────
    print(f'\n{"─" * 60}')
    print(f'  YouTube 動画取得（{len(YOUTUBE_CHANNELS)} チャンネル / 各最大 {MAX_YT_VIDEOS} 本）')
    print(f'{"─" * 60}')

    for channel in YOUTUBE_CHANNELS:
        name = channel['name']
        print(f'\n[{name}] ({channel["handle"]}) 取得中...')
        try:
            videos = fetch_youtube_channel(channel)
            print(f'  取得: {len(videos)} 件')
            for v in videos:
                print(f'    - [{v["category"]}] {v["title"][:50]}')
            new_fetched.extend(videos)
        except Exception as e:
            msg = f'[YouTube/{name}] エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ── 重複排除・マージ・ソート・上限カット ───────────────────────
    added   = 0
    skipped = 0
    for article in new_fetched:
        url = article.get('url', '')
        if not url or url in exist_urls:
            skipped += 1
            continue
        existing.append(article)
        exist_urls.add(url)
        added += 1

    # 日付の新しい順にソート（日付なし記事は末尾）
    existing.sort(key=lambda a: a.get('date') or '', reverse=True)

    # 上限超えを古い方から削除
    trimmed = 0
    if len(existing) > MAX_STORED:
        trimmed   = len(existing) - MAX_STORED
        existing  = existing[:MAX_STORED]

    # ── CSV書き出し ───────────────────────────────────────────────
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore', restval='')
        writer.writeheader()
        writer.writerows(existing)

    # ── サマリー ─────────────────────────────────────────────────
    print('\n' + '=' * 60)
    print(f'  新規追加:     {added} 件')
    print(f'  重複スキップ: {skipped} 件')
    if trimmed:
        print(f'  上限超え削除: {trimmed} 件（上限 {MAX_STORED} 件）')
    print(f'  合計件数:     {len(existing)} 件 → {OUTPUT_CSV}')

    if errors:
        with open(ERROR_LOG, 'w', encoding='utf-8') as f:
            f.write('LIFE CURATED エラーログ\n')
            f.write(f'実行日時: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write('=' * 60 + '\n')
            for err in errors:
                f.write(err + '\n')
        print(f'  エラー: {len(errors)} 件 → {ERROR_LOG}')
    else:
        print('  エラーなし')

    print('=' * 60)
    return existing


if __name__ == '__main__':
    main()
