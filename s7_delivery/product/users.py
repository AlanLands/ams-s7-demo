"""Named users and the role each acts as (`config/users.json`).

The Control Centre's role picker is a demonstration device; a product needs
people. A user is `{id, name, email, role, active, created_at}`; the Control
Centre resolves the `X-S7-User` header to a user, whose role becomes the
acting role and whose name is the actor recorded on approvals and activity.
`current_user()` is context-local (set by the server middleware per request)
so the engine can name the person without threading a parameter through
every action.
"""

from __future__ import annotations

import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from s7_delivery.factory.models import Role
from s7_delivery.product import config

FILE = "users.json"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CURRENT_USER: ContextVar[dict[str, Any] | None] = ContextVar("s7_current_user", default=None)


class UserError(config.ConfigError):
    pass


def _all() -> list[dict[str, Any]]:
    data = config.read_json(FILE, {"users": []})
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        raise UserError(f"{FILE}: expected {{'users': [...]}}")
    return users


def _save(users: list[dict[str, Any]]) -> None:
    config.write_json(FILE, {"users": users})


def _clean(name: Any, email: Any, role: Any) -> tuple[str, str, str]:
    name = str(name or "").strip()
    if not name:
        raise UserError("a user needs a name")
    email = str(email or "").strip()
    if email and not _EMAIL_RE.match(email):
        raise UserError(f"{email!r} is not an email address")
    try:
        role_value = Role(str(role)).value
    except ValueError as exc:
        raise UserError(
            f"unknown role {role!r}; expected one of {', '.join(r.value for r in Role)}"
        ) from exc
    return name, email, role_value


def list_users(*, active_only: bool = False) -> list[dict[str, Any]]:
    users = _all()
    if active_only:
        users = [u for u in users if u.get("active", True)]
    return sorted(users, key=lambda u: (u.get("role", ""), u.get("name", "").lower()))


def get(user_id: str) -> dict[str, Any]:
    for u in _all():
        if u["id"] == user_id:
            return u
    raise UserError(f"unknown user {user_id!r}")


def create(name: str, role: str, *, email: str = "", actor: str = "") -> dict[str, Any]:
    name, email, role_value = _clean(name, email, role)
    users = _all()
    if any(u["name"].lower() == name.lower() and u.get("role") == role_value for u in users):
        raise UserError(f"a {role_value} named {name!r} already exists")
    user = {
        "id": f"u-{secrets.token_hex(3)}", "name": name, "email": email,
        "role": role_value, "active": True, "created_at": config.now_iso(),
    }
    users.append(user)
    _save(users)
    config.audit(actor, "user.create", user["id"], detail=f"{name} as {role_value}", after=user)
    return user


def update(user_id: str, *, actor: str = "", **changes: Any) -> dict[str, Any]:
    users = _all()
    for i, u in enumerate(users):
        if u["id"] != user_id:
            continue
        before = dict(u)
        merged = {**u, **{k: v for k, v in changes.items() if v is not None}}
        name, email, role_value = _clean(merged["name"], merged.get("email", ""), merged["role"])
        merged.update({"name": name, "email": email, "role": role_value,
                       "active": bool(merged.get("active", True))})
        users[i] = merged
        _save(users)
        config.audit(actor, "user.update", user_id, before=before, after=merged)
        return merged
    raise UserError(f"unknown user {user_id!r}")


def delete(user_id: str, *, actor: str = "") -> None:
    users = _all()
    remaining = [u for u in users if u["id"] != user_id]
    if len(remaining) == len(users):
        raise UserError(f"unknown user {user_id!r}")
    before = next(u for u in users if u["id"] == user_id)
    _save(remaining)
    config.audit(actor, "user.delete", user_id, before=before)


# --- the request context ------------------------------------------------------


@contextmanager
def acting_as(user: dict[str, Any] | None):
    token = CURRENT_USER.set(user)
    try:
        yield user
    finally:
        CURRENT_USER.reset(token)


def current_user() -> dict[str, Any] | None:
    return CURRENT_USER.get()


def current_actor(default: str) -> str:
    """The acting person's name when a user is set, else `default` (the role
    label the engine used before users existed)."""
    user = CURRENT_USER.get()
    return str(user["name"]) if user else default


def resolve_header(user_id: str | None) -> dict[str, Any] | None:
    """`X-S7-User` → user dict, or `None` when absent. Unknown or inactive
    ids raise so a request can never silently act as nobody."""
    if not user_id:
        return None
    user = get(user_id)
    if not user.get("active", True):
        raise UserError(f"user {user['name']!r} is inactive")
    return user
