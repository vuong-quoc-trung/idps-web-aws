"""Fail-closed final-release gates. No prediction, optimization or raw extraction."""

import hashlib
import hmac
import json
import sqlite3
from collections import Counter

import numpy as np

from idps_ai.common import PipelineError, canonical_bytes, digest, file_sha256
from idps_ai.data.local_release import role_for_component
from idps_ai.data.resumable_near import checkpoint_read, load_vectors
from idps_ai.data.scaling_admission import validate as validate_normalized
from idps_ai.data.student_training import protected_near, validate_metadata


class GateError(PipelineError):
    def __init__(self, gate):
        self.gate = gate
        super().__init__("Final training gate failed: " + gate)


def require(condition, gate):
    if not condition:
        raise GateError(gate)


def load(path):
    return json.loads(path.read_text())


def signed(value, gate):
    c = dict(value)
    require(c.pop("fingerprint", None) == digest(c), gate)


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def check_cross_role(data, status):
    roles = ["TRAIN", "CALIBRATION", "EVALUATION"]
    for a, b in [(roles[0], roles[1]), (roles[0], roles[2]), (roles[1], roles[2])]:
        require(not set(data[a]["groups"]) & set(data[b]["groups"]), "GROUP_ROLE_LEAKAGE")
        references = np.unique(data[b]["x"][:, 76:], axis=0)
        for start in range(0, len(data[a]["x"]), 64):
            require(
                not protected_near(data[a]["x"][start : start + 64, 76:], references).any(),
                "CROSS_ROLE_CONTENT_NEAR_LEAKAGE",
            )
            status(phase="VALIDATE_CROSS_ROLE_NEAR", roles=a + "_" + b, anchor=start)


