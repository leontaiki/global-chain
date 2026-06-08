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
    # 概要のみ（マクロ・金融の見出しカバー用。本文はペイウォール）
    {"name": "Foreign Affairs",      "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "The Economist – Finance", "url": "https://www.economist.com/finance-and-economics/rss.xml"},
    {"name": "Reuters (見出しのみ)", "url": "https://news.google.com/rss/search?q=when:24h+site:reuters.com&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bloomberg (見出しのみ)", "url": "https://news.google.com/rss/search?q=when:24h+site:bloomberg.com&hl=en-US&gl=US&ceid=US:en"},
]
# 注: The Guardian と NPR は本文が完全無料で取得しやすく、全文取得の主力です。
#     BBC・Al Jazeera も多くが取得可。NYT はメーター制のため記事により部分取得。
#     FT/Bloomberg/Economist は本文ペイウォールのため概要のみ運用です。


# --- 18セクター定義 -----------------------------------------------------------
# 企画書 "Global Chain Radio" の全18分野。
# keywords: 記事の見出し・本文から拾う英語/日本語キーワード（小文字で照合）
SECTORS = {
    "政治":       {"en": "Politics",      "color": "#c0392b",
                   "keywords": ["election", "parliament", "congress", "senate", "vote", "democracy",
                                "policy", "government", "minister", "president", "coalition", "populis",
                                "referendum", "政治", "選挙", "政権"]},
    "経済":       {"en": "Economy",       "color": "#d35400",
                   "keywords": ["inflation", "gdp", "recession", "growth", "unemployment", "wages",
                                "consumer", "cpi", "deflation", "stimulus", "tariff", "trade deficit",
                                "経済", "物価", "景気"]},
    "金融":       {"en": "Finance",       "color": "#e67e22",
                   "keywords": ["fed", "central bank", "rate", "yield", "bond", "treasury", "dollar",
                                "currency", "stock", "equit", "credit", "bank", "liquidity", "ipo",
                                "hedge fund", "金利", "為替", "債券", "株"]},
    "保険":       {"en": "Insurance",     "color": "#16a085",
                   "keywords": ["insurance", "insurer", "reinsur", "actuari", "premium", "underwrit",
                                "claims", "pension fund", "保険", "年金"]},
    "医療":       {"en": "Healthcare",    "color": "#27ae60",
                   "keywords": ["healthcare", "hospital", "drug", "pharma", "fda", "clinical", "patient",
                                "medicine", "therapy", "biotech", "vaccine", "医療", "病院", "薬"]},
    "公衆衛生":   {"en": "Public Health",  "color": "#2ecc71",
                   "keywords": ["pandemic", "epidemic", "outbreak", "obesity", "mental health", "who",
                                "public health", "disease", "infection", "感染", "公衆衛生"]},
    "食糧":       {"en": "Food",          "color": "#f1c40f",
                   "keywords": ["wheat", "grain", "food security", "crop", "harvest", "famine",
                                "fertilizer", "commodity", "食糧", "穀物", "小麦"]},
    "農業":       {"en": "Agriculture",   "color": "#a4b400",
                   "keywords": ["farm", "agricultur", "irrigation", "livestock", "soybean", "subsid",
                                "land use", "農業", "農地"]},
    "エネルギー": {"en": "Energy",         "color": "#e74c3c",
                   "keywords": ["oil", "gas", "opec", "crude", "lng", "nuclear", "renewable", "solar",
                                "wind power", "grid", "electricity", "power plant", "uranium",
                                "石油", "原子力", "電力", "エネルギー"]},
    "テック":     {"en": "Technology",    "color": "#3498db",
                   "keywords": ["ai", "artificial intelligence", "semiconductor", "chip", "nvidia",
                                "cloud", "data center", "software", "tech", "quantum", "robot",
                                "半導体", "クラウド"]},
    "宇宙":       {"en": "Space",         "color": "#34495e",
                   "keywords": ["satellite", "space", "spacex", "nasa", "orbit", "rocket", "launch",
                                "gps", "starlink", "衛星", "宇宙"]},
    "軍事":       {"en": "Military",      "color": "#7f8c8d",
                   "keywords": ["military", "defense", "defence", "weapon", "missile", "army", "navy",
                                "war", "conflict", "nato", "troops", "arms", "軍", "兵器", "防衛"]},
    "外交":       {"en": "Diplomacy",     "color": "#2980b9",
                   "keywords": ["diplomacy", "summit", "treaty", "sanction", "alliance", "bilateral",
                                "embassy", "negotiation", "g7", "g20", "外交", "制裁", "条約"]},
    "不動産":     {"en": "Real Estate",   "color": "#8e44ad",
                   "keywords": ["real estate", "property", "housing", "mortgage", "office vacancy",
                                "reit", "rent", "construction", "不動産", "住宅"]},
    "アート":     {"en": "Art",           "color": "#9b59b6",
                   "keywords": ["art", "auction", "sotheby", "christie", "museum", "gallery", "painting",
                                "美術", "アート"]},
    "ファッション":{"en": "Fashion",       "color": "#e84393",
                   "keywords": ["fashion", "luxury", "lvmh", "apparel", "cotton", "textile", "brand",
                                "ファッション", "ブランド"]},
    "カルチャー": {"en": "Culture",       "color": "#fd79a8",
                   "keywords": ["culture", "anime", "k-pop", "kpop", "film", "movie", "game", "gaming",
                                "streaming", "music", "soft power", "文化", "アニメ"]},
    "地域":       {"en": "Local",         "color": "#636e72",
                   "keywords": ["rural", "aging", "depopulation", "local economy", "vacant", "decline",
                                "regional", "地方", "高齢化", "過疎"]},
}


