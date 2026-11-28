"""Microsoft Graph tenant reader (AGRC-161), against sample answers: no network, no database."""

from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.m365.graph import GraphCredentials, GraphTenantReader, M365CollectionError
from app.services.m365.sample import SAMPLE_TENANT_ID, sample_handler, sample_transport

CREDENTIALS = GraphCredentials("contoso-tenant", "client-id", "client-secret-must-not-leak")
NON_PREMIUM = httpx.Response(
    403, json={"error": {"code": "Authentication_RequestFromNonPremiumTenantOrB2CTenant"}}
)


def collect(overrides=None, transport=None):
    with GraphTenantReader(CREDENTIALS, transport=transport or sample_transport(overrides)) as reader:
        return reader.collect()


def test_a_collection_reads_every_section_from_the_tenant():
    data = collect()

    assert data["schema_version"] == 1
    assert data["tenant"]["id"] == SAMPLE_TENANT_ID
    assert data["tenant"]["verified_domains"] == ["halverstoncb.example"]
    sections = data["sections"]
    assert {name: section["status"] for name, section in sections.items()} == {
        "securityDefaults": "collected",
        "conditionalAccess": "collected",
        "globalAdministrators": "collected",
        "users": "collected",
        "signInActivity": "collected",
        "mfaRegistration": "collected",
        "subscribedSkus": "collected",
    }
    assert sections["securityDefaults"]["data"]["isEnabled"] is False
    assert len(sections["globalAdministrators"]["data"]) == 3
    assert "signInActivity" in sections["users"]["data"][0]


def test_the_reader_only_reads():
    seen = []
    handler = sample_handler()

    def record(request):
        seen.append((request.method, request.url.path))
        return handler(request)

    collect(transport=httpx.MockTransport(record))

    assert seen[0] == ("POST", "/contoso-tenant/oauth2/v2.0/token")
    assert {method for method, _ in seen[1:]} == {"GET"}


def test_the_token_request_uses_client_credentials_and_graph_scope():
    bodies = []
    handler = sample_handler()

    def record(request):
        if request.method == "POST":
            bodies.append(request.content.decode())
        return handler(request)

    collect(transport=httpx.MockTransport(record))

    assert "grant_type=client_credentials" in bodies[0]
    assert "scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" in bodies[0]


def test_a_tenant_without_entra_p1_records_premium_sections_as_not_available():
    data = collect(
        {
            "/v1.0/identity/conditionalAccess/policies": NON_PREMIUM,
            "/v1.0/reports/authenticationMethods/userRegistrationDetails": NON_PREMIUM,
        }
    )
    sections = data["sections"]
    assert sections["conditionalAccess"]["status"] == "not_available"
    assert "licence" in sections["conditionalAccess"]["reason"]
    assert sections["mfaRegistration"]["status"] == "not_available"


def test_without_sign_in_activity_the_users_are_read_without_it():
    calls = []
    handler = sample_handler()

    def answer(request):
        if request.url.path == "/v1.0/users":
            select = request.url.params["$select"]
            calls.append(select)
            if "signInActivity" in select:
                return NON_PREMIUM
        return handler(request)

    sections = collect(transport=httpx.MockTransport(answer))["sections"]

    assert len(calls) == 2 and "signInActivity" not in calls[1]
    assert sections["users"]["status"] == "collected"
    assert sections["signInActivity"]["status"] == "not_available"


def test_users_are_read_across_pages():
    handler = sample_handler()
    first = {"value": [{"id": "u1"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skiptoken=next"}

    def answer(request):
        if request.url.path == "/v1.0/users":
            if "$skiptoken" in request.url.params:
                return httpx.Response(200, json={"value": [{"id": "u2"}]})
            return httpx.Response(200, json=first)
        return handler(request)

    users = collect(transport=httpx.MockTransport(answer))["sections"]["users"]["data"]
    assert [user["id"] for user in users] == ["u1", "u2"]


def test_a_rejected_sign_in_fails_the_collection():
    with pytest.raises(M365CollectionError) as failure:
        collect({"/contoso-tenant/oauth2/v2.0/token": httpx.Response(401, json={"error": "invalid_client"})})

    assert failure.value.kind == "authentication"
    assert "invalid_client" in failure.value.message
    assert "client-secret-must-not-leak" not in failure.value.message


def test_a_missing_permission_fails_the_collection():
    denied = httpx.Response(403, json={"error": {"code": "Authorization_RequestDenied"}})
    with pytest.raises(M365CollectionError) as failure:
        collect({"/v1.0/policies/identitySecurityDefaultsEnforcementPolicy": denied})

    assert failure.value.kind == "permission"
    assert "identitySecurityDefaultsEnforcementPolicy" in failure.value.message


def test_an_unreachable_graph_fails_the_collection():
    def offline(request):
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(M365CollectionError) as failure:
        collect(transport=httpx.MockTransport(offline))
    assert failure.value.kind == "connection"


def test_a_graph_server_error_fails_the_collection():
    with pytest.raises(M365CollectionError) as failure:
        collect({"/v1.0/subscribedSkus": httpx.Response(503)})
    assert failure.value.kind == "connection"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_collection_is_off_by_default():
    assert _settings().ms365_data_mode == "disabled"


def test_graph_mode_needs_the_tenant_app_and_organization():
    with pytest.raises(ValidationError, match="MS365_CLIENT_SECRET"):
        _settings(ms365_data_mode="graph", ms365_tenant_id="t", ms365_client_id="c", ms365_organization_id=uuid4())

    settings = _settings(
        ms365_data_mode="graph",
        ms365_tenant_id="t",
        ms365_client_id="c",
        ms365_client_secret="s",
        ms365_organization_id=uuid4(),
    )
    assert settings.ms365_client_secret.get_secret_value() == "s"


def test_sample_mode_is_not_allowed_in_production():
    with pytest.raises(ValidationError, match="MS365_DATA_MODE=sample"):
        _settings(app_environment="production", ms365_data_mode="sample")
