"""Controls in scope of a new assessment, per knowledge-base version (AGRC-73).

Until the knowledge base is stored in the database (E0-03), the scope of an
assessment is the set of NIST CSF 2.0 subcategories that the agent's knowledge
base asks about. A test checks this list against the mappings in
app/agent/data/kb_demo.yaml, so the two cannot drift apart.
"""

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
