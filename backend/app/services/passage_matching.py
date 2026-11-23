"""Passages of uploaded documents that are relevant to the controls of an assessment (HU-12).

The text extracted from each evidence file is split into passages (paragraphs, or groups of
wrapped lines), and every passage is scored against every in-scope control with a fixed list of
English and Spanish terms per control. A match names the file, where the passage is (page,
section and character range in the extracted text), a literal excerpt, the terms that matched
and a confidence.

The matcher is deterministic and lexical: no model call, the same text always gives the same
matches, and every match can be explained by the terms it lists. It runs on demand, so matches
are never stale and nothing is stored; MATCHER_VERSION tells one matcher apart from the next.

A match only says that a passage is about a control. It is not evidence that the control is
implemented: a policy proves intent, not implementation (Aligo's evidence rubric), and only a
consultant verifies evidence. Matches are suggestions for the consultant (link the file to the
control) and the input of HU-13 (answer proposals that the representative confirms).
"""

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import AssessmentControl, EvidenceControlLink, EvidenceFile

MATCHER_VERSION = "lexical-0.1"

# A match needs at least one core term. With only one core term the confidence is
# MIN_MATCH_CONFIDENCE; each further core or supporting term raises it.
MIN_MATCH_CONFIDENCE = 0.55
MAX_CONFIDENCE = 0.95
EXCERPT_MAX_CHARS = 300
MAX_MATCHES_PER_FILE_AND_CONTROL = 3

# A passage grows line by line until it reaches this length, then the next line starts a new one.
PASSAGE_TARGET_CHARS = 700
PAGE_BREAK = "\f"


@dataclass(frozen=True)
class ControlTerms:
    core: tuple[str, ...]
    supporting: tuple[str, ...]


# Terms are written lower case and without accents; the text is folded the same way before
# matching, so "Autenticación" matches "autenticacion". A core term on its own is enough for a
# match; supporting terms only raise the confidence of a passage that already has a core term.
CONTROL_TERMS = {
    "PR.AA-01": ControlTerms(
        core=(
            "offboarding",
            "leaver",
            "employee leaving",
            "employee leaves",
            "deprovisioning",
            "deprovision",
            "disable the account",
            "disable their account",
            "disabled account",
            "disable accounts",
            "account is disabled",
            "accounts are disabled",
            "revoke access",
            "access revocation",
            "account removal",
            "identity lifecycle",
            "joiner mover leaver",
            "desvinculacion",
            "baja de usuario",
            "baja del empleado",
            "retiro del empleado",
            "revocacion de acceso",
            "deshabilitar la cuenta",
            "cuenta deshabilitada",
            "ciclo de vida de la identidad",
        ),
        # "termination of employment" is supporting only: policies also use it for disciplinary action.
        supporting=(
            "termination of employment",
            "employee termination",
            "human resources",
            "hr",
            "last working day",
            "last day",
            "employee",
            "contractor",
            "within 24 hours",
            "same day",
            "recursos humanos",
            "empleado",
            "contratista",
            "ultimo dia",
        ),
    ),
    "PR.AA-03": ControlTerms(
        core=(
            "multi factor authentication",
            "multifactor authentication",
            "mfa",
            "two factor authentication",
            "2fa",
            "second factor",
            "two step verification",
            "conditional access",
            "autenticacion multifactor",
            "autenticacion de doble factor",
            "doble factor",
            "segundo factor",
            "verificacion en dos pasos",
            "acceso condicional",
        ),
        supporting=(
            "administrator",
            "admin account",
            "administrative account",
            "privileged account",
            "privileged access",
            "privileged role",
            "authenticator",
            "hardware key",
            "security key",
            "fido2",
            "break glass",
            "administrador",
            "cuenta privilegiada",
            "acceso privilegiado",
        ),
    ),
    "PR.AA-05": ControlTerms(
        core=(
            "access review",
            "user access review",
            "access recertification",
            "recertification",
            "review of access rights",
            "access rights review",
            "entitlement review",
            "privilege review",
            "review the access privileges",
            "review of access privileges",
            "re evaluate the access privileges",
            "least privilege",
            "need to know",
            "revision de accesos",
            "revision de permisos",
            "recertificacion",
            "minimo privilegio",
            "privilegio minimo",
            "necesidad de conocer",
        ),
        supporting=(
            "quarterly",
            "annually",
            "semiannual",
            "periodic",
            "permissions",
            "access rights",
            "entitlements",
            "role based access",
            "rbac",
            "separation of duties",
            "segregation of duties",
            "system owner",
            "trimestral",
            "anual",
            "periodica",
            "permisos",
            "segregacion de funciones",
        ),
    ),
}