# =============================================================================
# 2. RSS取得（キャッシュ付き）
# =============================================================================

# 多くのメディア（Google News, NYT 等）は名乗り(User-Agent)が無いと
# アクセスを弾くため、ブラウザらしいヘッダを付けて取得する。
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")

# Mac等でよく起きる SSL: CERTIFICATE_VERIFY_FAILED を防ぐため、
# certifi のルート証明書を使ったSSLコンテキストを用意する。
import ssl
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


@st.cache_data(ttl=900, show_spinner=False)  # 15分キャッシュ
def fetch_feed(url: str):
    """単一フィードを取得して (記事リスト, ステータス文字列) を返す。
    ステータスは None=正常、それ以外は理由（HTTPエラーや空など）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read()
        parsed = feedparser.parse(raw)
        entries = []
        for e in parsed.entries:
            entries.append({
                "title": e.get("title", "(no title)"),
                "link": e.get("link", ""),
                "summary": _strip_html(e.get("summary", e.get("description", ""))),
                "published": _parse_time(e),
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
)


def is_free_fulltext(link: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(link).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in FREE_FULLTEXT_DOMAINS)


@st.cache_data(ttl=3600, show_spinner=False)  # 1時間キャッシュ
def fetch_article_body(url: str):
    """記事ページから本文を抽出して (本文テキスト, 理由) を返す。
    取れなければ ('', 理由)。標準ライブラリのみで実装（依存を増やさない）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read(800_000)  # 先頭800KBまで（巨大ページ対策）
        h = raw.decode("utf-8", errors="ignore")

        # 1) og:description / meta description（記事の要旨が入っていることが多い）
        meta = ""
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]*content=["\']([^"\']+)',
            h, re.I)
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:description|description)',
                h, re.I)
        if m:
            meta = html.unescape(m.group(1)).strip()

        # 2) <p> 段落のうち、ある程度の長さ（=本文らしい）ものだけ連結
        paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S | re.I)
        body_parts = []
        for p in paras:
            t = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
            if len(t) >= 40:
                body_parts.append(t)
        body = " ".join(body_parts)

        combined = (meta + " " + body).strip() if meta else body
        if len(combined) < 80:
            return "", "本文を十分に抽出できませんでした（ペイウォール等の可能性）"
        return combined[:6000], None  # 長すぎる場合は先頭6000字に制限
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
    """記事テキストを18セクターに対しスコアリングし、(sector, score) を降順で返す。"""
    low = text.lower()
    scores = []
    for jp, meta in SECTORS.items():
        score = 0
        for kw in meta["keywords"]:
            k = kw.lower()
            # 英数字のみのキーワードは「単語の区切り」で一致（ai が AIDS に誤一致しないように）
            if re.fullmatch(r"[a-z0-9 \-]+", k):
                score += len(re.findall(r"\b" + re.escape(k) + r"\b", low))
            else:
                # 日本語など（語境界の概念がない）は従来どおり部分一致
                score += low.count(k)
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
# 3a. 引き算エンジン（フェーズ1）— 「今日効く度」スコアとリスクトーン
#     広めのマクロ観測モード：18セクターを満遍なく拾いつつ、マクロ感応度で重み付け。
# =============================================================================

