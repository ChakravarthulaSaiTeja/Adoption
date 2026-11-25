"""The app's look: colours, WhatsApp-style message bubbles, status labels, buttons."""
from __future__ import annotations

import html
import re

import streamlit as st

ACCENT = "#128C7E"
ACCENT_DARK = "#075E54"

CSS = f"""
.block-container {{ max-width: 1100px; padding-top: 2.2rem; }}
h1 {{ font-weight: 700; letter-spacing: -0.01em; }}
[data-testid="stSidebarNav"] a span {{ font-size: 0.98rem; }}
.app-name {{ font-weight: 700; font-size: 1.15rem; color: {ACCENT_DARK}; margin: 0.2rem 0 0.6rem 0; }}
.wa-chat {{ background: #EFEAE2; border-radius: 12px; padding: 14px 16px; margin: 6px 0 12px 0; max-width: 520px; }}
.wa-bubble {{ background: #D9FDD3; border-radius: 10px 10px 2px 10px; padding: 9px 13px; max-width: 460px;
  margin-left: auto; font-size: 0.97rem; line-height: 1.45; color: #111B21;
  box-shadow: 0 1px 0.5px rgba(11, 20, 26, 0.13); white-space: normal; word-wrap: break-word; }}
a.wa-btn, a.wa-btn:visited {{ display: inline-block; background: {ACCENT}; color: #FFFFFF !important;
  padding: 0.55rem 1.1rem; border-radius: 8px; font-weight: 600; text-decoration: none; margin: 4px 0; }}
a.wa-btn:hover {{ background: {ACCENT_DARK}; }}
.chip {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; }}
.chip-green {{ background: #E3F4EC; color: #0B6B3A; }}
.chip-amber {{ background: #FFF4D6; color: #7A5600; }}
.chip-red {{ background: #FDE4E4; color: #9B1C1C; }}
.chip-grey {{ background: #EEF1F0; color: #3C4A45; }}
.step {{ display: flex; gap: 14px; align-items: center; border: 1px solid #E3E8E6; border-radius: 12px;
  padding: 12px 16px; margin: 0 0 10px 0; background: #FFFFFF; }}
.step.next {{ border-color: {ACCENT}; box-shadow: 0 0 0 2px rgba(18, 140, 126, 0.12); }}
.step-num {{ flex: 0 0 34px; height: 34px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-weight: 700; background: #EEF1F0; color: #3C4A45; }}
.step.done .step-num {{ background: {ACCENT}; color: #FFFFFF; }}
.step-title {{ font-weight: 650; }}
.step-summary {{ color: #5B6B66; font-size: 0.92rem; }}
"""

_LABELS = {
    "ready": "🟢 Ready", "review": "🟡 Needs review", "blocked": "🔴 Blocked", "approved": "✅ Approved",
    "sent": "📤 Sent", "accepted": "📤 Sent", "failed": "⚠️ Failed", "unknown": "⚠️ Unknown — check",
    "skipped": "⏭ Skipped", "sending": "⏳ Sending",
}
_TARGETS = {"desktop": "_self"}
_BOLD = re.compile(r"\*([^*\n]+)\*")


def inject_css() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def header(title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def bubble(body: str) -> str:
    """The message as WhatsApp shows it: *bold* in bold, line breaks kept, everything escaped."""
    lines = [_BOLD.sub(r"<b>\1</b>", html.escape(line, quote=False)) for line in body.split("\n")]
    return f'<div class="wa-bubble">{"<br>".join(lines)}</div>'


def chat(body: str) -> str:
    return f'<div class="wa-chat">{bubble(body)}</div>'


def status_label(status: str) -> str:
    return _LABELS.get(status, status)


def chip(text: str, colour: str = "grey") -> str:
    return f'<span class="chip chip-{colour}">{html.escape(text)}</span>'


def whatsapp_link_html(url: str, kind: str, label: str = "Open in WhatsApp") -> str:
    """A button-looking link. The desktop app opens without leaving the page. WhatsApp Web and
    wa.me links open in a new tab: WhatsApp Web's pages isolate themselves, so a tab can't be reused."""
    target = _TARGETS.get(kind, "_blank")
    return (f'<a class="wa-btn" href="{html.escape(url, quote=True)}" target="{target}" '
            f'rel="noopener">{html.escape(label)}</a>')