@dataclass(frozen=True)
class Passage:
    char_start: int  # offsets in the extracted text, end exclusive
    char_end: int
    text: str
    page: int | None
    section: str | None


@dataclass(frozen=True)
class TextMatch:
    control_code: str
    passage: Passage
    excerpt: str
    matched_terms: tuple[str, ...]
    confidence: float


def _fold_char(char: str) -> str:
    lowered = char.lower()
    if not lowered:
        return char
    return unicodedata.normalize("NFKD", lowered)[0]


def fold(text: str) -> str:
    """Lower case without accents, one character for each character, so positions stay valid."""
    return "".join(_fold_char(char) for char in text)


def _term_pattern(term: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in term.split()]
    # Words may be separated by spaces, hyphens or slashes; the last one may be plural.
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-/]+".join(words) + r"(?:s|es)?(?![a-z0-9])")


_PATTERNS = {
    code: (
        tuple((term, _term_pattern(term)) for term in terms.core),
        tuple((term, _term_pattern(term)) for term in terms.supporting),
    )
    for code, terms in CONTROL_TERMS.items()
}

_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.|section \d+|article \d+)\s+\S", re.IGNORECASE)
_SMALL_WORDS = {"a", "an", "and", "of", "the", "for", "to", "in", "on", "de", "del", "la", "el", "y", "los", "las"}


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not 3 <= len(stripped) <= 90 or stripped[-1] in ".;,":
        return False
    words = stripped.split()
    if len(words) > 12:
        return False
    if stripped.endswith(":") or _NUMBERED_HEADING.match(stripped):
        return True
    letters = [char for char in stripped if char.isalpha()]
    if len(letters) >= 4 and all(char.isupper() for char in letters):
        return True
    title_words = [word for word in words if word.lower() not in _SMALL_WORDS]
    return 0 < len(words) <= 6 and all(word[:1].isupper() for word in title_words)


def split_passages(text: str) -> list[Passage]:
    """Passages of the extracted text, with their offsets, page and section.

    A blank line, a heading, a page break or reaching PASSAGE_TARGET_CHARS ends a passage. Pages
    are known only when the text has page breaks (PDFs uploaded after HU-12); otherwise page is None.
    """
    has_pages = PAGE_BREAK in text
    passages: list[Passage] = []
    page = 1
    section: str | None = None
    start: int | None = None
    end = 0

    def close() -> None:
        nonlocal start
        if start is not None and text[start:end].strip():
            passages.append(
                Passage(
                    char_start=start,
                    char_end=end,
                    text=text[start:end],
                    page=page if has_pages else None,
                    section=section,
                )
            )
        start = None

    position = 0
    for raw_line in re.split(r"(\n|\f)", text):
        if raw_line == "\n":
            position += 1
            continue
        if raw_line == PAGE_BREAK:
            close()
            page += 1
            position += 1
            continue
        line_start, position = position, position + len(raw_line)
        stripped = raw_line.strip()
        if not stripped:
            close()
            continue
        if _is_heading(raw_line):
            close()
            section = stripped.rstrip(":").strip()
            continue
        if start is None:
            start = line_start + (len(raw_line) - len(raw_line.lstrip()))
        end = line_start + len(raw_line.rstrip())
        if end - start >= PASSAGE_TARGET_CHARS:
            close()
    close()
    return passages


