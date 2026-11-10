"""Student-training-v1 extension of the existing bounded admission index.

Strict admission is unchanged. Publisher anomaly, intent, teacher proposal and
observations are different facts. No training or raw HTTP persistence here.
"""

import json
import os
import re
from collections import Counter

import numpy as np

from idps_ai.common import (
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    fsync_dir,
)
from idps_ai.data.scaling_admission import AdmissionIndex


def publisher_target(value):
    if value in {"normal", "anomalous"}:
        return {
            "tier": "SILVER",
            "original_label": value,
            "target": int(value == "anomalous"),
            "target_task": "publisher_anomaly",
            "intent": "UNKNOWN_INTENT",
        }
    return {
        "tier": "UNLABELED",
        "original_label": None,
        "target": None,
        "target_task": "publisher_anomaly",
        "intent": "UNKNOWN_INTENT",
    }


def teacher_proposal(score, original, *, teacher, expected_teacher, threshold, allowed=True):
    if teacher != expected_teacher:
        raise PipelineError("Teacher fingerprint mismatch")
    if not allowed:
        return {
            "label": None,
            "tier": None,
            "abstained": True,
            "conflict": False,
            "reason": "PROTECTED_OR_UNAVAILABLE",
            "score": None,
        }
    if score is None or not np.isfinite(score) or not 0 <= score <= 1:
        raise PipelineError("Invalid teacher score")
    positive = score > threshold
    conflict = positive and original == 0
    accepted = positive and not conflict
    return {
        "label": 1 if accepted else None,
        "tier": "BRONZE" if accepted else None,
        "abstained": not accepted,
        "conflict": conflict,
        "score": float(score),
        "reason": "UNCALIBRATED_POSITIVE_PROPOSAL"
        if accepted
        else "PUBLISHER_CONFLICT"
        if conflict
        else "NO_VALIDATED_NEGATIVE_POLICY",
        "binary_disagreement": original is not None and int(positive) != original,
        "teacher": teacher,
        "threshold": threshold,
        "policy": "teacher-positive-proposal-v1",
        "calibrated_confidence": False,
        "rule_observed": False,
    }


def normalize_tier(
    tier, *, original=None, intent="UNKNOWN_INTENT", oracle=False, reviewed=False, provenance=None
):
    if tier not in {"GOLD", "SILVER", "BRONZE", "UNLABELED"}:
        raise PipelineError("Unknown reliability tier")
    if tier == "SILVER":
        result = publisher_target(original)
        if result["tier"] != "SILVER":
            raise PipelineError("Publisher label semantics unavailable")
        return result
    if tier == "GOLD":
        if (
            not (oracle or reviewed)
            or not provenance
            or intent not in {"BENIGN_INTENT", "ATTACK_INTENT"}
        ):
            raise PipelineError("GOLD requires real request-bound evidence")
        return {
            "tier": tier,
            "intent": intent,
            "target": int(intent == "ATTACK_INTENT"),
            "target_task": "attack_intent",
            "original_label": original,
        }
    if tier == "BRONZE" and not provenance:
        raise PipelineError("BRONZE requires versioned labeling provenance")
    return {
        "tier": tier,
        "intent": "UNKNOWN_INTENT",
        "target": None,
        "target_task": "unlabeled",
        "original_label": original,
    }


def apply_proposal(metadata, proposal):
    metadata = dict(metadata)
    metadata["pseudo"] = proposal
    if metadata["tier"] == "UNLABELED" and proposal["label"] is not None:
        metadata.update(
            tier="BRONZE", target=proposal["label"], target_task="teacher_high_risk_proxy"
        )
    # SILVER's original task/label is never replaced, even if teacher conflicts.
    return metadata


