"""Run snapshots keep the exact gap diagnosis at generation time."""

import pytest

from app.services.gap_analysis_runs import record_gap_analysis_run, run_gap_list
from tests.test_gaps import consultant_version, report_input


class RecordingSession:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        pass


def test_a_run_preserves_unique_gaps_and_explicitly_absent_evidence(monkeypatch):
    data = report_input(
        **{
            "PR.AA-01": [consultant_version("partially_implemented")],
            "PR.AA-03": [consultant_version("not_implemented")],
            "PR.AA-05": [consultant_version("not_applicable")],
        }
    )
    monkeypatch.setattr(
        "app.services.gap_analysis_runs.DbReportSource.load",
        lambda _self, _db, _org, _assessment: data,
    )
    db = RecordingSession()
    row = record_gap_analysis_run(
        db, data.organization.id, data.assessment.id, trigger="regeneration"
    )

    assert db.rows == [row]
    assert row.gap_count == 2
    snapshot = run_gap_list(row)
    assert {gap.control_code for gap in snapshot.gaps} == {"PR.AA-01", "PR.AA-03"}
    assert all(gap.evidence_absent for gap in snapshot.gaps)
    assert len({gap.control_code for gap in snapshot.gaps}) == row.gap_count
    assert snapshot.generated_at.isoformat() == row.snapshot["generated_at"].replace("Z", "+00:00")


def test_a_run_is_not_created_for_an_unknown_assessment(monkeypatch):
    monkeypatch.setattr("app.services.gap_analysis_runs.DbReportSource.load", lambda *_: None)
    db = RecordingSession()
    data = report_input()
    with pytest.raises(ValueError, match="unknown assessment"):
        record_gap_analysis_run(db, data.organization.id, data.assessment.id, trigger="regeneration")
    assert db.rows == []
