#!/usr/bin/env python3
"""Frozen Request v2 evaluation on P0 receipts; no fitting or threshold selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pyarrow.parquet as pq
from scipy.stats import beta
from threadpoolctl import threadpool_limits

from idps_ai.common import AI_ROOT, atomic_json, canonical_bytes, digest, file_sha256, load_json
from idps_ai.features.request_preprocessing import encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request
from idps_ai.mvp_inference import ResearchMVP

ART = AI_ROOT / ".artifacts"
WAF_ROOT = ART / "request_intelligence_v2_20261104"
WAF_RAW = ART / "autonomous_research_20261104/waf_v2/train.parquet"
WAF_SHA = "3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6"


def raw_key(method, url, body):
    return hashlib.sha256(canonical_bytes([method, url, body or ""])).hexdigest()


def interval(k, n):
    if not n:
        return None
    return [
        0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1)),
        1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k)),
    ]


def confusion(rows):
    known = [r for r in rows if r["lab_intent"] in {"benign", "attack"}]
    counts = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    for row in known:
        counts[
            ("T" if (row["flagged"] == (row["lab_intent"] == "attack")) else "F")
            + ("P" if row["flagged"] else "N")
        ] += 1
    positive, negative = counts["TP"] + counts["FN"], counts["FP"] + counts["TN"]
    return {
        **counts,
        "labeled_requests": len(known),
        "unknown_excluded": len(rows) - len(known),
        "descriptive_lab_sensitivity": counts["TP"] / positive if positive else None,
        "descriptive_lab_normal_flag_fraction": counts["FP"] / negative if negative else None,
        "descriptive_iid_95_ci_sensitivity": interval(counts["TP"], positive),
        "descriptive_iid_95_ci_normal_flag_fraction": interval(counts["FP"], negative),
        "independent_population_recall": None,
        "independent_population_fpr": None,
        "scope": "collector-controlled prospective single-lab intent; review pending; IID intervals descriptive only",
    }


def corpus(capture):
    plan = load_json(capture / "plan.json")
    if plan["plan_sha256"] != digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise RuntimeError("P0 capture plan integrity mismatch")
    report = load_json(capture / "capture-report.json")
    if report["plan_file_sha256"] != file_sha256(capture / "plan.json"):
        raise RuntimeError("P0 capture report is not bound to plan")
    by_id = {r["request_id"]: r for r in report["observations"]}
    if len(by_id) != len(plan["cases"]):
        raise RuntimeError("Missing/duplicate observed physical request IDs")
    records = []
    for case in plan["cases"]:
        rid = case["request_id"]
        path = capture / "receipts" / rid
        receipt = load_json(path / "receipt.json")
        headers = load_json(path / "request-headers.json")
        returned = load_json(path / "response-headers.json")
        body = (path / "request-body.bin").read_bytes()
        response = (path / "response-body.bin").read_bytes()
        if (
            receipt["request_id"] != rid
            or receipt["method"] != case["method"]
            or receipt["path"] != case["path"]
            or body.decode() != case["body"]
            or receipt["request_body_sha256"] != hashlib.sha256(body).hexdigest()
            or receipt["request_headers_sha256"] != digest(headers)
            or receipt["response_headers_sha256"] != digest(returned)
            or receipt["response_sha256"] != hashlib.sha256(response).hexdigest()
            or by_id[rid]["response_sha256"] != receipt["response_sha256"]
        ):
            raise RuntimeError("Request-bound evidence readback mismatch")
        records.append(
            {
                "record_id": case["case_id"],
                "request_id": rid,
                "family": case["family"],
                "lab_intent": by_id[rid]["lab_intent"],
                "outcome": by_id[rid]["exploit_outcome"],
                "http_request": {
                    "method": case["method"],
                    "url": case["path"],
                    "headers": "\r\n".join(f"{k}: {v}" for k, v in headers.items()),
                    "body": body.decode(),
                },
                "receipt_file": str(path / "receipt.json"),
            }
        )
    return plan, report, records


def vector(predictor, request):
    numeric = encode_request(
        predictor.numeric_spec, project_request(request["url"], request["method"])["numbers"]
    )
    symbolic, availability = rich_request_v2(
        request["method"], request["url"], request["headers"], request["body"]
    )
    content = predictor.vectorizer.transform([symbolic]).toarray().astype(np.float32)[0]
    result = np.concatenate((numeric, content))
    safe, _ = symbolic_request(
        request["method"], request["url"], request["headers"], request["body"]
    )
    return result, content, hashlib.sha256(safe.encode()).hexdigest(), availability


def overlaps(records, vectors, groups, contents):
    tensor = WAF_ROOT / "waf-rich-v2/rich-content.npz"
    with np.load(tensor, allow_pickle=False) as data:
        train = data["role"] == 0
        train_views = set(data["view"][train].astype(str).tolist())
        train_groups = set(data["group"][train].astype(str).tolist())
        all_views = set(data["view"].astype(str).tolist())
        train_index = np.flatnonzero(train)
        selected = np.random.default_rng(20261105).choice(
            train_index, min(512, len(train_index)), replace=False
        )
        sample_content = data["content"][selected]
    raw_keys = {
        raw_key(r["http_request"]["method"], r["http_request"]["url"], r["http_request"]["body"])
        for r in records
    }
    found = set()
    route_set = {urlsplit(r["http_request"]["url"]).path for r in records}
    route_counts = Counter()
    if file_sha256(WAF_RAW) != WAF_SHA:
        raise RuntimeError("Pinned WAF publisher train split changed")
    parquet = pq.ParquetFile(WAF_RAW)
    scanned = 0
    for batch in parquet.iter_batches(batch_size=8192, columns=["method", "url", "body"]):
        for method, url, body in zip(
            *(batch.column(k).to_pylist() for k in ["method", "url", "body"]), strict=True
        ):
            scanned += 1
            if not isinstance(method, str) or not isinstance(url, str):
                continue
            key = raw_key(method, url, body)
            if key in raw_keys:
                found.add(key)
            try:
                path = urlsplit(url).path
            except ValueError:
                continue
            if path in route_set:
                route_counts[path] += 1
    views = [hashlib.sha256(v.tobytes()).hexdigest() for v in vectors]
    similarities = np.asarray(contents) @ sample_content.T
    each = [
        {
            "exact_raw_overlap_waf_publisher_train": raw_key(
                r["http_request"]["method"], r["http_request"]["url"], r["http_request"]["body"]
            )
            in found,
            "exact_feature_overlap_model_train": v in train_views,
            "exact_feature_overlap_any_v2_development": v in all_views,
            "safe_template_overlap_model_train": group in train_groups,
            "max_content_cosine_to_sample512": float(similarities[i].max()),
        }
        for i, (r, v, group) in enumerate(zip(records, views, groups, strict=True))
    ]
    return each, {
        "waf_rows_scanned": scanned,
        "waf_raw_sha256": WAF_SHA,
        "waf_model_tensor_sha256": file_sha256(tensor),
        "waf_publisher_train_route_occurrences": dict(route_counts),
        "exact_raw_overlap_request_rows": sum(
            e["exact_raw_overlap_waf_publisher_train"] for e in each
        ),
        "exact_feature_overlap_model_train_rows": sum(
            e["exact_feature_overlap_model_train"] for e in each
        ),
        "safe_template_overlap_model_train_rows": sum(
            e["safe_template_overlap_model_train"] for e in each
        ),
        "near_content_sample_pairs_cosine_ge_0995": int(np.sum(similarities >= 0.995)),
        "scope": "full pinned publisher train raw scan plus exact v2 train feature/group lookup; near-content only512 sampled; no sealed data read; upstream source lineage not certified",
    }


def collision_summary(rows):
    by_view = defaultdict(list)
    for row in rows:
        by_view[row["feature_view_sha256"]].append(row)
    mixed = {
        k: v for k, v in by_view.items() if {r["lab_intent"] for r in v} >= {"benign", "attack"}
    }
    return {
        "unique_feature_views": len(by_view),
        "mixed_lab_intent_feature_views": len(mixed),
        "rows_on_mixed_views": sum(len(v) for v in mixed.values()),
        "attack_rows_on_mixed_views": sum(
            r["lab_intent"] == "attack" for v in mixed.values() for r in v
        ),
        "benign_rows_on_mixed_views": sum(
            r["lab_intent"] == "benign" for v in mixed.values() for r in v
        ),
        "all_rows_retained_in_metrics": True,
        "mixed_view_case_ids": [[r["case_id"] for r in v] for v in mixed.values()],
    }


def evaluate(capture, output):
    capture, output = Path(capture).resolve(), Path(output).resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    os.umask(0o077)
    plan, report, records = corpus(capture)
    evaluation_plan = {
        "created_at_unix": time.time(),
        "source_plan_file_sha256": file_sha256(capture / "plan.json"),
        "capture_report_sha256": file_sha256(capture / "capture-report.json"),
        "script_sha256": file_sha256(__file__),
        "baseline_manifest_sha256": file_sha256(AI_ROOT / "RESEARCH_MVP_V1_0_FROZEN.json"),
        "model": "request_intelligence_v2_frozen_step3072",
        "threshold_rule": "strict greater than frozen threshold",
        "primary_denominator": "all captured requests with receipt-bound lab intent; UNKNOWN separately reported; no collision quarantine",
        "contamination_sensitivity": "exclude exact raw, feature, safe-template overlaps only in separately labeled subset",
        "counterfactuals": ["full", "headers_missing", "body_missing", "both_missing"],
        "counterfactuals_are_not_new_requests": True,
        "independent_review": "pending; no independent-population Recall/FPR claim",
        "tuning_or_training": False,
        "glu207": "NOT_RUN_missing_actual_three_source_contract",
    }
    evaluation_plan["plan_sha256"] = digest(evaluation_plan)
    atomic_json(output / "evaluation-plan.json", evaluation_plan)
    predictor = ResearchMVP("request-v2", cpus=4)
    started = time.monotonic()
    variants = {}
    full_vectors, full_contents, full_groups = [], [], []
    with threadpool_limits(limits=4):
        for variant in evaluation_plan["counterfactuals"]:
            rows = []
            for record in records:
                request = dict(record["http_request"])
                if variant in {"headers_missing", "both_missing"}:
                    request["headers"] = None
                if variant in {"body_missing", "both_missing"}:
                    request["body"] = None
                values, content, group, availability = vector(predictor, request)
                start = time.perf_counter()
                prediction = predictor.predict(
                    {
                        "record_id": record["record_id"],
                        "schema_version": "research-mvp-1",
                        "http_request": request,
                    }
                )
                ms = (time.perf_counter() - start) * 1000
                result = prediction["models"]["request_intelligence_v2"]
                rows.append(
                    {
                        "case_id": record["record_id"],
                        "request_id": record["request_id"],
                        "family": record["family"],
                        "lab_intent": record["lab_intent"],
                        "exploit_outcome": record["outcome"],
                        "score": result["score"],
                        "flagged": result["above_research_threshold"],
                        "feature_view_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                        "predict_with_feature_ms": ms,
                        "availability": result["feature_availability"],
                        "review_status": "PENDING_INDEPENDENT_REVIEW",
                    }
                )
                if variant == "full":
                    full_vectors.append(values)
                    full_contents.append(content)
                    full_groups.append(group)
            variants[variant] = rows
        per_overlap, overlap = overlaps(records, full_vectors, full_groups, full_contents)
    for row, item in zip(variants["full"], per_overlap, strict=True):
        row["overlap"] = item
    primary = [
        r
        for r in variants["full"]
        if not any(
            r["overlap"][k]
            for k in [
                "exact_raw_overlap_waf_publisher_train",
                "exact_feature_overlap_model_train",
                "safe_template_overlap_model_train",
            ]
        )
    ]
    summaries = {
        name: {
            "lab_confusion": confusion(rows),
            "collisions": collision_summary(rows),
            "by_family": {
                f: confusion([r for r in rows if r["family"] == f])
                for f in sorted({r["family"] for r in rows})
            },
            "flags_changed_from_full": sum(
                r["flagged"] != original["flagged"]
                for r, original in zip(rows, variants["full"], strict=True)
            ),
        }
        for name, rows in variants.items()
    }
    blind, key = [], []
    for record in records:
        path = capture / "receipts" / record["request_id"]
        blind.append(
            {
                "review_id": digest([plan["plan_sha256"], record["request_id"]]),
                "case_id": record["record_id"],
                "request_id": record["request_id"],
                "request": record["http_request"],
                "receipt": str(path / "receipt.json"),
                "response": str(path / "response-body.bin"),
                "required_decision": "benign/attack/unknown; rationale and outcome independently assessed",
            }
        )
        key.append(
            {
                "case_id": record["record_id"],
                "lab_intent": record["lab_intent"],
                "family": record["family"],
                "exploit_outcome": record["outcome"],
            }
        )
    for name, rows in {
        "predictions.jsonl": variants["full"],
        "blind-review.jsonl": blind,
        "review-unblind-key.jsonl": key,
        "counterfactuals.jsonl": [
            dict(r, variant=k) for k, values in variants.items() for r in values
        ],
    }.items():
        with (output / name).open("x") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    family_failures = {
        f: {
            "false_positive_case_ids": [
                r["case_id"]
                for r in variants["full"]
                if r["family"] == f and r["lab_intent"] == "benign" and r["flagged"]
            ],
            "false_negative_case_ids": [
                r["case_id"]
                for r in variants["full"]
                if r["family"] == f and r["lab_intent"] == "attack" and not r["flagged"]
            ],
            "oracle_success_missed": [
                r["case_id"]
                for r in variants["full"]
                if r["family"] == f and r["exploit_outcome"] == "succeeded" and not r["flagged"]
            ],
        }
        for f in sorted({r["family"] for r in variants["full"]})
    }
    result = {
        "status": "COMPLETED_DESCRIPTIVE_P0_EVALUATION_REVIEW_PENDING",
        "run_id": plan["run_id"],
        "evaluation_plan_sha256": evaluation_plan["plan_sha256"],
        "physical_new_requests": len(records),
        "unique_method_url_body_representations": len(
            {
                raw_key(
                    r["http_request"]["method"], r["http_request"]["url"], r["http_request"]["body"]
                )
                for r in records
            }
        ),
        "lab_intent_counts": report["lab_intent_counts"],
        "independently_verified_labels": 0,
        "independent_review": "PENDING",
        "oracle_successes": report["oracle_successes"],
        "threshold": predictor.v2_threshold,
        "model_checkpoint_manifest_sha256": predictor.v2_manifest_sha,
        "overlap": overlap,
        "variants": summaries,
        "no_exact_overlap_subset": confusion(primary),
        "family_failures": family_failures,
        "latency_with_feature_extraction_ms": {
            "p50": float(
                np.percentile([r["predict_with_feature_ms"] for r in variants["full"]], 50)
            ),
            "p95": float(
                np.percentile([r["predict_with_feature_ms"] for r in variants["full"]], 95)
            ),
        },
        "evaluation_wall_seconds": time.monotonic() - started,
        "glu207": {
            "status": "NOT_RUN",
            "reason": "No Student/Nginx/Suricata fused207 causal contract; no padded features",
        },
        "hard_rules_suricata_comparison": "PENDING_REAL_PCAP_DECODE_OR_UNAVAILABLE; no simulated rule benchmark",
        "formal_admitted": 0,
        "training_updates": 0,
        "enforcement_actions": 0,
        "limits": [
            "New prospective capture from a different application than prior repo evaluation; upstream training application novelty not certified",
            "Single application/version/security-low instance, four family campaign groups, collector-controlled intent and internal Oracles",
            "No independent reviewer; do not call these independent Recall/FPR or production quality",
            "XSS success means unsafe reflection only; no browser execution verified",
            "IID intervals do not account for correlated requests/templates",
            "Missingness variants are inference counterfactuals on the same requests, never added to physical request count",
        ],
        "artifacts_sha256": {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()},
    }
    result["report_sha256"] = digest(result)
    atomic_json(output / "evaluation-report.json", result)
    atomic_json(
        output / "review-package.json",
        {
            "status": "PENDING_HUMAN_REVIEW",
            "format": "research evidence package; not formal evidence-v2 admission",
            "capture_plan": str(capture / "plan.json"),
            "capture_report": str(capture / "capture-report.json"),
            "blind_queue_sha256": file_sha256(output / "blind-review.jsonl"),
            "reviewer_id": None,
            "instruction": "Review blind queue without model outputs/unblind key; record intent, outcome, evidence/rationale and disagreements; do not alter raw evidence",
        },
    )
    print(
        json.dumps(
            {
                "requests": len(records),
                "lab_confusion": summaries["full"]["lab_confusion"],
                "independent_review": "PENDING",
                "output": str(output),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evaluate(args.capture, args.output)
