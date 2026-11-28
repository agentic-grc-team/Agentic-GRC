"""Read-only Microsoft Graph client that collects the tenant configuration (AGRC-161).

It signs in with the client-credentials flow and only sends GET requests to Graph, so it can read the
tenant but never change it. Everything is collected in memory first: when any required call fails, the
caller gets an `M365CollectionError` and nothing is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

LOGIN_BASE_URL = "https://login.microsoftonline.com"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GLOBAL_ADMINISTRATOR_TEMPLATE_ID = "62e90394-69f5-4237-9190-012177145e10"
SNAPSHOT_SCHEMA_VERSION = 1
MAX_PAGES = 50

# Graph answers 403 with these codes when a feature needs a licence the tenant lacks (Entra ID P1):
# the section is then recorded as "not available" instead of failing the whole collection.
LICENCE_ERROR_CODES = frozenset(
    {
        "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
        "AadPremiumLicenseRequired",
    }
)

USER_FIELDS = "id,displayName,userPrincipalName,accountEnabled,userType"


class M365CollectionError(Exception):
    """A connection, sign-in or permission failure. `message` is safe to show to the consultant."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind  # "connection", "authentication" or "permission"


class _LicenceRequired(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


@dataclass(frozen=True)
class GraphCredentials:
    tenant_id: str
    client_id: str
    client_secret: str


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("code") or "")
    if isinstance(error, str):  # the token endpoint answers {"error": "invalid_client", ...}
        return error
    return ""


class GraphTenantReader:
    def __init__(
        self,
        credentials: GraphCredentials,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self._credentials = credentials
        self._client = httpx.Client(transport=transport, timeout=timeout_seconds)
        self._token: str | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GraphTenantReader:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _sign_in(self) -> str:
        url = f"{LOGIN_BASE_URL}/{self._credentials.tenant_id}/oauth2/v2.0/token"
        try:
            response = self._client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                    "scope": GRAPH_SCOPE,
                },
            )
        except httpx.HTTPError as error:
            raise M365CollectionError(
                "Could not reach the Microsoft sign-in service. Check the network and try again.",
                kind="connection",
            ) from error
        if response.status_code != 200:
            code = _error_code(response)
            raise M365CollectionError(
                "Microsoft rejected the app sign-in"
                + (f" ({code})" if code else "")
                + ". Check MS365_TENANT_ID, MS365_CLIENT_ID and MS365_CLIENT_SECRET.",
                kind="authentication",
            )
        token = response.json().get("access_token")
        if not token:
            raise M365CollectionError(
                "The Microsoft sign-in service returned no access token.", kind="authentication"
            )
        return token

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if self._token is None:
            self._token = self._sign_in()
        url = path if path.startswith("https://") else f"{GRAPH_BASE_URL}{path}"
        try:
            response = self._client.get(
                url, params=params, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as error:
            raise M365CollectionError(
                "Could not reach Microsoft Graph. Check the network and try again.",
                kind="connection",
            ) from error
        if response.status_code == 200:
            return response.json()
        code = _error_code(response)
        if response.status_code == 403 and code in LICENCE_ERROR_CODES:
            raise _LicenceRequired(code)
        if response.status_code in (401, 403):
            raise M365CollectionError(
                f"Microsoft Graph refused to read {path.split('?')[0]}"
                + (f" ({code})" if code else "")
                + ". Check that the app has the read-only permissions with admin consent.",
                kind="permission",
            )
        raise M365CollectionError(
            f"Microsoft Graph answered {response.status_code} for {path.split('?')[0]}. Try again later.",
            kind="connection",
        )

    def _get_all(self, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = self._get(path, params)
        for _ in range(MAX_PAGES):
            items.extend(page.get("value", []))
            next_link = page.get("@odata.nextLink")
            if not next_link:
                return items
            page = self._get(next_link)
        raise M365CollectionError(
            f"Microsoft Graph returned more than {MAX_PAGES} pages for {path}.", kind="connection"
        )

    def _optional(self, read) -> dict[str, Any]:
        try:
            return {"status": "collected", "data": read()}
        except _LicenceRequired as missing:
            return {
                "status": "not_available",
                "reason": f"The tenant licence does not include this data ({missing.code}).",
            }

    def collect(self) -> dict[str, Any]:
        """The tenant configuration as one JSON document, or `M365CollectionError`."""
        organization = self._get("/organization", {"$select": "id,displayName,verifiedDomains"})
        details = (organization.get("value") or [{}])[0]

        def users_with_sign_in() -> list[dict[str, Any]]:
            return self._get_all("/users", {"$select": f"{USER_FIELDS},signInActivity", "$top": "999"})

        sign_in = self._optional(users_with_sign_in)
        if sign_in["status"] == "collected":
            users = {"status": "collected", "data": sign_in["data"]}
        else:
            users = {"status": "collected", "data": self._get_all("/users", {"$select": USER_FIELDS, "$top": "999"})}

        sections = {
            "securityDefaults": {
                "status": "collected",
                "data": self._get("/policies/identitySecurityDefaultsEnforcementPolicy"),
            },
            "conditionalAccess": self._optional(
                lambda: self._get_all("/identity/conditionalAccess/policies")
            ),
            "globalAdministrators": {
                "status": "collected",
                "data": self._get_all(
                    f"/directoryRoles(roleTemplateId='{GLOBAL_ADMINISTRATOR_TEMPLATE_ID}')/members",
                    {"$select": "id,displayName,userPrincipalName"},
                ),
            },
            "users": users,
            "signInActivity": {
                "status": sign_in["status"],
                **({"reason": sign_in["reason"]} if "reason" in sign_in else {}),
            },
            "mfaRegistration": self._optional(
                lambda: self._get_all("/reports/authenticationMethods/userRegistrationDetails")
            ),
            "subscribedSkus": {
                "status": "collected",
                "data": self._get_all(
                    "/subscribedSkus",
                    {"$select": "skuId,skuPartNumber,capabilityStatus,consumedUnits,prepaidUnits"},
                ),
            },
        }
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "tenant": {
                "id": details.get("id") or self._credentials.tenant_id,
                "display_name": details.get("displayName"),
                "verified_domains": [
                    domain.get("name") for domain in details.get("verifiedDomains", []) if domain.get("name")
                ],
            },
            "sections": sections,
        }
