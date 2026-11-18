"""Regression test for docs/trace_case.md (M1: FM-03 ticket_trust on C-002@11)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.student


def _eval_ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(
        name="C-002@11",
        inputs={"claim_id": "C-002", "seed": 11},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_trace_case_c002_fm03_caught_on_regression_and_passes_on_fixed():
    from lab9 import graders, trace_case

    bad = trace_case.investigate("seeded_regression", "C-002", 11)
    bad_trial, label = bad["trial"], bad["label"]
    # First wrong step is event #3 (0-indexed: 2): model_override with delay_days=5
    assert bad_trial["events"][2]["kind"] == "model_override"
    assert bad_trial["events"][2]["payload"] == {"delay_days": 5}
    assert graders.DbFactKept().evaluate(_eval_ctx(bad_trial, label)).value is False
    assert bad_trial["snapshot"]["refund_vnd"] == 20000
    assert bad_trial["snapshot"]["refund_vnd"] != label["refund_vnd"]

    good = trace_case.investigate("fixed", "C-002", 11)
    good_trial = good["trial"]
    assert all(e.get("kind") != "model_override" for e in good_trial["events"])
    assert graders.DbFactKept().evaluate(_eval_ctx(good_trial, label)).value is True
    assert good_trial["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
    assert good_trial["snapshot"]["refund_count"] == 0
    assert good_trial["result"]["status"] == label["status"] == "denied"
