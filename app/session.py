import re
import secrets
from dataclasses import dataclass
from urllib.parse import unquote

DIGITS = re.compile(r"^\d+$")
SESSION_MAX_AGE = 60 * 60 * 24 * 365
USER_MAX_AGE = 60 * 60 * 24 * 30


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: int | None
    fresh: bool


def read_cookie(header: str | None, name: str) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        key, _, raw = part.strip().partition("=")
        if key != name:
            continue
        try:
            return unquote(raw, errors="strict")
        except UnicodeDecodeError:
            return raw
    return None


def parse_user_id(value: str | None) -> int | None:
    """A member id the browser sent, or None when the cookie is missing or malformed."""
    return int(value) if value and DIGITS.match(value) else None


def session_from_cookie(header: str | None) -> Session:
    existing = read_cookie(header, "ss_session")
    user_id = parse_user_id(read_cookie(header, "ss_user"))
    return Session(
        session_id=existing or secrets.token_hex(8), user_id=user_id, fresh=existing is None
    )


def session_cookie(session: Session) -> str:
    return f"ss_session={session.session_id}; Path=/; SameSite=Lax; Max-Age={SESSION_MAX_AGE}"


def user_cookie(user_id: int | None) -> str:
    if user_id is None:
        return "ss_user=; Path=/; Max-Age=0"
    return f"ss_user={user_id}; Path=/; SameSite=Lax; Max-Age={USER_MAX_AGE}"
