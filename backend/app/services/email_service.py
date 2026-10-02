import html

import httpx

from app.core.config import settings


class EmailDeliveryError(RuntimeError):
    """Raised when a transactional authentication email cannot be delivered."""


def send_auth_code(to_email: str, code: str, purpose: str) -> None:
    if purpose == "verify_email":
        subject = "Verify your AskLAW email"
        action = "verify your email address"
    elif purpose == "reset_password":
        subject = "Reset your AskLAW password"
        action = "reset your password"
    else:
        raise ValueError("Unsupported authentication email purpose")

    if not settings.RESEND_API_KEY.strip() or not settings.EMAIL_FROM.strip():
        raise EmailDeliveryError("Email delivery is not configured")

    safe_code = html.escape(code)
    expires = settings.EMAIL_OTP_EXPIRE_MINUTES
    body = (
        "<div style=\"font-family:Arial,sans-serif;color:#202833;line-height:1.6\">"
        "<h2 style=\"color:#192b40\">AskLAW</h2>"
        f"<p>Use this one-time code to {action}:</p>"
        f"<p style=\"font-size:28px;font-weight:700;letter-spacing:6px\">{safe_code}</p>"
        f"<p>This code expires in {expires} minutes.</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
        "</div>"
    )

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailDeliveryError("Authentication email delivery failed") from exc
