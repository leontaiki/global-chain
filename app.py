# -*- coding: utf-8 -*-
"""
Global Chain — Macro Intelligence Dashboard (Gemini Free Tier Optimized)
========================================================================
世界の主要メディアのRSSを集約し、18セクターへ自動分類・市場への因果の連鎖を紡ぐ
マクロ／インデックス投資家向け自分用ダッシュボード。

実行方法:
    pip install -r requirements.txt
    streamlit run app.py
"""

import re
import html
import time
import json
import os
import datetime as dt
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components
import feedparser

# =============================================================================
# 1. 初期設定 — RSSフィードと18セクターの定義
# =============================================================================

DEFAULT_FEEDS = [
    {"name": "The Guardian – World", "url": "https://www.theguardian.com/world/rss"},
    {"name": "BBC – World",          "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "BBC – Business",       "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "NPR – World",          "url": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "Al Jazeera",           "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "NYT – World",          "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "Foreign Affairs",      "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "The Economist – Finance", "url": "https://www.economist.com/finance-and-economics/rss.xml"},
    {"name": "Reuters (見出しのみ)", "url": "https://news.google.com/rss/search?q=when:24h+site:reuters.com&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bloomberg (見出しのみ)", "url": "https://news.google.com/rss/search?q=when:24h+site:bloomberg.com&hl=en-US&gl=US&ceid=US:en"},
]

SECTORS = {
    "政治":       {"en": "Politics",      "color": "#c0392b", "macro_weight": 1,
                   "keywords": ["election", "parliament", "congress", "senate", "vote", "democracy", "policy", "government", "minister", "president", "coalition", "populis", "referendum", "政治", "選挙", "政権"]},
    "経済":       {"en": "Economy",       "color": "#d35400", "macro_weight": 1,
                   "keywords": ["inflation", "gdp", "recession", "growth", "unemployment", "wages", "consumer", "cpi", "deflation", "stimulus", "tariff", "trade deficit", "経済", "物価", "景気"]},
    "金融":       {"en": "Finance",       "color": "#e67e22", "macro_weight": 1,
                   "keywords": ["fed", "central bank", "rate", "yield", "bond", "treasury", "dollar", "currency", "stock", "equit", "credit", "bank", "liquidity", "ipo", "hedge fund", "金利", "為替", "債券", "株"]},
    "保険":       {"en": "Insurance",     "color": "#16a085", "macro_weight": 0,
                   "keywords": ["insurance", "insurer", "reinsur", "actuari", "premium", "underwrit", "claims", "pension fund", "保険", "年金"]},
    "医療":       {"en": "Healthcare",    "color": "#27ae60", "macro_weight": 0,
                   "keywords": ["healthcare", "hospital", "drug", "pharma", "fda", "clinical", "patient", "medicine", "therapy", "biotech", "vaccine", "医療", "病院", "薬"]},
    "公衆衛生":   {"en": "Public Health",  "color": "#2ecc71", "macro_weight": 0,
                   "keywords": ["pandemic", "epidemic", "outbreak", "obesity", "mental health", "who", "public health", "disease", "infection", "感染", "公衆衛生"]},
    "食糧":       {"en": "Food",          "color": "#f1c40f", "macro_weight": 1,
                   "keywords": ["wheat", "grain", "food security", "crop", "harvest", "famine", "fertilizer", "commodity", "食糧", "穀物", "小麦"]},
    "農業":       {"en": "Agriculture",   "color": "#a4b400", "macro_weight": 0,
                   "keywords": ["farm", "agricultur", "irrigation", "livestock", "soybean", "subsid", "land use", "農業", "農地"]},
    "エネルギー": {"en": "Energy",         "color": "#e74c3c", "macro_weight": 1,
                   "keywords": ["oil", "gas", "opec", "crude", "lng", "nuclear", "renewable", "solar", "wind power", "grid", "electricity", "power plant", "uranium", "石油", "原子力", "電力", "エネルギー"]},
    "テック":     {"en": "Technology",    "color": "#3498db", "macro_weight": 1,
                   "keywords": ["ai", "artificial intelligence", "semiconductor", "chip", "nvidia", "cloud", "data center", "software", "tech", "quantum", "robot", "半導体", "クラウド"]},
    "宇宙":       {"en": "Space",         "color": "#34495e", "macro_weight": 0,
                   "keywords": ["satellite", "space", "spacex", "nasa", "orbit", "rocket", "launch", "gps", "starlink", "衛星", "宇宙"]},
    "軍事":       {"en": "Military",      "color": "#7f8c8d", "macro_weight": 1,
                   "keywords": ["military", "defense", "defence", "weapon", "missile", "army", "navy", "war", "conflict", "nato", "troops", "arms", "軍", "兵器", "防衛"]},
    "外交":       {"en": "Diplomacy",     "color": "#2980b9", "macro_weight": 1,
                   "keywords": ["diplomacy", "summit", "treaty", "sanction", "alliance", "bilateral", "embassy", "negotiation", "g7", "g20", "外交", "制裁", "条約"]},
    "不動産":     {"en": "Real Estate",   "color": "#8e44ad", "macro_weight": 0,
                   "keywords": ["real estate", "property", "housing", "mortgage", "office vacancy", "reit", "rent", "construction", "不動産", "住宅"]},
    "アート":     {"en": "Art",           "color": "#9b59b6", "macro_weight": 0,
                   "keywords": ["art", "auction", "sotheby", "christie", "museum", "gallery", "painting", "美術", "アート"]},
    "ファッション":{"en": "Fashion",       "color": "#e84393", "macro_weight": 0,
                   "keywords": ["fashion", "luxury", "lvmh", "apparel", "cotton", "textile", "brand", "ファッション", "ブランド"]},
    "カルチャー": {"en": "Culture",       "color": "#fd79a8", "macro_weight": 0,
                   "keywords": ["culture", "anime", "k-pop", "kpop", "film", "movie", "game", "gaming", "streaming", "music", "soft power", "文化", "アニメ"]},
    "地域":       {"en": "Local",         "color": "#636e72", "macro_weight": 0,
                   "keywords": ["rural", "aging", "depopulation", "local economy", "vacant", "decline", "regional", "地方", "高齢化", "過疎"]},
}

# =============================================================================
# 2. RSS取得（キャッシュ・重複除去・SSL設定）
# =============================================================================

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

import ssl
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

@st.cache_data(ttl=900, show_spinner=False)
def fetch_feed(url: str):
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
            return [], "記事0件"
        return entries, None
    except Exception as ex:
        return [], str(ex)

FREE_FULLTEXT_DOMAINS = ("bbc.co.uk", "bbc.com", "nytimes.com", "apnews.com", "npr.org", "theguardian.com", "reuters.com", "aljazeera.com")

def is_free_fulltext(link: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(link).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in FREE_FULLTEXT_DOMAINS)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_article_body(url: str):
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read(800_000)
        h = raw.decode("utf-8", errors="ignore")
        
        meta = ""
        # 書き出しのデコードバグを完全に回避するため、外側をダブルクォートのraw文字列にし、バックスラッシュを二重エスケープ
        m = re.search(r"<meta[^>]+(property|name)=[\\x22\\x27](og:description|description)[\\x22\\x27][^>]*content=[\\x22\\x27]([^\\x22\\x27]+)", h, re.I)
        if m: meta = html.unescape(m.group(3)).strip()

        paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S | re.I)
        body_parts = []
        for p in paras:
            t = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
            if len(t) >= 40: body_parts.append(t)
        body = " ".join(body_parts)

        combined = (meta + " " + body).strip() if meta else body
        if len(combined) < 80:
            return "", "本文を十分に抽出できませんでした（ペイウォール等の可能性）"
        return combined[:6000], None
    except Exception as ex:
        return "", str(ex)

