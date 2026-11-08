"""Score-free novelty and stored-XSS Oracle boundaries, no lab or model runs."""

import importlib.util
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

s = importlib.util.spec_from_file_location(
    "body_eval", Path(__file__).parents[1] / "scripts/body-carried-request-v3.py"
)
b = importlib.util.module_from_spec(s)
s.loader.exec_module(b)


def test_catalog_is_bounded_and_matching_is_predeclared():
    rows = b.cases()
    assert len(rows) == 24
    assert Counter((r["family"], r["intent"]) for r in rows) == {
        ("xss", "ATTACK_INTENT"): 6,
        ("xss", "BENIGN_INTENT"): 6,
        ("cmd_injection", "ATTACK_INTENT"): 6,
        ("cmd_injection", "BENIGN_INTENT"): 6,
    }
    assert len({r["pair_id"] for r in rows}) == 12
    assert all(r["method"] == "POST" and r["role"] == "EVALUATION_ONLY" for r in rows)


def test_oracle_needs_persistence_and_display_region_not_HTTP200():
    value = '<svg onload="alert(&#49;)"></svg>'
    display = ('<div id="guestbook_comments">Message: ' + value + "<br /></div>").encode()
    ok, proof = b.guestbook_proof(value, display, 200, 0, 1, True)
    assert ok and not proof["browser_execution_tested"]
    assert not b.guestbook_proof(value, display, 200, 0, 0, True)[0]
    assert not b.guestbook_proof(value, value.encode(), 200, 0, 1, True)[0]
    assert not b.guestbook_proof(value, display, 500, 0, 1, True)[0]
    literal = "Literal: &lt;svg onload=&quot;demo&quot;&gt;"
    page = ('<div id="guestbook_comments">Message: ' + literal + "</div>").encode()
    assert b.guestbook_proof(literal, page, 200, 0, 1, False)[0]
    assert not b.guestbook_proof(value, display, 200, 0, 1, False)[0]


def test_old_control_rejects_entire_pair_without_substitution_or_scoring(monkeypatch):
    selected = b.cases()[:2]
    f = np.zeros(588, np.float32)
    x = np.zeros(634, np.float32)
    different = x.copy()
    different[0] = 1
    hist = [{"sample_id": "old", "method": "GET", "endpoint_template": "/other"}]
    monkeypatch.setattr(b, "references", lambda c: (hist, {"old": (x.copy(), f.copy())}, {}, {}))

    def representation(case):
        value = x if case["intent"] == "BENIGN_INTENT" else different
        return f, value, f, {"raw": "new", "template": "new"}, np.zeros(46, np.uint8)

    c = SimpleNamespace(representation=representation)
    excluded, qualified = b.preaudit(c, selected)
    assert not qualified
    assert "HISTORICAL_EXACT_CANDIDATE" in excluded[selected[0]["case_id"]]
    assert all("PAIR_NOT_BOTH_QUALIFIED" in excluded[r["case_id"]] for r in selected)
