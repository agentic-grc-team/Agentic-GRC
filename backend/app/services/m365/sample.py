"""Sample Microsoft Graph answers for a fictional tenant, used instead of a real one (AGRC-161).

`sample_transport()` plugs into `GraphTenantReader` in place of the network, so sample mode and the
tests run the same code path as a real collection. The data is synthetic and includes a few weak
settings on purpose (security defaults off, a report-only MFA policy, a stale admin account).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

SAMPLE_TENANT_ID = "00000000-0000-4000-8000-000000000161"

_DOMAIN = "halverstoncb.example"


def _user(n: int, name: str, last_sign_in: str | None, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-9000-{n:012d}",
        "displayName": name,
        "userPrincipalName": f"{name.split()[0].lower()}@{_DOMAIN}",
        "accountEnabled": enabled,
        "userType": "Member",
        "signInActivity": {"lastSignInDateTime": last_sign_in},
    }


USERS = [
    _user(1, "Dana Whitfield", "2026-11-20T08:14:00Z"),
    _user(2, "Omar Reyes", "2026-11-21T16:02:00Z"),
    _user(3, "Priya Natarajan", "2026-11-19T10:45:00Z"),
    _user(4, "Legacy Admin", "2025-12-02T09:00:00Z"),
    _user(5, "Front Desk", None, enabled=False),
]

GLOBAL_ADMINS = [{k: USERS[i][k] for k in ("id", "displayName", "userPrincipalName")} for i in (0, 1, 3)]

SAMPLE_RESPONSES: dict[str, Any] = {
    "/v1.0/organization": {
        "value": [
            {
                "id": SAMPLE_TENANT_ID,
                "displayName": "Halverston Community Bank (sample)",
                "verifiedDomains": [{"name": _DOMAIN, "isDefault": True}],
            }
        ]
    },
    "/v1.0/policies/identitySecurityDefaultsEnforcementPolicy": {
        "id": "00000000-0000-0000-0000-000000000005",
        "displayName": "Security Defaults",
        "isEnabled": False,
    },
    "/v1.0/identity/conditionalAccess/policies": {
        "value": [
            {
                "id": "require-mfa-admins",
                "displayName": "Require MFA for administrators",
                "state": "enabledForReportingButNotEnforced",
                "conditions": {
                    "users": {"includeRoles": ["62e90394-69f5-4237-9190-012177145e10"]},
                    "applications": {"includeApplications": ["All"]},
                },
                "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
            },
            {
                "id": "block-legacy-auth",
                "displayName": "Block legacy authentication",
                "state": "enabled",
                "conditions": {
                    "users": {"includeUsers": ["All"]},
                    "clientAppTypes": ["exchangeActiveSync", "other"],
                },
                "grantControls": {"operator": "OR", "builtInControls": ["block"]},
            },
        ]
    },
    "/v1.0/directoryRoles(roleTemplateId='62e90394-69f5-4237-9190-012177145e10')/members": {
        "value": GLOBAL_ADMINS
    },
    "/v1.0/users": {"value": USERS},
    "/v1.0/reports/authenticationMethods/userRegistrationDetails": {
        "value": [
            {
                "id": user["id"],
                "userPrincipalName": user["userPrincipalName"],
                "isAdmin": user in (USERS[0], USERS[1], USERS[3]),
                "isMfaRegistered": user is not USERS[3],
                "methodsRegistered": [] if user is USERS[3] else ["microsoftAuthenticatorPush"],
            }
            for user in USERS
        ]
    },
    "/v1.0/subscribedSkus": {
        "value": [
            {
                "skuId": "f245ecc8-75af-4f8e-b61f-27d8114de5f3",
                "skuPartNumber": "O365_BUSINESS_PREMIUM",
                "capabilityStatus": "Enabled",
                "consumedUnits": 5,
                "prepaidUnits": {"enabled": 10, "suspended": 0, "warning": 0},
            }
        ]
    },
}

Handler = Callable[[httpx.Request], httpx.Response]


def sample_handler(overrides: dict[str, httpx.Response] | None = None) -> Handler:
    """Answer Graph requests from `SAMPLE_RESPONSES`; `overrides` replaces the answer for a path."""
    overrides = overrides or {}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method != "GET" and not path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(405, json={"error": {"code": "MethodNotAllowed"}})
        if path in overrides:
            return overrides[path]
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "sample-token", "token_type": "Bearer"})
        if path in SAMPLE_RESPONSES:
            return httpx.Response(200, content=json.dumps(SAMPLE_RESPONSES[path]).encode())
        return httpx.Response(404, json={"error": {"code": "Request_ResourceNotFound"}})

    return handle


def sample_transport(overrides: dict[str, httpx.Response] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(sample_handler(overrides))
