"""Controls in scope of a new assessment, per knowledge-base version (AGRC-73), and the
NIST CSF 2.0 functions and categories used to group them (AGRC-63).

Until the knowledge base is stored in the database (E0-03), the scope of an
assessment is the set of NIST CSF 2.0 subcategories that the agent's knowledge
base asks about. A test checks this list against the mappings in
agentic_grc_agent/data/kb_demo.yaml, so the two cannot drift apart.
"""

# Official NIST CSF 2.0 functions and categories (NIST CSWP 29, Appendix A), in framework order.
CSF_FUNCTIONS = {
    "GV": "Govern",
    "ID": "Identify",
    "PR": "Protect",
    "DE": "Detect",
    "RS": "Respond",
    "RC": "Recover",
}

CSF_CATEGORIES = {
    "GV.OC": "Organizational Context",
    "GV.RM": "Risk Management Strategy",
    "GV.RR": "Roles, Responsibilities, and Authorities",
    "GV.PO": "Policy",
    "GV.OV": "Oversight",
    "GV.SC": "Cybersecurity Supply Chain Risk Management",
    "ID.AM": "Asset Management",
    "ID.RA": "Risk Assessment",
    "ID.IM": "Improvement",
    "PR.AA": "Identity Management, Authentication, and Access Control",
    "PR.AT": "Awareness and Training",
    "PR.DS": "Data Security",
    "PR.PS": "Platform Security",
    "PR.IR": "Technology Infrastructure Resilience",
    "DE.CM": "Continuous Monitoring",
    "DE.AE": "Adverse Event Analysis",
    "RS.MA": "Incident Management",
    "RS.AN": "Incident Analysis",
    "RS.CO": "Incident Response Reporting and Communication",
    "RS.MI": "Incident Mitigation",
    "RC.RP": "Incident Recovery Plan Execution",
    "RC.CO": "Incident Recovery Communication",
}

# Official NIST CSF 2.0 subcategory wording (NIST CSWP 29). These titles end up in the report and the PDF.
CSF_SUBCATEGORY_TITLES = {
    "PR.AA-01": (
        "Identities and credentials for authorized users, services, and hardware "
        "are managed by the organization"
    ),
    "PR.AA-03": "Users, services, and hardware are authenticated",
    "PR.AA-05": (
        "Access permissions, entitlements, and authorizations are defined in a policy, "
        "managed, enforced, and reviewed, and incorporate the principles of least "
        "privilege and separation of duties"
    ),
}

# Knowledge-base version -> the subcategory codes its questions map to.
KB_SCOPES = {
    "demo-0.2": ("PR.AA-01", "PR.AA-03", "PR.AA-05"),
}


def controls_for_kb_version(kb_version: str) -> list[tuple[str, str]]:
    """(code, title) of every control in scope for this knowledge-base version."""
    return [(code, CSF_SUBCATEGORY_TITLES[code]) for code in KB_SCOPES[kb_version]]


def group_controls_by_domain(controls: list[tuple[str, str]]) -> list[dict]:
    """Group (code, title) controls into CSF functions and categories, in framework order.

    Only functions and categories that contain at least one of the given controls are returned.
    A category missing from the catalog keeps its code and gets name None, so nothing is invented.
    """
    by_category: dict[str, list[dict]] = {}
    for code, title in sorted(controls):
        by_category.setdefault(code.split("-")[0], []).append({"code": code, "title": title})

    category_order = list(CSF_CATEGORIES)
    functions = []
    for function_code, function_name in CSF_FUNCTIONS.items():
        category_codes = sorted(
            (code for code in by_category if code.startswith(f"{function_code}.")),
            key=lambda code: (
                category_order.index(code) if code in CSF_CATEGORIES else len(category_order),
                code,
            ),
        )
        if not category_codes:
            continue
        functions.append(
            {
                "code": function_code,
                "name": function_name,
                "categories": [
                    {
                        "code": category_code,
                        "name": CSF_CATEGORIES.get(category_code),
                        "controls": by_category[category_code],
                    }
                    for category_code in category_codes
                ],
            }
        )
    return functions
