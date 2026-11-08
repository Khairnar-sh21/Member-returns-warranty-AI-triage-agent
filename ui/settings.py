"""App-level settings (not business policy — that lives in rules.yaml)."""

AUTHOR = "Shubham Khairnar"
LINKEDIN_URL = "https://www.linkedin.com/in/shubham-khairnar"
GITHUB_URL = "https://github.com/Khairnar-sh21/Member-returns-warranty-AI-triage-agent"
CASE_STUDY_URL = ""  # optional write-up link; hidden when empty

# Live-mode limits for the public demo. A "call" is one triage run.
LIVE_CALLS_PER_SESSION = 15
# Shared across all visitors; keeps us inside the Gemini free tier (500/day).
LIVE_CALLS_PER_DAY = 300

MAX_MESSAGE_CHARS = 1000