def validate_release(source, repo, old, pilot, status):
    status(phase="VALIDATE_COMPLETION")
    require(load(source / "completion.json")["state"] == "COMPLETED", "DATA_COMPLETION")
    for name in ["result.json", "thermal-report.json"]:
        require(
            load(source / "attempts/data-v1" / name)["state"] == "COMPLETED", "DATA_SUPERVISION"
        )
    require(not (source / "attempts/data-v1/failure.json").exists(), "DATA_FAILURE_MARKER")
    require(not (source / "attempts/data-v1/thermal-terminal.json").exists(), "DATA_SAFETY_MARKER")
    plan = load(source / "plan.json")
    cfg = load(source / "final-training-config.json")
    summary = load(source / "materialized/summary.json")
    accounting = load(source / "release-accounting.json")
    for obj in [plan, cfg, summary]:
        signed(obj, "SOURCE_CONFIG_FINGERPRINT")
    require(load(source / "completion.json")["summary"] == summary, "SUMMARY_COMPLETION_BINDING")
    require(summary["binding"] == digest(plan), "INDEX_BINDING")
    require(cfg["dataset_fingerprint"] == summary["fingerprint"], "DATASET_FINGERPRINT")
    require(cfg["training_readiness"] == "PASS", "SOURCE_READINESS")
    require(cfg["feature_contract"] == "student-http588-rich-v2-publisher-v1", "FEATURE_CONTRACT")
    locked = load(repo / "ai-training/configs/research/local-release-200k-20261110.json")[
        "final_training"
    ]
    for k in ["model", "training", "evaluation", "resources", "task", "tiers"]:
        require(cfg[k] == locked[k], "LOCKED_DESIGN_CHANGED")
    for name, sha in plan["code_hashes"].items():
        require(file_sha256(repo / name) == sha, "DATA_CODE_BINDING")
    require(file_sha256(old / "plan.json") == plan["old_plan_sha256"], "OLD_PLAN_BINDING")
    require(
        file_sha256(old / "materialized/ledger.jsonl") == plan["old_ledger_sha256"],
        "OLD_LEDGER_BINDING",
    )
    require(
        file_sha256(pilot / "data/split.json") == plan["pilot_split_sha256"], "PILOT_SPLIT_BINDING"
    )
    key = (source / "identity.key").read_bytes()
    require(hashlib.sha256(key).hexdigest() == plan["key_fingerprint"], "IDENTITY_KEY_BINDING")
    for name, sha in summary["files"].items():
        require(file_sha256(source / "materialized" / name) == sha, "LEDGER_INDEX_HASH")
    for name, sha in cfg["data_files"].items():
        require(file_sha256(source / "final-data" / name) == sha, "SPLIT_TENSOR_HASH")
    for name, sha in load(source / "protection-ready.json")["files"].items():
        require(file_sha256(source / name) == sha, "PROTECTION_HASH")
    require(
        file_sha256(source / "legacy-review.sqlite")
        == load(source / "legacy-review-complete.json")["sha256"],
        "LEGACY_CHECKPOINT_HASH",
    )
    with ro(source / "legacy-review.sqlite") as db:
        require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "LEGACY_SQLITE")
        require(
            db.execute("SELECT count(*) FROM checked").fetchone()[0] == 27235, "LEGACY_COVERAGE"
        )

    status(phase="VALIDATE_SOURCE_LEDGER_PRIVACY")
    eligible, refs, source_tiers, accepted_tiers = {}, {}, Counter(), Counter()
    parsed = valid588 = physical = 0
    with ro(source / "materialized/index.sqlite") as db:
        require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY")
        n, unique = db.execute("SELECT count(*),count(DISTINCT s||':'||n) FROM r").fetchone()
        require(n == unique == accounting["source_positions"] == 200000, "SOURCE_POSITIONS")
        require(
            db.execute(
                "SELECT count(*) FROM r WHERE s='waf' AND ((n>=49964 AND n<99964) OR (n>=1098539 AND n<1148539))"
            ).fetchone()[0]
            == accounting["new_positions"]
            == 100000,
            "ADDITIONAL_COORDINATES",
        )
        normalized = {}
        for i, rj, mj in db.execute(
            "SELECT r.i,r.j,student.j FROM r JOIN student USING(i) ORDER BY r.i"
        ):
            r, m = json.loads(rj), json.loads(mj)
            validate_normalized(r)
            validate_metadata(m)
            require(
                m["intent"] == "UNKNOWN_INTENT" and m["outcome"] == "UNKNOWN_OUTCOME",
                "TARGET_SEMANTICS",
            )
            require(r["privacy_valid"] is True, "PRIVACY_FLAG")
            if r["source"] == "waf":
                require(
                    m["tier"] == "SILVER" and m["target_task"] == "publisher_anomaly",
                    "LABEL_PROVENANCE",
                )
                require(
                    m["original_label"] in ["normal", "anomalous"]
                    and m["target"] == int(m["original_label"] == "anomalous"),
                    "PUBLISHER_LABEL",
                )
            else:
                require(
                    r["source"] == "first-party"
                    and m["tier"] == "UNLABELED"
                    and m["target"] is None,
                    "REFERENCE_LABEL",
                )
            source_tiers[m["tier"]] += 1
            parsed += int(m["parsed"])
            valid588 += int(r["feature_valid"])
            physical += int(r["identity_verified"])
            if m["feature_ref"]:
                ref = m["feature_ref"]
                refs.setdefault(ref["shard"], []).append((i, ref["slot"]))
            normalized[i] = (r, m)
        dbaccepted = dict(db.execute("SELECT i,y FROM accepted"))
        for m in map(json.loads, (source / "materialized/ledger.jsonl").open()):
            i = m["row"]
            r, original = normalized[i]
            require(all(m[k] == v for k, v in original.items()), "METADATA_LEDGER_PARITY")
            require(
                m["source"] == r["source"] and m["source_row"] == r["source_row"],
                "SOURCE_COORDINATE_PARITY",
            )
            if m["decision"] == "TRAINING_ELIGIBLE":
                require(
                    not m["reasons"] and i in dbaccepted and m["target"] == dbaccepted[i],
                    "ADMISSION_INDEX",
                )
                require(
                    m["tier"] == "SILVER" and m["target_task"] == "publisher_anomaly",
                    "ELIGIBLE_LABEL",
                )
                require(
                    not db.execute("SELECT 1 FROM blocked WHERE i=?", (i,)).fetchone(),
                    "PROTECTED_ROW_ADMITTED",
                )
                eligible[i] = m
                accepted_tiers[m["tier"]] += 1
        require(
            len(eligible)
            == len(dbaccepted)
            == summary["counts"]["ACTUAL_TRAINING_ELIGIBLE"]
            == 21331,
            "ELIGIBLE_ACCOUNTING",
        )
        require(
            not db.execute(
                "SELECT 1 FROM accepted JOIN student_roots USING(i) JOIN student_bad USING(c) LIMIT 1"
            ).fetchone(),
            "CONFLICT_COMPONENT_ADMITTED",
        )
    require(dict(source_tiers) == accounting["source_tiers"], "SOURCE_TIERS")
    require(dict(accepted_tiers) == accounting["accepted_tiers"], "ACCEPTED_TIERS")
    require(valid588 == 199927 and physical == 73, "FEATURE_PHYSICAL_COUNTS")

    status(phase="VALIDATE_SHARDS")
    # Validate every shard; retain only the admitted rows in RAM.
    matrices = {}
    found = {
        str(p.relative_to(source / "materialized"))
        for p in (source / "materialized/features").glob("*.npz")
    }
    require(found == set(refs), "SHARD_SET")
    for name, places in refs.items():
        file = source / "materialized" / name
        if name in plan["old_shard_sha256"]:
            require(file_sha256(file) == plan["old_shard_sha256"][name], "REUSED_SHARD_HASH")
        else:
            a, b = map(int, file.stem.split("-"))
            prior = source / "additional/features" / f"{a - 100000:09}-{b - 100000:09}.npz"
            require(file_sha256(file) == file_sha256(prior), "NEW_SHARD_COPY_HASH")
        with np.load(file, allow_pickle=False) as z:
            x = z["x"]
            require(
                x.dtype == np.float32
                and x.ndim == 2
                and x.shape[1] == 588
                and np.isfinite(x).all(),
                "FINITE_FEATURES",
            )
            require(
                sorted(slot for _, slot in places) == list(range(len(x))), "SHARD_SLOT_COVERAGE"
            )
            for i, slot in places:
                if i in eligible:
                    vector = x[slot].copy()
                    v = hashlib.sha256(vector.tobytes()).hexdigest()
                    expected = hmac.new(
                        key, canonical_bytes(["full588view", v]), hashlib.sha256
                    ).hexdigest()
                    require(expected == eligible[i]["view_key"], "FEATURE_VIEW_HASH")
                    matrices[i] = vector
    require(len(matrices) == len(eligible), "ELIGIBLE_FEATURE_COVERAGE")
    cache = source / "materialized/near-resumable-v1"
    cm = load(cache / "vectors-manifest.json")
    vectors, counts, manifest = load_vectors(cache, cm["source_binding"])
    progress = load(cache / "progress.json")
    near = checkpoint_read(
        cache / "checkpoint.json",
        progress["checkpoint_binding"],
        len(vectors),
        manifest["rows"],
        128,
    )
    require(
        near["next_unique_anchor"] == len(vectors) == 60065 and sum(map(int, counts)) == valid588,
        "NEAR_COVERAGE",
    )
    require(near["pairs"] == summary["protected_near"]["pairs"] == 1710578139, "NEAR_ACCUMULATOR")
    require(
        load(source / "completion.json")["deterministic_finalization"] is True,
        "DETERMINISTIC_FINALIZATION",
    )
    del vectors, counts

    status(phase="VALIDATE_CANONICAL_SPLIT")
    canonical = {}
    for i, m in eligible.items():
        if m["view_key"] in canonical:
            require(m["target"] == eligible[canonical[m["view_key"]]]["target"], "MIXED_LABEL_VIEW")
        else:
            canonical[m["view_key"]] = i
    require(
        len(canonical) == cfg["canonical_views"] == accounting["accepted_views"] == 17588,
        "CANONICAL_COUNT",
    )
    mult = Counter(m["view_key"] for m in eligible.values())
    ti = [json.loads(line) for line in (source / "materialized/training-index.jsonl").open()]
    require([v["row"] for v in ti] == list(eligible), "TRAINING_INDEX_COVERAGE")
    for v in ti:
        m = eligible[v["row"]]
        require(
            v["features"] == m["feature_ref"]
            and v["target"] == m["target"]
            and v["primary_tier"] == "SILVER",
            "TRAINING_INDEX_PARITY",
        )
        require(
            v["feature_view_inverse_weight"] == 1 / mult[m["view_key"]]
            and not v["optimization_consumed"],
            "DUPLICATE_WEIGHT",
        )
    split = load(source / "final-data/split.json")
    require(digest(split) == cfg["split_fingerprint"], "SPLIT_FINGERPRINT")
    require(
        len({v["row"] for v in split}) == len(split) == len(canonical), "CANONICAL_SPLIT_UNIQUENESS"
    )
    require({v["row"] for v in split} == set(canonical.values()), "CANONICAL_FIRST_ROW_POLICY")
    bygroup, bycomponent, data = {}, {}, {}
    for v in split:
        m = eligible[v["row"]]
        require(v["target"] == m["target"], "SPLIT_LABEL_PARITY")
        require(
            bycomponent.setdefault(m["component"], v["role"]) == v["role"],
            "EXACT_COMPONENT_LEAKAGE",
        )
        bygroup.setdefault(v["group"], []).append(v)
    for g, members in bygroup.items():
        minimum = min(v["row"] for v in members)
        expected = role_for_component(minimum, any(v["row"] < 100000 for v in members))
        require(all(v["role"] == expected for v in members), "REPRODUCIBLE_ROLE_ASSIGNMENT")
    for role in ["TRAIN", "CALIBRATION", "EVALUATION"]:
        with np.load(source / "final-data" / (role.lower() + ".npz"), allow_pickle=False) as z:
            d = {k: z[k].copy() for k in z.files}
        rows = [v for v in split if v["role"] == role]
        require(
            d["x"].shape == (len(rows), 588)
            and d["x"].dtype == np.float32
            and np.isfinite(d["x"]).all(),
            "SPLIT_FEATURE_SHAPE",
        )
        require(
            d["rows"].tolist() == [v["row"] for v in rows]
            and d["y"].tolist() == [v["target"] for v in rows]
            and d["groups"].tolist() == [v["group"] for v in rows],
            "SPLIT_ARRAY_METADATA",
        )
        for i, row in enumerate(d["rows"]):
            require(np.array_equal(d["x"][i], matrices[int(row)]), "SPLIT_SOURCE_FEATURE_PARITY")
        classes = Counter(str(int(v)) for v in d["y"])
        require(
            dict(classes) == cfg["split_counts"][role]["classes"]
            and len(rows) == cfg["split_counts"][role]["examples"],
            "SPLIT_COUNTS",
        )
        data[role] = d
    check_cross_role(data, status)

    status(phase="VALIDATE_PROTECTED_HELDOUT")
    protection = load(source / "pilot-protection.json")
    pg, pv = set(protection["groups"]), set(protection["views"])
    with ro(source / "protection-build/index.sqlite") as db:
        pg.update(
            hmac.new(key, canonical_bytes(["safe-template", g]), hashlib.sha256).hexdigest()
            for (g,) in db.execute("SELECT k FROM protected_group")
        )
        pv.update(
            hmac.new(key, canonical_bytes(["full588view", v]), hashlib.sha256).hexdigest()
            for (v,) in db.execute("SELECT k FROM protected_view")
        )
    for i, m in eligible.items():
        require(
            i not in protection["rows"]
            and not set(normalized[i][0]["groups"]) & pg
            and m["view_key"] not in pv,
            "PROTECTED_HELDOUT_IDENTITY",
        )
    with np.load(source / "protected-vectors.npz", allow_pickle=False) as z:
        references = z["full"].copy()
    allx = np.stack(list(matrices.values()))
    for a in range(0, len(allx), 64):
        require(
            not protected_near(allx[a : a + 64, 76:], references).any(), "PROTECTED_HELDOUT_NEAR"
        )
        status(phase="VALIDATE_PROTECTED_HELDOUT_NEAR", anchor=a, records=len(allx))
    oldtrain = {v["row"] for v in load(pilot / "data/split.json") if v["role"] == "TRAIN"}
    oldviews = {
        m["view_key"]
        for m in map(json.loads, (old / "materialized/ledger.jsonl").open())
        if m["row"] in oldtrain
    }
    new_views = sum(eligible[int(i)]["view_key"] not in oldviews for i in data["TRAIN"]["rows"])
    require(
        new_views >= 100 and len(data["TRAIN"]["rows"]) > 2667, "MEANINGFUL_ADDITIONAL_TRAINING"
    )
    require(
        cfg["planned_steps"] == 10 * ((len(data["TRAIN"]["rows"]) + 63) // 64) == 2490,
        "UPDATE_BUDGET",
    )
    report = {
        "state": "PASS",
        "dataset_fingerprint": summary["fingerprint"],
        "config_fingerprint": cfg["fingerprint"],
        "split_fingerprint": cfg["split_fingerprint"],
        "source_positions": 200000,
        "new_positions": 100000,
        "valid_observations": parsed,
        "offline588_observations": valid588,
        "eligible_records": len(eligible),
        "canonical_views": len(canonical),
        "aliases": len(eligible) - len(canonical),
        "training_examples": len(data["TRAIN"]["rows"]),
        "split_counts": cfg["split_counts"],
        "source_tiers": dict(source_tiers),
        "accepted_tiers": dict(accepted_tiers),
        "additional_TRAIN_views_vs_previous_pilot": new_views,
        "verified_physical_source_identities": physical,
        "verified_physical_training_identities": 0,
        "privacy": "PASS_TYPED_NORMALIZED_METADATA_AND_EXISTING_PINNED_PROJECTION",
        "protected_heldout": "PASS_KNOWN_EXACT_AND_FULL588_CONTENT_NEAR",
        "global_raw_campaign_time_lineage": "PARTIAL",
        "independent_review": "PENDING",
        "deterministic_scope": "frozen code/hash-bound metadata finalization and reproduced locked roles; not new raw extraction",
        "evaluation_predictions": "NOT_RUN",
        "accounting": accounting,
    }
    report["fingerprint"] = digest(report)
    return report, cfg, eligible