def _excerpt(text: str, passage: Passage, first_hit: int) -> str:
    """At most EXCERPT_MAX_CHARS of literal passage text around the first core term."""
    collapsed = " ".join(passage.text.split())
    if len(collapsed) <= EXCERPT_MAX_CHARS:
        return collapsed
    window_start = max(passage.char_start, first_hit - EXCERPT_MAX_CHARS // 3)
    # Start at a word, not in the middle of one.
    while window_start > passage.char_start and not text[window_start - 1].isspace() and window_start < first_hit:
        window_start += 1
    window = " ".join(text[window_start:passage.char_end].split())
    if len(window) <= EXCERPT_MAX_CHARS:
        return window
    cut = window[:EXCERPT_MAX_CHARS]
    last_space = cut.rfind(" ")
    return cut[:last_space] if last_space > EXCERPT_MAX_CHARS // 2 else cut


def _confidence(core_hits: int, supporting_hits: int) -> float:
    score = MIN_MATCH_CONFIDENCE + 0.1 * (core_hits - 1) + 0.1 * min(supporting_hits, 3)
    return round(min(score, MAX_CONFIDENCE), 2)


def match_text(text: str, control_codes: list[str]) -> list[TextMatch]:
    """Matches between the passages of one text and the given controls.

    Controls without terms in CONTROL_TERMS are skipped; the caller reports them. For each control
    the best MAX_MATCHES_PER_FILE_AND_CONTROL passages are kept, most confident first.
    """
    folded = fold(text)
    passages = split_passages(text)
    matches: list[TextMatch] = []
    for code in control_codes:
        if code not in _PATTERNS:
            continue
        core_patterns, supporting_patterns = _PATTERNS[code]
        found = []
        for passage in passages:
            scope = folded[passage.char_start:passage.char_end]
            heading = fold(passage.section or "")
            core = []
            first_hit = None
            for term, pattern in core_patterns:
                hit = pattern.search(scope)
                if hit or pattern.search(heading):
                    core.append(term)
                    if hit and (first_hit is None or hit.start() < first_hit):
                        first_hit = hit.start()
            if not core:
                continue
            supporting = [term for term, pattern in supporting_patterns if pattern.search(scope)]
            anchor = passage.char_start + (first_hit or 0)
            found.append(
                TextMatch(
                    control_code=code,
                    passage=passage,
                    excerpt=_excerpt(text, passage, anchor),
                    matched_terms=tuple(core + supporting),
                    confidence=_confidence(len(core), len(supporting)),
                )
            )
        found.sort(key=lambda match: (-match.confidence, match.passage.char_start))
        matches.extend(found[:MAX_MATCHES_PER_FILE_AND_CONTROL])
    return matches


@dataclass(frozen=True)
class PassageMatch:
    evidence_file_id: UUID
    file_name: str
    assessment_control_id: UUID
    control_code: str
    match: TextMatch
    linked: bool  # the file is already linked to this control


@dataclass(frozen=True)
class AssessmentPassageMatches:
    matches: list[PassageMatch]
    files_checked: int
    controls_without_terms: list[str]


def find_passage_matches(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    *,
    evidence_file_id: UUID | None = None,
    min_confidence: float = MIN_MATCH_CONFIDENCE,
) -> AssessmentPassageMatches:
    """Matches for the in-scope controls of one assessment.

    The files are the organization's files of this assessment and the organization's files that
    belong to no assessment: the same files that can be linked to its controls.
    """
    controls = list(
        db.scalars(
            select(AssessmentControl)
            .where(
                AssessmentControl.organization_id == organization_id,
                AssessmentControl.assessment_id == assessment_id,
                AssessmentControl.in_scope.is_(True),
            )
            .order_by(AssessmentControl.control_code)
        )
    )
    statement = select(EvidenceFile).where(
        EvidenceFile.organization_id == organization_id,
        or_(EvidenceFile.assessment_id == assessment_id, EvidenceFile.assessment_id.is_(None)),
    )
    if evidence_file_id is not None:
        statement = statement.where(EvidenceFile.id == evidence_file_id)
    files = list(db.scalars(statement.order_by(EvidenceFile.created_at, EvidenceFile.id)))

    linked_pairs = set(
        db.execute(
            select(EvidenceControlLink.evidence_file_id, EvidenceControlLink.assessment_control_id).where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.assessment_id == assessment_id,
            )
        ).all()
    )
    control_by_code = {control.control_code: control for control in controls}
    codes = list(control_by_code)

    matches = []
    for evidence_file in files:
        for text_match in match_text(evidence_file.extracted_text, codes):
            if text_match.confidence < min_confidence:
                continue
            control = control_by_code[text_match.control_code]
            matches.append(
                PassageMatch(
                    evidence_file_id=evidence_file.id,
                    file_name=evidence_file.original_filename,
                    assessment_control_id=control.id,
                    control_code=control.control_code,
                    match=text_match,
                    linked=(evidence_file.id, control.id) in linked_pairs,
                )
            )
    matches.sort(
        key=lambda item: (item.control_code, -item.match.confidence, item.file_name, item.match.passage.char_start)
    )
    return AssessmentPassageMatches(
        matches=matches,
        files_checked=len(files),
        controls_without_terms=[code for code in codes if code not in CONTROL_TERMS],
    )
