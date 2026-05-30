"""
HTML fragments for HTMX WebSocket out-of-band swaps (server -> browser).
"""

from __future__ import annotations

from django.utils.html import escape


def user_message_row(message: str) -> str:
    safe = escape(message)
    return (
        '<div class="flex w-full justify-end" hx-swap-oob="beforeend:#thread">'
        '<div class="max-w-[85%] rounded-2xl bg-sky-600 px-4 py-2 text-sm text-white">'
        f"{safe}"
        "</div>"
        "</div>"
    )


def assistant_shell(bubble_id: str) -> str:
    return (
        '<div class="flex w-full justify-start" hx-swap-oob="beforeend:#thread">'
        f'<div id="{bubble_id}" '
        'class="max-w-[85%] rounded-2xl bg-zinc-800 px-4 py-2 text-sm text-zinc-100">'
        "</div>"
        "</div>"
    )


def token_append(bubble_id: str, token: str) -> str:
    safe = escape(token)
    return f'<span hx-swap-oob="beforeend:#{bubble_id}">{safe}</span>'


def error_banner(message: str) -> str:
    safe = escape(message)
    return (
        '<div id="error-banner" role="alert" '
        'class="rounded-lg border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-100" '
        'hx-swap-oob="true">'
        f"{safe}"
        "</div>"
    )


def clear_error() -> str:
    return '<div id="error-banner" hx-swap-oob="true" class="hidden" aria-hidden="true"></div>'


def typing_indicator(show: bool) -> str:
    if show:
        return (
            '<div id="typing-indicator" hx-swap-oob="true" '
            'class="text-xs text-zinc-400 px-2 py-1">Thinking…</div>'
        )
    return '<div id="typing-indicator" hx-swap-oob="true" class="hidden"></div>'
