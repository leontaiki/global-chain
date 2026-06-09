# -*- coding: utf-8 -*-
"""
Global Chain — Macro Intelligence Dashboard
============================================
世界のトップメディアのRSSを集約し、18セクターへ自動分類する自分専用ダッシュボード。

実行方法:
    pip install streamlit feedparser
    streamlit run app.py

依存: streamlit, feedparser のみ（どちらもpipで一発）。
APIキーは不要。記事の分類・波及セクター・要約はすべてローカルで完結します。
（高品質なAI要約をしたい場合は、サイドバーの「AI要約（Gemini API）」を参照）
"""

import re
import html
import time
import json
import datetime as dt
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components
import feedparser


# =============================================================================
# 1. 初期設定 — RSSフィードと18セクターの定義
# =============================================================================

# --- 主要メディアのRSS URL（初期サンプル） -----------------------------------
# サイドバーから自由に追加・削除できます。
# ★印 = 直リンクで本文の「全文取得」が効く無料メディア。
# （無印 = ペイウォール等のため概要のみ。Google News経由のため全文取得は対象外）
DEFAULT_FEEDS = [
    # ★ 全文取得が効く無料・直リンクメディア（要約・分類の質が高い）
    {"name": "The Guardian – World", "url": "https://www.theguardian.com/world/rss"},
    {"name": "BBC – World",          "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "BBC – Business",       "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "NPR – World",          "url": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "Al Jazeera",           "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "NYT – World",          "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    # ★ カルチャー＆ソフトパワー向け（映画・音楽・アート・ファッション・テック）
    {"name": "The Guardian – Culture", "url": "https://www.theguardian.com/culture/rss"},
    {"name": "The Guardian – Fashion", "url": "https://www.theguardian.com/fashion/rss"},
    {"name": "BBC – Entertainment & Arts", "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"},
    {"name": "NYT – Arts",           "url": "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml"},
    {"name": "NPR – Pop Culture",    "url": "https://feeds.npr.org/1008/rss.xml"},
    {"name": "BBC – Technology",     "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    # ★ 医療・サイエンス向け（論文ジャーナル＋医療ニュース）
    {"name": "STAT News",           "url": "https://www.statnews.com/feed/"},
    {"name": "NEJM",                "url": "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss"},
    {"name": "The Lancet",          "url": "https://www.thelancet.com/rssfeed/lancet_online.xml"},
    {"name": "JAMA",                "url": "https://jamanetwork.com/rss/site_3/67.xml"},
    {"name": "Nature Medicine",     "url": "https://www.nature.com/nm.rss"},
    {"name": "Foreign Affairs",      "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "The Economist – Finance", "url": "https://www.economist.com/finance-and-economics/rss.xml"},
    {"name": "CNBC – Top News",     "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
    {"name": "CNBC – Finance",       "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"},
    {"name": "CNBC – Economy",       "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"},
]
# 注: The Guardian と NPR は本文が完全無料で取得しやすく、全文取得の主力です。
#     BBC・Al Jazeera も多くが取得可。NYT はメーター制のため記事により部分取得。
#     CNBC は直リンクで本文・画像が取得でき、金融/経済の主力です（Google News経由は廃止）。
#     Economist/Foreign Affairs は本文ペイウォールのため概要のみ運用です。
#     Culture/Fashion/Arts/Tech 系はカルチャービューで主役になります。


# --- 18セクター定義 -----------------------------------------------------------
# 企画書 "Global Chain Radio" の全18分野。
# strong = そのセクター固有の強い語（2点）。weak = 一般的で誤爆しやすい語（1点）。
# ASCII語は単語境界一致、日本語は部分一致（classify_sectors 参照）。
SECTORS = {
    "政治":       {"en": "Politics",      "color": "#c0392b",
                   "strong": ["election", "parliament", "congress", "senate", "referendum",
                              "democracy", "coalition", "政治", "選挙", "政権"],
                   "weak": ["vote", "policy", "government", "minister", "president", "populis"]},
    "経済":       {"en": "Economy",       "color": "#d35400",
                   "strong": ["inflation", "gdp", "recession", "deflation", "cpi", "unemployment",
                              "trade deficit", "経済", "物価", "景気"],
                   "weak": ["growth", "wages", "consumer", "stimulus", "tariff"]},
    "金融":       {"en": "Finance",       "color": "#e67e22",
                   "strong": ["central bank", "federal reserve", "treasury yield", "bond market",
                              "stock market", "hedge fund", "ipo", "liquidity", "equit",
                              "金利", "為替", "債券", "株"],
                   "weak": ["fed", "rate", "yield", "bond", "dollar", "currency", "stock",
                            "credit", "bank"]},
    "保険":       {"en": "Insurance",     "color": "#16a085",
                   "strong": ["insurance", "insurer", "reinsur", "actuari", "underwrit",
                              "pension fund", "insurance claim", "保険", "年金"],
                   "weak": ["premium"]},
    "医療":       {"en": "Healthcare",    "color": "#27ae60",
                   "strong": ["healthcare", "hospital", "pharma", "fda", "clinical", "biotech",
                              "medicine", "医療", "病院", "薬"],
                   "weak": ["drug", "patient", "therapy"]},
    "公衆衛生":   {"en": "Public Health",  "color": "#2ecc71",
                   "strong": ["pandemic", "epidemic", "outbreak", "obesity", "mental health",
                              "world health organization", "quarantine", "public health",
                              "disease", "infection", "感染", "公衆衛生"],
                   "weak": ["vaccine"]},
    "食糧":       {"en": "Food",          "color": "#f1c40f",
                   "strong": ["wheat", "grain", "food security", "crop", "harvest", "famine",
                              "fertilizer", "食糧", "穀物", "小麦"],
                   "weak": ["commodity"]},
    "農業":       {"en": "Agriculture",   "color": "#a4b400",
                   "strong": ["agricultur", "irrigation", "livestock", "soybean", "farmland",
                              "農業", "農地"],
                   "weak": ["farm", "subsid", "land use"]},
    "エネルギー": {"en": "Energy",         "color": "#e74c3c",
                   "strong": ["opec", "crude oil", "lng", "nuclear", "renewable", "solar",
                              "wind power", "electricity", "power plant", "uranium",
                              "石油", "原子力", "電力", "エネルギー"],
                   "weak": ["oil", "gas", "crude", "grid"]},
    "テック":     {"en": "Technology",    "color": "#3498db",
                   "strong": ["artificial intelligence", "semiconductor", "nvidia", "data center",
                              "quantum", "software", "半導体", "クラウド"],
                   "weak": ["ai", "chip", "cloud", "tech", "robot"]},
    "宇宙":       {"en": "Space",         "color": "#34495e",
                   "strong": ["satellite", "spacex", "nasa", "orbit", "rocket", "starlink",
                              "space agency", "衛星", "宇宙"],
                   "weak": ["space", "launch", "gps"]},
    "軍事":       {"en": "Military",      "color": "#7f8c8d",
                   "strong": ["military", "defense", "defence", "weapon", "missile", "army",
                              "navy", "nato", "troops", "warfare", "軍", "兵器", "防衛"],
                   "weak": ["war", "conflict", "arms"]},
    "外交":       {"en": "Diplomacy",     "color": "#2980b9",
                   "strong": ["diplomacy", "treaty", "sanction", "alliance", "bilateral",
                              "embassy", "g7", "g20", "外交", "制裁", "条約"],
                   "weak": ["summit", "negotiation"]},
    "不動産":     {"en": "Real Estate",   "color": "#8e44ad",
                   "strong": ["real estate", "mortgage", "office vacancy", "reit",
                              "housing market", "不動産", "住宅"],
                   "weak": ["property", "housing", "rent", "construction"]},
    "アート":     {"en": "Art",           "color": "#9b59b6",
                   "strong": ["museum", "gallery", "sotheby", "christie", "painting", "theatre",
                              "theater", "broadway", "exhibition", "sculpture", "tony award",
                              "美術", "アート", "演劇", "舞台"],
                   "weak": ["art", "auction"]},
    "ファッション":{"en": "Fashion",       "color": "#e84393",
                   "strong": ["fashion", "lvmh", "apparel", "runway", "couture", "designer",
                              "vogue", "catwalk", "haute couture", "ファッション", "ランウェイ"],
                   "weak": ["luxury", "textile", "ブランド"]},
    "カルチャー": {"en": "Culture",       "color": "#fd79a8",
                   "strong": ["anime", "k-pop", "kpop", "cinema", "video game", "box office",
                              "grammy", "oscar", "concert", "festival", "soft power",
                              "文化", "アニメ", "映画"],
                   "weak": ["culture", "film", "movie", "gaming", "streaming", "music",
                            "album", "celebrity"]},
    "地域":       {"en": "Local",         "color": "#636e72",
                   "strong": ["depopulation", "rural", "local economy", "地方", "高齢化", "過疎"],
                   "weak": ["aging", "vacant", "decline", "regional"]},
}


# =============================================================================
# 2. RSS取得（キャッシュ付き）
# =============================================================================

# 多くのメディア（Google News, NYT 等）は名乗り(User-Agent)が無いと
# アクセスを弾くため、ブラウザらしいヘッダを付けて取得する。
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")

# ブラウザに近いヘッダー一式（NPR等のクラウドIPブロック回避を試みる用）
_BROWSER_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/rss+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
}

# Mac等でよく起きる SSL: CERTIFICATE_VERIFY_FAILED を防ぐため、
# certifi のルート証明書を使ったSSLコンテキストを用意する。
import ssl
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


def _extract_entry_image(e) -> str:
    """RSSエントリから記事サムネイル画像URLを探す。無ければ空文字。"""
    # 1) media:thumbnail / media:content（最も一般的）
    for key in ("media_thumbnail", "media_content"):
        items = e.get(key)
        if items:
            for it in items:
                url = it.get("url")
                if url:
                    return _upgrade_image_res(url)
    # 2) enclosure（画像タイプのものだけ）
    for enc in e.get("links", []):
        if enc.get("rel") == "enclosure" and "image" in (enc.get("type") or ""):
            if enc.get("href"):
                return _upgrade_image_res(enc["href"])
    # 3) 本文HTML内の最初の <img>
    body = e.get("summary", e.get("description", "")) or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', body, re.I)
    if m:
        return _upgrade_image_res(m.group(1))
    return ""


def _upgrade_image_res(url: str) -> str:
    """RSSが配る画像URLをそのまま使う。
    （メディア別のURL書き換えによる高解像度化は誤爆でリンク切れを起こすため撤去。
      画質改善が必要なら、確実に動くと検証できた方法だけを後から限定的に追加する。）"""
    return url or ""


def _clean_feed_summary(raw_html: str) -> str:
    """RSS概要から『関連記事リンク』teaserを除去してから本文テキスト化する。
    Guardian等は概要に『… – in pictures』『full list of winners』等のリンクを混ぜるため、
    そうしたリンク(<a>)だけを狙って除去する（本文の文章は残す）。"""
    s = raw_html or ""
    # 「Continue reading」以降（関連リンクの塊が続くことが多い）を切り落とす
    s = re.split(r"continue reading", s, flags=re.I)[0]
    # teaser的な語を含む <a>...</a> リンクを丸ごと削除
    teaser = (r"in pictures|full list|– video|\bvideo\b|explained|live updates|"
              r"as it happened|in charts|\bquiz\b|crossword|gallery|best of the show")
    s = re.sub(rf'<a\b[^>]*>(?:(?!</a>).)*?(?:{teaser})(?:(?!</a>).)*?</a>',
               ' ', s, flags=re.S | re.I)
    return _strip_html(s)


@st.cache_data(ttl=900, show_spinner=False)  # 15分キャッシュ
def fetch_feed(url: str):
    """単一フィードを取得して (記事リスト, ステータス文字列) を返す。
    ステータスは None=正常、それ以外は理由（HTTPエラーや空など）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read()
        parsed = feedparser.parse(raw)
        entries = []
        for e in parsed.entries:
            entries.append({
                "title": e.get("title", "(no title)"),
                "link": e.get("link", ""),
                "summary": _clean_feed_summary(e.get("summary", e.get("description", ""))),
                "published": _parse_time(e),
                "image": _extract_entry_image(e),
            })
        if not entries:
            # 取得はできたが記事が0件 → 理由をできるだけ伝える
            reason = "記事0件"
            if getattr(parsed, "bozo", 0) and getattr(parsed, "bozo_exception", None):
                reason += f"（解析警告: {parsed.bozo_exception}）"
            return [], reason
        return entries, None
    except urllib.error.HTTPError as ex:
        return [], f"HTTP {ex.code}（アクセス拒否の可能性）"
    except Exception as ex:  # noqa: BLE001
        return [], str(ex)


# 本文の全文取得を試みる「無料・直リンク」メディアのドメイン。
# FT/Bloomberg/Economist/WSJ などのペイウォール、Google News経由のリンクは対象外。
FREE_FULLTEXT_DOMAINS = (
    "bbc.co.uk", "bbc.com", "nytimes.com", "apnews.com",
    "npr.org", "theguardian.com", "reuters.com", "aljazeera.com",
    "cnbc.com", "statnews.com",
)


def is_free_fulltext(link: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(link).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in FREE_FULLTEXT_DOMAINS)


def _extract_jsonld_body(h: str) -> str:
    """JSON-LD 構造化データから articleBody を取り出す（最も確実）。"""
    bodies = []
    for m in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            h, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            continue
        stack = [data]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                b = o.get("articleBody")
                if isinstance(b, str) and len(b) > 200:
                    bodies.append(b)
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return html.unescape(max(bodies, key=len)).strip() if bodies else ""


_NOISE_SNIPPETS = ("subscribe", "sign up", "newsletter", "advertisement",
                   "cookie", "all rights reserved", "follow us", "sign in",
                   "share this", "read more", "©")


@st.cache_data(ttl=1800, show_spinner=False)  # 30分キャッシュ
def fetch_pubmed(query: str, n: int = 15):
    """PubMed E-utilities で論文を検索し、最新順にメタ情報を返す。
    返り値: [{title, link, source(誌名), pubdate}], エラー時は []"""
    import urllib.request
    import urllib.parse
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    q = urllib.parse.quote(query)
    try:
        es = f"{base}/esearch.fcgi?db=pubmed&term={q}&retmax={n}&sort=date&retmode=json"
        req = urllib.request.Request(es, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as r:
            ids = json.loads(r.read()).get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        su = f"{base}/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json"
        req2 = urllib.request.Request(su, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req2, timeout=15, context=_SSL_CTX) as r:
            result = json.loads(r.read()).get("result", {})
        papers = []
        for pmid in ids:
            rec = result.get(pmid)
            if not rec:
                continue
            papers.append({
                "title": (rec.get("title") or "").rstrip("."),
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": rec.get("fulljournalname") or rec.get("source", "PubMed"),
                "pubdate": rec.get("pubdate", ""),
            })
        return papers
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=3600, show_spinner=False)  # 1時間キャッシュ
def fetch_article_body(url: str):
    """記事ページから本文を抽出して (本文テキスト, 理由) を返す。
    取れなければ ('', 理由)。標準ライブラリのみで実装（依存を増やさない）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read(1_200_000)  # 先頭1.2MBまで
        h = raw.decode("utf-8", errors="ignore")

        # 1) JSON-LD の articleBody（最優先・最も確実）
        body = _extract_jsonld_body(h)

        # 2) ダメなら、ノイズ要素を除いた上で <article> 領域の <p> を拾う
        if len(body) < 200:
            clean = re.sub(
                r'<(script|style|noscript|nav|header|footer|aside|form|figure)[^>]*>.*?</\1>',
                ' ', h, flags=re.S | re.I)
            art = re.search(r'<article[^>]*>(.*?)</article>', clean, re.S | re.I)
            region = art.group(1) if art else clean
            seen, parts = set(), []
            for p in re.findall(r"<p[^>]*>(.*?)</p>", region, re.S | re.I):
                t = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
                if len(t) < 40:
                    continue
                low = t.lower()
                if any(b in low for b in _NOISE_SNIPPETS):
                    continue
                key = t[:60]
                if key in seen:
                    continue
                seen.add(key)
                parts.append(t)
            body = " ".join(parts)

        # 3) meta description で補完（本文が薄いとき）
        if len(body) < 200:
            m = re.search(
                r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]*content=["\']([^"\']+)',
                h, re.I)
            meta = html.unescape(m.group(1)).strip() if m else ""
            body = (meta + " " + body).strip()

        if len(body) < 80:
            return "", "本文を十分に抽出できませんでした（ペイウォール等の可能性）"
        return body[:8000], None
    except urllib.error.HTTPError as ex:
        return "", f"HTTP {ex.code}"
    except Exception as ex:  # noqa: BLE001
        return "", str(ex)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def _parse_time(entry) -> dt.datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return dt.datetime.fromtimestamp(time.mktime(t))
            except Exception:  # noqa: BLE001
                pass
    return dt.datetime.min


def _chip_text_color(hex_color: str) -> str:
    """背景色の明るさから、読みやすい文字色（黒/白）を選ぶ。"""
    h = hex_color.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return "#fdfbf6"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1c1813" if luminance > 0.6 else "#fdfbf6"


# =============================================================================
# 3. セクター分類 & 投資仮説の「波及セクター」推定（ローカル・APIキー不要）
# =============================================================================

def classify_sectors(text: str):
    """記事テキストを18セクターに対しスコアリングし、(sector, score) を降順で返す。
    strong語=2点 / weak語=1点。英数字語は単語境界一致、日本語は部分一致。"""
    low = text.lower()

    def _count(kw: str) -> int:
        k = kw.lower()
        if re.fullmatch(r"[a-z0-9 \-]+", k):
            return len(re.findall(r"\b" + re.escape(k) + r"\b", low))
        return low.count(k)

    scores = []
    for jp, meta in SECTORS.items():
        score = 0
        for kw in meta.get("strong", []):
            score += _count(kw) * 2
        for kw in meta.get("weak", []):
            score += _count(kw)
        if score > 0:
            scores.append((jp, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def heuristic_summary(text: str, n_lines: int = 3):
    """読み込めた本文から要点文を抽出する簡易要約（オフライン）。
    戻り値: (要約文字列, 状態) — 状態は 'ok' / 'thin'（本文が薄く要約困難）。
    ※ これは英語原文から重要文を選んで文章化する抽出方式で、
       『グローバルチェーン視点での再構成』は行いません（それはAI要約の役割）。"""
    text = _strip_html(text)
    sentences = re.split(r"(?<=[.!?。])\s+", text)

    # 重複・ほぼ重複を除外しつつ、20字以上の文だけ残す
    seen, uniq = set(), []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        key = re.sub(r"[^a-z0-9]+", "", s.lower())  # 句読点違いを同一視
        if key and key not in seen:
            seen.add(key)
            uniq.append(s)

    # 1文目（多くは見出しの再掲）が後続文と内容的に重なる場合は除く
    if len(uniq) >= 2:
        head_words = set(re.findall(r"[a-z0-9]+", uniq[0].lower()))
        second_words = set(re.findall(r"[a-z0-9]+", uniq[1].lower()))
        if head_words and len(head_words & second_words) / len(head_words) > 0.8:
            uniq = uniq[1:]

    # 使える文が1つ以下＝実質「見出しだけ」→ 正直に伝える
    if len(uniq) <= 1:
        only = uniq[0] if uniq else (text[:120] if text else "")
        return only, "thin"

    # 本文中で頻出する内容語（記事の主題語）を抽出し、それを多く含む文を重視
    STOP = set("the a an and or but of to in on for with as at by from is are was were "
               "be been being this that these those it its he she they we you i his her "
               "their our your has have had will would can could said says say new more "
               "than then so not no into over after before about up out".split())
    words = [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    ranked = []
    for i, s in enumerate(uniq):
        sw = re.findall(r"[a-z]{4,}", s.lower())
        topic = sum(freq.get(w, 0) for w in sw)
        # 文の長さで正規化（長文の有利を抑える）＋ リード文を少し優遇
        weight = topic / (len(sw) + 1) + max(0, 2 - i) * 0.5
        ranked.append((weight, i, s))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    top = sorted(ranked[:n_lines], key=lambda x: x[1])  # 元の順序へ
    prose = " ".join(s.rstrip(".") + "." for _, _, s in top)  # 文章としてつなぐ
    return prose, "ok"


def hypothesis_hint(scores):
    """波及セクター上位から、その記事固有の波及構造だけを示す（定型の決まり文句は付けない）。"""
    if not scores:
        return "明確なセクター波及は検出されませんでした。"
    top = scores[0][0]
    spill = [s for s, _ in scores[1:3]]
    if spill:
        return f"主軸は【{top}】、波及先は【{'・'.join(spill)}】。"
    return f"主軸は【{top}】。"


# =============================================================================
# 3a. 引き算エンジン（フェーズ1）— ビュー別「効く度」スコアとトーン
#     2つのビューで重み付けを切り替える：
#       - マクロ投資 : 市場を動かす要因（金融・経済・エネルギー・軍事…）を重視
#       - カルチャー : ソフトパワー（カルチャー・アート・ファッション・テック…）を重視
# =============================================================================

# 市場を動かす「シグナル語」
RISK_OFF_WORDS = ["war", "conflict", "sanction", "crisis", "crash", "recession",
                  "default", "attack", "invasion", "inflation", "rate hike",
                  "tariff", "shortage", "strike", "tension", "escalat"]
RISK_ON_WORDS = ["rate cut", "ceasefire", "truce", "deal", "stimulus", "rally",
                 "recovery", "easing", "breakthrough", "agreement"]
# 文化的な「話題」語
BUZZ_WORDS = ["box office", "hit", "record", "award", "oscar", "grammy", "viral",
              "trend", "sold out", "blockbuster", "debut", "launch", "premiere",
              "collaboration", "streaming", "sensation", "anime", "k-pop", "festival"]

# 医療・科学系の「注目語」（論文・承認・試験）
MEDICAL_BUZZ = ["clinical trial", "phase 3", "phase 2", "fda approval", "fda approved",
                "meta-analysis", "randomized", "rct", "placebo", "double-blind",
                "peer-reviewed", "breakthrough therapy", "efficacy", "approval",
                "primary endpoint", "survival benefit", "significant reduction",
                "systematic review", "nejm", "lancet", "jama", "nature medicine"]

VIEW_PROFILES = {
    "マクロ投資": {
        "weight": {
            "金融": 4, "経済": 4, "エネルギー": 4, "軍事": 3, "外交": 2, "テック": 2,
            "不動産": 2, "食糧": 1, "農業": 1, "政治": 1, "公衆衛生": 1, "宇宙": 1,
            "保険": 1, "医療": 0, "地域": 0, "アート": 0, "ファッション": 0, "カルチャー": 0,
        },
        "pos": RISK_ON_WORDS, "neg": RISK_OFF_WORDS,
        "threshold": 7,
        "tone_high": "リスクオン寄り", "tone_low": "リスクオフ寄り",
        "tone_neutral": "中立",
        "tone_color_high": "#27ae60", "tone_color_low": "#c0392b", "tone_color_neutral": "#8a8f78",
        "default_sector": "すべて",
    },
    "カルチャー＆ソフトパワー": {
        "weight": {
            "カルチャー": 4, "アート": 3, "ファッション": 3, "テック": 2, "地域": 2,
            "医療": 1, "公衆衛生": 1, "政治": 1, "外交": 1, "食糧": 1, "宇宙": 1,
            "不動産": 1, "金融": 1, "経済": 1, "農業": 0, "軍事": 0, "エネルギー": 0, "保険": 0,
        },
        "pos": BUZZ_WORDS, "neg": [],
        "threshold": 4,
        "tone_high": "話題が活発", "tone_low": "落ち着いた一日",
        "tone_color_high": "#e84393", "tone_color_low": "#8a8f78",
        "default_sector": "すべて",
    },
    "医療・サイエンス": {
        "weight": {
            "医療": 4, "公衆衛生": 4, "テック": 2, "政治": 1, "経済": 1, "保険": 1,
            "食糧": 1, "農業": 0, "金融": 0, "エネルギー": 0, "軍事": 0, "外交": 0,
            "不動産": 0, "アート": 0, "ファッション": 0, "カルチャー": 0, "地域": 0, "宇宙": 0,
        },
        "pos": MEDICAL_BUZZ, "neg": [],
        "threshold": 3,
        "tone_high": "注目の研究あり", "tone_low": "静かな週",
        "tone_color_high": "#2980b9", "tone_color_low": "#8a8f78",
        "default_sector": "すべて",
    },
}


def impact_score(title: str, summary: str, scores, profile):
    """記事の『効く度』を返す。 (score, pos回数, neg回数)"""
    text = f"{title} {summary}".lower()
    weight = profile["weight"]
    s = 0.0
    for sec, _ in scores[:3]:
        s += weight.get(sec, 0)
    pos = sum(text.count(k) for k in profile["pos"])
    neg = sum(text.count(k) for k in profile["neg"])
    s += (pos + neg) * 1.7
    if len(scores) >= 3:
        s += 2          # 連鎖が広い（複数セクターにまたがる）ほど重要
    elif len(scores) >= 2:
        s += 1
    return s, pos, neg


def daily_brief(articles, profile):
    """画面最上部の一行サマリー用に、注目件数とトーンを集計して返す。"""
    th = profile["threshold"]
    notable = [a for a in articles if a.get("impact", 0) >= th]
    pos = sum(a.get("risk_on", 0) for a in notable)
    neg = sum(a.get("risk_off", 0) for a in notable)
    if not profile["neg"]:
        # ネガ語が無いビュー（カルチャー・医療）：Buzz語が1件でもあれば「活発」
        if pos >= 1:
            return notable, profile.get("tone_high", "話題が活発"), profile.get("tone_color_high", "#e84393")
        return notable, profile.get("tone_low", "落ち着いた一日"), profile.get("tone_color_low", "#8a8f78")
    # マクロ：リスクオン/オフ
    if pos > neg * 1.3:
        return notable, profile.get("tone_high", "リスクオン寄り"), profile.get("tone_color_high", "#27ae60")
    elif neg > pos * 1.3:
        return notable, profile.get("tone_low", "リスクオフ寄り"), profile.get("tone_color_low", "#c0392b")
    return notable, profile.get("tone_neutral", "中立"), profile.get("tone_color_neutral", "#8a8f78")


def build_llm_prompt(title: str, text: str, link: str) -> str:
    """Gemini / ChatGPT / チャット版Claude に貼り付けるためのプロンプトを組み立てる。
    日本語訳＋Global Chain Radio形式の要約を、追加課金なしで作ってもらうためのもの。"""
    return f"""あなたは「Global Chain Radio」という英語ラジオ番組の編集者です。日本の医師が、政治・経済・金融・医療・公衆衛生・食糧・エネルギー・テック・軍事・外交・文化などを、歴史とグローバルなサプライチェーン（Chain）という一つの相互依存システムとして読み解く番組です。文体はThe Economist調で、密度が高く構造的です。

以下の英語ニュースについて、次の形式で日本語で出力してください。

【1. 全文の日本語訳】
（本文を自然な日本語に訳す）

【2. Today's Theme】
（日常ニュースとマクロ視点を橋渡しする一文）

【3. 3 Key Takeaways】
（サプライチェーン・歴史・システムの観点から要点を3つ）

【4. The Essence】
（なぜ今このニュースがグローバルチェーン上で重要か。投資・臨床・政策の意思決定層に響く本質を、歴史的文脈を交えて）

【5. 波及セクター】
（影響が及ぶ分野を列挙）

---
タイトル: {title}
本文: {text}
原文URL: {link}
"""


def copy_button(text: str, key: str, label: str = "📋 プロンプトをコピー"):
    """クリックでクリップボードにコピーするボタン（標準コンポーネントで実装）。"""
    payload = json.dumps(text)  # 改行・引用符を安全にJSへ
    components.html(f"""
    <button id="btn_{key}" style="
        font-family: -apple-system, sans-serif; font-size: 14px; font-weight: 600;
        color: #fdfbf6; background: #8a3a2e; border: none; border-radius: 6px;
        padding: 9px 16px; cursor: pointer; width: 100%;">
      {label}
    </button>
    <script>
      const b = document.getElementById("btn_{key}");
      b.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText({payload});
          b.textContent = "✅ コピーしました！";
          b.style.background = "#2e7d32";
          setTimeout(() => {{ b.textContent = "{label}"; b.style.background = "#8a3a2e"; }}, 1800);
        }} catch (e) {{
          b.textContent = "コピー失敗（手動で選択してください）";
        }}
      }});
    </script>
    """, height=48)


# =============================================================================
# 3b. Gemini API による本物の要約（任意・無料枠あり）
#     企画書 "Global Chain Radio" の固定フォーマットで、グローバルチェーン視点で再構成する。
# =============================================================================

@st.cache_data(ttl=86400, show_spinner=False)  # 同一テキストは24時間キャッシュ（呼び出し抑制）
def gemini_analysis(text: str, title: str, api_key: str, model: str):
    """記事を Global Chain Radio 形式に再構成して返す。
    戻り値: dict(theme, takeaways[3], essence, sectors[]) または {'error': ...}"""
    try:
        import google.generativeai as genai
    except ImportError:
        return {"error": "google-generativeai 未インストール（pip install google-generativeai）"}
    if not api_key:
        return {"error": "APIキーが未設定です（サイドバーで入力してください）"}

    system = (
        "You are the lead writer of 'Global Chain Radio', an English radio program produced "
        "by a doctor in Japan. The program reads each day's news not as an isolated dot, but as "
        "a point on the lines and planes of global supply chains and history. You connect "
        "politics, economics, finance, health, food, energy, technology, space, the military, "
        "diplomacy, and culture as one interdependent system (the 'Chain'). Your tone is dense, "
        "structural, and analytical, in the style of The Economist. You always reframe a news "
        "item by asking: where does this sit in the global chain, and what historical pattern "
        "does it echo?"
    )
    user = f"""次の英語ニュースを、Global Chain Radio の視点で分析してください。
最重要は「連鎖（chain）」です。出来事が市場・セクターへどう波及するかを、因果のドミノとして具体的に示すこと。
例：「軍事衝突 → ホルムズ海峡の海運リスク → 原油↑ → インフレ再燃 → 金利↑ → グロース株に逆風／防衛・エネルギー関連に追い風 → リスクオフ」。
推測が混じる場合は断定しすぎず、ただし因果の方向（↑↓）は明示すること。

# 出力は JSON のみ（前置き・コードブロック・説明文は禁止）
{{
  "theme": "今日のテーマ（日常ニュースとマクロ視点を橋渡しする一文・40字以内）",
  "chain": ["出来事", "一次効果", "二次効果", "市場/セクターへの帰結", "（必要なら）最終的な地合い"],
  "risk_tone": "リスクオン / リスクオフ / 中立 のいずれか",
  "sectors": ["影響が及ぶ分野を2〜4個（例: 軍事, エネルギー, 金融）"],
  "index_implication": "S&P500長期インデックス投資家への含意。多くの場合『長期方針の変更は不要』。変更不要ならそう明示し、例外的に注意すべき時だけ理由を述べる（80字以内）"
}}

# 記事
タイトル: {title}
本文: {text[:5000]}
"""
    try:
        genai.configure(api_key=api_key)
        gm = genai.GenerativeModel(model, system_instruction=system)
        resp = gm.generate_content(
            user,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 2048,
                "response_mime_type": "application/json",  # JSONだけを強制出力
            },
        )
        raw = (resp.text or "").replace("```json", "").replace("```", "").strip()
        # 前後に余計な文字が付いても、最初の { から最後の } までを取り出す
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0) if m else raw)
    except Exception as ex:  # noqa: BLE001
        msg = str(ex)
        if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
            return {"error": "無料枠の上限に達しました。少し時間をおくか、"
                             "サイドバーのモデルを Flash-Lite（無料枠が広い）に切り替えてください。"}
        return {"error": msg}


# =============================================================================
# 4. 画面構成 — Streamlit UI
# =============================================================================

st.set_page_config(page_title="Global Chain — Macro Intelligence",
                   page_icon="🌐", layout="wide")

# ---- カスタムCSS（エディトリアル/ターミナル風の落ち着いた配色） ----
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ---- 全体：白基調 + インク文字（The Economist系） ---- */
.stApp { background: #ffffff; color: #121212; }
[data-testid="stMain"] { background: #ffffff; }
[data-testid="stSidebar"] { background: #f4f4f2; border-right: 1px solid #d9d9d6; }
[data-testid="stSidebar"] * { color: #1a1a1a; }
.stApp p, .stApp li, .stApp span, .stApp label, .stMarkdown { color: #2b2b2b; }

h1, h2, h3, h4 { font-family: 'Spectral', serif; color: #121212 !important;
                 letter-spacing: .2px; }

/* ---- ヘッダー：上に赤いルール ---- */
.gc-title { font-size: 2.3rem; font-weight: 800; margin-bottom: 2px; color: #121212; }
.gc-sub { color: #E3120B; font-family: 'IBM Plex Mono', monospace;
          font-size: .78rem; letter-spacing: 3px; text-transform: uppercase; font-weight: 600;
          border-top: 3px solid #E3120B; display: inline-block; padding-top: 6px; }

/* ---- 記事カード ---- */
.gc-card { background: #ffffff; border: 1px solid #e2e2df;
           border-left: 3px solid #d0d0cc; border-radius: 3px;
           padding: 14px 20px; margin-bottom: 10px; transition: border-color .15s; }
.gc-card:hover { border-left-color: #E3120B; }
.gc-source { font-family: 'IBM Plex Mono', monospace; font-size: .68rem;
             color: #8a8a8a; text-transform: uppercase; letter-spacing: 1.5px; }
.gc-headline { font-family: 'Spectral', serif; font-size: 1.15rem; color: #121212;
               line-height: 1.35; margin: 5px 0 0 0; font-weight: 600; }

/* ---- セクターチップ ---- */
.gc-chip { display: inline-block; font-family: 'IBM Plex Mono', monospace;
           font-size: .68rem; padding: 3px 9px; border-radius: 3px; margin: 2px 4px 2px 0;
           font-weight: 600; letter-spacing: .3px; }

/* ---- THE ESSENCE / 含意ボックス ---- */
.gc-essence { background: #f7f7f5; border: 1px solid #e2e2df;
              border-left: 3px solid #E3120B; border-radius: 3px;
              padding: 13px 17px; margin-top: 10px; color: #2b2b2b; }
.gc-essence b { color: #E3120B; font-family: 'IBM Plex Mono', monospace; font-size: .7rem;
                letter-spacing: 1.5px; }

/* ---- 区切り線 ---- */
hr { border-color: #d9d9d6 !important; }

/* ---- セクター別 横棒ヒートマップ ---- */
.gc-bars { margin: 4px 0 2px 0; }
.gc-bar-row { display: flex; align-items: center; gap: 10px; margin: 3px 0; }
.gc-bar-label { width: 76px; flex-shrink: 0; font-family: 'Spectral', serif;
                font-size: .9rem; color: #121212; text-align: right; }
.gc-bar-track { flex: 1; background: #f0f0ee; border-radius: 2px; height: 16px; }
.gc-bar-fill { height: 16px; border-radius: 2px; min-width: 3px; transition: width .3s; }
.gc-bar-val { width: 28px; flex-shrink: 0; font-family: 'IBM Plex Mono', monospace;
              font-size: .78rem; color: #595959; }

/* ---- フェーズ1: 一行サマリー（5秒で結論） ---- */
.gc-brief { background: #ffffff; border: 1px solid #e2e2df; border-left: 5px solid #E3120B;
            border-radius: 3px; padding: 13px 18px; margin: 4px 0 14px 0;
            font-size: 1.02rem; color: #121212; }
.gc-brief-tone { font-family: 'IBM Plex Mono', monospace; font-weight: 600;
                 font-size: .82rem; letter-spacing: .5px; }
.gc-brief-sub { font-size: .8rem; color: #595959; margin-top: 5px;
                font-family: 'Spectral', serif; }

/* ---- フェーズ2: 連鎖（CHAIN）表示 ---- */
.gc-chain { background: #f7f7f5; border: 1px solid #e2e2df; border-left: 4px solid #E3120B;
            border-radius: 3px; padding: 13px 17px; margin: 8px 0; }
.gc-chain b { color: #E3120B; font-family: 'IBM Plex Mono', monospace; font-size: .74rem;
              letter-spacing: 1px; }
.gc-chain-body { margin-top: 8px; font-family: 'Spectral', serif; font-size: 1.02rem;
                 line-height: 1.7; color: #121212; }

/* ---- 常時表示キッカー（見出し上の小見出し） ---- */
.gc-meta { display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
           margin: 6px 0 -4px 2px; }
.gc-meta-sec { font-family: 'IBM Plex Mono', monospace; font-size: .62rem; font-weight: 600;
               padding: 1px 7px; border-radius: 2px; letter-spacing: .3px; }
.gc-meta-txt { font-family: 'IBM Plex Mono', monospace; font-size: .66rem; color: #8a8a8a;
               letter-spacing: .5px; text-transform: uppercase; }

/* ---- 記事サムネイル（ある記事だけ自然に表示） ---- */
.gc-thumb { width: 100%; max-width: 420px; height: 180px; object-fit: cover;
            border-radius: 4px; margin: 4px 0 2px 0; display: block;
            border: 1px solid #e2e2df; }
@media (max-width: 640px) { .gc-thumb { height: 150px; } }

/* ---- 今日の主役（ヒーローカード） ---- */
.gc-hero-label { font-family: 'IBM Plex Mono', monospace; font-size: .72rem; font-weight: 600;
                 letter-spacing: 2px; text-transform: uppercase; color: #E3120B;
                 border-bottom: 2px solid #E3120B; display: inline-block;
                 padding-bottom: 3px; margin: 6px 0 12px 0; }
.gc-hero-big { display: block; text-decoration: none; border: 1px solid #e2e2df;
               border-radius: 4px; overflow: hidden; margin-bottom: 12px;
               transition: box-shadow .15s; }
.gc-hero-big:hover { box-shadow: 0 4px 16px rgba(0,0,0,.12); }
.gc-hero-img { width: 100%; height: 340px; object-fit: cover; display: block; }
.gc-hero-body { padding: 14px 18px; }
.gc-hero-kicker { margin-bottom: 6px; }
.gc-hero-chip { font-family: 'IBM Plex Mono', monospace; font-size: .64rem; font-weight: 600;
                padding: 2px 8px; border-radius: 2px; margin-right: 8px; }
.gc-hero-src { font-family: 'IBM Plex Mono', monospace; font-size: .68rem; color: #8a8a8a;
               letter-spacing: .5px; text-transform: uppercase; }
.gc-hero-title { font-family: 'Spectral', serif; font-size: 1.5rem; font-weight: 700;
                 color: #121212; line-height: 1.25; }
.gc-hero-sm { display: block; text-decoration: none; border: 1px solid #e2e2df;
              border-radius: 4px; overflow: hidden; height: 100%;
              transition: box-shadow .15s; }
.gc-hero-sm:hover { box-shadow: 0 4px 16px rgba(0,0,0,.10); }
.gc-hero-img-sm { width: 100%; height: 160px; object-fit: cover; display: block; }
.gc-hero-sm .gc-hero-kicker { padding: 10px 12px 0 12px; margin-bottom: 4px; }
.gc-hero-title-sm { font-family: 'Spectral', serif; font-size: 1.05rem; font-weight: 600;
                    color: #121212; line-height: 1.3; padding: 0 12px 12px 12px; }
.gc-hero-noimg { background: linear-gradient(135deg, #f0f0ee, #e2e2df); }
@media (max-width: 640px) { .gc-hero-title { font-size: 1.2rem; } .gc-hero-img { height: 220px; } }

/* ---- PubMed論文カード ---- */
.gc-paper { border-left: 3px solid #2980b9; background: #f7f9fb;
            border: 1px solid #e2e2df; border-left: 3px solid #2980b9;
            border-radius: 3px; padding: 10px 14px; margin-bottom: 7px; }
.gc-paper-meta { font-family: 'IBM Plex Mono', monospace; font-size: .66rem; color: #2980b9;
                 text-transform: uppercase; letter-spacing: .5px; margin-bottom: 3px; }
.gc-paper-title { font-family: 'Spectral', serif; font-size: 1.02rem; font-weight: 600;
                  color: #121212; line-height: 1.35; text-decoration: none; }
.gc-paper-title:hover { color: #2980b9; }

/* ---- 記事＝展開バーを一体型カードに ---- */
[data-testid="stExpander"] { background: #ffffff; border: 1px solid #e2e2df !important;
                             border-left: 3px solid #E3120B !important; border-radius: 3px;
                             margin-bottom: 9px; }
[data-testid="stExpander"] summary { padding: 12px 16px; }
[data-testid="stExpander"] summary p { font-family: 'Spectral', serif !important;
                                       font-size: 1.12rem !important; font-weight: 600 !important;
                                       color: #121212 !important; line-height: 1.35; }
[data-testid="stExpander"] summary:hover p { color: #E3120B !important; }

/* ---- スマホ対応 ---- */
@media (max-width: 640px) {
  .gc-title { font-size: 1.5rem !important; line-height: 1.25; }
  .gc-sub { font-size: .62rem !important; letter-spacing: 1.5px; }
  [data-testid="stMain"] .block-container { padding-left: .8rem; padding-right: .8rem; }
  [data-testid="stExpander"] summary p { font-size: 1rem !important; }
  .gc-chip { font-size: .62rem; padding: 2px 7px; }
}

</style>
""", unsafe_allow_html=True)

st.markdown('<div class="gc-sub">A DOCTOR IN JAPAN READS THE WORLD AS ONE SYSTEM</div>',
            unsafe_allow_html=True)
st.markdown('<div class="gc-title">🌐 Global Chain — Macro Intelligence Dashboard</div>',
            unsafe_allow_html=True)
st.caption("世界のトップメディアのRSSを集約し、18セクターへ自動分類する自分専用ダッシュボード")
st.divider()

# ---- サイドバー：フィード管理 + セクターフィルタ ----
with st.sidebar:
    st.header("⚙️ 設定")

    view = st.radio("📊 ビュー", list(VIEW_PROFILES.keys()),
                    help="マクロ投資＝市場を動かす要因を重視。カルチャー＝ソフトパワー（文化・アート・ファッション）を重視。")
    profile = VIEW_PROFILES[view]

    if "feeds" not in st.session_state:
        st.session_state.feeds = list(DEFAULT_FEEDS)
    else:
        # DEFAULT_FEEDS と同期：新規は追加、同名はURLを最新に更新
        default_by_name = {f["name"]: f["url"] for f in DEFAULT_FEEDS}
        existing_names = {f["name"] for f in st.session_state.feeds}
        for f in st.session_state.feeds:
            if f["name"] in default_by_name:
                f["url"] = default_by_name[f["name"]]   # 壊れたURLを修正
        for f in DEFAULT_FEEDS:
            if f["name"] not in existing_names:
                st.session_state.feeds.append(f)
        # 既定から外したフィード（壊れていたBMJ等）を掃除
        _retired = {"BMJ", "medRxiv", "bioRxiv"}
        st.session_state.feeds = [f for f in st.session_state.feeds
                                  if f["name"] not in _retired]

    st.subheader("📡 RSSフィード")
    feed_labels = [f["name"] for f in st.session_state.feeds]
    active = st.multiselect("読み込むメディア", feed_labels, default=feed_labels)

    with st.expander("➕ フィードを追加"):
        new_name = st.text_input("メディア名", key="new_name")
        new_url = st.text_input("RSS URL", key="new_url")
        if st.button("追加", use_container_width=True):
            if new_name and new_url:
                st.session_state.feeds.append({"name": new_name, "url": new_url})
                st.rerun()

    st.subheader("🏷️ セクターフィルタ")
    sector_options = ["すべて"] + [f"{jp}（{m['en']}）" for jp, m in SECTORS.items()]
    selected_sector = st.selectbox("表示するセクター", sector_options)

    sort_order = st.selectbox("並び順",
                              ["今日効く度順", "新しい順", "セクター別", "全文取得できる順"])
    only_notable = st.toggle("ノイズを削る（今日効く記事だけ）", value=False,
                             help="長期投資・番組素材に効く記事だけに絞ります。静かな日は『方針変更不要』と表示します。")

    max_per_feed = st.slider("各メディアの最大記事数", 3, 30, 10)
    if st.button("🔄 最新を再取得", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # ---- 医療・サイエンスビュー専用：専門分野・論文検索（PubMed） ----
    if view == "医療・サイエンス":
        st.divider()
        st.subheader("🔬 専門分野・論文検索")
        st.caption("PubMedから最新論文を検索し、画面上部に独立表示します。")

        if "med_query" not in st.session_state:
            st.session_state.med_query = ""

        med_input = st.text_input("検索ワード（英語）",
                                  value=st.session_state.med_query,
                                  placeholder="例: COPD exacerbation",
                                  help="PubMed構文OK（AND / OR / NOT、\"...\"[journal] など）")
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("🔎 検索", use_container_width=True, key="med_search"):
                st.session_state.med_query = med_input.strip()
                st.rerun()
        with c2:
            if st.button("クリア", use_container_width=True, key="med_clear"):
                st.session_state.med_query = ""
                st.rerun()

        st.caption("📚 診療科プリセット（タップで検索）")
        SPECIALTY_PRESETS = [
            ("呼吸器", "respiratory medicine"), ("皮膚科", "dermatology"),
            ("腫瘍", "oncology"), ("循環器", "cardiology"),
            ("神経", "neurology"), ("感染症", "infectious disease"),
            ("消化器", "gastroenterology"), ("内分泌", "endocrinology"),
            ("精神科", "psychiatry"), ("免疫", "immunology allergy"),
            ("整形外科", "orthopedics"), ("救急集中", "critical care medicine"),
        ]
        pcols = st.columns(2)
        for idx, (jp_name, term) in enumerate(SPECIALTY_PRESETS):
            with pcols[idx % 2]:
                active_mark = "✅ " if st.session_state.med_query == term else ""
                if st.button(f"{active_mark}{jp_name}", key=f"sp_{term}",
                             use_container_width=True):
                    st.session_state.med_query = term
                    st.rerun()

    st.divider()
    st.subheader("🤖 AI要約（Gemini API）")
    use_ai = st.toggle("本物のAI要約をONにする", value=False,
                       help="グローバルチェーン視点で記事を再構成します。Gemini無料枠の範囲なら課金なしです。")
    api_key = ""
    ai_model = "gemini-2.5-flash-lite"
    if use_ai:
        import os as _os
        api_key = st.text_input("GEMINI_API_KEY", type="password",
                                value=_os.environ.get("GEMINI_API_KEY", ""),
                                help="Google AI Studio (aistudio.google.com) で無料発行。環境変数 GEMINI_API_KEY があれば自動入力されます。")
        ai_model = st.selectbox("モデル",
                                ["gemini-2.5-flash-lite", "gemini-2.5-flash"],
                                index=0,
                                help="無料枠はFlash系のみ。Flash-Lite=無料枠が広い(推奨) / Flash=高品質だが無料枠が少ない")
        st.caption("💡 無料枠の目安: Flash-Lite ≈ 1日1,000回 / Flash ≈ 1日20回。"
                   "上限超過時は時間をおくかFlash-Liteへ。無料枠は入力がGoogleのモデル改善に使われる場合あり。")

# ---- 記事の取得・分類 ----
active_feeds = [f for f in st.session_state.feeds if f["name"] in active]
all_articles = []
errors = []

progress = st.empty()
for f in active_feeds:
    with st.spinner(f"取得中… {f['name']}"):
        entries, err = fetch_feed(f["url"])
    if err:
        errors.append(f"{f['name']}: {err}")
    for e in entries[:max_per_feed]:
        text = f"{e['title']}. {e['summary']}"
        scores = classify_sectors(text)
        e["source"] = f["name"]
        e["scores"] = scores
        e["primary"] = scores[0][0] if scores else "未分類"
        imp, off, on = impact_score(e["title"], e["summary"], scores, profile)
        e["impact"], e["risk_off"], e["risk_on"] = imp, off, on
        all_articles.append(e)

# --- フェーズ0(a): 重複記事の除去 ---------------------------------------------
# 同じニュースが複数メディア/フィードで重複することがある。
# リンク（クエリ除く）または正規化タイトルが一致したら、最初の1件だけ残す。
def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())

def _norm_link(u: str) -> str:
    return (u or "").split("?")[0].rstrip("/").lower()

_seen_keys, _deduped = set(), []
for a in all_articles:
    keys = {("L", _norm_link(a["link"]))} if a.get("link") else set()
    keys.add(("T", _norm_title(a["title"])))
    if keys & _seen_keys:           # いずれかのキーが既出なら重複
        continue
    _seen_keys |= keys
    _deduped.append(a)
_dupes_removed = len(all_articles) - len(_deduped)
all_articles = _deduped

# 一行サマリーは「その日全体」で集計（フィルタで絞る前のスナップショット）
_notable_all, _tone, _tone_color = daily_brief(all_articles, profile)

# まず新しい順に並べる（以降の並び替えは安定ソートなので、各グループ内は新しい順が保たれる）
all_articles.sort(key=lambda x: x["published"], reverse=True)

if sort_order == "セクター別":
    _order = {s: i for i, s in enumerate(SECTORS)}
    all_articles.sort(key=lambda x: _order.get(x["primary"], 999))
elif sort_order == "全文取得できる順":
    all_articles.sort(key=lambda x: not is_free_fulltext(x["link"]))
elif sort_order == "今日効く度順":
    all_articles.sort(key=lambda x: x.get("impact", 0), reverse=True)
# 「新しい順」はそのまま

# ノイズ削減フィルタ（今日効く記事だけに絞る）
if only_notable:
    all_articles = [a for a in all_articles if a.get("impact", 0) >= profile["threshold"]]

# セクターフィルタ適用
if selected_sector != "すべて":
    target = selected_sector.split("（")[0]
    all_articles = [a for a in all_articles
                    if any(s == target for s, _ in a["scores"])]

# ---- フェーズ1: 5秒で結論が出る一行サマリー（最上部） ----
if all_articles:
    n_notable = len(_notable_all)
    if n_notable == 0:
        st.markdown(
            '<div class="gc-brief" style="border-left-color:#8a8f78;">'
            '<span class="gc-brief-tone" style="color:#8a8f78;">● 静かな一日</span>'
            '　今日は長期の方針を変える必要はなさそうです。'
            '市場全体を動かすニュースは検出されていません。</div>',
            unsafe_allow_html=True)
    else:
        # 医療ビューではBuzz語ヒット順（論文が上に来る）、それ以外はデフォルト順
        if profile.get("neg") == [] and profile.get("tone_high") in ("注目の研究あり", "話題が活発"):
            _candidates = sorted(_notable_all, key=lambda a: a.get("risk_on", 0), reverse=True)
        else:
            _candidates = _notable_all
        top_titles = " ／ ".join(html.escape(a["title"][:46]) for a in _candidates[:3])
        st.markdown(
            f'<div class="gc-brief" style="border-left-color:{_tone_color};">'
            f'<span class="gc-brief-tone" style="color:{_tone_color};">● 全体トーン: {_tone}</span>'
            f'　今日の注目 <b>{n_notable}</b> 件'
            f'<div class="gc-brief-sub">主役の連鎖候補: {top_titles}</div></div>',
            unsafe_allow_html=True)

# ---- 今日の主役：効く度トップ3を大型ビジュアルカードで ----
def _hero_kicker(a):
    sec = a["scores"][0][0] if a["scores"] else ""
    color = SECTORS.get(sec, {}).get("color", "#888")
    chip = (f'<span class="gc-hero-chip" style="background:{color};'
            f'color:{_chip_text_color(color)};">{sec}</span>' if sec else "")
    return f'{chip}<span class="gc-hero-src">{html.escape(a["source"])}　⚡{int(round(a.get("impact",0)))}</span>'

@st.cache_data(ttl=3600, show_spinner=False)
def _image_ok(url: str) -> bool:
    """画像URLが実際に読み込めるか（200かつ画像）を確認する。死んでいれば False。"""
    if not url:
        return False
    import urllib.request
    import urllib.error
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA}, method=method)
            with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as r:
                ct = (r.headers.get("Content-Type") or "").lower()
                return getattr(r, "status", 200) == 200 and "image" in ct
        except Exception:  # noqa: BLE001
            continue
    return False


def _hero_img(a, cls):
    """画像が生きていれば <img> を返す。無い/死んでいれば空文字（画像欄を出さない）。
    Streamlitは class を除去するため、サイズ指定は style で直接当てる。"""
    url = a.get("image")
    if not url or not _image_ok(url):
        return ""
    h = 340 if cls == "gc-hero-img" else 160
    style = (f"width:100%;height:{h}px;object-fit:cover;display:block;"
             f"border-bottom:1px solid #e2e2df;")
    return f'<img src="{html.escape(url)}" loading="lazy" style="{style}">'

# ---- 医療・サイエンス：PubMed論文検索の結果を独立表示 ----
if view == "医療・サイエンス" and st.session_state.get("med_query"):
    q = st.session_state.med_query
    st.markdown(f'<div class="gc-hero-label">🔬 論文検索: {html.escape(q)}</div>',
                unsafe_allow_html=True)
    with st.spinner(f"PubMedで「{q}」を検索中…"):
        papers = fetch_pubmed(q, 15)
    if not papers:
        st.info("該当する論文が見つかりませんでした。キーワードを変えてみてください。")
    else:
        st.caption(f"PubMed 最新 {len(papers)} 件（新しい順）")
        for p in papers:
            st.markdown(
                f'<div class="gc-paper">'
                f'<div class="gc-paper-meta">{html.escape(p["source"])} · {html.escape(p["pubdate"])}</div>'
                f'<a class="gc-paper-title" href="{html.escape(p["link"])}" target="_blank" rel="noopener">'
                f'{html.escape(p["title"])}</a></div>',
                unsafe_allow_html=True)
    st.divider()

heroes = [a for a in sorted(all_articles, key=lambda x: x.get("impact", 0), reverse=True)
          if a.get("impact", 0) >= profile["threshold"]][:3]
if heroes:
    st.markdown('<div class="gc-hero-label">今日の主役</div>', unsafe_allow_html=True)
    h0 = heroes[0]
    st.markdown(
        f'<a class="gc-hero-big" href="{html.escape(h0["link"])}" target="_blank" rel="noopener">'
        f'{_hero_img(h0, "gc-hero-img")}'
        f'<div class="gc-hero-body"><div class="gc-hero-kicker">{_hero_kicker(h0)}</div>'
        f'<div class="gc-hero-title">{html.escape(h0["title"])}</div></div></a>',
        unsafe_allow_html=True)
    rest = heroes[1:]
    if rest:
        cols = st.columns(len(rest))
        for col, h in zip(cols, rest):
            with col:
                st.markdown(
                    f'<a class="gc-hero-sm" href="{html.escape(h["link"])}" target="_blank" rel="noopener">'
                    f'{_hero_img(h, "gc-hero-img-sm")}'
                    f'<div class="gc-hero-kicker">{_hero_kicker(h)}</div>'
                    f'<div class="gc-hero-title-sm">{html.escape(h["title"])}</div></a>',
                    unsafe_allow_html=True)
    st.write("")

# ---- セクター別の記事件数サマリー（上部タブ的な俯瞰） ----
counts = defaultdict(int)
for a in all_articles:
    if a["scores"]:
        counts[a["scores"][0][0]] += 1

if counts:
    st.markdown("##### セクター別ヒートマップ（今読み込んでいる記事の主軸分布）")
    items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    _max = max(c for _, c in items) or 1
    rows = ""
    for sec, c in items:
        color = SECTORS.get(sec, {}).get("color", "#666")
        pct = int(c / _max * 100)
        rows += (
            '<div class="gc-bar-row">'
            f'<div class="gc-bar-label">{sec}</div>'
            f'<div class="gc-bar-track"><div class="gc-bar-fill" '
            f'style="width:{pct}%;background:{color};"></div></div>'
            f'<div class="gc-bar-val">{c}</div>'
            '</div>'
        )
    st.markdown(f'<div class="gc-bars">{rows}</div>', unsafe_allow_html=True)
    st.write("")

if errors:
    # 「本当の取得失敗」と「取得できたが0件」を分けて、簡潔に状況を伝える
    real_fail = [e for e in errors if "記事0件" not in e]
    empty_only = [e for e in errors if "記事0件" in e]
    if not all_articles:
        st.warning("記事を取得できませんでした。各フィードの状況は以下のとおりです：")
        for e in errors:
            st.text("• " + e)
    else:
        head = []
        if real_fail:
            head.append(f"取得失敗 {len(real_fail)}件")
        if empty_only:
            head.append(f"0件 {len(empty_only)}件")
        with st.expander("⚠️ フィードの状況（" + " / ".join(head) + "）"):
            if real_fail:
                st.caption("取得に失敗したフィード（一時的な可能性あり。再取得で回復することがあります）")
                for e in real_fail:
                    st.text("• " + e)
            if empty_only:
                st.caption("取得はできたが記事が0件だったフィード")
                for e in empty_only:
                    st.text("• " + e)

_cap = f"📰 {len(all_articles)} 件の記事"
if _dupes_removed:
    _cap += f"（重複 {_dupes_removed} 件を除外）"
st.caption(_cap)

# 全文取得済みリンクを保持（都度取得・セッション内で記憶）
if "fulltext" not in st.session_state:
    st.session_state.fulltext = set()

# ---- 記事カード一覧 ----
_current_sector = None
for idx, a in enumerate(all_articles):
    # セクター別表示のときは、グループの切れ目に見出しを出す
    if sort_order == "セクター別" and a["primary"] != _current_sector:
        _current_sector = a["primary"]
        _c = SECTORS.get(_current_sector, {}).get("color", "#888")
        st.markdown(
            f'<h3 style="margin:18px 0 6px 0;border-bottom:2px solid {_c};'
            f'display:inline-block;padding-bottom:2px;">{_current_sector}</h3>',
            unsafe_allow_html=True)

    link = a["link"]
    teaser = a["summary"]

    # この記事を全文取得済みか？取得済みなら本文を使い、分類も本文で再計算する
    body_text, body_reason = "", None
    if link in st.session_state.fulltext:
        body_text, body_reason = fetch_article_body(link)

    if body_text:
        analysis_text = f"{a['title']}. {body_text}"
        read_len = len(body_text)
        read_label = "📄 全文取得"
    else:
        analysis_text = f"{a['title']}. {teaser}"
        read_len = len(teaser)
        read_label = "📄 RSS概要のみ"

    scores = classify_sectors(analysis_text)
    primary = scores[0][0] if scores else "未分類"
    primary_color = SECTORS.get(primary, {}).get("color", "#444")

    # ---- 常時表示の「キッカー」（見出し上の小見出し）: セクター・出典・効く度・読込状態 ----
    meta_date = a['published'].strftime('%m/%d %H:%M') if a['published'] != dt.datetime.min else ''
    impact_val = int(round(a.get("impact", 0)))
    sec_chips = "".join(
        f'<span class="gc-meta-sec" style="background:{SECTORS[s]["color"]};'
        f'color:{_chip_text_color(SECTORS[s]["color"])};">{s}</span>'
        for s, _ in scores[:2]
    )
    st.markdown(
        f'<div class="gc-meta">{sec_chips}'
        f'<span class="gc-meta-txt">{html.escape(a["source"])} · {meta_date}'
        f' · ⚡{impact_val} · {read_label}</span></div>',
        unsafe_allow_html=True)

    # 画像は「今日の主役」カードに集約。リストはテキスト中心ですっきり保つ。

    # タイトル自体を展開バーにして、カードと要約を一体化する
    with st.expander(a["title"]):

        # セクターチップ（全スコア）
        chips = ""
        for sec, sc in scores[:4]:
            color = SECTORS[sec]["color"]
            chips += f'<span class="gc-chip" style="background:{color};color:{_chip_text_color(color)};">{sec} {sc}</span>'
        if chips:
            st.markdown(chips, unsafe_allow_html=True)

        if True:

            # --- 全文取得のコントロール ---
            if body_text:
                st.success(f"本文を取得済み（{read_len:,}字）。要約・分類はこの本文に基づきます。")
            elif body_reason:
                st.warning(f"全文取得を試みましたが失敗しました: {body_reason}")
            if not body_text and is_free_fulltext(link):
                if st.button("📄 全文を取得して再分析", key=f"ft_{idx}"):
                    st.session_state.fulltext.add(link)
                    st.rerun()
            elif not body_text and link and not is_free_fulltext(link):
                st.caption("※ このメディアは有料の壁、またはGoogle News経由のリンクのため全文取得の対象外です（RSS概要のみ）。")

            # === AI要約モード（Gemini API） ===
            if use_ai:
                if not api_key:
                    st.info("サイドバーで GEMINI_API_KEY を入力するとAI要約が有効になります。")
                else:
                    with st.spinner("Global Chain Radio 形式で分析中…"):
                        result = gemini_analysis(analysis_text, a["title"], api_key, ai_model)
                    if "error" in result:
                        st.error(f"AI要約エラー: {result['error']}")
                    else:
                        st.markdown(f"**🎙️ Today's Theme**　{result.get('theme','')}")

                        # 🔗 連鎖（CHAIN）— このアプリの主役
                        chain = result.get("chain", [])
                        if chain:
                            tone = result.get("risk_tone", "")
                            tone_color = ("#27ae60" if "オン" in tone
                                          else "#c0392b" if "オフ" in tone else "#8a8f78")
                            steps = '<span style="color:#8a3a2e;font-weight:700;"> → </span>'.join(
                                html.escape(str(s)) for s in chain)
                            tone_badge = (f'<span style="background:{tone_color};color:#fff;'
                                          f'font-size:.7rem;padding:2px 8px;border-radius:3px;'
                                          f'font-family:IBM Plex Mono,monospace;">{html.escape(tone)}</span>'
                                          if tone else "")
                            st.markdown(
                                f'<div class="gc-chain"><b>🔗 連鎖（CHAIN）</b>　{tone_badge}'
                                f'<div class="gc-chain-body">{steps}</div></div>',
                                unsafe_allow_html=True)

                        secs = "・".join(result.get("sectors", []))
                        if secs:
                            st.markdown(f"**波及セクター**：{secs}")

                        impl = result.get("index_implication", "")
                        if impl:
                            st.markdown(
                                f'<div class="gc-essence"><b>📊 インデックス投資家への含意</b><br>'
                                f'{html.escape(impl)}</div>',
                                unsafe_allow_html=True)
                        if link:
                            st.markdown(f"[原文を読む ↗]({link})")

            # === 抽出要約モード（無料・APIなし） ===
            if not use_ai:
                summary, status = heuristic_summary(analysis_text)
                if status == "thin":
                    st.markdown("**📝 要約**")
                    st.caption("本文がほとんど取得できていないため要約できません（実質、見出しのみ）。"
                               "上の『全文を取得』が使えるメディアなら取得すると要約できます。")
                    if summary:
                        st.markdown(f"> {summary}")
                else:
                    st.markdown("**📝 要約（読み込めた本文からの抽出・文章形式）**")
                    st.markdown(summary)
                    st.caption("※ これは原文の重要文をつないだ抽出要約です。"
                               "グローバルチェーン視点での再構成はサイドバーのAI要約をご利用ください。")

                st.markdown(
                    f'<div class="gc-essence"><b>THE ESSENCE — 波及セクター</b><br>'
                    f'{hypothesis_hint(scores)}</div>',
                    unsafe_allow_html=True)

                # Gemini / ChatGPT 等に貼り付けて、無料で「翻訳＋GCR形式要約」を作るためのプロンプト
                st.markdown("**🤖 無料で翻訳＋要約（Gemini / ChatGPT 用）**")
                prompt_text = body_text if body_text else teaser
                full_prompt = build_llm_prompt(a["title"], prompt_text, link)
                copy_button(full_prompt, key=str(idx))
                st.caption("コピー → Gemini や ChatGPT に貼り付けるだけ。"
                           "全文取得済みの記事ほど、訳・要約の質が上がります。")
                if st.checkbox("プロンプトの中身を見る", key=f"pp_{idx}"):
                    st.code(full_prompt, language="text")

                if link:
                    st.markdown(f"[原文を読む ↗]({link})")

if not all_articles and not errors:
    st.info("サイドバーでメディアを選び、「最新を再取得」を押してください。")
