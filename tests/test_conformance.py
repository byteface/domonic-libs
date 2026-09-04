"""Gate the curated CSSOM / DOM conformance suite against its baseline.

The suite in ``domonic_libs/conformance/suite/`` runs spec assertions through the
tree-walking interpreter against a live domonic DOM. These tests fail if any file
regresses below :data:`domonic_libs.conformance.BASELINE` -- raise a baseline when
domonic improves, never lower one silently.
"""

import pytest

from domonic_libs.conformance import BASELINE, run_suite

_RESULT = run_suite()
_BY_NAME = {f.filename: f for f in _RESULT.files}


def test_every_suite_file_ran():
    assert set(_BY_NAME) == set(BASELINE), "suite files and BASELINE are out of sync"
    for f in _RESULT.files:
        assert not f.error, f"{f.filename} errored before any case ran: {f.error}"
        assert f.total > 0


@pytest.mark.parametrize("filename", sorted(BASELINE))
def test_file_meets_baseline(filename):
    f = _BY_NAME[filename]
    assert f.passed >= BASELINE[filename], (
        f"{filename}: {f.passed}/{f.total} pass, baseline is {BASELINE[filename]}. "
        + "; ".join(f"{c.name}: {c.message}" for c in f.cases if c.status == "FAIL")
    )


def test_totals_do_not_regress():
    assert _RESULT.passed >= sum(BASELINE.values())
