"""Passage matching of document text to controls (HU-12). Pure unit tests, no database."""

import tempfile
from pathlib import Path

from reportlab.pdfgen import canvas

from app.api.v1.endpoints.evidence import extract_text
from app.services.assessment_scope import KB_SCOPES
from app.services.passage_matching import (
    CONTROL_TERMS,
    EXCERPT_MAX_CHARS,
    MAX_CONFIDENCE,
    MAX_MATCHES_PER_FILE_AND_CONTROL,
    MIN_MATCH_CONFIDENCE,
    fold,
    match_text,
    split_passages,
)

DEMO_CONTROLS = ["PR.AA-01", "PR.AA-03", "PR.AA-05"]


def matches_for(text, code):
    return [match for match in match_text(text, DEMO_CONTROLS) if match.control_code == code]


# --- The term lists ------------------------------------------------------------------------


def test_every_control_in_the_kb_scope_has_terms():
    in_scope = {code for codes in KB_SCOPES.values() for code in codes}

    assert set(CONTROL_TERMS) == in_scope


def test_terms_are_written_folded_and_core_terms_exist():
    for code, terms in CONTROL_TERMS.items():
        assert terms.core, code
        for term in terms.core + terms.supporting:
            assert term == fold(term), (code, term)
            assert term == " ".join(term.split()), (code, term)
        assert not set(terms.core) & set(terms.supporting), code


# --- Matching ------------------------------------------------------------------------------


def test_an_english_mfa_passage_matches_pr_aa_03_with_its_terms():
    text = "All administrator accounts must use MFA with an authenticator app when they sign in."

    [match] = matches_for(text, "PR.AA-03")

    assert match.matched_terms == ("mfa", "administrator", "authenticator")
    assert match.confidence == 0.75
    assert match.excerpt == text


def test_a_spanish_passage_with_accents_matches():
    text = "Todas las cuentas de administrador deben usar autenticación multifactor."

    [match] = matches_for(text, "PR.AA-03")

    assert match.matched_terms == ("autenticacion multifactor", "administrador")
    assert match.excerpt == text  # the excerpt keeps the original text, accents included


def test_unrelated_text_gives_no_match():
    text = "The cafeteria opens at eight. Visitors sign the guest book at reception."

    assert match_text(text, DEMO_CONTROLS) == []


def test_supporting_terms_alone_are_not_a_match():
    text = "Every employee and contractor reports to human resources on the last working day."

    assert matches_for(text, "PR.AA-01") == []


def test_terms_match_whole_words_only():
    # "hr" inside "three" and "mfa" inside "comfortable" must not count.
    text = "Three comfortable chairs. Offboarding is handled by the service desk."

    [match] = matches_for(text, "PR.AA-01")

    assert match.matched_terms == ("offboarding",)


def test_plural_and_hyphenated_forms_match():
    text = "Leavers are removed by the service desk. Multi-factor authentication is mandatory."

    assert matches_for(text, "PR.AA-01")[0].matched_terms[0] == "leaver"
    assert matches_for(text, "PR.AA-03")[0].matched_terms[0] == "multi factor authentication"


def test_confidence_grows_with_terms_and_is_capped():
    one_term = "Offboarding is documented."
    many_terms = (
        "Offboarding: human resources notifies IT on the last working day, and the employee or "
        "contractor has their account deprovisioned within 24 hours; access revocation is logged."
    )

    assert matches_for(one_term, "PR.AA-01")[0].confidence == MIN_MATCH_CONFIDENCE
    assert matches_for(many_terms, "PR.AA-01")[0].confidence == MAX_CONFIDENCE


def test_the_same_text_always_gives_the_same_matches():
    text = "Access rights are subject to a quarterly access review.\n\nMFA is required for admins."

    assert match_text(text, DEMO_CONTROLS) == match_text(text, DEMO_CONTROLS)


def test_controls_without_terms_are_skipped():
    assert match_text("MFA is required for every login.", ["DE.CM-01"]) == []


def test_at_most_a_few_passages_per_control():
    text = "\n\n".join(f"Paragraph {number}: MFA is required." for number in range(6))

    assert len(matches_for(text, "PR.AA-03")) == MAX_MATCHES_PER_FILE_AND_CONTROL


# --- Locator and excerpt -------------------------------------------------------------------


def test_the_locator_points_at_the_passage_in_the_extracted_text():
    text = "Introduction to the policy.\n\nOffboarding: accounts are disabled on the last day.\n\nEnd."

    [match] = matches_for(text, "PR.AA-01")

    passage = match.passage
    assert text[passage.char_start:passage.char_end] == "Offboarding: accounts are disabled on the last day."
    assert passage.page is None  # no page breaks in this text


def test_page_breaks_give_the_page_number():
    text = "Cover page\fSecond page about something else.\fThird page: MFA is required for admins."

    [match] = matches_for(text, "PR.AA-03")

    assert match.passage.page == 3


def test_a_heading_becomes_the_section_and_its_terms_count():
    text = "3.2 Access Review\nAll access rights are checked every quarter by the system owner."

    [match] = matches_for(text, "PR.AA-05")

    assert match.passage.section == "3.2 Access Review"
    assert "access review" in match.matched_terms
    assert match.excerpt == "All access rights are checked every quarter by the system owner."


def test_a_long_passage_gives_a_short_excerpt_around_the_first_core_term():
    filler = "This sentence describes general security governance in some detail. " * 8
    text = filler + "Administrators must use multi-factor authentication for every remote login. " + filler

    [match] = matches_for(text, "PR.AA-03")

    assert len(match.excerpt) <= EXCERPT_MAX_CHARS
    assert "multi-factor authentication" in match.excerpt
    assert match.excerpt.split()[0] in filler.split() + ["Administrators"]  # starts at a word


def test_passages_split_at_blank_lines_and_keep_wrapped_lines_together():
    text = "First line of a paragraph\nthat wraps onto a second line.\n\nA second paragraph."

    passages = split_passages(text)

    assert [passage.text for passage in passages] == [
        "First line of a paragraph\nthat wraps onto a second line.",
        "A second paragraph.",
    ]


# --- Page breaks in uploaded PDFs ----------------------------------------------------------


def test_pdf_extraction_keeps_pages_apart():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policy.pdf"
        document = canvas.Canvas(str(path))
        document.drawString(72, 720, "Cover page")
        document.showPage()
        document.drawString(72, 720, "MFA is required for all administrator accounts.")
        document.showPage()
        document.save()

        text = extract_text(str(path), ".pdf")

    assert text.split("\f") == ["Cover page", "MFA is required for all administrator accounts."]
    assert matches_for(text, "PR.AA-03")[0].passage.page == 2
