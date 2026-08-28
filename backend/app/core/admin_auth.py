"""Minimal, development-safe authentication boundary for the admin API
namespace (/api/v1/admin/*).

This is explicitly NOT production-grade authentication: there is no admin-
accounts table, no session, no password, no per-admin identity, and no
expiry. It exists only because the admin dashboard exposes actions (approve/
reject content) and data (contributor phone numbers) that must not be
reachable by an arbitrary caller, and because nothing resembling
authentication or authorization existed anywhere in this backend before the
admin dashboard feature.

A single shared secret (settings.admin_api_token) gates every /admin route,
checked via the FastAPI dependency below. The admin frontend's login screen
asks a human for this token plus a free-text display name (attribution only,
NOT an identity check) and stores both in the browser; neither is ever baked
into the built frontend bundle. Replace this with real per-admin accounts
before exposing the admin app beyond a small trusted team.
"""

from fastapi import Header, HTTPException

from app.core.config import settings


class AdminPrincipal:
    """The caller of an admin request. `name` is a self-reported display
    label used only for attribution (ObservationModeration.decided_by) -- it
    is NOT a verified identity, since no admin-accounts system exists yet."""

    def __init__(self, name: str):
        self.name = name


def require_admin(
    x_admin_token: str | None = Header(default=None),
    x_admin_name: str | None = Header(default=None),
) -> AdminPrincipal:
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=503,
            detail="The admin API is not configured on this server (ADMIN_API_TOKEN is unset).",
        )
    if not x_admin_token or x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")

    display_name = (x_admin_name or "").strip() or "admin"
    return AdminPrincipal(name=display_name)
