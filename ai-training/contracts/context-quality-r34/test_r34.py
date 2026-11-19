"""Regression tests for causal masking, privacy, event binding and metric denominators."""

import numpy as np
from field_schema import FEATURES, WIDTH, project
from login_data import DAY, RAW, features, mix
from login_study import cutoff, measure


def history(t, users=None):
    rows = np.zeros(len(t), dtype=RAW)
    rows["user"] = users if users is not None else 10
    rows["ts"] = t
    rows["ctx"] = (np.arange(len(t))[:, None] % 2) + np.arange(1, 6)
    return rows


def test_prefix_and_label_invariance():
    a = history([1, 4, 9, 12])
    expected, supported = features(a[:3])
    assert list(supported) == [False, True, True]
    a["y"] = 1
    v, good = features(a)
    np.testing.assert_array_equal(v[:3], expected)
    np.testing.assert_array_equal(good[:3], supported)
    a["ctx"][3] = 101
    np.testing.assert_array_equal(features(a)[0][:3], expected)


def test_ties_have_shared_prefix_then_abstain():
    v, ok = features(history([2, 9, 9, 21]))
    assert list(ok) == [False, True, True, False]
    assert v[1, 0] == v[2, 0] == np.float32(1 / 5)
    assert not v[3].any()


def test_actor_scope_and_retention():
    rows = history([0, DAY, 0, 31 * DAY, 32 * DAY], [1, 1, 2, 2, 2])
    v, ok = features(rows)
    assert list(ok) == [False, True, False, False, True]
    assert v[-1, 0] == np.float32(1 / 5)
    rows["ctx"][-1, :] = 0
    assert not features(rows)[1][-1]


def test_distinct_stable_actor_roles():
    a = np.arange(1024, dtype=np.uint64)
    assert len(np.unique(mix(a))) == len(a)
    roles = mix(a) % 100
    np.testing.assert_array_equal(roles[::-1], mix(a[::-1]) % 100)
    assert set(roles) == set(range(100))


def test_mixed_json_duplicate_and_form_agree():
    single = project("/?page=2", '{"quantity":3}')
    assert single == project("/?page=4", "quantity=1")
    assert len(single) == 2 * WIDTH == len(set(FEATURES))
    both = project("/?page=2", '{"quantity":3,"quantity":"small"}')
    assert both[-5:-2] == [1, 1, 1]
    assert project("/", "{}") == project("/", None)


def test_excludes_private_literals_and_caps():
    assert not any(project("/?token=abc", '{"password":"abc","q":"joe@example.org"}'))
    assert not any(project("/", '{"tags":'))
    assert not any(project("/", "q=" + "a" * 4097))
    assert max(project("/", "&".join(["page=2"] * 31))) == 4
    assert project("/", '{"items":[{"token":"value1"}]}') == project("/", '{"items":[3,5]}')
    assert project("/?page=1%26limit%3D2", None) != project("/?page=1&limit=2", None)


def test_strict_ties_and_all_request_denominator():
    y = np.array([0] * 400 + [1, 1])
    p = np.array([0.0] * 398 + [0.7, 0.9, np.nan, 0.8])
    w = np.ones(len(y))
    t = cutoff(y, p, w)
    cell = measure(y, p, t, w)
    assert cell["effective_recall"] == 0.5 and cell["reference_alert_rate"] == 0.005
    assert cell["coverage_positive"] == 0.5
    all_tied = np.zeros_like(p)
    assert not (all_tied > cutoff(y, all_tied, w)).any()


def test_archive_fixture_to_real_columns(tmp_path):
    import csv
    import hashlib
    import io
    import zipfile

    from login_data import FIELDS, extract_rows

    from idps_ai.common import load_json

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["index", "Login Timestamp", "User ID", "Is Account Takeover", *FIELDS])
    for i in range(3):
        writer.writerow(
            [i, f"2020-01-01 00:00:0{i}.100", -12, i == 2, "US", 123, "PC", "A/13", "B/7"]
        )
    archive = tmp_path / "rba.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("rba-dataset.csv", buf.getvalue())
    extract_rows(tmp_path, archive, hashlib.sha256(archive.read_bytes()).hexdigest())
    manifest = load_json(tmp_path / "raw-index.json")
    assert manifest["rows"] == 3 and len(manifest["bucket_shas"]) == 1
    rows = np.fromfile(next((tmp_path / "account-buckets").glob("*.bin")), RAW)
    assert rows["y"].tolist() == [0, 0, 1]
    assert rows["ts"][2] - rows["ts"][0] == 2000


def test_peer_counts_are_observed_before_anchor_and_missing_is_distinct():
    from login_data import PEERS, peer_features, peer_keys

    a = history([5, 10, 12, 15])
    keys = []
    for cols in PEERS:
        k, v = peer_keys(a["ctx"][:1], cols)
        assert v[0]
        keys.append((k, np.array([30])))
    a["ctx"][3] = 0
    v = peer_features(a, keys, 10)
    assert not np.any(v[0]) and not np.any(v[3])
    assert v[1, 0] == v[2, 0] == 1
    assert v[1, 2] > v[2, 2] > 0
    assert not (v < 0).any()
    assert np.max(v) <= 1


def test_locked_held_actor_and_strong_rule_comparison(tmp_path):
    import pytest
    from login_data import HISTORY_WIDTH, NAMES
    from login_study import train, transfer

    from idps_ai.common import atomic_json, file_sha256, load_json

    folder = tmp_path / "login-inputs"
    folder.mkdir()
    bins = []
    rng = np.random.default_rng(34)
    for j in range(100):
        u = np.full(12, j, dtype=np.uint64)
        y = np.array([0, 0, 1] * 4, dtype=np.uint8)
        valid = np.arange(len(y)) % 4 != 0
        x = rng.random((len(y), len(NAMES)), dtype=np.float32)
        x[~valid, :HISTORY_WIDTH] = 0
        x[:, HISTORY_WIDTH] = 1
        f = folder / f"{j:02d}.npz"
        np.savez_compressed(f, x=x, u=u, y=y, valid=valid)
        bins.append({"sha256": file_sha256(f)})
    atomic_json(tmp_path / "projection.json", {"role_bins": bins})
    train(tmp_path)
    lock = load_json(tmp_path / "login-lock.json")
    assert lock["supported_fit_positive_accounts_by_arm"]["PEER"] == 50
    assert lock["support"]["SELECT"]["users"] == 15
    transfer(tmp_path)
    held = load_json(tmp_path / "login-transfer.json")
    assert held["metrics"][lock["selected"]]["request"]["rows"] == 240
    assert held["learned_vs_selected_rule"]["rule"] == lock["selected_deterministic_control"]
    assert held["frozen_sha"] == file_sha256(tmp_path / "login-lock.json")
    with pytest.raises(ValueError, match="already"):
        transfer(tmp_path)
    with pytest.raises(ValueError, match="already"):
        train(tmp_path)
