"""The assessment scope matches the agent's knowledge base and the official CSF 2.0 wording (AGRC-73, AGRC-63)."""

import re
from pathlib import Path

import yaml

from app.db.models import CSF_CODE_REGEX
from app.schemas.assessments import DEFAULT_KB_VERSION
from app.services.assessment_scope import (
    CSF_CATEGORIES,
    CSF_FUNCTIONS,
    CSF_SUBCATEGORY_TITLES,
    KB_SCOPES,
    controls_for_kb_version,
    group_controls_by_domain,
)

KB_DEMO_PATH = Path(__file__).resolve().parents[1] / "app" / "agent" / "data" / "kb_demo.yaml"


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


def test_catalog_has_the_six_functions_and_22_categories_of_csf_2_0():
    assert list(CSF_FUNCTIONS) == ["GV", "ID", "PR", "DE", "RS", "RC"]
    assert len(CSF_CATEGORIES) == 22
    assert CSF_CATEGORIES["PR.AA"] == "Identity Management, Authentication, and Access Control"
    for category_code in CSF_CATEGORIES:
        assert category_code.split(".")[0] in CSF_FUNCTIONS


def test_demo_scope_groups_into_protect_and_identity_management():
    assert group_controls_by_domain(controls_for_kb_version("demo-0.2")) == [
        {
            "code": "PR",
            "name": "Protect",
            "categories": [
                {
                    "code": "PR.AA",
                    "name": "Identity Management, Authentication, and Access Control",
                    "controls": [
                        {"code": code, "title": title}
                        for code, title in controls_for_kb_version("demo-0.2")
                    ],
                }
            ],
        }
    ]


def test_grouping_follows_framework_order_and_skips_empty_domains():
    controls = [
        ("DE.CM-01", "Networks are monitored"),
        ("PR.DS-01", "Data at rest is protected"),
        ("GV.PO-01", "Policy is established"),
        ("PR.AA-03", "Users are authenticated"),
    ]

    functions = group_controls_by_domain(controls)

    assert [function["code"] for function in functions] == ["GV", "PR", "DE"]
    assert [category["code"] for category in functions[1]["categories"]] == ["PR.AA", "PR.DS"]


def test_unknown_category_keeps_its_code_without_an_invented_name():
    functions = group_controls_by_domain([("PR.ZZ-01", "Not a CSF 2.0 category")])

    assert functions[0]["categories"] == [
        {"code": "PR.ZZ", "name": None, "controls": [{"code": "PR.ZZ-01", "title": "Not a CSF 2.0 category"}]}
    ]


def test_no_controls_gives_no_domains():
    assert group_controls_by_domain([]) == []