# マクロ（特に市場全体）への効きやすさ。アートやファッションは0でも、分類自体は残る。
MACRO_WEIGHT = {
    "金融": 3, "経済": 3, "エネルギー": 3, "軍事": 2, "外交": 2, "テック": 2,
    "公衆衛生": 1, "食糧": 1, "農業": 1, "政治": 1, "宇宙": 1, "保険": 1,
    "医療": 1, "不動産": 1, "地域": 1, "アート": 0, "ファッション": 0, "カルチャー": 0,
}
# 市場を動かす「シグナル語」。リスクオフ＝不安、リスクオン＝楽観の方向。
RISK_OFF_WORDS = ["war", "conflict", "sanction", "crisis", "crash", "recession",
                  "default", "attack", "invasion", "inflation", "rate hike",
                  "tariff", "shortage", "strike", "tension", "escalat"]
RISK_ON_WORDS = ["rate cut", "ceasefire", "truce", "deal", "stimulus", "rally",
                 "recovery", "easing", "breakthrough", "agreement"]
NOTABLE_THRESHOLD = 6  # これ以上を「今日効く記事」とみなす


def impact_score(title: str, summary: str, scores):
    """記事の『今日効く度』を返す。 (score, risk_off回数, risk_on回数)"""
    text = f"{title} {summary}".lower()
    s = 0.0
    for sec, _ in scores[:3]:
        s += MACRO_WEIGHT.get(sec, 0)
    off = sum(text.count(k) for k in RISK_OFF_WORDS)
    on = sum(text.count(k) for k in RISK_ON_WORDS)
    s += (off + on) * 1.5
    if len(scores) >= 3:
        s += 2          # 連鎖が広い（複数セクターにまたがる）ほど重要
    elif len(scores) >= 2:
        s += 1
    return s, off, on


def daily_brief(articles):
    """画面最上部の一行サマリー用に、注目件数とリスクトーンを集計して返す。"""
    notable = [a for a in articles if a.get("impact", 0) >= NOTABLE_THRESHOLD]
    off = sum(a.get("risk_off", 0) for a in notable)
    on = sum(a.get("risk_on", 0) for a in notable)
    if on > off * 1.3:
        tone, color = "リスクオン寄り", "#27ae60"
    elif off > on * 1.3:
        tone, color = "リスクオフ寄り", "#c0392b"
    else:
        tone, color = "中立", "#8a8f78"
    return notable, tone, color


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
            generation_config={"temperature": 0.4, "max_output_tokens": 900},
        )
        out = (resp.text or "").replace("```json", "").replace("```", "").strip()
        import json
        return json.loads(out)
    except Exception as ex:  # noqa: BLE001
        return {"error": str(ex)}


# =============================================================================
# 4. 画面構成 — Streamlit UI
# =============================================================================

st.set_page_config(page_title="Global Chain — Macro Intelligence",
                   page_icon="🌐", layout="wide")

