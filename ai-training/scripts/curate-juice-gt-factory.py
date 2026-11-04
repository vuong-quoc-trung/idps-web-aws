#!/usr/bin/env python3
"""Integrity-check and vectorize only observed Juice Shop lab evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.common import (
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content import rich_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.training.resources import resource_envelope


def _factory(path):
    spec = importlib.util.spec_from_file_location("juice_gt_factory_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def curate(plan_path, run_path, factory_path, output, encoder_version="rich_v1"):
    plan_path, run_path, factory_path, output = map(
        Path, (plan_path, run_path, factory_path, output)
    )
    if output.exists():
        raise PipelineError("Juice curation output already exists")
    if encoder_version not in ("rich_v1", "rich_v2"):
        raise PipelineError("Unsupported Juice content encoder version")
    encoder = rich_request_v2 if encoder_version == "rich_v2" else rich_request
    plan, report = load_json(plan_path), load_json(run_path)
    if plan.get("plan_sha256") != digest(
        {k: v for k, v in plan.items() if k != "plan_sha256"}
    ) or report.get("report_sha256") != digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    ):
        raise PipelineError("Juice plan or evidence self-hash mismatch")
    if (
        report["plan_file_sha256"] != file_sha256(plan_path)
        or plan["script_sha256"] != report["script_sha256"]
        or plan["script_sha256"] != file_sha256(factory_path)
    ):
        raise PipelineError("Juice evidence/code binding changed")
    if (
        report["target"] != plan["target"]
        or report["requests_sent"] != len(plan["cases"])
        or report["proxy_correlated"] != len(plan["cases"])
    ):
        raise PipelineError("Juice target or proxy request count mismatch")
    if len({x["request_id"] for x in report["proxy_receipts"]}) != len(plan["cases"]):
        raise PipelineError("Duplicate Juice proxy request IDs")
    factory = _factory(factory_path)
    observations = {o["request_id"]: o for o in report["observations"]}
    receipts = {r["request_id"]: r for r in report["proxy_receipts"]}
    if len(observations) != len(plan["cases"]):
        raise PipelineError("Duplicate Juice observation IDs")
    numbers, texts, labels, tiers, groups, raw_ids = [], [], [], [], [], []
    spec = bounded_spec()
    counts = Counter()
    for case in plan["cases"]:
        request_id = case["request_id"]
        obs, receipt = observations.get(request_id), receipts.get(request_id)
        if (
            not obs
            or not receipt
            or obs["case_id"] != case["case_id"]
            or obs["path"] != case["path"]
            or obs["method"] != case["method"]
        ):
            raise PipelineError("Juice case/observation mismatch")
        body = factory._body(case["body_profile"]) if case["body_profile"] else b""
        if any(
            (
                hashlib.sha256(body).hexdigest() != case["body_sha256"],
                receipt["method"] != case["method"],
                receipt["path_sha256"] != hashlib.sha256(case["path"].encode()).hexdigest(),
                receipt["body_sha256"] != case["body_sha256"],
                receipt["response_sha256"] != obs["response_sha256"],
                receipt["status"] != obs["status"],
            )
        ):
            raise PipelineError("Juice proxy/application evidence mismatch")
        tier = obs["ground_truth_tier"]
        if tier == "UNKNOWN":
            counts["unknown_quarantined"] += 1
            continue
        if tier not in ("BENIGN_WORKFLOW_VERIFIED", "ATTACK_ATTEMPT_VERIFIED"):
            raise PipelineError("Unsupported lab label tier")
        if tier == "BENIGN_WORKFLOW_VERIFIED" and (
            case["intended_class"] != "benign" or not obs["application_semantic_ok"]
        ):
            raise PipelineError("Benign Oracle contradiction")
        if tier == "ATTACK_ATTEMPT_VERIFIED" and case["intended_class"] != "attack":
            raise PipelineError("Attack intent contradiction")
        method, path = case["method"], case["path"]
        values = encode_request(spec, project_request(path, method)["numbers"])
        symbolic, availability = encoder(method, path, None, body.decode() if body else None)
        numbers.append(values)
        texts.append(symbolic)
        labels.append(int(tier == "ATTACK_ATTEMPT_VERIFIED"))
        tiers.append(tier)
        groups.append(case["campaign_id"])
        raw_ids.append(
            hashlib.sha256(canonical_bytes([method, path, case["body_sha256"]])).digest()
        )
        counts["body_redacted"] += availability["body_redacted"]
        counts["redacted_query_fields"] += availability["redacted_query_fields"]
    content = (
        HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )
        .transform(texts)
        .toarray()
        .astype(np.float32)
    )
    numeric = np.asarray(numbers, np.float32)
    labels = np.asarray(labels, np.int8)
    view_keys = [
        hashlib.sha256(np.concatenate((a, b)).tobytes()).digest()
        for a, b in zip(numeric, content, strict=True)
    ]
    classes_by_view = defaultdict(set)
    for key, label in zip(view_keys, labels, strict=True):
        classes_by_view[key].add(int(label))
    mixed = {key for key, values in classes_by_view.items() if len(values) > 1}
    if len(set(raw_ids)) != len(raw_ids):
        counts["exact_request_duplicate_rows"] = len(raw_ids) - len(set(raw_ids))
    keep = []
    seen = set()
    for i, key in enumerate(view_keys):
        if key in mixed:
            counts["rows_on_mixed_views_quarantined"] += 1
            continue
        if key in seen:
            counts["same_label_view_duplicate_rows"] += 1
            continue
        seen.add(key)
        keep.append(i)
    output.mkdir(parents=True, mode=0o700)
    tensor = output / "lab-request-views.npz"
    with tensor.open("xb") as stream:
        np.savez_compressed(
            stream,
            numeric=numeric[keep],
            content=content[keep],
            label=labels[keep],
            group=np.asarray([groups[i] for i in keep], dtype="S64"),
            view=np.asarray([view_keys[i].hex() for i in keep], dtype="S64"),
        )
        stream.flush()
        os.fsync(stream.fileno())
    tensor.chmod(0o600)
    result = {
        "format_version": 1,
        "scope": "single Juice Shop instance, collector-controlled lab intent; development only",
        "plan_file_sha256": file_sha256(plan_path),
        "run_report_file_sha256": file_sha256(run_path),
        "factory_script_sha256": file_sha256(factory_path),
        "curator_script_sha256": file_sha256(__file__),
        "encoder_version": encoder_version,
        "encoder_code_sha256": file_sha256(
            Path(__file__).resolve().parents[1]
            / (
                "src/idps_ai/features/rich_content_v2.py"
                if encoder_version == "rich_v2"
                else "src/idps_ai/features/rich_content.py"
            )
        ),
        "physical_client_requests_sent": report["requests_sent"],
        "proxy_correlated": report["proxy_correlated"],
        "unique_complete_request_representations": report["unique_http_representations"],
        "labels_before_feature_quarantine": {
            "benign": int(np.sum(labels == 0)),
            "attack_attempt": int(np.sum(labels == 1)),
        },
        "unique_numeric76_views": len({x.tobytes() for x in numeric}),
        "unique_numeric76_content512_views_before_quarantine": len(classes_by_view),
        "mixed_label_feature_views": len(mixed),
        "quality_counts": dict(counts),
        "research_candidate_views_after_quarantine": len(keep),
        "candidate_benign_views": int(np.sum(labels[keep] == 0)),
        "candidate_attack_attempt_views": int(np.sum(labels[keep] == 1)),
        "campaign_ids": len(set(groups)),
        "independent_applications": 1,
        "independent_environments": 0,
        "request_header_values_observed_for_projection": False,
        "fit_ready": False,
        "eval_ready": False,
        "formal_admitted": 0,
        "why_not_fit_or_evaluate": "Single short lab session with one application, no independent campaign/time or enough benign views to support FPR 1%; possible view-label collision and header missingness. Do not score model or select threshold on this cohort.",
        "tensor_sha256": file_sha256(tensor),
        "no_raw_http_or_secret_in_tensor": True,
    }
    result["report_sha256"] = digest(result)
    atomic_json(output / "report.json", result)
    (output / "report.json").chmod(0o600)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "run-report", "factory-script", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--encoder", choices=("rich_v1", "rich_v2"), default="rich_v2")
    args = parser.parse_args()
    with resource_envelope(4, 8):
        result = curate(args.plan, args.run_report, args.factory_script, args.output, args.encoder)
    print(
        {
            "views": result["research_candidate_views_after_quarantine"],
            "mixed": result["mixed_label_feature_views"],
            "report": args.output,
        }
    )
