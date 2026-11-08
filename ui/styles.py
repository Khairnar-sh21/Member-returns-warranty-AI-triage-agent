"""Design tokens and global CSS (from the PulseBand UI concept)."""

import streamlit as st

INK = "#1B2228"
MUTED = "#5D6872"
FAINT = "#8A949C"
LINE = "#E2E6E9"
TEAL = "#0F6B6B"

OUTCOME_COLORS = {
    "automated": {"bg": "#E5F3EA", "fg": "#1D6B3F", "line": "#9FCDB0", "label": "Automated"},
    "needs_review": {"bg": "#FCEFD6", "fg": "#8A5300", "line": "#E8C27A", "label": "Needs review"},
    "escalated": {"bg": "#FBE7E4", "fg": "#A8261B", "line": "#E9A79E", "label": "Escalated"},
}

STATUS_ICONS = {
    "pass": ("✓", "#E5F3EA", "#1D6B3F"),
    "fail": ("✗", "#FBE7E4", "#A8261B"),
    "flag": ("!", "#FBE7E4", "#A8261B"),
    "info": ("i", "#EAF2F7", "#1F4A63"),
    "skip": ("–", "#ECEFF1", MUTED),
}

CSS = f"""
<style>
.block-container {{ padding: 1.25rem 3.5rem 3.5rem; max-width: 1280px; }}
section[data-testid="stSidebar"] {{ width: 300px !important; min-width: 300px !important;
  border-right: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-size: 15px; padding: 10px 0; margin-right: 32px; }}
h1, h2, h3 {{ color: {INK}; }}

[class*="st-key-pbcard"] {{ background: #F7F8F9; border: 1px solid {LINE}; border-radius: 10px;
  padding: 18px 20px; }}
[class*="st-key-pbcard"] pre {{ background: #fff !important; border: 1px solid {LINE};
  border-radius: 8px; }}

.pb-banner {{ display:flex; justify-content:space-between; align-items:center; gap:16px;
  padding:9px 16px; background:#F3F5F6; border:1px solid {LINE}; border-radius:8px;
  font-size:13px; color:{MUTED}; }}
.pb-tag {{ font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  color:{INK}; padding:2px 7px; border:1px solid #CDD3D8; border-radius:4px; background:#fff;
  margin-right:10px; }}
.pb-banner a, .pb-link {{ color:{TEAL}; font-weight:600; text-decoration:none; }}

.pb-title {{ font-size:30px; font-weight:700; color:{INK}; line-height:1.2; }}
.pb-subtitle {{ font-size:16px; color:{MUTED}; margin-top:4px; }}
.pb-label {{ font-size:14px; color:{MUTED}; }}
.pb-h {{ font-size:20px; font-weight:600; color:{INK}; }}
.pb-h-sm {{ font-size:18px; font-weight:600; color:{INK}; }}
.pb-mono {{ font-family:'Source Code Pro', monospace; }}
.pb-muted {{ color:{MUTED}; }}
.pb-faint {{ color:{FAINT}; font-size:12px; }}

.pb-card {{ background:#F7F8F9; border:1px solid {LINE}; border-radius:10px; padding:20px 24px; }}
.pb-card-strong {{ background:#fff; border:1.5px solid {TEAL}; border-radius:10px; padding:20px 24px;
  box-shadow:0 2px 10px rgba(15,107,107,.08); }}
.pb-card-head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}

.pb-pill {{ display:inline-block; font-size:13px; font-weight:600; padding:3px 10px;
  border-radius:999px; white-space:nowrap; }}
.pb-chip-ai {{ background:#E6F2F1; color:{TEAL}; font-size:12px; }}
.pb-chip-rules {{ background:{INK}; color:#fff; font-size:12px; }}

.pb-kv {{ display:grid; grid-template-columns:170px 1fr; gap:12px; padding:9px 0;
  border-top:1px solid #E6E9EC; font-size:15px; }}
.pb-kv > div:first-child {{ color:{MUTED}; }}
.pb-kv > div:last-child {{ font-weight:500; color:{INK}; overflow-wrap:anywhere; }}

.pb-note {{ font-size:13px; color:{MUTED}; padding:10px 12px; background:#fff;
  border:1px solid {LINE}; border-radius:8px; }}
.pb-info {{ display:flex; gap:12px; padding:14px 16px; border-radius:8px; background:#EAF2F7;
  color:#1F4A63; font-size:14px; line-height:1.55; }}

.pb-metric {{ background:#F7F8F9; border:1px solid {LINE}; border-radius:10px; padding:16px 20px;
  display:flex; flex-direction:column; gap:4px; height:100%; }}
.pb-metric-value {{ font-size:26px; font-weight:600; line-height:1.25; color:{INK}; }}
.pb-metric-sub {{ font-size:13px; color:{MUTED}; }}

.pb-rule {{ display:grid; grid-template-columns:28px minmax(0,1fr) auto; gap:14px; padding:12px 0;
  border-top:1px solid #E9ECEE; align-items:start; }}
.pb-icon {{ width:26px; height:26px; border-radius:13px; display:flex; align-items:center;
  justify-content:center; font-size:14px; font-weight:700; }}
.pb-rule-name {{ font-size:16px; font-weight:600; color:{INK}; }}
.pb-rule-why {{ font-size:15px; color:{MUTED}; }}
.pb-rule-code {{ font-size:12px; color:{FAINT}; font-family:'Source Code Pro', monospace;
  padding-top:3px; }}

.pb-request {{ display:flex; gap:10px; align-items:center; padding:12px 16px; border:1px solid {LINE};
  border-radius:8px; font-size:15px; min-width:0; }}
.pb-request .pb-ellipsis {{ color:{MUTED}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

.pb-email {{ background:#fff; border:1px solid {LINE}; border-radius:8px; }}
.pb-email-head {{ padding:12px 16px; border-bottom:1px solid #E9ECEE; font-size:13px; color:{MUTED}; }}
.pb-email-body {{ padding:14px 16px; font-size:14px; line-height:1.6; white-space:pre-wrap; color:{INK}; }}

.pb-table {{ border:1px solid {LINE}; border-radius:8px; overflow:hidden; font-size:15px; }}
.pb-tr {{ display:grid; gap:16px; padding:10px 16px; border-top:1px solid #E9ECEE; }}
.pb-th {{ background:#F3F5F6; font-size:13px; color:{MUTED}; font-weight:600; border-top:none; }}

.pb-side-brand {{ display:flex; align-items:center; gap:10px; }}
.pb-side-logo {{ width:30px; height:30px; border-radius:8px; background:{TEAL}; }}
.pb-side-kicker {{ font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:{MUTED}; }}
.pb-meter {{ background:#fff; border:1px solid {LINE}; border-radius:10px; padding:14px 16px; }}
.pb-meter-bar {{ height:6px; border-radius:3px; background:#E6EAEC; overflow:hidden; margin:8px 0 6px; }}
.pb-meter-bar > div {{ height:100%; background:{TEAL}; }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)
