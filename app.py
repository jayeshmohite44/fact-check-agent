import streamlit as st
import pdfplumber
import json
import os
import io
import re
import time
import pandas as pd
from groq import Groq
from tavily import TavilyClient

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Fact Checker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .hero {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
        padding: 2rem 2.5rem; border-radius: 14px;
        color: white; margin-bottom: 2rem;
    }
    .hero h1 { margin:0; font-size:2rem; font-weight:700; }
    .hero p  { margin:.4rem 0 0; opacity:.85; font-size:1rem; }

    .card-verified    {border-left:5px solid #10b981;background:#f0fdf4;padding:1.1rem 1.2rem;border-radius:0 10px 10px 0;margin-bottom:1rem;}
    .card-inaccurate  {border-left:5px solid #f59e0b;background:#fffbeb;padding:1.1rem 1.2rem;border-radius:0 10px 10px 0;margin-bottom:1rem;}
    .card-false       {border-left:5px solid #ef4444;background:#fef2f2;padding:1.1rem 1.2rem;border-radius:0 10px 10px 0;margin-bottom:1rem;}
    .card-unverifiable{border-left:5px solid #9ca3af;background:#f9fafb;padding:1.1rem 1.2rem;border-radius:0 10px 10px 0;margin-bottom:1rem;}

    .badge {display:inline-block;font-size:.78rem;font-weight:600;padding:3px 12px;border-radius:20px;}
    .badge-verified    {background:#d1fae5;color:#065f46;}
    .badge-inaccurate  {background:#fef3c7;color:#92400e;}
    .badge-false       {background:#fee2e2;color:#991b1b;}
    .badge-unverifiable{background:#f3f4f6;color:#374151;}

    .upload-hint {text-align:center;padding:2.5rem 2rem;background:#f9fafb;border-radius:12px;border:2px dashed #d1d5db;}
    .upload-hint .icon {font-size:2.8rem;margin-bottom:.8rem;}
    .upload-hint h3 {color:#374151;margin:0 0 .4rem;}
    .upload-hint p  {color:#6b7280;margin:0;}

    div[data-testid="metric-container"] {
        background:white; border:1px solid #e5e7eb;
        border-radius:10px; padding:.9rem 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_keys():
    groq_key  = ""
    tavily_key = ""
    try:
        groq_key   = st.secrets.get("GROQ_API_KEY",   os.getenv("GROQ_API_KEY",   ""))
        tavily_key = st.secrets.get("TAVILY_API_KEY",  os.getenv("TAVILY_API_KEY",  ""))
    except Exception:
        groq_key   = os.getenv("GROQ_API_KEY",  "")
        tavily_key = os.getenv("TAVILY_API_KEY", "")
    return groq_key, tavily_key


def safe_json(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try extracting first [...] or {...} block
    for pattern in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    raise ValueError(f"Could not parse JSON from:\n{raw[:400]}")


def extract_pdf_text(pdf_bytes: io.BytesIO) -> str:
    pages = []
    with pdfplumber.open(pdf_bytes) as pdf:
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text()
            if txt:
                pages.append(f"[Page {i+1}]\n{txt}")
    return "\n\n".join(pages)


def extract_claims(text: str, client: Groq) -> list:
    prompt = f"""You are a meticulous fact-checker.

Analyze the document below and extract EVERY specific, verifiable factual claim — even if it looks plausible.

Focus on:
- Statistics and percentages  ("65% of brands report…")
- Specific dates / years       ("launched in 2021", "as of Q1 2024")
- Financial figures            ("raised $50M", "valued at $10B")
- Performance / technical facts ("achieves 97% accuracy")
- Rankings and superlatives    ("the largest", "fastest-growing")
- Company facts                ("founded by X in Y", "headquartered in Z")
- User / market-size figures   ("100 million users", "70% of Fortune 500")

Return up to 12 of the most specific, verifiable claims as a JSON array.
Respond with ONLY valid JSON — no preamble, no markdown fences.

[
  {{
    "claim":        "exact text of the claim",
    "type":         "statistic|date|financial|technical|ranking|company_fact|market_size",
    "search_query": "precise Google-style query to verify this claim"
  }}
]

DOCUMENT TEXT (first 7000 chars):
{text[:7000]}"""

    resp = client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500,
        temperature=0.1
    )
    return safe_json(resp.choices[0].message.content)


def verify_claim(claim_obj: dict, groq_client: Groq, tavily_client: TavilyClient) -> dict:
    claim        = claim_obj["claim"]
    search_query = claim_obj.get("search_query", claim)
    claim_type   = claim_obj.get("type", "unknown")

    # 1. Web search
    search_context = "No web results returned."
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

    # 2. LLM verification
    verify_prompt = f"""You are a rigorous fact-checker. Verify the claim below using ONLY the web search results provided.

CLAIM: "{claim}"
TYPE:  {claim_type}

WEB SEARCH RESULTS:
{search_context[:4000]}

Rules:
- Verified     → search results CONFIRM the claim is current and accurate
- Inaccurate   → claim was once true but figures/dates are OUTDATED, or key details are WRONG
- False        → claim is clearly contradicted by evidence, or fabricated with no support
- Unverifiable → genuinely no useful evidence either way (use sparingly)

Be aggressive: when evidence contradicts a claim even partially, prefer Inaccurate or False over Verified.

Respond with ONLY a JSON object — no preamble, no markdown:
{{
  "verdict":      "Verified|Inaccurate|False|Unverifiable",
  "confidence":   "High|Medium|Low",
  "explanation":  "1-2 sentence verdict with specific evidence cited",
  "correct_info": "Accurate current figure/fact if Inaccurate or False; otherwise null",
  "best_source":  "Most relevant URL from results; null if none"
}}"""

    resp = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": verify_prompt}],
        max_tokens=600,
        temperature=0.1
    )

    try:
        result = safe_json(resp.choices[0].message.content)
    except Exception:
        result = {
            "verdict": "Unverifiable", "confidence": "Low",
            "explanation": "Could not parse verification response.",
            "correct_info": None, "best_source": None
        }

    result.update({"claim": claim, "type": claim_type, "source_urls": source_urls})
    return result


def verdict_card(result: dict, index: int):
    verdict = result.get("verdict", "Unverifiable")
    icons   = {"Verified":"✅","Inaccurate":"⚠️","False":"❌","Unverifiable":"❓"}
    icon    = icons.get(verdict, "❓")
    css     = f"card-{verdict.lower()}"

    html = f"""
    <div class='{css}'>
      <div style='font-size:.72rem;color:#6b7280;text-transform:uppercase;
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
    if ci and str(ci).lower() not in ("null","none","n/a",""):
        html += f"""
      <div style='font-size:.875rem;color:#374151;margin-bottom:6px;'>
        <strong>✏️ Correct info:</strong> {ci}
      </div>"""

    bs = result.get("best_source")
    if bs and str(bs).lower() not in ("null","none","no source found",""):
        short = bs[:90] + ("…" if len(bs) > 90 else "")
        html += f"""
      <div style='font-size:.8rem;color:#6b7280;margin-bottom:8px;'>
        <strong>Source:</strong>
        <a href='{bs}' target='_blank' style='color:#4f46e5;'>{short}</a>
      </div>"""

    html += f"""
      <span class='badge badge-{verdict.lower()}'>{verdict}</span>
      <span style='font-size:.75rem;color:#9ca3af;margin-left:8px;'>
        Confidence: {result.get('confidence','')}
      </span>
    </div>"""

    st.markdown(html, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
default_groq, default_tav = get_api_keys()

with st.sidebar:
    st.markdown("### ⚙️ API Keys")

    if default_groq and default_tav:
        st.success("✅ Keys loaded from deployment secrets")

    groq_key = st.text_input(
        "Groq API Key  (free)",
        type="password",
        value=default_groq,
        help="console.groq.com — free, no credit card needed"
    )
    tavily_key = st.text_input(
        "Tavily API Key  (free)",
        type="password",
        value=default_tav,
        help="tavily.com — free tier: 1 000 searches/month"
    )

    st.markdown("---")
    st.markdown("### 📖 How it works")
    st.markdown("""
1. **Extract** — Llama 3.1 reads your PDF and identifies every verifiable claim

2. **Search** — Each claim is checked against live web data via Tavily

3. **Verdict** — Claims are classified:
   - ✅ **Verified** — Confirmed accurate
   - ⚠️ **Inaccurate** — Wrong or outdated
   - ❌ **False** — Clearly incorrect
   - ❓ **Unverifiable** — No evidence either way
    """)
    st.markdown("---")
    st.caption("Built with Groq (Llama 3.1) + Tavily · Cogculture Assessment")


# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class='hero'>
  <h1>🔍 AI Fact Checker</h1>
  <p>Upload a PDF — every factual claim is automatically extracted and verified against live web data.</p>
</div>
""", unsafe_allow_html=True)

# ── Gate on API keys ──────────────────────────────────────────────────────────
if not groq_key or not tavily_key:
    st.warning("⚠️ Enter your **Groq** and **Tavily** API keys in the sidebar to continue.")
    with st.expander("🔑 How to get both keys — both are FREE"):
        st.markdown("""
**Groq API Key (free — no credit card):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with Google or email
3. Click **"API Keys"** → **"Create API Key"**
4. Copy the key (starts with `gsk_`)

---

**Tavily API Key (free — 1,000 searches/month):**
1. Go to [tavily.com](https://tavily.com)
2. Sign up → copy your key from the dashboard
        """)
    st.stop()

# ── File upload ───────────────────────────────────────────────────────────────
uploaded = st.file_uploader("📄 Upload PDF", type=["pdf"])

if uploaded is None:
    st.markdown("""
    <div class='upload-hint'>
      <div class='icon'>📄</div>
      <h3>Drop a PDF above to begin</h3>
      <p>The checker extracts every verifiable claim and cross-references it against live web sources.</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

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

# ── Pipeline ──────────────────────────────────────────────────────────────────
st.markdown("---")

try:
    groq_client   = Groq(api_key=groq_key)
    tavily_client = TavilyClient(api_key=tavily_key)
except Exception as e:
    st.error(f"❌ Could not initialise API clients: {e}")
    st.stop()

with st.status("Processing…", expanded=True) as status:
    st.write("📄 Reading PDF…")
    try:
        pdf_bytes = io.BytesIO(uploaded.read())
        pdf_text  = extract_pdf_text(pdf_bytes)
        if not pdf_text.strip():
            st.error("❌ No text found. The PDF may be image-based — only text-based PDFs are supported.")
            st.stop()
        st.write(f"✅ Extracted {len(pdf_text):,} characters")
    except Exception as e:
        st.error(f"❌ PDF extraction failed: {e}")
        st.stop()

    st.write("🧠 Identifying verifiable claims…")
    try:
        claims = extract_claims(pdf_text, groq_client)
        st.write(f"✅ Found {len(claims)} verifiable claims")
    except Exception as e:
        st.error(f"❌ Claim extraction failed: {e}")
        st.stop()

    status.update(label="Claims identified — starting verification…", state="running")

if not claims:
    st.warning("⚠️ No verifiable claims found in this document.")
    st.stop()

st.subheader(f"🔍 Verifying {len(claims)} Claims")
progress = st.progress(0, text="Starting…")
results  = []

for i, claim_obj in enumerate(claims):
    snippet = claim_obj["claim"][:70]
    progress.progress(i / len(claims), text=f"Claim {i+1}/{len(claims)}: \"{snippet}…\"")
    try:
        res = verify_claim(claim_obj, groq_client, tavily_client)
    except Exception as e:
        res = {
            "claim": claim_obj["claim"], "type": claim_obj.get("type","unknown"),
            "verdict":"Unverifiable","confidence":"Low",
            "explanation": f"Error: {e}",
            "correct_info":None,"best_source":None,"source_urls":[]
        }
    results.append(res)
    time.sleep(0.2)

progress.progress(1.0, text="✅ All claims verified!")
time.sleep(0.4)
progress.empty()

# ── Summary ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 Summary")

verdicts   = [r.get("verdict","Unverifiable") for r in results]
n_verified = verdicts.count("Verified")
n_inac     = verdicts.count("Inaccurate")
n_false    = verdicts.count("False")
n_unver    = verdicts.count("Unverifiable")
n_total    = len(results)
n_issues   = n_inac + n_false

m0,m1,m2,m3,m4 = st.columns(5)
m0.metric("📋 Total",        n_total)
m1.metric("✅ Verified",     n_verified)
m2.metric("⚠️ Inaccurate",  n_inac)
m3.metric("❌ False",        n_false)
m4.metric("❓ Unverifiable", n_unver)

if n_issues == 0:
    st.success(f"✅ Document appears accurate — {n_verified}/{n_total} claims confirmed.")
elif n_issues <= 2:
    st.warning(f"⚠️ Minor issues found — {n_issues} claim(s) flagged.")
else:
    rate = (n_issues/n_total)*100 if n_total else 0
    st.error(f"❌ Significant issues — {n_issues}/{n_total} claims are inaccurate or false ({rate:.0f}% issue rate).")

# ── Detailed results ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Detailed Results")

filter_opt = st.selectbox(
    "Filter:", ["All","Verified","Inaccurate","False","Unverifiable"],
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
    "Claim":        r.get("claim",""),
    "Type":         r.get("type",""),
    "Verdict":      r.get("verdict",""),
    "Confidence":   r.get("confidence",""),
    "Explanation":  r.get("explanation",""),
    "Correct Info": r.get("correct_info","") or "",
    "Best Source":  r.get("best_source","")  or ""
} for r in results]

df        = pd.DataFrame(rows)
csv_bytes  = df.to_csv(index=False).encode("utf-8")
json_bytes = json.dumps(results, indent=2, default=str).encode("utf-8")
fname      = uploaded.name.replace(".pdf","")

dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("📊 Download CSV",  csv_bytes,  f"fact_check_{fname}.csv",  "text/csv",         use_container_width=True)
with dl2:
    st.download_button("📄 Download JSON", json_bytes, f"fact_check_{fname}.json", "application/json", use_container_width=True)
