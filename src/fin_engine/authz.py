"""Authorization seam (v1.5.9).

fin-engine is a single-user local tool: by default every action is allowed, and
there is no login. This module is the EXTENSION POINT for access control, not an
auth system. It exists so that adding real role-based access later is a matter
of supplying an ``Authorizer`` — not rewiring the engine.

Design: callers that perform a sensitive action (read figures, post an entry,
run advice) call ``authorizer.require(Permission.X, principal)``. The default
``AllowAll`` authorizer permits everything, so current behaviour is unchanged.
A real deployment supplies a ``RoleBasedAuthorizer`` (example below) or its own.

This is deliberately small. It does NOT authenticate (verify identity) — that is
the host application's job (OS login, SSO, etc.). It only answers "may this
principal do this?" once identity is established.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Permission(str, Enum):
    READ = "read"        # view figures / statements
    POST = "post"        # record journal entries
    REVERSE = "reverse"  # reverse posted entries
    ADVISE = "advise"    # request LLM advice
    ADMIN = "admin"      # manage the chart of accounts, restore backups


class Authorizer(Protocol):
    """Answers whether a principal may perform an action."""

    def allowed(self, permission: Permission, principal: str) -> bool: ...


class PermissionError_(PermissionError):
    """Raised when an action is denied. (Subclass so callers can catch it.)"""


def require(authorizer: Authorizer, permission: Permission,
           principal: str = "") -> None:
    """Raise ``PermissionError`` if the action is not allowed; else return."""
    if not authorizer.allowed(permission, principal):
        raise PermissionError_(
            f"principal {principal!r} not permitted to {permission.value}")


@dataclass(frozen=True)
class AllowAll:
    """Default: permit everything (single-user local tool)."""

    def allowed(self, permission: Permission, principal: str) -> bool:
        return True


@dataclass
class RoleBasedAuthorizer:
    """Example RBAC authorizer: map a principal to a role, a role to permissions.

    Not used by default — it demonstrates that the seam supports real RBAC. A
    host app constructs one and passes it where an ``Authorizer`` is accepted.
    """

    # role -> permissions it grants
    roles: dict[str, set[Permission]] = field(default_factory=lambda: {
        "viewer": {Permission.READ},
        "bookkeeper": {Permission.READ, Permission.POST, Permission.REVERSE,
                       Permission.ADVISE},
        "admin": set(Permission),
    })
    # principal -> role
    principals: dict[str, str] = field(default_factory=dict)

    def allowed(self, permission: Permission, principal: str) -> bool:
        role = self.principals.get(principal)
        return role is not None and permission in self.roles.get(role, set())
