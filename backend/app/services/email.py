"""Transactional email behind a provider interface (console | smtp | resend)."""
from __future__ import annotations

import asyncio
import html
import smtplib
import uuid
from email.message import EmailMessage
from urllib.parse import quote

import httpx

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import create_jwt

log = get_logger("provok.email")

_sent_for_tests: list[dict[str, str]] = []


def sent_emails() -> list[dict[str, str]]:
    return _sent_for_tests


UNSUBSCRIBE_TOKEN_TTL_SECONDS = 365 * 24 * 3600


def unsubscribe_token(user_id: uuid.UUID) -> str:
    return create_jwt(user_id, "unsubscribe", UNSUBSCRIBE_TOKEN_TTL_SECONDS)


class _Unsubscribe:
    """Links for a notification email: a page for people, and an RFC 8058 one-click endpoint for mail clients."""

    def __init__(self, user_id: uuid.UUID) -> None:
        s = get_settings()
        token = unsubscribe_token(user_id)
        self.page_url = f"{s.web_url}/unsubscribe?token={token}"
        self.one_click_url = f"{s.api_url}{s.api_prefix}/email/unsubscribe?token={token}"

    @property
    def headers(self) -> dict[str, str]:
        return {"List-Unsubscribe": f"<{self.one_click_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def _layout(title: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None,
            unsubscribe_url: str | None = None) -> str:
    button = (
        f'<p style="margin:28px 0"><a href="{html.escape(cta_url or "")}" style="background:#FF5A1F;color:#0A0A0B;'
        f'padding:12px 22px;border-radius:999px;font-weight:700;text-decoration:none;display:inline-block">'
        f"{html.escape(cta_label or '')}</a></p>" if cta_label and cta_url else ""
    )
    footer = (f' <a href="{html.escape(unsubscribe_url)}" style="color:#6E6B64">Unsubscribe from debate emails</a>.'
              if unsubscribe_url else "")
    return f"""<!doctype html><html><body style="margin:0;background:#0A0A0B;color:#F2EFE9;font-family:-apple-system,
Segoe UI,Roboto,Helvetica,Arial,sans-serif"><div style="max-width:520px;margin:0 auto;padding:40px 24px">
<div style="font-weight:800;letter-spacing:-0.02em;font-size:22px">PROVOK</div>
<h1 style="font-size:26px;letter-spacing:-0.02em;margin:28px 0 12px">{html.escape(title)}</h1>
<div style="color:#C9C5BC;font-size:15px;line-height:1.6">{body_html}</div>{button}
<p style="color:#6E6B64;font-size:12px;margin-top:40px">You're receiving this because of activity on your Provok
account. If this wasn't you, you can ignore this email.{footer}</p></div></body></html>"""


async def send_email(to: str, subject: str, html_body: str, text_body: str,
                     headers: dict[str, str] | None = None) -> None:
    s = get_settings()
    headers = headers or {}
    if s.email_provider == "console" or s.is_test:
        _sent_for_tests.append({"to": to, "subject": subject, "text": text_body, "html": html_body, **headers})
        log.info("email_console", to=to, subject=subject, text=text_body)
        return
    try:
        if s.email_provider == "ses":
            await asyncio.to_thread(_send_ses, to, subject, html_body, text_body, headers)
        elif s.email_provider == "resend":
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {s.resend_api_key}"},
                    json={"from": s.email_from, "to": [to], "subject": subject, "html": html_body, "text": text_body,
                          "headers": headers},
                )
                resp.raise_for_status()
        else:
            await asyncio.to_thread(_send_smtp, to, subject, html_body, text_body, headers)
        log.info("email_sent", provider=s.email_provider, subject=subject)
    except Exception as exc:
        log.error("email_failed", provider=s.email_provider, subject=subject, error=str(exc))


def _send_ses(to: str, subject: str, html_body: str, text_body: str, headers: dict[str, str]) -> None:
    import boto3
    s = get_settings()
    simple: dict = {"Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": text_body, "Charset": "UTF-8"},
                             "Html": {"Data": html_body, "Charset": "UTF-8"}}}
    if headers:
        simple["Headers"] = [{"Name": k, "Value": v} for k, v in headers.items()]
    boto3.client("sesv2", region_name=s.ses_region).send_email(
        FromEmailAddress=s.email_from,
        Destination={"ToAddresses": [to]},
        Content={"Simple": simple},
    )


def _send_smtp(to: str, subject: str, html_body: str, text_body: str, headers: dict[str, str]) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    for name, value in headers.items():
        msg[name] = value
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password)
        smtp.send_message(msg)


async def send_verification(to: str, name: str, token: str, *, next_path: str = "/") -> None:
    url = f"{get_settings().web_url}/verify-email?token={token}"
    if next_path != "/":
        url += f"&next={quote(next_path, safe='')}"
    await send_email(to, "Confirm your email for Provok",
                     _layout(f"Welcome to the arena, {name}.",
                             "<p>Confirm your email to start debating and voting.</p>", "Confirm email", url),
                     f"Welcome to Provok, {name}. Confirm your email: {url}")


async def send_password_reset(to: str, token: str) -> None:
    s = get_settings()
    url = f"{s.web_url}/reset-password?token={token}"
    await send_email(to, "Reset your Provok password",
                     _layout("Reset your password",
                             f"<p>This link expires in {s.password_reset_ttl_minutes} minutes.</p>",
                             "Choose a new password", url),
                     f"Reset your Provok password (expires in {s.password_reset_ttl_minutes} min): {url}")


async def _send_notification(to: str, user_id: uuid.UUID, subject: str, title: str, body_html: str,
                             cta_label: str, cta_url: str, text: str) -> None:
    unsub = _Unsubscribe(user_id)
    await send_email(to, subject, _layout(title, body_html, cta_label, cta_url, unsub.page_url),
                     f"{text}\n\nUnsubscribe from debate emails: {unsub.page_url}", unsub.headers)


async def send_challenge(to: str, user_id: uuid.UUID, challenger: str, question: str, debate_url: str) -> None:
    await _send_notification(to, user_id, f"{challenger} challenged you on Provok", f"{challenger} wants to debate you.",
                             f"<p><b>{html.escape(question)}</b></p><p>Take the other side and the debate starts "
                             "right away. If nobody answers in time, they can bring in an AI instead.</p>",
                             "Accept the challenge", debate_url,
                             f"{challenger} challenged you to a debate: '{question}'. Accept: {debate_url}")


async def send_turn_reminder(to: str, user_id: uuid.UUID, question: str, debate_url: str) -> None:
    await _send_notification(to, user_id, "Your move on Provok", "It's your turn.",
                             f"<p>Your opponent has spoken on <b>{html.escape(question)}</b>. The clock is running.</p>",
                             "Make your argument", debate_url, f"It's your turn in '{question}': {debate_url}")


async def send_debate_result(to: str, user_id: uuid.UUID, question: str, verdict_url: str) -> None:
    await _send_notification(to, user_id, "The verdict is in", "The verdict is in.",
                             f"<p>The judge has ruled on <b>{html.escape(question)}</b>.</p>",
                             "See who won", verdict_url, f"The verdict is in for '{question}': {verdict_url}")