# ---- カスタムCSS（エディトリアル/ターミナル風の落ち着いた配色） ----
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ---- 全体：紙のようなクリーム背景 + インク色の文字 ---- */
.stApp { background: #f4efe3; color: #23201a; }
[data-testid="stMain"] { background: #f4efe3; }

/* 上部ヘッダー/ツールバーは残しつつ、黒い背景だけ紙色にする（機能は維持） */
[data-testid="stHeader"] { background: #f4efe3 !important; }
[data-testid="stToolbar"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #ebe4d3; border-right: 1px solid #d8cfb8; }
[data-testid="stSidebar"] * { color: #2c281f; }
.stApp p, .stApp li, .stApp span, .stApp label, .stMarkdown { color: #3a342a; }

h1, h2, h3, h4 { font-family: 'Spectral', serif; color: #1c1813 !important;
                 letter-spacing: .2px; }

/* ---- ヘッダー ---- */
.gc-title { font-size: 2.3rem; font-weight: 800; margin-bottom: 2px; color: #1c1813; }
.gc-sub { color: #8a3a2e; font-family: 'IBM Plex Mono', monospace;
          font-size: .78rem; letter-spacing: 3px; text-transform: uppercase; font-weight: 500; }

/* ---- 記事カード：紙の上の一段明るいカード ---- */
.gc-card { background: #fbf8f0; border: 1px solid #e0d7c2;
           border-left: 3px solid #c9bfa6; border-radius: 4px;
           padding: 14px 20px; margin-bottom: 10px;
           box-shadow: 0 1px 2px rgba(60,50,30,.06); transition: border-color .15s; }
.gc-card:hover { border-left-color: #8a3a2e; }
.gc-source { font-family: 'IBM Plex Mono', monospace; font-size: .68rem;
             color: #9a8f78; text-transform: uppercase; letter-spacing: 1.5px; }
.gc-headline { font-family: 'Spectral', serif; font-size: 1.15rem; color: #1c1813;
               line-height: 1.35; margin: 5px 0 0 0; font-weight: 600; }

/* ---- セクターチップ ---- */
.gc-chip { display: inline-block; font-family: 'IBM Plex Mono', monospace;
           font-size: .68rem; padding: 3px 9px; border-radius: 3px; margin: 2px 4px 2px 0;
           font-weight: 600; letter-spacing: .3px; }

/* ---- THE ESSENCE ボックス ---- */
.gc-essence { background: #f3ece0; border: 1px solid #d8cdb4;
              border-left: 3px solid #8a3a2e; border-radius: 4px;
              padding: 13px 17px; margin-top: 10px; }
.gc-essence b { color: #8a3a2e; font-family: 'IBM Plex Mono', monospace; font-size: .7rem;
                letter-spacing: 1.5px; }
.gc-essence { color: #3a342a; }

/* ---- 区切り線を細いインク色に ---- */
hr { border-color: #d8cfb8 !important; }

/* ---- フェーズ1: 一行サマリー（5秒で結論） ---- */
.gc-brief { background: #fbf8f0; border: 1px solid #e0d7c2; border-left: 5px solid #8a8f78;
            border-radius: 5px; padding: 13px 18px; margin: 4px 0 14px 0;
            font-size: 1.02rem; color: #2a261f; box-shadow: 0 1px 3px rgba(60,50,30,.08); }
.gc-brief-tone { font-family: 'IBM Plex Mono', monospace; font-weight: 600;
                 font-size: .82rem; letter-spacing: .5px; }
.gc-brief-sub { font-size: .8rem; color: #6b6354; margin-top: 5px;
                font-family: 'Spectral', serif; }

/* ---- フェーズ2: 連鎖（CHAIN）表示 ---- */
.gc-chain { background: #f7f1e4; border: 1px solid #d8cdb4; border-left: 4px solid #8a3a2e;
            border-radius: 5px; padding: 13px 17px; margin: 8px 0; }
.gc-chain b { color: #8a3a2e; font-family: 'IBM Plex Mono', monospace; font-size: .74rem;
              letter-spacing: 1px; }
.gc-chain-body { margin-top: 8px; font-family: 'Spectral', serif; font-size: 1.02rem;
                 line-height: 1.7; color: #2a261f; }

/* ---- 記事＝展開バーを一体型カードに ---- */
[data-testid="stExpander"] { background: #fbf8f0; border: 1px solid #e0d7c2 !important;
                             border-left: 3px solid #8a3a2e !important; border-radius: 4px;
                             margin-bottom: 9px; box-shadow: 0 1px 2px rgba(60,50,30,.06); }
[data-testid="stExpander"] summary { padding: 12px 16px; }
[data-testid="stExpander"] summary p { font-family: 'Spectral', serif !important;
                                       font-size: 1.12rem !important; font-weight: 600 !important;
                                       color: #1c1813 !important; line-height: 1.35; }
[data-testid="stExpander"] summary:hover p { color: #8a3a2e !important; }

/* ---- スマホ対応：狭い画面でタイトル縮小・余白調整・チップ折返し ---- */
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

    if "feeds" not in st.session_state:
        st.session_state.feeds = list(DEFAULT_FEEDS)

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

    st.divider()
    st.subheader("🤖 AI要約（Gemini API）")
    use_ai = st.toggle("本物のAI要約をONにする", value=False,
                       help="グローバルチェーン視点で記事を再構成します。Gemini無料枠（1日1,500回）の範囲なら無料です。")
    api_key = ""
    ai_model = "gemini-2.5-flash"
    if use_ai:
        import os as _os
        api_key = st.text_input("GEMINI_API_KEY", type="password",
                                value=_os.environ.get("GEMINI_API_KEY", ""),
                                help="Google AI Studio (aistudio.google.com) で無料発行。環境変数 GEMINI_API_KEY があれば自動入力されます。")
        ai_model = st.selectbox("モデル",
                                ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
                                index=0,
                                help="無料枠はFlash系のみ。Flash=高品質 / Flash-Lite=高速・軽量")
        st.caption("💡 無料枠（1日1,500回・毎分15回）の範囲なら課金なし。"
                   "ただし無料枠は入力がGoogleのモデル改善に使われる場合があります。")

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
        imp, off, on = impact_score(e["title"], e["summary"], scores)
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
_notable_all, _tone, _tone_color = daily_brief(all_articles)

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
    all_articles = [a for a in all_articles if a.get("impact", 0) >= NOTABLE_THRESHOLD]

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
        top_titles = " ／ ".join(html.escape(a["title"][:46]) for a in _notable_all[:3])
        st.markdown(
            f'<div class="gc-brief" style="border-left-color:{_tone_color};">'
            f'<span class="gc-brief-tone" style="color:{_tone_color};">● 全体トーン: {_tone}</span>'
            f'　今日の注目 <b>{n_notable}</b> 件'
            f'<div class="gc-brief-sub">主役の連鎖候補: {top_titles}</div></div>',
            unsafe_allow_html=True)

# ---- セクター別の記事件数サマリー（上部タブ的な俯瞰） ----
counts = defaultdict(int)
for a in all_articles:
    if a["scores"]:
        counts[a["scores"][0][0]] += 1

if counts:
    st.markdown("##### セクター別ヒートマップ（今読み込んでいる記事の主軸分布）")
    cols = st.columns(6)
    items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for i, (sec, c) in enumerate(items):
        color = SECTORS.get(sec, {}).get("color", "#666")
        with cols[i % 6]:
            st.markdown(
                f'<div class="gc-chip" style="background:{color};color:{_chip_text_color(color)};">{sec} · {c}</div>',
                unsafe_allow_html=True)
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

    # タイトル自体を展開バーにして、カードと要約を一体化する
    with st.expander(a["title"]):

        # メタ情報（出典・日時・読込文字数）
        meta_date = a['published'].strftime('%m/%d %H:%M') if a['published'] != dt.datetime.min else ''
        st.markdown(
            f'<div class="gc-source">{html.escape(a["source"])} · {meta_date} · {read_label}: {read_len:,}字</div>',
            unsafe_allow_html=True)

        # セクターチップ
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