def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

def _parse_time(entry) -> dt.datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try: return dt.datetime.fromtimestamp(time.mktime(t))
            except: pass
    return dt.datetime.min

def _chip_text_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    try: r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except: return "#fdfbf6"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1c1813" if luminance > 0.6 else "#fdfbf6"

def classify_sectors(text: str):
    low = text.lower()
    scores = []
    for jp, meta in SECTORS.items():
        score = 0
        for kw in meta["keywords"]:
            k = kw.lower()
            if re.fullmatch(r"[a-z0-9 \-]+", k):
                score += len(re.findall(r"" + re.escape(k) + r"", low))
            else:
                score += low.count(k)
        if score > 0:
            scores.append((jp, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores

# =============================================================================
# 3. Gemini API 連携層 (無料枠・JSON Structured Output 最適化)
# =============================================================================

@st.cache_data(ttl=1800, show_spinner=False)
def generate_macro_summary(articles_text: str, api_key: str):
    if not api_key:
        return {
            "regime": "API KEY REQUIRED",
            "chain": "サイドバーで GEMINI_API_KEY を入力すると、今日動くべきかどうかのマクロ連鎖サマリーがここに自動生成されます。",
            "action": "NO CHANGE"
        }
    
    prompt = f"""
    You are a world-class macro investor and a product designer like Steve Jobs. 
    Analyze today's news headlines, filter out the noise, and extract the absolute essence for a long-term index investor.
    Determine whether there is a true macro regime shift today or if investors should do nothing.

    CRITICAL RULES:
    1. If there are no market-shaking macro events (e.g., major geopolitical conflicts, sudden rate surprises, systemic supply chain breakdowns), you MUST set "action" to "NO CHANGE".
    2. When describing the "chain", trace the causal domino effect explicitly using arrows (➔), focusing on asset classes, inflation, rates, or macro variables.

    Respond STRICTLY in JSON format with the following keys. Do not wrap in markdown code blocks, do not write prose.
    {{
      "regime": "一言で表す現在の世界マクロ環境（例: 地政学リスク緊迫化 / リスクオン継続 / 利下げ織り込みなど）",
      "chain": "今日最も注目すべきマクロの因果関係の連鎖（例: イラン衝突 ➔ 原油供給懸念 ➔ 原油↑ ➔ インフレ再燃懸念 ➔ 金利上昇圧力 ➔ リスクオフ株売り）",
      "action": "投資家への一言（大きな地殻変動がない日は必ず 'NO CHANGE（投資方針に変更なし。本を読んで過ごしましょう）' とすること）"
    }}

    【Today's Headlines】
    {articles_text}
    """
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        return {"regime": "分析エラー", "chain": f"同期エラーまたは取得失敗: {str(e)}", "action": "ERROR"}

@st.cache_data(ttl=86400, show_spinner=False)
def gemini_analysis(text: str, title: str, api_key: str):
    if not api_key:
        return {"error": "APIキーが設定されていません。"}

    prompt = f"""
    You are the lead writer of 'Global Chain Radio', an analytical program inspired by The Economist.
    Rewrite this news item not as an isolated event, but as a dynamic vector on the global supply chain and historical patterns.
    
    Respond STRICTLY in JSON format with the following structure. No prose outside the JSON.
    {{
      "theme": "日常ニュースとマクロ視点を橋渡しする一文（40字以内）",
      "takeaways": [
        "要点1（サプライチェーンやマクロシステムの観点・60字以内）",
        "要点2",
        "要点3"
      ],
      "chain_flow": "出来事から市場・コモディティ・金利等へ至る因果のドミノ効果（例: 地政学リスク ➔ 原油供給寸断 ➔ 原油価格↑ ➔ 物価上昇圧力 ➔ 金利高止まり ➔ 債券安・株売り）",
      "essence": "投資・政策の意思決定層に真に響く、このニュースがグローバルシステム上で持つ本質的意味（120字以内）",
      "sectors": ["波及する具体的なセクターを2〜4個（例: 軍事, エネルギー, 金融）"]
    }}

    Title: {title}
    Body: {text[:5000]}
    """
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as ex:
        return {"error": str(ex)}

# =============================================================================
# 4. 画面構成 — Streamlit UI
# =============================================================================

st.set_page_config(page_title="Global Chain — Macro Intelligence", page_icon="🌐", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');
.stApp { background: #f4efe3; color: #23201a; }
[data-testid="stMain"] { background: #f4efe3; }
[data-testid="stSidebar"] { background: #ebe4d3; border-right: 1px solid #d8cfb8; }
h1, h2, h3, h4 { font-family: 'Spectral', serif; color: #1c1813 !important; }
.gc-title { font-size: 2.3rem; font-weight: 800; margin-bottom: 2px; color: #1c1813; }
.gc-sub { color: #8a3a2e; font-family: 'IBM Plex Mono', monospace; font-size: .78rem; letter-spacing: 3px; text-transform: uppercase; font-weight: 500; }
.gc-chip { display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: .68rem; padding: 3px 9px; border-radius: 3px; margin: 2px 4px 2px 0; font-weight: 600; }
.gc-essence { background: #f3ece0; border: 1px solid #d8cdb4; border-left: 3px solid #8a3a2e; border-radius: 4px; padding: 13px 17px; margin-top: 10px; }
.gc-essence b { color: #8a3a2e; font-family: 'IBM Plex Mono', monospace; font-size: .7rem; letter-spacing: 1.5px; }

.macro-box { background: #1c1813; color: #f4efe3; padding: 20px; border-radius: 6px; margin: 15px 0 25px 0; border-left: 6px solid #8a3a2e; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
.macro-regime { font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: #e67e22; letter-spacing: 2px; font-weight: bold; text-transform: uppercase; }
.macro-chain { font-family: 'Spectral', serif; font-size: 1.4rem; font-weight: 700; margin: 8px 0; color: #f4efe3; line-height: 1.4; }
.macro-action { font-size: 0.88rem; color: #bbaea1; border-top: 1px solid #332d24; padding-top: 8px; margin-top: 8px; }

[data-testid="stExpander"] { background: #fbf8f0; border: 1px solid #e0d7c2 !important; border-left: 3px solid #8a3a2e !important; border-radius: 4px; margin-bottom: 9px; }
[data-testid="stExpander"] summary p { font-family: 'Spectral', serif !important; font-size: 1.12rem !important; font-weight: 600 !important; color: #1c1813 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="gc-sub">A DOCTOR IN JAPAN READS THE WORLD AS ONE SYSTEM</div>', unsafe_allow_html=True)
st.markdown('<div class="gc-title">🌐 Global Chain — Macro Intelligence Dashboard</div>', unsafe_allow_html=True)
st.caption("世界のトップメディアからノイズを削ぎ落とし、因果の連鎖を結晶化するマクロ意思決定システム")
st.divider()

with st.sidebar:
    st.header("⚙️ システムインフラ")
    
    api_key = st.text_input("GEMINI_API_KEY", type="password", 
                            value=os.environ.get("GEMINI_API_KEY", ""),
                            help="Google AI Studioで発行した無料枠のキーを入力。空の場合は環境変数から読み込みます。")

    if "feeds" not in st.session_state:
        st.session_state.feeds = list(DEFAULT_FEEDS)

    st.subheader("📡 フィードソース制御")
    feed_labels = [f["name"] for f in st.session_state.feeds]
    active = st.multiselect("同期メディア", feed_labels, default=feed_labels)

    with st.expander("➕ フィードソース追加"):
        new_name = st.text_input("メディア名")
        new_url = st.text_input("RSS URL")
        if st.button("追加実行", use_container_width=True) and new_name and new_url:
            st.session_state.feeds.append({"name": new_name, "url": new_url})
            st.rerun()

    st.subheader("🧹 バフェット・フィルター")
    use_noise_filter = st.toggle("マクロ・ノイズカット", value=True,
                                 help="政治・経済・金融・エネルギー・軍事などの主要マクロ変数に関係のない、投資上『ノイズ』となる記事を自動でタイムラインから非表示にします。")

    if st.button("🔄 パイプラインを完全再同期", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

active_feeds = [f for f in st.session_state.feeds if f["name"] in active]
all_articles = []
errors = []
seen_titles = set()

for f in active_feeds:
    entries, err = fetch_feed(f["url"])
    if err:
        errors.append(f"{f['name']}: {err}")
    for e in entries:
        title_slug = re.sub(r'[^a-zA-Z0-9一-鿿぀-ゟ゠-ヿ]', '', e["title"].lower())[:30]
        if title_slug in seen_titles:
            continue
        seen_titles.add(title_slug)

        text = f"{e['title']}. {e['summary']}"
        scores = classify_sectors(text)
        
        e["source"] = f["name"]
        e["scores"] = scores
        e["primary"] = scores[0][0] if scores else "未分類"
        
        macro_score = sum(sc for sec, sc in scores if SECTORS.get(sec, {}).get("macro_weight", 0) == 1)
        e["macro_score"] = macro_score
        
        if use_noise_filter and macro_score == 0 and len(scores) > 0:
            continue
            
        all_articles.append(e)

all_articles.sort(key=lambda x: x["published"], reverse=True)

if all_articles:
    meta_input = "\n".join([f"- [{a['primary']}] {a['title']}" for a in all_articles[:15]])
    with st.spinner("マクロレジームを抽出中..."):
        macro_intel = generate_macro_summary(meta_input, api_key)
    
    st.markdown(f"""
    <div class="macro-box">
        <div class="macro-regime">Today's Macro Regime: {macro_intel.get('regime', 'UNKNOWN')}</div>
        <div class="macro-chain">🌐 {macro_intel.get('chain', '')}</div>
        <div class="macro-action">⚖️ <b>INVESTOR ACTION:</b> {macro_intel.get('action', 'NO CHANGE')}</div>
    </div>
    """, unsafe_allow_html=True)

col_ui1, col_ui2, col_ui3 = st.columns([2, 2, 1])
with col_ui1:
    sector_options = ["すべてのセクター"] + [f"{jp}（{m['en']}）" for jp, m in SECTORS.items()]
    selected_sector = st.selectbox("フィルター", sector_options, label_visibility="collapsed")
with col_ui2:
    sort_order = st.selectbox("ソート", ["新しい順", "セクター別", "全文取得優先"], label_visibility="collapsed")
with col_ui3:
    max_display = st.number_input("表示上限数", min_value=5, max_value=200, value=30, label_visibility="collapsed")

if sort_order == "セクター別":
    _order = {s: i for i, s in enumerate(SECTORS)}
    all_articles.sort(key=lambda x: _order.get(x["primary"], 999))
elif sort_order == "全文取得優先":
    all_articles.sort(key=lambda x: not is_free_fulltext(x["link"]))

if selected_sector != "すべてのセクター":
    target = selected_sector.split("（")[0]
    all_articles = [a for a in all_articles if any(s == target for s, _ in a["scores"])]

display_articles = all_articles[:max_display]

counts = defaultdict(int)
for a in display_articles:
    if a["scores"]: counts[a["scores"][0][0]] += 1
if counts:
    cols = st.columns(6)
    items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for i, (sec, c) in enumerate(items):
        color = SECTORS.get(sec, {}).get("color", "#666")
        with cols[i % 6]:
            st.markdown(f'<div class="gc-chip" style="background:{color};color:{_chip_text_color(color)};">{sec} · {c}</div>', unsafe_allow_html=True)
    st.write("")

if "fulltext" not in st.session_state:
    st.session_state.fulltext = set()

_current_sector = None
for idx, a in enumerate(display_articles):
    if sort_order == "セクター別" and a["primary"] != _current_sector:
        _current_sector = a["primary"]
        _c = SECTORS.get(_current_sector, {}).get("color", "#888")
        st.markdown(f'<h3 style="margin:20px 0 8px 0; border-bottom:2px solid {_c}; display:inline-block;">{_current_sector}</h3>', unsafe_allow_html=True)

    link = a["link"]
    body_text, body_reason = "", None
    if link in st.session_state.fulltext:
        body_text, body_reason = fetch_article_body(link)

    analysis_text = f"{a['title']}. {body_text if body_text else a['summary']}"
    read_label = "📄 全文ソース" if body_text else "📄 RSS概要"
    
    scores = classify_sectors(analysis_text)
    
    with st.expander(a["title"]):
        meta_date = a['published'].strftime('%m/%d %H:%M') if a['published'] != dt.datetime.min else ''
        st.markdown(f'<div class="gc-source">{html.escape(a["source"])} · {meta_date} · {read_label} ({len(analysis_text):,}字)</div>', unsafe_allow_html=True)

        chips = "".join([f'<span class="gc-chip" style="background:{SECTORS[sec]["color"]};color:{_chip_text_color(SECTORS[sec]["color"])};">{sec}</span>' for sec, _ in scores[:3]])
        if chips: st.markdown(chips, unsafe_allow_html=True)

        if not body_text and is_free_fulltext(link):
            if st.button("📥 本文をフルスクレイピングして再分析", key=f"ft_{idx}"):
                st.session_state.fulltext.add(link)
                st.rerun()

        if api_key:
            with st.spinner("Geminiがサプライチェーンの連鎖を解析中..."):
                res = gemini_analysis(analysis_text, a["title"], api_key)
            
            if "error" in res:
                st.error(f"Gemini解析エラー: {res['error']}")
            else:
                st.markdown(f"**🎙️ Today's Theme:** {res.get('theme', '')}")
                st.markdown("**3 Key Takeaways:**")
                for t in res.get("takeaways", []):
                    st.markdown(f"- {t}")
                
                st.markdown(f"""
                <div class="gc-essence">
                    <b>🔗 GLOBAL CHAIN FLOW (因果の連鎖)</b><br>
                    <span style="font-family:'IBM Plex Mono', monospace; font-size:0.9rem; color:#8a3a2e;">{res.get('chain_flow', '')}</span>
                    <br><br>
                    <b>THE ESSENCE (マクロの本質)</b><br>
                    {res.get('essence', '')}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("サイドバーで GEMINI_API_KEY を設定すると、ここにGeminiによる自動連鎖解析が完全無料で表示されます。")
            st.markdown(f"> {a['summary']}")

        if link: st.markdown(f"[Go to Original Article ↗]({link})")

if errors:
    st.write("---")
    with st.expander(f"📡 ネットワーク通信ステータス: {len(errors)}件のフィードで前回のキャッシュをサイレント適用中"):
        for err in errors:
            st.caption(f"• {err}")
"""
