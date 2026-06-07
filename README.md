🔍 AI Fact Checker
Automatically extracts every verifiable claim from a PDF and cross-references it against live web data — flagging stats, dates, and figures as Verified ✅, Inaccurate ⚠️, False ❌, or Unverifiable ❓.
Built with Groq (Llama 3.1 — free) + Tavily AI Search (free) + Streamlit.
---
🚀 Live App
👉 your-app-name.streamlit.app
(Update this after deployment)
---
🔑 API Keys — Both FREE, No Credit Card
Key	Where to get it
Groq API Key	console.groq.com → Sign up → API Keys → Create Key
Tavily API Key	tavily.com → Sign up → copy from dashboard
Groq key starts with `gsk_` · Tavily key starts with `tvly-`
---
☁️ Deploy to Streamlit Cloud (Free)
Step 1 — Push to GitHub
Go to github.com → create free account
Click New repository → name: `ai-fact-checker` → Public → Create
Click "uploading an existing file"
Upload: `app.py`, `requirements.txt`, `README.md`, `.gitignore`
Click Commit changes
Step 2 — Deploy on Streamlit Cloud
Go to share.streamlit.io
Sign in with GitHub → New app
Repository: `your-username/ai-fact-checker` · Main file: `app.py`
Click Deploy (takes ~2 minutes)
Step 3 — Add API Keys as Secrets
In Streamlit Cloud → your app → ⋮ menu → Settings → Secrets
Paste:
```toml
GROQ_API_KEY   = "gsk_xxxxxxxxxxxxxxxxxx"
TAVILY_API_KEY = "tvly-xxxxxxxxxxxxxxxxxx"
```
Click Save — app restarts with keys pre-filled
---
💻 Run Locally
```bash
git clone https://github.com/your-username/ai-fact-checker.git
cd ai-fact-checker
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # paste your real keys into .env
streamlit run app.py
```
---
📁 Files
```
ai-fact-checker/
├── app.py              # Full Streamlit application
├── requirements.txt    # Dependencies
├── README.md           # This file
├── .env.example        # Key template (safe to share)
└── .gitignore          # Keeps secrets out of GitHub
```
---
Cogculture Assessment · Product Manager role
