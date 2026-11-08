# Deploy to Streamlit Community Cloud

This is a click-by-click guide for you. The public link runs in **Demo mode** with no API key, so it always works and costs nothing. Adding a Gemini key is optional and only needed if you want visitors to switch on Live mode.

**You cannot change the Python version after the first deploy.** Pick **3.11** in Advanced settings the first time.

---

## Before you click Deploy

1. The GitHub repo must be **public**: [Khairnar-sh21/Member-returns-warranty-AI-triage-agent](https://github.com/Khairnar-sh21/Member-returns-warranty-AI-triage-agent). Streamlit Community Cloud reads it from there.
2. Replace the LinkedIn placeholder in two places (search for `your-profile`):
   - `ui/settings.py` → `LINKEDIN_URL`
   - `README.md` → the LinkedIn link at the top
3. Commit and push those two edits:

```bash
cd "/Users/shubhamkhairnar/Desktop/Claude Projects/Whoop"
git add ui/settings.py README.md
git commit -m "Add LinkedIn URL"
git push
```

---

## Deploy (about 5 minutes)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with the **same GitHub account** that owns the repo (`Khairnar-sh21`).
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `Khairnar-sh21/Member-returns-warranty-AI-triage-agent`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** pick something like `pulseband-triage` (this becomes `https://pulseband-triage.streamlit.app`)
4. Click **Advanced settings**:
   - **Python version:** **3.11** (do not skip this; the default is newer and can break installs)
   - **Secrets:** leave blank for now. Demo mode does not need a key.
5. Click **Save**, then **Deploy**.
6. Wait 1–3 minutes. The first build installs everything in `requirements.txt`. When it finishes you'll get a public URL.

If the build fails, open **Manage app** (bottom-right) and read the log. The two usual causes are "wrong Python version" (delete the app and redeploy, picking 3.11) and a missing file on GitHub (confirm `app.py` and `requirements.txt` are on `main`).

---

## After it is live

1. Open the public URL in a private/incognito window (so you see what a hiring manager sees).
2. Confirm:
   - The banner says "Unofficial concept · Synthetic data"
   - The sidebar is on **Demo mode**
   - Clicking **Run triage** on "Band won't charge" shows a result, a decision trace, a case, an RMA, and a drafted reply
   - **Ops dashboard** and **Evaluation** both have numbers (67% automation, 100% eval)
3. Paste the public URL into `README.md` where it says `add your Streamlit link here`, commit, and push. GitHub will update within a minute; Streamlit Cloud will restart on that push, which is fine.

---

## Optional: turn on Live mode (free Gemini key)

Live mode lets visitors type their own message. It is capped at 15 calls per visit and 300 per day.

1. Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. In Streamlit Cloud, open your app → **App settings** (⋮ menu) → **Secrets**.
3. Paste this, with your real key:

```toml
LLM_PROVIDER = "gemini"
GEMINI_API_KEY = "your-key-here"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

4. Save. The app restarts. Visitors still land on Demo mode; they can switch to Live in the sidebar.

Never put the key in GitHub. `.env` and `.streamlit/secrets.toml` are git-ignored on purpose.

---

## If you need to change Python later

Streamlit cannot change the Python version in place. Delete the app (note the URL), then deploy again with **Python 3.11** in Advanced settings and reuse the same subdomain so the link does not change.
