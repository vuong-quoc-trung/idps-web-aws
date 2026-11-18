import numpy as np
import pytest
from auth_graph import Graph, cutoff
from history import Prefix
from publisher import episodes
from study import measure, threshold


def prefix():
    p = Prefix()
    for i, route in enumerate([1, 2, 1, 2, 3]):
        assert p.observe(5 * i, route) == (None, "SHORT_PREFIX")
    return p


def test_prior_routes_distinguish_same_target_and_are_private():
    first = prefix()
    second = Prefix()
    for i in range(5):
        second.observe(5 * i, 4)
    v, reason = first.observe(25, 1)
    w, _ = second.observe(25, 1)
    assert reason == "AVAILABLE" and v != w
    assert v[:4] == pytest.approx([3 / 5, 1, 2 / 5, 3 / 5])
    assert len(v) == 8 and all(np.isfinite(v))


def test_same_second_uses_shared_prefix_and_makes_next_bucket_ambiguous():
    a, b = prefix(), prefix()
    expected = {r: a.observe(25, r) for r in (1, 2)}
    assert {r: b.observe(25, r) for r in (2, 1)} == expected
    assert a.observe(30, 2) == b.observe(30, 2) == (None, "CLOCK_TIE")


def test_aged_and_nonmonotonic_prefix_abstain():
    assert prefix().observe(2000, 1) == (None, "SESSION_GAP")
    p = prefix()
    assert p.observe(19, 2) == (None, "CLOCK_REGRESSION")
    assert p.observe(22, 1) == (None, "SHORT_PREFIX")


def test_future_does_not_change_committed_projection():
    p = prefix()
    v, _ = p.observe(21, 2)
    for i in range(6):
        p.observe(28 + 3 * i, 9)
    assert v == prefix().observe(21, 2)[0]


def test_publisher_inactivity_boundary_and_order():
    assert episodes({3810, 2010, 100, 209}) == [100, 2010]
    assert episodes([]) == []


def test_strict_threshold_is_tie_safe():
    y = np.r_[np.zeros(199), 1]
    p = np.r_[0.9, 0.9, np.full(197, 0.3), 0.91]
    t = threshold(y, p)
    assert t == 0.9 and measure(y, p, t)["fp"] == 0
    assert cutoff({90: 2, 30: 197}) == 90


def test_abstain_denominator_and_event_group_independence():
    assert (
        measure(np.array([1, 1, 0, 0]), np.array([0.8, np.nan, 0.1, np.nan]), 0.5)["recall"] == 0.5
    )
    g = Graph()
    held = g.score(1, 2, 3)
    assert g.score(1, 2, 3) == held
    g.update({(1, 2, 3): 4, (2, 2, 3): 1})
    assert g.total == 2 and g.score(1, 2, 3)[1] == 0 and g.score(1, 2, 4)[1] == 1
    assert g.score(1, 2, 3)[2] < g.score(1, 2, 4)[2]


def test_compressed_prefix_never_emits_partial_final_line(tmp_path):
    import gzip
    import hashlib

    from auth_graph import lines

    data = gzip.compress(b"first\nsecond\npartial")
    # Release a prefix of gzip with no trailer; include a boundary inside the stream.
    chunks = [data[:13], data[13:-8]]
    manifest = {"chunks": []}
    for i, chunk in enumerate(chunks):
        (tmp_path / f"{i:03d}.gzpart").write_bytes(chunk)
        manifest["chunks"].append({"sha256": hashlib.sha256(chunk).hexdigest()})
    assert list(lines(tmp_path, manifest)) == [b"first", b"second"]
    (tmp_path / "001.gzpart").write_bytes(b"changed")
    with pytest.raises(ValueError, match="untrusted compressed range"):
        list(lines(tmp_path, manifest))


def test_context_uses_both_actor_and_source_with_fixed_destination():
    g = Graph()
    for _ in range(20):
        g.update([(1, 10, 100), (2, 20, 200)])
    known = g.score(1, 10, 100)
    reassigned = g.score(1, 20, 100)
    unfamiliar = g.score(2, 20, 100)
    assert known[0] == reassigned[0] == unfamiliar[0]
    assert known[2] < reassigned[2] < unfamiliar[2]
