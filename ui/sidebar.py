from __future__ import annotations

import streamlit as st

from triage.classifier import PROMPT_VERSION
from triage.config import get_rules
from triage.data import get_store
from triage.demo import load_cache
from ui import session
from ui.components import esc, html
from ui.settings import CASE_STUDY_URL, GITHUB_URL, LINKEDIN_URL, LIVE_CALLS_PER_SESSION

MODE_LABELS = {"demo": "Demo mode", "live": "Live mode"}


def render() -> None:
    rules = get_rules()
    with st.sidebar:
        html(
            '<div class="pb-side-brand"><div class="pb-side-logo" aria-hidden="true">'
            '<svg width="30" height="30" viewBox="0 0 30 30" fill="none">'
            '<path d="M3.5 16.5 H8 L10.5 8 L14.5 22.5 L17.5 11 L20 16.5 H26.5" '
            'stroke="#fff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg></div>'
            '<div class="pb-side-kicker">PulseBand</div></div>'
            '<div style="font-size:22px;font-weight:700;line-height:1.2;margin-top:10px">'
            'Member Triage Agent</div>'
            '<div class="pb-muted" style="font-size:14px;line-height:1.5;margin-top:8px">'
            'Reads member support messages with AI, then resolves them with deterministic '
            'policy rules.</div>'
        )
        st.divider()

        live_ok = session.live_available()
        st.radio(
            "Mode",
            options=["demo", "live"],
            format_func=MODE_LABELS.get,
            key="mode",
            disabled=not live_ok,
        )
        if session.is_live():
            st.caption("Each triage calls the AI model. Limited per session to control cost.")
        elif live_ok:
            st.caption("Replays cached AI responses for the sample scenarios. No API calls are made.")
        else:
            st.caption("Replays cached AI responses for the sample scenarios. Live mode isn't "
                       "configured on this deployment.")

        if live_ok:
            left = min(session.session_remaining(), session.daily_remaining())
            pct = int(100 * left / LIVE_CALLS_PER_SESSION)
            html(
                '<div class="pb-meter"><div class="pb-label" style="font-size:13px">'
                'Live calls remaining this session</div>'
                f'<div><span style="font-size:28px;font-weight:600">{left}</span>'
                f'<span class="pb-muted" style="font-size:15px"> / {LIVE_CALLS_PER_SESSION}</span></div>'
                f'<div class="pb-meter-bar"><div style="width:{pct}%"></div></div>'
                '<div class="pb-faint">Shared daily cap resets 00:00 UTC</div></div>'
            )

        st.divider()
        links = [("GitHub repository", GITHUB_URL), ("LinkedIn", LINKEDIN_URL)]
        if CASE_STUDY_URL:
            links.insert(1, ("Case study write-up", CASE_STUDY_URL))
        html(
            '<div style="font-size:14px;font-weight:600;margin-bottom:8px">Links</div>'
            + "".join(f'<div style="margin:6px 0"><a class="pb-link" href="{esc(url)}" '
                      f'target="_blank" style="font-weight:400">{esc(label)} ↗</a></div>'
                      for label, url in links)
        )

        provider = session.provider()
        cache = load_cache()
        model = provider.model if provider else (cache.model if cache else "—")
        html(
            '<div class="pb-faint" style="line-height:1.6;margin-top:24px">'
            f'{len(get_store().members)} synthetic members · 5 regions<br>'
            f'Policy {esc(rules.policy.version)} · Prompt {esc(PROMPT_VERSION)}<br>'
            f'Model {esc(model)}<br>'
            f'Policy date (demo clock): {rules.today():%b %d, %Y}</div>'
        )
