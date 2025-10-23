"""Test email adapter that captures outbound messages."""

from __future__ import annotations

from typing import List, Sequence, Tuple

sent_emails: List[dict[str, object]] = []


def reset() -> None:
    sent_emails.clear()


def send_email(
    to_addrs: Sequence[str],
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: Sequence[Tuple[str, bytes]] | None = None,
) -> None:
    sent_emails.append(
        {
            "to": list(to_addrs),
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "attachments": list(attachments or []),
        }
    )
