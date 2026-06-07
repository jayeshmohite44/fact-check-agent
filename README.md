# 🔍 AI Fact Checker

Automatically extracts every verifiable claim from a PDF and cross-references it against live web data — flagging stats, dates, and figures as **Verified ✅**, **Inaccurate ⚠️**, **False ❌**, or **Unverifiable ❓**.

Built with **Claude (Anthropic)** + **Tavily AI Search** + **Streamlit**.

---

## 🚀 Live App

👉 **[your-app-name.streamlit.app](https://your-app-name.streamlit.app)**
*(Update this link after deployment — see Step 4 below)*

---

## 🧠 How It Works

| Step | What happens |
|------|-------------|
| **1. Extract** | Claude reads the PDF and identifies every specific, verifiable claim — statistics, dates, financial figures, company facts, rankings |
| **2. Search** | Each claim is searched against live web sources using Tavily AI Search |
| **3. Verify** | Claude evaluates the search results against the claim and assigns a verdict with evidence |
| **4. Report** | Results are displayed in a colour-coded dashboard with sources; downloadable as CSV or JSON |

---

## 🔑 API Keys You Need

| Key | Where to get it | Cost |
|-----|----------------|------|
| **Anthropic API Key** | [console.anthropic.com](https://console.anthropic.com) → API Keys | ~$0.01–0.15 per document |
| **Tavily API Key** | [tavily.com](https://tavily.com) → Dashboard | Free (1,000 searches/month) |

---

## ☁️ Deploying to Streamlit Cloud (Free — Recommended)

This is the fastest path. No server needed.

### Step 1 — Upload code to GitHub

1. Go to [github.com](https://github.com) and create a free account (if you don't have one)
2. Click **"New repository"** → name it `ai-fact-checker` → set to **Public** → click **Create repository**
3. On the repository page, click **"uploading an existing file"**
4. Drag and drop these files from this folder:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
   - The `.streamlit/` folder (containing `config.toml`)
5. Click **"Commit changes"**

### Step 2 — Connect to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Fill in:
   - **Repository:** `your-username/ai-fact-checker`
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Click **"Deploy!"** — Streamlit will build and launch your app (takes ~2 minutes)

### Step 3 — Add your API keys (secrets)

Your API keys must **never** go in the code. Add them safely in Streamlit:

1. In Streamlit Cloud, click your app → **"Settings"** (top right ⋮ menu)
2. Click **"Secrets"**
3. Paste exactly this (replace with your real keys):

```toml
ANTHROPIC_API_KEY = "sk-ant-xxxxxxxxxxxxxxxxxx"
TAVILY_API_KEY    = "tvly-xxxxxxxxxxxxxxxxxx"
```

4. Click **"Save"** — the app restarts automatically

### Step 4 — Get your live URL

Your app is now live at:
```
https://your-app-name.streamlit.app
```
Copy this URL — this is what you submit as your **Deployed App Link**.

---

## 💻 Running Locally (Optional)

```bash
# 1. Clone the repo
git clone https://github.com/your-username/ai-fact-checker.git
cd ai-fact-checker

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env
# Open .env and paste your real API keys

# 5. Run
streamlit run app.py
# Opens at http://localhost:8501
```

---

## 📁 File Structure

```
ai-fact-checker/
├── app.py                  # Main application
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .env.example            # API key template (safe to share)
├── .gitignore              # Keeps .env out of GitHub
└── .streamlit/
    └── config.toml         # App theme settings
```

---

## 🧪 What Gets Tested

The evaluator will upload a **Trap Document** containing:
- Outdated statistics (e.g. user counts from 2021)
- Incorrect financial figures
- False founding dates or company facts
- Fabricated percentages

The app is designed to catch all of these by:
1. Extracting claims aggressively (up to 12 per document)
2. Searching with optimised, specific queries per claim
3. Applying a strict verification standard — partial contradictions are flagged as **Inaccurate**, not overlooked

---

## ⚠️ Known Limitations

- **Scanned / image PDFs** are not supported (only text-based PDFs)
- **Very large PDFs** are analysed on the first ~8,000 characters of text
- **Tavily free tier** allows 1,000 searches/month (~80 documents of 12 claims each)
- Verification accuracy depends on the quality and recency of web search results

---

## 📹 Demo Video

A 30-second screen recording is included in the submission in case API credits are exhausted during evaluation.

---

*Assessment submission for Cogculture · Product Manager role*
