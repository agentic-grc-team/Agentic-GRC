"""The assessment scope matches the agent's knowledge base and the official CSF 2.0 wording (AGRC-73)."""

import re
from pathlib import Path

import yaml

from app.db.models import CSF_CODE_REGEX
from app.schemas.assessments import DEFAULT_KB_VERSION
from app.services.assessment_scope import (
    CSF_SUBCATEGORY_TITLES,
    KB_SCOPES,
    controls_for_kb_version,
)

KB_DEMO_PATH = Path(__file__).resolve().parents[2] / "agentic_grc_agent" / "data" / "kb_demo.yaml"


def load_kb_demo() -> dict:
    with KB_DEMO_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_default_kb_version_is_the_agent_kb_version():
    kb = load_kb_demo()

    assert kb["kb_version"] == DEFAULT_KB_VERSION
    assert DEFAULT_KB_VERSION in KB_SCOPES


def test_demo_scope_matches_the_kb_question_mappings():
    kb = load_kb_demo()
    mapped_codes = {
        mapping["node_code"]
        for question in kb["questions"]
        for mapping in question["mappings"]
    }

    assert set(KB_SCOPES[kb["kb_version"]]) == mapped_codes


def test_titles_are_the_official_csf_wording():
    assert CSF_SUBCATEGORY_TITLES == {
        "PR.AA-01": "Identities and credentials for authorized users, services, and hardware are managed by the organization",
        "PR.AA-03": "Users, services, and hardware are authenticated",
        "PR.AA-05": "Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed, and incorporate the principles of least privilege and separation of duties",
    }


def test_every_scope_code_has_a_title_and_a_valid_format():
    for codes in KB_SCOPES.values():
        assert len(codes) == len(set(codes))
        for code in codes:
            assert re.fullmatch(CSF_CODE_REGEX, code)
            assert code in CSF_SUBCATEGORY_TITLES


def test_controls_for_kb_version_returns_codes_with_titles_in_order():
    assert controls_for_kb_version("demo-0.2") == [
        ("PR.AA-01", CSF_SUBCATEGORY_TITLES["PR.AA-01"]),
        ("PR.AA-03", CSF_SUBCATEGORY_TITLES["PR.AA-03"]),
        ("PR.AA-05", CSF_SUBCATEGORY_TITLES["PR.AA-05"]),
    ]