def validate_metadata(m):
    expected = {
        "tier",
        "original_label",
        "target",
        "target_task",
        "intent",
        "outcome",
        "parsed",
        "body_observation",
        "headers_observation",
        "feature_ref",
        "feature_contract",
        "physical_identity",
        "teacher_pretrain_template_overlap",
        "pseudo",
    }
    if set(m) != expected or m["tier"] not in {"GOLD", "SILVER", "BRONZE", "UNLABELED"}:
        raise PipelineError("Unknown student metadata schema")
    if m["original_label"] not in {None, "normal", "anomalous"} or m["target"] not in {None, 0, 1}:
        raise PipelineError("Unsupported original label")
    for field in [
        "target_task",
        "intent",
        "outcome",
        "body_observation",
        "headers_observation",
        "feature_contract",
        "physical_identity",
    ]:
        if not isinstance(m[field], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", m[field]):
            raise PipelineError("Unsafe student metadata category")
    for field in ["parsed", "teacher_pretrain_template_overlap"]:
        if type(m[field]) is not bool:
            raise PipelineError("Student flags must be bool")
    ref = m["feature_ref"]
    if ref is not None and (
        set(ref) != {"shard", "slot"}
        or not re.fullmatch(r"features/[0-9]{9}-[0-9]{9}\.npz", ref["shard"])
        or type(ref["slot"]) is not int
        or not 0 <= ref["slot"] < 256
    ):
        raise PipelineError("Unsafe feature reference")
    p = m["pseudo"]
    expected_p = {"label", "tier", "abstained", "conflict", "reason", "score"}
    optional = {
        "binary_disagreement",
        "teacher",
        "threshold",
        "policy",
        "calibrated_confidence",
        "rule_observed",
    }
    if not expected_p <= set(p) or set(p) - expected_p - optional:
        raise PipelineError("Unsafe teacher metadata")
    if p["reason"] not in {
        "PROTECTED_OR_UNAVAILABLE",
        "UNCALIBRATED_POSITIVE_PROPOSAL",
        "PUBLISHER_CONFLICT",
        "NO_VALIDATED_NEGATIVE_POLICY",
    }:
        raise PipelineError("Unknown teacher reason")
    if "teacher" in p:
        t = p["teacher"]
        if set(t) != {
            "checkpoint_manifest",
            "threshold",
            "model",
            "parameters",
            "encoder",
            "probability_calibrated",
        } or not re.fullmatch(r"[a-f0-9]{64}", t["checkpoint_manifest"]):
            raise PipelineError("Unknown teacher identity schema")
        if (
            t["model"] != "Frozen Request v2 step3072"
            or t["encoder"] != "rich_content_v2+bounded-request-v1"
            or t["parameters"] != 50696
            or t["probability_calibrated"] is not False
        ):
            raise PipelineError("Unknown teacher identity")


def protected_near(content, references):
    """Bounded exhaustive numerical comparison; no capped candidate buckets."""
    if content.ndim != 2 or references.ndim != 2 or content.shape[1] != references.shape[1]:
        raise PipelineError("Near comparison dimension mismatch")
    if not np.isfinite(content).all() or not np.isfinite(references).all():
        raise PipelineError("Nonfinite near vector")
    if not len(references):
        return np.zeros(len(content), bool)
    return (
        np.max(
            content.astype(np.float64, copy=False) @ references.astype(np.float64, copy=False).T,
            axis=1,
        )
        >= 0.995 - 1e-7
    )


class StudentIndex(AdmissionIndex):
    """Reuse original transaction/cursor/group machinery; separate final policy."""

    def __init__(self, directory, binding):
        super().__init__(directory, binding)
        self.db.executescript("""CREATE TABLE IF NOT EXISTS student(i INTEGER PRIMARY KEY,j TEXT);
        CREATE TABLE IF NOT EXISTS blocked(i INTEGER PRIMARY KEY,why TEXT);
        CREATE TABLE IF NOT EXISTS protected_group(k TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS protected_view(k TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS old_train_group(k TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS protected_route(k TEXT PRIMARY KEY);""")
        self.db.commit()

    def append_student(self, entries):
        start = self.cursor

        def rows():
            for i, (row, metadata) in enumerate(entries, start):
                # Reject unrecognized/raw metadata before any transaction commits.
                validate_metadata(metadata)
                self.db.execute(
                    "INSERT INTO student VALUES(?,?)", (i, canonical_bytes(metadata).decode())
                )
                yield row

        self.append(rows())
        assert self.db.execute("SELECT count(*) FROM student").fetchone()[0] == self.cursor

    def finish(self, near_report, teacher):
        self.db.executescript(
            "DROP TABLE IF EXISTS student_roots; CREATE TABLE student_roots(i INTEGER PRIMARY KEY,c INTEGER);"
        )
        for (i,) in self.db.execute("SELECT i FROM r ORDER BY i"):
            self.db.execute("INSERT INTO student_roots VALUES(?,?)", (i, self.find(i)))
        self.db.executescript("""CREATE INDEX src ON student_roots(c);
        DROP TABLE IF EXISTS student_bad; CREATE TABLE student_bad(c INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO student_bad SELECT DISTINCT c FROM student_roots JOIN blocked USING(i);
        INSERT OR IGNORE INTO student_bad SELECT DISTINCT c FROM student_roots JOIN r USING(i)
          WHERE v IN (SELECT v FROM r WHERE v IS NOT NULL GROUP BY v,task HAVING min(y)!=max(y));
        INSERT OR IGNORE INTO student_bad SELECT DISTINCT c FROM student_roots JOIN r USING(i)
          WHERE raw IN (SELECT raw FROM r WHERE raw IS NOT NULL GROUP BY raw,task HAVING min(y)!=max(y));
        """)
        self.db.commit()
        counts = Counter()
        source_tiers = Counter()
        accepted_tiers = Counter()
        classes = Counter()
        reasons = Counter()
        pseudo = Counter()
        sources = {}
        bodies = Counter()
        self.db.executescript(
            "DROP TABLE IF EXISTS accepted; CREATE TABLE accepted(i INTEGER PRIMARY KEY,v TEXT,y INTEGER); CREATE INDEX av ON accepted(v);"
        )
        ledger_tmp = self.root / ".ledger.writing"
        train_tmp = self.root / ".train.writing"
        with ledger_tmp.open("wb") as ledger, train_tmp.open("wb") as train:
            query = """SELECT r.i,r.j,s.j,c,b.c IS NOT NULL,blocked.why,
            (SELECT min(x.i) FROM r x WHERE x.raw=r.raw) FROM r
            JOIN student s USING(i) JOIN student_roots USING(i)
            LEFT JOIN student_bad b USING(c) LEFT JOIN blocked USING(i) ORDER BY r.i"""
            for i, rj, sj, component, bad, why, first in self.db.execute(query):
                r = json.loads(rj)
                m = json.loads(sj)
                source_tiers[m["tier"]] += 1
                bodies[m["body_observation"]] += 1
                counts["SOURCE_ROWS"] += 1
                counts["PARSED_HTTP_OBSERVATIONS"] += int(m["parsed"])
                counts["VERIFIED_PHYSICAL_REQUESTS"] += int(r["identity_verified"])
                counts["FEATURE_COMPATIBLE"] += int(r["feature_valid"])
                reason = set(r["reasons"])
                reason.update([why] if why else [])
                if bad:
                    reason.add("PROTECTED_OR_CONFLICT_COMPONENT")
                if r["representation_key"] is not None and first != i:
                    reason.add("EXACT_REPRESENTATION_DUPLICATE")
                if not r["feature_valid"]:
                    reason.add("MODEL_FEATURE_UNAVAILABLE")
                decision = "TRAINING_ELIGIBLE" if not reason else "QUARANTINED_FOR_PROFILE"
                if not reason:
                    counts["DEDUPLICATED_TRAINING_EXAMPLES"] += 1
                    accepted_tiers[m["tier"]] += 1
                    if m["target"] is not None:
                        counts["ACTUAL_TRAINING_ELIGIBLE"] += 1
                    classes[m["target_task"] + ":" + str(m["target"])] += 1
                    self.db.execute(
                        "INSERT INTO accepted VALUES(?,?,?)", (i, r["view_key"], m["target"])
                    )
                p = m["pseudo"]
                pseudo["scored"] += int(p.get("score") is not None)
                pseudo["abstained"] += int(p["abstained"])
                pseudo["conflicts"] += int(p["conflict"])
                pseudo["binary_disagreements"] += int(p.get("binary_disagreement", False))
                pseudo["aux_BRONZE_proposals_before_quarantine"] += int(p["label"] is not None)
                pseudo["aux_BRONZE_proposals_eligible"] += int(
                    not reason and p["label"] is not None
                )
                counts["QUARANTINED"] += int(bool(reason))
                reasons.update(reason)
                sources.setdefault(r["source"], Counter())[decision] += 1
                ledger.write(
                    canonical_bytes(
                        {
                            "row": i,
                            "source": r["source"],
                            "source_row": r["source_row"],
                            "request_key": r["request_key"],
                            "representation_key": r["representation_key"],
                            "view_key": r["view_key"],
                            "component": component,
                            "decision": decision,
                            "reasons": sorted(reason),
                            **m,
                        }
                    )
                    + b"\n"
                )
            self.db.commit()
            for i, v, y in self.db.execute("SELECT i,v,y FROM accepted ORDER BY i"):
                m = json.loads(
                    self.db.execute("SELECT j FROM student WHERE i=?", (i,)).fetchone()[0]
                )
                n = self.db.execute("SELECT count(*) FROM accepted WHERE v=?", (v,)).fetchone()[0]
                train.write(
                    canonical_bytes(
                        {
                            "row": i,
                            "features": m["feature_ref"],
                            "primary_tier": m["tier"],
                            "target": y,
                            "task": m["target_task"],
                            "intent": m["intent"],
                            "feature_view_inverse_weight": 1 / n,
                            "aux_pseudo": m["pseudo"],
                            "role": "TRAIN_STAGING_EXPOSED",
                            "optimization_consumed": False,
                        }
                    )
                    + b"\n"
                )
            for f in [ledger, train]:
                f.flush()
                os.fsync(f.fileno())
        ledger_tmp.replace(self.root / "ledger.jsonl")
        train_tmp.replace(self.root / "training-index.jsonl")
        fsync_dir(self.root)
        counts["ACTUAL_TRAINING_CONSUMED"] = 0
        for key in [
            "SOURCE_ROWS",
            "PARSED_HTTP_OBSERVATIONS",
            "VERIFIED_PHYSICAL_REQUESTS",
            "DEDUPLICATED_TRAINING_EXAMPLES",
            "FEATURE_COMPATIBLE",
            "QUARANTINED",
            "ACTUAL_TRAINING_ELIGIBLE",
        ]:
            counts.setdefault(key, 0)
        for tier in ["GOLD", "SILVER", "BRONZE", "UNLABELED"]:
            counts[tier] = accepted_tiers[tier]
        assert (
            counts["QUARANTINED"] + counts["DEDUPLICATED_TRAINING_EXAMPLES"]
            == counts["SOURCE_ROWS"]
        )
        summary = {
            "profile": "student-training-v1",
            "binding": self.binding,
            "counts": dict(counts),
            "source_primary_tiers": dict(source_tiers),
            "accepted_primary_tiers": dict(accepted_tiers),
            "class_distribution_by_task": dict(classes),
            "tier_count_scope": "primaryacceptedexamples; teacherBRONZEauxiliary is separate and never doublecounted",
            "source_counts": {k: dict(v) for k, v in sources.items()},
            "quarantine_reasons_overlapping": dict(reasons),
            "body_observation_metadata": dict(bodies),
            "pseudo": dict(pseudo),
            "teacher": teacher,
            "teacher_accuracy": "NOT_EVALUATED; publisheragreement/ownpseudo are not trustedaccuracy",
            "protected_near": near_report,
            "new_independent_evaluation": False,
            "unique_feature_views_accepted": self.db.execute(
                "SELECT count(DISTINCT v) FROM accepted"
            ).fetchone()[0],
            "files": {
                "ledger.jsonl": file_sha256(self.root / "ledger.jsonl"),
                "training-index.jsonl": file_sha256(self.root / "training-index.jsonl"),
            },
            "strict_profile_unchanged": True,
            "training": "NOT_STARTED",
            "physical_count_scope": "retainedfirstpartyidentities only; WAFpublicationrows are not verifiedphysicalrequests",
        }
        summary["fingerprint"] = digest(summary)
        atomic_json(self.root / "summary.json", summary)
        atomic_json(
            self.root / "progress.json",
            {
                "state": "COMPLETED",
                "rows_committed": self.cursor,
                "fingerprint": summary["fingerprint"],
                "binding": self.binding,
            },
        )
        return summary
