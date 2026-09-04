"""Gate the curated test262-style battery against its baseline.

``src/domonic_libs/js262/suite/*.js`` runs spec assertions through the JS
interpreter. These tests fail if any file regresses below
:data:`domonic_libs.js262.BASELINE`; raise a baseline when the interpreter or
domonic improves, never lower one silently. ``python -m domonic_libs.js262``
regenerates ``docs/js-compliance.md``.
"""

import pytest

from domonic_libs.js262 import BASELINE, run_suite

_RESULT = run_suite()
_BY_NAME = {f.filename: f for f in _RESULT.files}


def test_suite_and_baseline_in_sync():
    assert set(_BY_NAME) == set(BASELINE)
    for f in _RESULT.files:
        assert not f.error, f"{f.filename} errored before any check ran: {f.error}"
        assert f.total > 0


@pytest.mark.parametrize("filename", sorted(BASELINE))
def test_file_meets_baseline(filename):
    f = _BY_NAME[filename]
    assert f.passed >= BASELINE[filename], (
        f"{filename}: {f.passed}/{f.total}, baseline {BASELINE[filename]}. "
        + "; ".join(f"{c.name}: {c.message}" for c in f.cases if c.status == "FAIL")
    )


def test_total_does_not_regress():
    assert _RESULT.passed >= sum(BASELINE.values())
