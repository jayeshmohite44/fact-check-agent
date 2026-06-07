import streamlit as st
import anthropic
import pdfplumber
import json
import os
import io
import re
import time
import pandas as pd
from tavily import TavilyClient

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Fact Checker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Hero banner */
    .hero {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
        padding: 2rem 2.5rem;
        border-radius: 14px;
        color: white;
        margin-bottom: 2rem;
    }
    .hero h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .hero p  { margin: 0.4rem 0 0; opacity: 0.85; font-size: 1rem; }

    /* Verdict cards */
    .card-verified    { border-left: 5px solid #10b981; background:#f0fdf4; padding:1.1rem 1.2rem; border-radius:0 10px 10px 0; margin-bottom:1rem; }
    .card-inaccurate  { border-left: 5px solid #f59e0b; background:#fffbeb; padding:1.1rem 1.2rem; border-radius:0 10px 10px 0; margin-bottom:1rem; }
    .card-false       { border-left: 5px solid #ef4444; background:#fef2f2; padding:1.1rem 1.2rem; border-radius:0 10px 10px 0; margin-bottom:1rem; }
    .card-unverifiable{ border-left: 5px solid #9ca3af; background:#f9fafb; padding:1.1rem 1.2rem; border-radius:0 10px 10px 0; margin-bottom:1rem; }

    /* Badges */
    .badge { display:inline-block; font-size:0.78rem; font-weight:600; padding:3px 12px; border-radius:20px; }
    .badge-verified    { background:#d1fae5; color:#065f46; }
    .badge-inaccurate  { background:#fef3c7; color:#92400e; }
    .badge-false       { background:#fee2e2; color:#991b1b; }
    .badge-unverifiable{ background:#f3f4f6; color:#374151; }

    /* Upload zone */
    .upload-hint {
        text-align:center; padding:2.5rem 2rem;
        background:#f9fafb; border-radius:12px;
        border: 2px dashed #d1d5db;
    }
    .upload-hint .icon { font-size:2.8rem; margin-bottom:0.8rem; }
    .upload-hint h3 { color:#374151; margin:0 0 0.4rem; }
    .upload-hint p  { color:#6b7280; margin:0; }

    /* Metric strip */
    div[data-testid="metric-container"] {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 0.9rem 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_keys():
    """Pull keys from Streamlit secrets → env vars → empty string (fallback to UI input)."""
    ant_key = ""
    tav_key = ""
    try:
        ant_key = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
        tav_key = st.secrets.get("TAVILY_API_KEY",    os.getenv("TAVILY_API_KEY",    ""))
    except Exception:
        ant_key = os.getenv("ANTHROPIC_API_KEY", "")
        tav_key = os.getenv("TAVILY_API_KEY",    "")
    return ant_key, tav_key


def safe_json(raw: str) -> dict | list:
    """Parse JSON even if Claude wraps it in markdown fences."""
    raw = raw.strip()
    # Strip ```json … ``` or ``` … ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)
    raw = raw.strip()
    return json.loads(raw)


def extract_pdf_text(pdf_bytes: io.BytesIO) -> str:
    """Extract all text from a PDF file object."""
    pages = []
    with pdfplumber.open(pdf_bytes) as pdf:
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text()
            if txt:
                pages.append(f"[Page {i+1}]\n{txt}")
    return "\n\n".join(pages)


def extract_claims(text: str, client: anthropic.Anthropic) -> list[dict]:
    """Ask Claude to identify every specific, verifiable factual claim in the text."""
    prompt = f"""You are a meticulous fact-checker.

Analyze the document below and extract EVERY specific, verifiable factual claim — even if it looks plausible.

Focus on:
- Statistics and percentages  ("65 % of brands report…")
- Specific dates / years       ("launched in 2021", "as of Q1 2024")
- Financial figures            ("raised $50 M", "valued at $10 B")
- Performance / technical facts ("achieves 97 % accuracy", "processes 1 M req/s")
- Rankings and superlatives    ("the largest", "fastest-growing", "more than double")
- Company facts                ("founded by X in Y", "headquartered in Z")
- User / market-size figures   ("100 million users", "used by 70 % of Fortune 500")

Return up to 12 of the most specific, verifiable claims as a JSON array.
Respond with ONLY the JSON — no preamble, no markdown fences.

[
  {{
    "claim":        "exact text of the claim",
    "type":         "statistic|date|financial|technical|ranking|company_fact|market_size",
    "search_query": "precise Google-style query to verify this claim"
  }}
]

DOCUMENT TEXT (first 8 000 chars):
{text[:8000]}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    return safe_json(msg.content[0].text)


def verify_claim(claim_obj: dict,
                  anthropic_client: anthropic.Anthropic,
                  tavily_client:    TavilyClient) -> dict:
    """Web-search the claim, then ask Claude for a verdict."""
    claim        = claim_obj["claim"]
    search_query = claim_obj.get("search_query", claim)
    claim_type   = claim_obj.get("type", "unknown")

    # ── 1. Web search ──────────────────────────────────────────────────────
    search_context = "No web results were returned."
    source_urls    = []
    try:
        resp    = tavily_client.search(query=search_query, max_results=5, search_depth="advanced")
        results = resp.get("results", [])
        answer  = resp.get("answer", "")
        if answer:
            search_context = f"SEARCH SUMMARY: {answer}\n\n"
        for r in results:
            search_context += (
                f"Source: {r.get('url','')}\n"
                f"Title:  {r.get('title','')}\n"
                f"Snippet:{r.get('content','')[:500]}\n\n"
            )
            if r.get("url"):
                source_urls.append(r["url"])
    except Exception as e:
        search_context = f"Search error: {e}"

    # ── 2. LLM verification ────────────────────────────────────────────────
    verify_prompt = f"""You are a rigorous fact-checker. Verify the claim below using ONLY the web search results provided.

CLAIM: "{claim}"
TYPE:  {claim_type}

WEB SEARCH RESULTS:
{search_context[:4000]}

Rules:
- If search results CONFIRM the claim is current and accurate → Verified
- If the claim was once true but figures/dates are now OUTDATED, or key details are WRONG → Inaccurate
- If the claim is clearly contradicted by evidence, or no evidence supports it → False
- Only use Unverifiable if there is genuinely no useful evidence either way

Be aggressive: when evidence contradicts a claim even partially, prefer Inaccurate or False over Verified.

Respond with ONLY a JSON object — no preamble, no markdown fences:
{{
  "verdict":      "Verified|Inaccurate|False|Unverifiable",
  "confidence":   "High|Medium|Low",
  "explanation":  "1-2 sentence verdict with specific evidence cited",
  "correct_info": "The accurate current figure/fact if verdict is Inaccurate or False; otherwise null",
  "best_source":  "Most relevant URL from results; null if none"
}}"""

    msg = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": verify_prompt}]
    )

    try:
        result = safe_json(msg.content[0].text)
    except Exception:
        result = {
            "verdict":      "Unverifiable",
            "confidence":   "Low",
            "explanation":  "Could not parse verification response.",
            "correct_info": None,
            "best_source":  None
        }

    result.update({"claim": claim, "type": claim_type, "source_urls": source_urls})
    return result


def verdict_card(result: dict, index: int):
    """Render a color-coded result card."""
    verdict = result.get("verdict", "Unverifiable")
    icons   = {"Verified": "✅", "Inaccurate": "⚠️", "False": "❌", "Unverifiable": "❓"}
    icon    = icons.get(verdict, "❓")
    css     = f"card-{verdict.lower()}"

    # Build the inner HTML
    html = f"""
    <div class='{css}'>
      <div style='font-size:0.72rem;color:#6b7280;text-transform:uppercase;
                  letter-spacing:.06em;margin-bottom:5px;'>
        Claim #{index+1} &nbsp;·&nbsp; {result.get('type','').replace('_',' ').title()}
      </div>
      <div style='font-size:1rem;font-weight:600;margin-bottom:8px;'>
        {icon}&nbsp; "{result['claim']}"
      </div>
      <div style='font-size:.875rem;color:#374151;margin-bottom:6px;'>
        <strong>Finding:</strong> {result.get('explanation','—')}
      </div>"""

    ci = result.get("correct_info")
    if ci and str(ci).lower() not in ("null", "none", "n/a", ""):
        html += f"""
      <div style='font-size:.875rem;color:#374151;margin-bottom:6px;'>
        <strong>✏️ Correct info:</strong> {ci}
      </div>"""

    bs = result.get("best_source")
    if bs and str(bs).lower() not in ("null", "none", "no source found", ""):
        short = bs[:90] + ("…" if len(bs) > 90 else "")
        html += f"""
      <div style='font-size:.8rem;color:#6b7280;margin-bottom:8px;'>
        <strong>Source:</strong>
        <a href='{bs}' target='_blank' style='color:#4f46e5;'>{short}</a>
      </div>"""

    conf = result.get("confidence", "")
    html += f"""
      <span class='badge badge-{verdict.lower()}'>{verdict}</span>
      <span style='font-size:.75rem;color:#9ca3af;margin-left:8px;'>
        Confidence: {conf}
      </span>
    </div>"""

    st.markdown(html, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
default_ant, default_tav = get_api_keys()

with st.sidebar:
    st.markdown("### ⚙️ API Keys")

    secrets_found = bool(default_ant and default_tav)
    if secrets_found:
        st.success("✅ Keys loaded from deployment secrets")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value=default_ant,
        help="console.anthropic.com"
    )
    tavily_key = st.text_input(
        "Tavily API Key",
        type="password",
        value=default_tav,
        help="tavily.com — free tier: 1 000 searches/month"
    )

    st.markdown("---")
    st.markdown("### 📖 How it works")
    st.markdown("""
1. **Extract** — Claude reads your PDF and identifies every specific, verifiable claim

2. **Search** — Each claim is looked up against live web data via Tavily AI Search

3. **Verdict** — Claims are classified:
   - ✅ **Verified** — Confirmed accurate
   - ⚠️ **Inaccurate** — Wrong or outdated
   - ❌ **False** — Clearly incorrect
   - ❓ **Unverifiable** — No evidence either way
    """)

    st.markdown("---")
    st.caption("Built with Claude + Tavily · Cogculture Assessment")


# ── Hero header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class='hero'>
  <h1>🔍 AI Fact Checker</h1>
  <p>Upload a PDF — every factual claim is automatically extracted and verified against live web data.</p>
</div>
""", unsafe_allow_html=True)

# ── Gate on API keys ──────────────────────────────────────────────────────────
if not anthropic_key or not tavily_key:
    st.warning("⚠️ Enter your **Anthropic** and **Tavily** API keys in the sidebar to continue.")
    with st.expander("🔑 How to get API keys"):
        st.markdown("""
**Anthropic (Claude):** [console.anthropic.com](https://console.anthropic.com)
— Create an account → API Keys → New key.

**Tavily (free tier — 1 000 searches/month):** [tavily.com](https://tavily.com)
— Sign up → copy your API key from the dashboard.
        """)
    st.stop()

# ── File upload ───────────────────────────────────────────────────────────────
uploaded = st.file_uploader("📄 Upload PDF", type=["pdf"])

if uploaded is None:
    st.markdown("""
    <div class='upload-hint'>
      <div class='icon'>📄</div>
      <h3>Drop a PDF above to begin</h3>
      <p>The checker will extract every verifiable claim and cross-reference it against live web sources.</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

# File info + start button
info_col, btn_col = st.columns([3, 1])
with info_col:
    st.markdown(f"""
    <div style='background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
                padding:.75rem 1rem;font-size:.9rem;'>
      📎 <strong>{uploaded.name}</strong>&nbsp;·&nbsp;{uploaded.size/1024:.1f} KB
    </div>""", unsafe_allow_html=True)
with btn_col:
    start = st.button("🚀 Run Fact Check", type="primary", use_container_width=True)

if not start:
    st.stop()

# ── Processing pipeline ───────────────────────────────────────────────────────
st.markdown("---")

# Init clients
try:
    ant_client = anthropic.Anthropic(api_key=anthropic_key)
    tav_client = TavilyClient(api_key=tavily_key)
except Exception as e:
    st.error(f"❌ Could not initialise API clients: {e}")
    st.stop()

# Step 1 — Extract PDF text
with st.status("Processing…", expanded=True) as status:
    st.write("📄 Reading PDF…")
    try:
        pdf_bytes = io.BytesIO(uploaded.read())
        pdf_text  = extract_pdf_text(pdf_bytes)
        if not pdf_text.strip():
            st.error("❌ No text found. The PDF may be a scanned image — only text-based PDFs are supported.")
            st.stop()
        st.write(f"✅ Extracted {len(pdf_text):,} characters")
    except Exception as e:
        st.error(f"❌ PDF extraction failed: {e}")
        st.stop()

    # Step 2 — Extract claims
    st.write("🧠 Identifying verifiable claims with Claude…")
    try:
        claims = extract_claims(pdf_text, ant_client)
        st.write(f"✅ Found {len(claims)} verifiable claims")
    except Exception as e:
        st.error(f"❌ Claim extraction failed: {e}")
        st.stop()

    status.update(label="Claims identified — starting verification…", state="running")

if not claims:
    st.warning("⚠️ No verifiable claims found in this document.")
    st.stop()

# Step 3 — Verify claims
st.subheader(f"🔍 Verifying {len(claims)} Claims")
progress  = st.progress(0, text="Starting…")
results   = []

for i, claim_obj in enumerate(claims):
    snippet = claim_obj["claim"][:70]
    progress.progress(i / len(claims), text=f"Claim {i+1}/{len(claims)}: \"{snippet}…\"")
    try:
        res = verify_claim(claim_obj, ant_client, tav_client)
    except Exception as e:
        res = {
            "claim":        claim_obj["claim"],
            "type":         claim_obj.get("type", "unknown"),
            "verdict":      "Unverifiable",
            "confidence":   "Low",
            "explanation":  f"Error during verification: {e}",
            "correct_info": None,
            "best_source":  None,
            "source_urls":  []
        }
    results.append(res)
    time.sleep(0.25)   # light rate-limit buffer

progress.progress(1.0, text="✅ All claims verified!")
time.sleep(0.4)
progress.empty()

# ── Summary metrics ───────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 Summary")

verdicts    = [r.get("verdict", "Unverifiable") for r in results]
n_verified  = verdicts.count("Verified")
n_inac      = verdicts.count("Inaccurate")
n_false     = verdicts.count("False")
n_unver     = verdicts.count("Unverifiable")
n_total     = len(results)
n_issues    = n_inac + n_false

m0, m1, m2, m3, m4 = st.columns(5)
m0.metric("📋 Total",         n_total)
m1.metric("✅ Verified",      n_verified)
m2.metric("⚠️ Inaccurate",   n_inac)
m3.metric("❌ False",         n_false)
m4.metric("❓ Unverifiable",  n_unver)

if n_issues == 0:
    st.success(f"✅ **Document appears accurate** — {n_verified}/{n_total} claims confirmed, no issues detected.")
elif n_issues <= 2:
    st.warning(f"⚠️ **Minor issues found** — {n_issues} claim(s) contain inaccuracies or false information.")
else:
    rate = (n_issues / n_total) * 100 if n_total else 0
    st.error(f"❌ **Significant issues** — {n_issues}/{n_total} claims are inaccurate or false ({rate:.0f}% issue rate).")

# ── Detailed results ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Detailed Results")

filter_opt = st.selectbox(
    "Filter:",
    ["All", "Verified", "Inaccurate", "False", "Unverifiable"],
    label_visibility="collapsed"
)
filtered = results if filter_opt == "All" else [r for r in results if r.get("verdict") == filter_opt]

if not filtered:
    st.info(f"No claims with verdict: {filter_opt}")
else:
    for idx, res in enumerate(filtered):
        verdict_card(res, idx)

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("⬇️ Export")

rows = [{
    "Claim":           r.get("claim", ""),
    "Type":            r.get("type",  ""),
    "Verdict":         r.get("verdict",""),
    "Confidence":      r.get("confidence",""),
    "Explanation":     r.get("explanation",""),
    "Correct Info":    r.get("correct_info","") or "",
    "Best Source":     r.get("best_source","")  or ""
} for r in results]

df = pd.DataFrame(rows)
csv_bytes  = df.to_csv(index=False).encode("utf-8")
json_bytes = json.dumps(results, indent=2, default=str).encode("utf-8")
fname_base = uploaded.name.replace(".pdf", "")

dl1, dl2 = st.columns(2)
with dl1:
    st.download_button(
        "📊 Download CSV",
        data=csv_bytes,
        file_name=f"fact_check_{fname_base}.csv",
        mime="text/csv",
        use_container_width=True
    )
with dl2:
    st.download_button(
        "📄 Download JSON",
        data=json_bytes,
        file_name=f"fact_check_{fname_base}.json",
        mime="application/json",
        use_container_width=True
    )
