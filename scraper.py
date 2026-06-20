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
        ('anthropic',     'anthropic'),
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
MAX_ARTICLES          = 5   # 通常取得（最新）
MAX_ARTICLES_BACKFILL = 50  # 遡及取得
MAX_YT_VIDEOS          = 5  # YouTube通常取得
MAX_YT_VIDEOS_BACKFILL = 30 # YouTube遡及取得
DELAY                  = 2  # 秒

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

# ─── Claude API クライアント（APIキーがある場合のみ初期化） ──────────────────
ANTHROPIC_CLIENT = None
_ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
if _ANTHROPIC_KEY:
    try:
        import anthropic as _anthropic_lib
        ANTHROPIC_CLIENT = _anthropic_lib.Anthropic(api_key=_ANTHROPIC_KEY)
    except Exception:
        pass

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
    # {
    #     'category': 'ガジェット・プロダクト',
    #     'source':   'GetNavi Web',
    #     'base_url': 'https://getnavi.jp',
    #     'rss_urls': [
    #         'https://getnavi.jp/gadgets/feed/',
    #         'https://getnavi.jp/feed/',
    #         'https://getnavi.jp/feed',
    #     ],
    #     'article_selectors': [
    #         {'tag': 'article', 'class_re': r''},
    #         {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
    #     ],
    # },
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
    {
        'category': 'fashion',
        'source':   'WWD JAPAN',
        'base_url': 'https://www.wwdjapan.com',
        'rss_urls': [
            'https://www.wwdjapan.com/feed/',
            'https://www.wwdjapan.com/feed',
            'https://www.wwdjapan.com/rss.xml',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(article|post|item|card)'},
        ],
    },
    # {
    #     'category': 'product',
    #     'source':   'BLUE LUG BLOG',
    #     'base_url': 'https://bluelug.com/blog',
    #     'rss_urls': [
    #         'https://bluelug.com/blog/feed/',
    #         'https://bluelug.com/blog/feed',
    #     ],
    #     'article_selectors': [
    #         {'tag': 'article', 'class_re': r''},
    #         {'tag': 'div',     'class_re': r'(post|entry|article|item)'},
    #     ],
    # },
    {
        'category': 'カフェ・スポット',
        'source':   'カジキッサ',
        'base_url': 'https://kajikissa.com',
        'rss_urls': [
            'https://kajikissa.com/feed/',
            'https://kajikissa.com/feed',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'fashion',
        'source':   'HOUYHNHNM',
        'base_url': 'https://www.houyhnhnm.jp',
        'rss_urls': [
            'https://www.houyhnhnm.jp/feed/',
            'https://www.houyhnhnm.jp/feed',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(article|post|item|card|entry)'},
        ],
    },
    {
        'category': 'インテリア',
        'source':   'キオク的サンサク',
        'base_url': 'https://www.kiokutekisansaku.com',
        'rss_urls': [],
        'start_urls': ['https://www.kiokutekisansaku.com/post'],
        'article_selectors': [
            {'tag': 'div', 'class_re': r'(post|article|item|card|entry|blog)'},
        ],
        'url_path_filter': '/posts/',
        'title_strip_re':  r'^\d{1,2}\.\d{1,2}\.\d{4}',  # "12.19.2024" / "11.8.2024" の日付プレフィックスを除去
    },
    {
        'category': 'インテリア',
        'source':   'ROOMIE',
        'base_url': 'https://www.roomie.jp',
        'rss_urls': [
            'https://www.roomie.jp/feed/',
            'https://www.roomie.jp/feed',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'fashion',
        'source':   'BAYCREW\'S',
        'base_url': 'https://baycrews.co.jp',
        'rss_urls': [
            'https://baycrews.co.jp/feed',
            'https://baycrews.co.jp/feed/',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    {
        'category': 'fashion',
        'source':   'FUDGE',
        'base_url': 'https://fudge.jp',
        'rss_urls': [
            'https://fudge.jp/feed/',
        ],
        'article_selectors': [
            {'tag': 'article', 'class_re': r''},
            {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
        ],
    },
    # {
    #     'category': 'インテリア',
    #     'source':   'RIGNA',
    #     'base_url': 'https://rigna.co.jp',
    #     'rss_urls': [
    #         'https://rigna.co.jp/feed/',
    #         'https://rigna.co.jp/feed',
    #     ],
    #     'article_selectors': [
    #         {'tag': 'article', 'class_re': r''},
    #         {'tag': 'div',     'class_re': r'(post|article|item|card|entry)'},
    #     ],
    # },
    {
        'category': 'インテリア',
        'source':   '北欧、暮らしの道具店',
        'base_url': 'https://hokuohkurashi.com',
        'rss_urls': [],
        'start_urls': ['https://hokuohkurashi.com/note'],
        'article_selectors': [
            {'tag': 'section', 'class_re': r'articles-list'},
        ],
        'url_path_filter': '/note/',
    },
    # {
    #     'category': 'インテリア',
    #     'source':   'MAARKET',
    #     'base_url': 'https://maarket.jp',
    #     'rss_urls': [],
    #     'start_urls': ['https://maarket.jp/view/news/list'],
    #     'url_path_filter': '/view/news/2',
    #     'title_prefer_shorter': True,
    # },
    {
        'category': 'product',
        'source':   'PHILE WEB',
        'base_url': 'https://www.phileweb.com',
        'rss_urls': ['https://www.phileweb.com/rss.php'],
    },
    {
        'category': 'travel',
        'source':   'colocal',
        'base_url': 'https://colocal.jp',
        'rss_urls': ['https://colocal.jp/feed/'],
    },
    {
        'category': 'product',
        'source':   'CAMP HACK',
        'base_url': 'https://camphack.nap-camp.com',
        'rss_urls': ['https://camphack.nap-camp.com/feed/'],
    },
    {
        'category': 'fashion',
        'source':   'FULLRESS',
        'base_url': 'https://fullress.com',
        'rss_urls': ['https://fullress.com/feed/'],
    },
    {
        'category': 'fashion',
        'source':   'GQ JAPAN Web',
        'base_url': 'https://www.gqjapan.jp',
        'rss_urls': ['https://www.gqjapan.jp/rss/'],
    },
    {
        'category': 'product',
        'source':   'VAGUE',
        'base_url': 'https://vague.style',
        'rss_urls': ['https://vague.style/feed/'],
    },
    {
        'category': 'product',
        'source':   'LIFEHACKER JP',
        'base_url': 'https://www.lifehacker.jp',
        'rss_urls': ['https://www.lifehacker.jp/feed/'],
    },
    # UOMO: トップページがJS重依存のため記事取得不可、保留
    # {
    #     'category': 'fashion',
    #     'source':   'UOMO',
    #     'base_url': 'https://webuomo.jp',
    #     'rss_urls': [],
    #     'start_urls': ['https://webuomo.jp/'],
    #     'url_path_filter': '/20',
    # },
    {
        'category': 'design',
        'source':   'Pen Online',
        'base_url': 'https://www.pen-online.jp',
        'rss_urls': [],
        'start_urls': ['https://www.pen-online.jp/'],
        'url_path_filter': '/article/',
        'require_japanese': True,
        'title_strip_re': r'^(Art&Design|Lifestyle|Gourmet|Watches|Fashion|Travel|Culture|Art|Beauty|Design)\s+',
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
    ('art',      ['美術館', 'ギャラリー', '個展', '展覧会', 'アーティスト', '絵画', '彫刻', '写真展',
                  'インスタレーション', 'コレクター']),
    ('food',     ['カフェ', 'コーヒー', 'レストラン', 'グルメ', '料理', 'レシピ', 'ランチ', 'ディナー',
                  'スイーツ', 'ベーカリー', '喫茶', 'シェフ', 'ワイン', 'Bar', '食材']),
    ('travel',   ['旅行', '観光', 'ホテル', '旅館', '温泉', '旅先', '宿', '街歩き', '海外', '都市']),
    ('event',    ['イベント', 'フェア', '期間限定', 'オープン', 'ポップアップ', 'フェスティバル',
                  'マーケット', 'ワークショップ', 'デザインウィーク', 'サローネ']),
    ('design',   ['建築', 'プロダクトデザイン', '工業デザイン', 'グラフィック', 'クラフト', 'デザイナー',
                  '設計', '建物', 'アーキテクト', 'パビリオン', '構造']),
    ('interior', ['インテリア', '家具', 'ソファ', 'チェア', 'テーブル', '照明', '収納',
                  'ルームツアー', 'リノベーション', '一人暮らし', '北欧', '間取り', '模様替え',
                  'ラグ', 'カーテン', '棚', 'DIY', 'リビング', 'ダイニング']),
    ('product',  ['ガジェット', '家電', 'スマホ', 'カメラ', '乗り物', '自転車', '文具', '調理器具',
                  'アウトドア', 'テクノロジー', 'AI', 'デバイス', '新発売', 'レビュー',
                  'ギア', 'オーディオ', 'スピーカー', '時計', '車', 'バイク']),
    ('fashion',  ['ファッション', 'コーデ', '着こなし', 'ブランド', 'アパレル',
                  'スニーカー', 'シューズ', 'バッグ', 'ジュエリー', 'アクセサリー',
                  'コレクション', 'ウェア', 'Tシャツ', 'デニム']),
    ('culture',  ['映画', '音楽', '書籍', 'マンガ', 'ゲーム', 'ポッドキャスト', '写真',
                  'インタビュー', 'レコード', 'ライブ', 'カルチャー', '読書']),
]


def classify_category(title, excerpt='', source=''):
    """タイトルと説明文からカテゴリを推定する（index.html の KEYWORD_RULES と同一ルール）。"""
    text = (title or '') + ' ' + (excerpt or '')
    for cat, keywords in KEYWORD_RULES_PY:
        for kw in keywords:
            if kw in text:
                return cat
    return 'culture'


_VALID_CATS = {'interior', 'design', 'food', 'travel', 'event', 'product', 'fashion', 'culture', 'art'}

_CLAUDE_SYSTEM = """以下の記事タイトルを9つのカテゴリのいずれか1つに分類してください。
カテゴリ：interior / design / food / travel / event / product / fashion / culture / art
番号付きリストで、カテゴリ名のみ1単語で回答してください。

【カテゴリ定義】
- interior：家具・ソファ・チェア・照明・収納・ルームツアー・リノベーション・北欧インテリア・間取り・DIY・部屋づくり（家の中の空間・家具のみ）
- design：建築・プロダクトデザイン・工業デザイン・グラフィック・クラフト・デザイナー・設計・建物・都市・アーキテクチャー
- food：カフェ・コーヒー・レストラン・グルメ・料理・レシピ・食材・シェフ・ベーカリー・食全般
- travel：旅行・観光・ホテル・旅館・街歩き・旅先・宿・地域紹介・ローカル
- event：イベント・フェア・期間限定・オープン・ポップアップ・展示会・マーケット・フェスティバル
- product：ガジェット・家電・テクノロジー・AI・乗り物全般（車・バイク・自転車）・カメラ・オーディオ・時計・アウトドアギア・生活用品・日用品・科学ニュース
- fashion：衣類・スニーカー・シューズ・バッグ・ジュエリー・アクセサリー・コーデ・ブランドコレクション・アパレル全般
- culture：映画・音楽・書籍・マンガ・インタビュー・レコード・社会・動物・自然・カルチャー全般
- art：美術館・ギャラリー・個展・展覧会・アーティスト・絵画・彫刻・写真展・インスタレーション

【重要ルール】
- ガジェット・テック・科学ニュース・乗り物 → 必ずproduct
- 財布・バッグ・傘・日用品・生活用品 → product（interiorではない）
- 家庭菜園・植物単体 → product
- 衣類・スニーカー・ブランドファッション → fashion
- 動物・自然・社会現象の記事 → culture
- 建築・デザイナー・プロダクトデザイン → design（interiorではない）
- 地域・ローカル・街の紹介 → travel
- その他判断が難しいもの → culture（デフォルト）"""


def classify_with_claude_batch(articles):
    """1ソース分の記事をClaude APIでまとめて分類。失敗時はNoneを返す。"""
    if not ANTHROPIC_CLIENT or not articles:
        return None
    prompt = '\n'.join(f'{i+1}. {a["title"]}' for i, a in enumerate(articles))
    try:
        msg = ANTHROPIC_CLIENT.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=50,
            system=_CLAUDE_SYSTEM,
            messages=[{'role': 'user', 'content': prompt}],
        )
        cats = []
        for line in msg.content[0].text.strip().split('\n'):
            line = re.sub(r'^\d+[\.\:\)]\s*', '', line.strip()).lower()
            cats.append(line if line in _VALID_CATS else None)
        return cats
    except Exception as e:
        print(f'    Claude API エラー: {e}')
        return None


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


# ─── YouTube ショート判定 ────────────────────────────────────────────────────

_SHORTS_WORD_RE = re.compile(r'\bshorts\b', re.IGNORECASE)   # "shorts"（単独単語）


def parse_duration_seconds(iso_duration):
    """ISO 8601 形式（PT1M30S 等）を秒数に変換する。"""
    if not iso_duration:
        return 0
    m = re.match(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not m:
        return 0
    days    = int(m.group(1) or 0)
    hours   = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def is_short_video(title, url, duration_sec):
    """ショート動画かどうかを判定する（3条件のいずれかに該当したらTrue）。"""
    title_l = title.lower()
    if '#shorts' in title_l or '#short' in title_l:  # ハッシュタグ付き
        return True
    if _SHORTS_WORD_RE.search(title):                 # "shorts" 単独単語（# なし）
        return True
    if '/shorts/' in url:                             # URL に /shorts/ を含む
        return True
    if 0 < duration_sec < 180:                        # 動画長が 3 分未満（YouTube Shorts 最大長）
        return True
    return False


# ─── YouTube 動画取得 ─────────────────────────────────────────────────────────

def fetch_youtube_channel(channel, backfill=False):
    """YouTube Data API v3 でチャンネルの最新動画を取得する（ショート除外）。"""
    handle     = channel['handle']
    name       = channel['name']
    max_videos = MAX_YT_VIDEOS_BACKFILL if backfill else MAX_YT_VIDEOS

    # ① チャンネルのアップロード再生リストIDを取得
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

    # ② ショート除外後に max_videos 件残るよう多めに取得
    fetch_count = min(max_videos * 2, 50)
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/playlistItems',
        params={
            'part':       'snippet',
            'playlistId': uploads_id,
            'maxResults': fetch_count,
            'key':        YOUTUBE_API_KEY,
        },
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    playlist_items = resp.json().get('items', [])

    # 動画IDと snippet を収集
    video_ids   = []
    snippet_map = {}
    for item in playlist_items:
        snippet  = item['snippet']
        video_id = snippet.get('resourceId', {}).get('videoId', '')
        if video_id:
            video_ids.append(video_id)
            snippet_map[video_id] = snippet

    if not video_ids:
        return []

    wait()

    # ③ videos.list で contentDetails（duration）+ snippet（thumbnails）を一括取得
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/videos',
        params={
            'part': 'contentDetails,snippet',
            'id':   ','.join(video_ids),
            'key':  YOUTUBE_API_KEY,
        },
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()

    video_info = {}   # video_id -> {'duration_sec', 'portrait', 'thumbnail'}
    for v in resp.json().get('items', []):
        vid    = v['id']
        thumbs = v.get('snippet', {}).get('thumbnails', {})

        # 縦動画判定
        portrait = False
        default_t = thumbs.get('default', {})
        w, h = default_t.get('width', 0), default_t.get('height', 0)
        if w and h and h > w:
            portrait = True
        maxres_url = thumbs.get('maxres', {}).get('url', '')
        if '-portrait' in maxres_url:
            portrait = True

        # サムネイル URL（videos.list のほうが高解像度優先）
        thumb_url = (
            thumbs.get('maxres') or
            thumbs.get('high')   or
            thumbs.get('medium') or
            thumbs.get('default') or {}
        ).get('url', f'https://img.youtube.com/vi/{vid}/hqdefault.jpg')

        video_info[vid] = {
            'duration_sec': parse_duration_seconds(
                v.get('contentDetails', {}).get('duration', '')
            ),
            'portrait':  portrait,
            'thumbnail': thumb_url,
        }

    # ④ ショート・縦動画を除外しながら記事化
    articles          = []
    skipped_shorts    = 0
    skipped_portrait  = 0
    for video_id in video_ids:
        if len(articles) >= max_videos:
            break

        info    = video_info.get(video_id, {})
        snippet = snippet_map[video_id]
        title   = snippet.get('title', '').strip()
        url     = f'https://www.youtube.com/watch?v={video_id}'

        if is_short_video(title, url, info.get('duration_sec', 0)):
            skipped_shorts += 1
            continue

        if info.get('portrait'):
            skipped_portrait += 1
            continue

        desc_raw = snippet.get('description', '')
        excerpt  = desc_raw[:100].replace('\n', ' ').strip()
        pub_date = snippet.get('publishedAt', '')[:10]

        articles.append({
            'category':    classify_category(title, excerpt, name),
            'source':      name,
            'source_type': 'YouTube',
            'title':       title,
            'url':         url,
            'excerpt':     excerpt,
            'date':        pub_date,
            'thumbnail':   info.get('thumbnail', ''),
        })

    if skipped_shorts:
        print(f'  ショート除外: {skipped_shorts} 件')
    if skipped_portrait:
        print(f'  縦動画除外:   {skipped_portrait} 件')

    return articles


# ─── RSS 取得 ────────────────────────────────────────────────────────────────

def fetch_via_rss(media, backfill=False):
    max_count = MAX_ARTICLES_BACKFILL if backfill else MAX_ARTICLES
    for rss_url in media.get('rss_urls', []):
        wait()
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if feed.bozo and not feed.entries:
                continue
            if not feed.entries:
                continue

            entries = list(reversed(feed.entries))[:max_count] if backfill else feed.entries[:max_count]
            articles = []
            for entry in entries:
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

def fetch_via_html(media, backfill=False):
    max_count = MAX_ARTICLES_BACKFILL if backfill else MAX_ARTICLES
    page_urls = media.get('start_urls') or [media['base_url']]
    seen = set()
    articles = []
    base = media['base_url']
    base_host = urlparse(base).netloc

    for page_url in page_urls:
        page_articles = fetch_html_page(media, page_url, base_host, seen, max_count)
        articles.extend(page_articles)
        if len(articles) >= max_count:
            break
    return articles[:max_count]


def fetch_html_page(media, page_url, base_host, seen, max_count=MAX_ARTICLES):
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

    url_path_filter  = media.get('url_path_filter', '')
    title_strip_re   = media.get('title_strip_re', '')

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
        if title_strip_re:
            title = re.sub(title_strip_re, '', title).strip()
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
        if len(articles) >= max_count:
            break

    if not articles:
        if media.get('title_prefer_shorter'):
            # 同URLが本文抜粋→タイトルの順で2回リンクされるページ向け（例: MAARKET）
            # 全リンクを収集してURLごとに最短テキストをタイトルとして採用する
            link_texts: dict = {}
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href'].strip()
                full_url = urljoin(effective_page_url, href)
                if not looks_like_article(full_url):
                    continue
                text = clean_text(a_tag.get_text())
                if text and len(text) >= 8:
                    link_texts.setdefault(full_url, []).append(text)
            for full_url, texts in list(link_texts.items()):
                title = min(texts, key=len)
                long_texts = [t for t in texts if t != title]
                excerpt = long_texts[0][:200] if long_texts else ''
                if title_strip_re:
                    title = re.sub(title_strip_re, '', title).strip()
                if not title or len(title) < 8:
                    continue
                if media.get('require_japanese') and not has_japanese_chars(title):
                    continue
                articles.append({
                    'category':  media['category'],
                    'source':    media['source'],
                    'title':     title,
                    'url':       full_url,
                    'excerpt':   excerpt,
                    'date':      '',
                    'thumbnail': '',
                })
                if len(articles) >= max_count:
                    break
        else:
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href'].strip()
                full_url = urljoin(effective_page_url, href)
                if full_url in seen or not looks_like_article(full_url):
                    continue
                seen.add(full_url)
                title = clean_text(a_tag.get_text())
                if title_strip_re:
                    title = re.sub(title_strip_re, '', title).strip()
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
                if len(articles) >= max_count:
                    break

    return articles


# ─── メイン処理 ──────────────────────────────────────────────────────────────

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
    errors       = []
    new_normal   = []
    new_backfill = []

    print('=' * 60)
    print('  LIFE CURATED scraper.py  記事収集開始')
    print(f'  対象: {len(MEDIA_LIST)} 媒体')
    print(f'  出力: {OUTPUT_CSV}')
    print('=' * 60)

    existing   = load_existing_csv()
    exist_urls = {a['url'] for a in existing}
    print(f'\n既存件数: {len(existing)} 件')

    # ─── ① 通常取得（最新5件・OGP取得・Claude API分類） ──────────
    print(f'\n{"─" * 60}')
    print(f'  ① 通常取得（各最大 {MAX_ARTICLES} 件 / Claude API分類）')
    print(f'{"─" * 60}')

    for media in MEDIA_LIST:
        source = media['source']
        print(f'\n[{source}] ({media["category"]}) 取得中...')
        try:
            articles = []
            method   = ''

            articles, used_rss = fetch_via_rss(media, backfill=False)
            if articles:
                method = f'RSS: {used_rss}'
                print(f'  RSS 成功 ({len(articles)} 件)')
            else:
                print('  RSS 失敗 → HTML スクレイピング')
                articles = fetch_via_html(media, backfill=False)
                method   = 'HTML scraping'
                if articles:
                    print(f'  HTML 成功 ({len(articles)} 件)')
                else:
                    raise ValueError('記事が 1 件も取得できませんでした')

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

            claude_cats = classify_with_claude_batch(articles)
            if claude_cats:
                print(f'  Claude 分類: {" / ".join(c or "?" for c in claude_cats)}')
            for i, article in enumerate(articles):
                if claude_cats and i < len(claude_cats) and claude_cats[i]:
                    article['category'] = claude_cats[i]
                else:
                    article['category'] = classify_category(article['title'], article.get('excerpt', ''))
            new_normal.extend(articles)

        except Exception as e:
            msg = f'[{source}] {method or "取得"} エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ─── ② 遡及取得（過去記事・キーワード分類・OGPなし） ─────────
    print(f'\n{"─" * 60}')
    print(f'  ② 遡及取得（各最大 {MAX_ARTICLES_BACKFILL} 件 / キーワード分類）')
    print(f'{"─" * 60}')

    seen_so_far = exist_urls | {a['url'] for a in new_normal}

    for media in MEDIA_LIST:
        source = media['source']
        print(f'\n[{source}] 遡及取得中...')
        try:
            articles = []

            articles, _ = fetch_via_rss(media, backfill=True)
            if articles:
                print(f'  RSS ({len(articles)} 件)')
            else:
                articles = fetch_via_html(media, backfill=True)
                if articles:
                    print(f'  HTML ({len(articles)} 件)')

            added_bf = 0
            for article in articles:
                url = article.get('url', '')
                if not url or url in seen_so_far:
                    continue
                article['category'] = classify_category(article['title'], article.get('excerpt', ''))
                new_backfill.append(article)
                seen_so_far.add(url)
                added_bf += 1
            if added_bf:
                print(f'  遡及新規: {added_bf} 件')

        except Exception as e:
            msg = f'[{source}] 遡及エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ─── ③ YouTube通常取得（最新5件・Claude API分類） ────────────
    print(f'\n{"─" * 60}')
    print(f'  ③ YouTube 通常取得（各最大 {MAX_YT_VIDEOS} 件 / Claude API分類）')
    print(f'{"─" * 60}')

    for channel in YOUTUBE_CHANNELS:
        name = channel['name']
        print(f'\n[{name}] ({channel["handle"]}) 取得中...')
        try:
            videos = fetch_youtube_channel(channel, backfill=False)
            claude_cats = classify_with_claude_batch(videos)
            if claude_cats:
                print(f'  Claude 分類: {" / ".join(c or "?" for c in claude_cats)}')
            for i, v in enumerate(videos):
                if claude_cats and i < len(claude_cats) and claude_cats[i]:
                    v['category'] = claude_cats[i]
            print(f'  取得: {len(videos)} 件')
            for v in videos:
                print(f'    - [{v["category"]}] {v["title"][:50]}')
            new_normal.extend(videos)
        except Exception as e:
            msg = f'[YouTube/{name}] エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ─── ④ YouTube遡及取得（最大30件・キーワード分類） ──────────
    print(f'\n{"─" * 60}')
    print(f'  ④ YouTube 遡及取得（各最大 {MAX_YT_VIDEOS_BACKFILL} 件 / キーワード分類）')
    print(f'{"─" * 60}')

    seen_for_yt = exist_urls | {a['url'] for a in new_normal} | {a['url'] for a in new_backfill}

    for channel in YOUTUBE_CHANNELS:
        name = channel['name']
        print(f'\n[{name}] 遡及取得中...')
        try:
            videos = fetch_youtube_channel(channel, backfill=True)
            added_bf = 0
            for v in videos:
                url = v.get('url', '')
                if not url or url in seen_for_yt:
                    continue
                new_backfill.append(v)
                seen_for_yt.add(url)
                added_bf += 1
            if added_bf:
                print(f'  遡及新規: {added_bf} 件')
        except Exception as e:
            msg = f'[YouTube/{name}] 遡及エラー: {e}'
            print(f'  ✗ {msg}')
            errors.append(msg)

    # ─── ⑤ マージ・ソート・CSV保存（上限なし） ──────────────────
    added_normal   = 0
    added_backfill = 0
    skipped        = 0

    for article in new_normal:
        url = article.get('url', '')
        if not url or url in exist_urls:
            skipped += 1
            continue
        existing.append(article)
        exist_urls.add(url)
        added_normal += 1

    for article in new_backfill:
        url = article.get('url', '')
        if not url or url in exist_urls:
            continue
        existing.append(article)
        exist_urls.add(url)
        added_backfill += 1

    existing.sort(key=lambda a: a.get('date') or '', reverse=True)

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore', restval='')
        writer.writeheader()
        writer.writerows(existing)

    print('\n' + '=' * 60)
    print(f'  通常新規追加: {added_normal} 件')
    print(f'  遡及新規追加: {added_backfill} 件')
    print(f'  重複スキップ: {skipped} 件')
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
