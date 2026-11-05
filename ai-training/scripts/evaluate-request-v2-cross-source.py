#!/usr/bin/env python3
"""Frozen v2 cross-source publisher-label evaluation; no new training or traffic."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import resource
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import numpy as np
import pyarrow.parquet as pq
from scipy.stats import beta
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.metrics import average_precision_score

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
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / ".artifacts"
SOURCE = ART / "attack_evidence_20261101/research/modsec-wp-v2.xlsx"
SOURCE_SHA = "f959c79e185502b03206f6fdeb29306a65571394c2f009dda503d43ba306d16d"
SOURCE_AUDIT = ART / "attack_evidence_20261101/modsec-wp-audit-final/report.json"
WAF_RAW = ART / "autonomous_research_20261104/waf_v2/train.parquet"
WAF_RAW_SHA = "3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6"
WAF_V2 = ART / "request_intelligence_v2_20261104"
WAF_TENSOR = WAF_V2 / "waf-rich-v2/rich-content.npz"
WAF_PLAN = WAF_V2 / "frozen-plan.json"
WAF_FIT = WAF_V2 / "run/fit-report.json"
WAF_THRESHOLD = WAF_V2 / "run/threshold-manifest.json"
WAF_CHECKPOINT = WAF_V2 / "run/model"
WAF_V1_NUMERIC = ART / "autonomous_content_intelligence_20261104/study-v1/numeric_mlp"
WAF_V1_REPORT = ART / "autonomous_content_intelligence_20261104/study-v1/report.json"
AUDIT_CODE = ROOT / "scripts/audit-modsec-wp.py"
CODE = (
    "src/idps_ai/features/rich_content_v2.py",
    "src/idps_ai/features/rich_content.py",
    "src/idps_ai/features/safe_content.py",
    "src/idps_ai/features/request_view.py",
    "src/idps_ai/features/request_preprocessing.py",
    "src/idps_ai/features/request_encoding.py",
    "src/idps_ai/training/checkpoint.py",
    "src/idps_ai/training/models.py",
    "scripts/audit-modsec-wp.py",
)
FAMILIES = ("normal", "bruteforce", "fileinclusion-ldf", "rce", "sqli", "xss")


def _verified_json(path, field="report_sha256"):
    data = load_json(path)
    if data.get(field) != digest({k: v for k, v in data.items() if k != field}):
        raise PipelineError(f"Artifact self-hash mismatch: {path}")
    return data


def _code_hashes():
    return {name: file_sha256(ROOT / name) for name in CODE}


def _audit_module():
    spec = importlib.util.spec_from_file_location("frozen_modsec_audit", AUDIT_CODE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workbook_rows():
    audit = _audit_module()
    with zipfile.ZipFile(SOURCE) as archive:
        members = archive.infolist()
        if (
            len(members) > 50
            or sum(info.file_size for info in members) > 600 * 1024**2
            or "xl/worksheets/sheet1.xml" not in archive.namelist()
            or "xl/sharedStrings.xml" in archive.namelist()
        ):
            raise PipelineError("ModSec workbook archive bounds changed")
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            first = True
            for _, element in ElementTree.iterparse(stream, events=("end",)):
                if element.tag != audit.NS + "row":
                    continue
                values = [audit._cell_value(cell) for cell in element]
                element.clear()
                if first:
                    if tuple(values) != audit.FIELDS:
                        raise PipelineError("ModSec workbook schema changed")
                    first = False
                    continue
                if len(values) != len(audit.FIELDS):
                    raise PipelineError("ModSec workbook row schema changed")
                yield dict(zip(audit.FIELDS, values, strict=True))


def _raw_key(method, url, body):
    return hashlib.sha256(canonical_bytes([method, url, body])).hexdigest()


def _waf_overlap(raw_keys):
    if file_sha256(WAF_RAW) != WAF_RAW_SHA:
        raise PipelineError("WAF train fingerprint changed")
    found = set()
    parquet = pq.ParquetFile(WAF_RAW)
    if parquet.metadata.num_rows != 1_924_461:
        raise PipelineError("WAF train row count changed")
    for batch in parquet.iter_batches(batch_size=8192, columns=["method", "url", "body"]):
        methods, urls, bodies = (
            batch.column(name).to_pylist() for name in ("method", "url", "body")
        )
        for method, url, body in zip(methods, urls, bodies, strict=True):
            if not isinstance(method, str) or not isinstance(url, str):
                continue
            key = _raw_key(method, url, body or "")
            if key in raw_keys:
                found.add(key)
    return found


def prepare(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise PipelineError("Cross-source preparation output already exists")
    if file_sha256(SOURCE) != SOURCE_SHA:
        raise PipelineError("Pinned ModSec-WP workbook fingerprint changed")
    audit = load_json(SOURCE_AUDIT)
    if (
        audit["workbook_sha256"] != SOURCE_SHA
        or audit["rows"] != 108_883
        or audit["counts"]["distinct_transaction_ids"] != 27_686
    ):
        raise PipelineError("ModSec source audit mismatch")
    tx = {}
    bad_tx = set()
    counts = Counter()
    for row in _workbook_rows():
        counts["workbook_rows"] += 1
        # Apache day/month/year clock; the 2026 coverage-gap augmentation is
        # excluded before the model sees this source.
        year = row["event_time"].split("/")[-1][:4] if "/" in row["event_time"] else ""
        if year not in ("2024", "2026"):
            counts["invalid_year"] += 1
            continue
        if year == "2026":
            counts["augmented_2026_excluded"] += 1
            continue
        method, url, body = row["request_line_method"], row["request_line_url"], row["request_body"]
        label = row["label"].lower()
        tid = row["transaction_id"]
        if not tid or not method or not url or label not in FAMILIES:
            counts["invalid_identity_or_label"] += 1
            continue
        key = _raw_key(method, url, body)
        item = (key, label, method, url, body, row["request_useragent"], row["request_host"])
        if tid in tx:
            counts["repeated_tx_rows"] += 1
            if tx[tid] != item:
                bad_tx.add(tid)
            continue
        tx[tid] = item
    if counts["workbook_rows"] != 108_883 or counts["augmented_2026_excluded"] != 60:
        raise PipelineError("ModSec source year/row distribution changed")
    counts["distinct_2024_transaction_ids"] = len(tx)
    counts["conflicting_transaction_ids"] = len(bad_tx)
    by_raw = defaultdict(set)
    for tid, item in tx.items():
        if tid not in bad_tx:
            by_raw[item[0]].add(item[1])
    bad_raw = {key for key, labels in by_raw.items() if len(labels) > 1}
    counts["conflicting_raw_representations"] = len(bad_raw)
    entries = [
        (tid, item) for tid, item in tx.items() if tid not in bad_tx and item[0] not in bad_raw
    ]
    raw_overlap = _waf_overlap({item[0] for _, item in entries})
    counts["exact_method_url_body_overlap_waf_train"] = len(raw_overlap)

    with np.load(WAF_TENSOR, allow_pickle=False) as data:
        waf_train_view = set(data["view"][data["role"] == 0].astype(str))
        waf_train_group = set(data["group"][data["role"] == 0].astype(str))
        waf_train_content = data["content"][data["role"] == 0]
    numerical, symbols = [], []
    labels, family, method, raw, group, route, tx_hash = [], [], [], [], [], [], []
    body_present, ua_present, host_present = [], [], []
    spec = bounded_spec()
    for tid, item in entries:
        raw_key, label, meth, url, body, ua, host = item
        header = (
            " ".join(
                part
                for part in (f"User-Agent: {ua}" if ua else "", f"Host: {host}" if host else "")
                if part
            )
            or None
        )
        try:
            values = encode_request(spec, project_request(url, meth)["numbers"])
            text, _ = rich_request_v2(meth, url, header, body or None)
            template, _ = symbolic_request(meth, url, header, body or None)
        except (PipelineError, ValueError, OverflowError):
            counts["unprojectable_transaction_ids"] += 1
            continue
        numerical.append(values)
        symbols.append(text)
        labels.append(int(label != "normal"))
        family.append(label)
        method.append(meth)
        raw.append(raw_key)
        group.append(hashlib.sha256(template.encode()).hexdigest())
        route.append(hashlib.sha256(canonical_bytes([meth, urlsplit(url).path])).hexdigest())
        tx_hash.append(hashlib.sha256(tid.encode()).hexdigest())
        body_present.append(bool(body))
        ua_present.append(bool(ua))
        host_present.append(bool(host))
    if len(numerical) < 1000:
        raise PipelineError("ModSec request-content evaluation lacks candidates")
    content = (
        HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )
        .transform(symbols)
        .toarray()
        .astype(np.float32)
    )
    numeric = np.asarray(numerical, np.float32)
    views = [
        hashlib.sha256(np.concatenate((a, b)).tobytes()).hexdigest()
        for a, b in zip(numeric, content, strict=True)
    ]
    view_labels = defaultdict(set)
    for view, label in zip(views, labels, strict=True):
        view_labels[view].add(label)
    bad_view = {view for view, labels in view_labels.items() if len(labels) > 1}
    counts["conflicting_v2_feature_views"] = len(bad_view)
    keep = np.asarray([i for i, view in enumerate(views) if view not in bad_view], np.int64)
    counts["tx_rows_after_quarantine"] = len(keep)
    counts["unique_complete_request_representations_after_quarantine"] = len({raw[i] for i in keep})
    counts["unique_v2_views_after_quarantine"] = len({views[i] for i in keep})
    raw_overlap_rows = sum(raw[i] in raw_overlap for i in keep)
    view_overlap_rows = sum(views[i] in waf_train_view for i in keep)
    template_overlap_rows = sum(group[i] in waf_train_group for i in keep)
    counts.update(
        raw_overlap_rows=raw_overlap_rows,
        view_overlap_rows=view_overlap_rows,
        template_overlap_rows=template_overlap_rows,
    )
    # Fixed-seed bounded sample; this is not an exhaustive near-duplicate proof.
    rng = np.random.default_rng(20261104)
    left = rng.choice(len(waf_train_content), min(512, len(waf_train_content)), replace=False)
    right = rng.choice(keep, min(512, len(keep)), replace=False)
    similarity = waf_train_content[left] @ content[right].T
    near_probe = {
        "waf_train_sample": len(left),
        "modsec_sample": len(right),
        "content_cosine_ge_0_995_pairs": int(np.sum(similarity >= 0.995)),
        "max_content_cosine": float(np.max(similarity)),
    }

    output.mkdir(parents=True, mode=0o700)
    tensor = output / "cohort.npz"
    with tensor.open("xb") as stream:
        np.savez_compressed(
            stream,
            numeric=numeric[keep],
            content=content[keep],
            label=np.asarray(labels, np.int8)[keep],
            family=np.asarray(family, dtype="S32")[keep],
            method=np.asarray(method, dtype="S16")[keep],
            raw=np.asarray(raw, dtype="S64")[keep],
            view=np.asarray(views, dtype="S64")[keep],
            group=np.asarray(group, dtype="S64")[keep],
            route=np.asarray(route, dtype="S64")[keep],
            tx_hash=np.asarray(tx_hash, dtype="S64")[keep],
            body_present=np.asarray(body_present, np.int8)[keep],
            ua_present=np.asarray(ua_present, np.int8)[keep],
            host_present=np.asarray(host_present, np.int8)[keep],
            raw_overlap=np.asarray([raw[i] in raw_overlap for i in keep], np.int8),
            view_overlap=np.asarray([views[i] in waf_train_view for i in keep], np.int8),
            template_overlap=np.asarray([group[i] in waf_train_group for i in keep], np.int8),
        )
        stream.flush()
        os.fsync(stream.fileno())
    tensor.chmod(0o600)
    report = {
        "format_version": 1,
        "source": "ModSec-WP v2 Zenodo 10.5281/zenodo.21872151; CC BY 4.0 publisher metadata",
        "scope": "2024 WordPress testbed, retrospective publisher labels; not blind or verified attack intent",
        "source_workbook_sha256": SOURCE_SHA,
        "source_audit_file_sha256": file_sha256(SOURCE_AUDIT),
        "waf_train_sha256": WAF_RAW_SHA,
        "waf_v2_train_tensor_sha256": file_sha256(WAF_TENSOR),
        "encoder_sha256": file_sha256(ROOT / "src/idps_ai/features/rich_content_v2.py"),
        "numeric_spec_sha256": digest(spec),
        "code_sha256": file_sha256(__file__),
        "counts": dict(counts),
        "publisher_family_counts_after_quarantine": dict(Counter(family[i] for i in keep)),
        "method_counts_after_quarantine": dict(Counter(method[i] for i in keep)),
        "feature_availability": {
            "request_method_url_body": True,
            "user_agent_observed_rows": int(sum(ua_present[i] for i in keep)),
            "host_observed_rows": int(sum(host_present[i] for i in keep)),
            "all_other_header_values": "unavailable; never fabricated",
            "response_waf_rule_status_as_model_input": False,
        },
        "near_duplicate_probe": near_probe,
        "physical_request_count_verified": False,
        "label_semantics": "publisher normal vs publisher sqli/xss/fileinclusion/rce/bruteforce; hybrid scenario/regex/manual, per-row basis unavailable",
        "independent_attack_intent_verified": 0,
        "formal_admitted": 0,
        "cohort_sha256": file_sha256(tensor),
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "preparation-report.json", report)
    (output / "preparation-report.json").chmod(0o600)
    return report


def freeze(output, plan_path):
    output, plan_path = Path(output), Path(plan_path)
    if plan_path.exists() or plan_path.is_symlink():
        raise PipelineError("Cross-source evaluation plan already exists")
    preparation = _verified_json(output / "preparation-report.json")
    tensor = output / "cohort.npz"
    if preparation["cohort_sha256"] != file_sha256(tensor):
        raise PipelineError("Cross-source prepared cohort fingerprint changed")
    with np.load(tensor, allow_pickle=False) as data:
        label = data["label"]
        view = data["view"]
        raw_overlap = data["raw_overlap"]
        view_overlap = data["view_overlap"]
        template_overlap = data["template_overlap"]
    primary = (raw_overlap == 0) & (view_overlap == 0) & (template_overlap == 0)
    if (
        len(label) != preparation["counts"]["tx_rows_after_quarantine"]
        or min(np.bincount(label, minlength=2)) < 100
        or len(set(view[primary])) < 100
    ):
        raise PipelineError("ModSec publisher cohort lacks two-class primary coverage")
    waf_plan = _verified_json(WAF_PLAN, "plan_sha256")
    waf_fit = _verified_json(WAF_FIT)
    waf_threshold = load_json(WAF_THRESHOLD)
    loaded = load_checkpoint(WAF_CHECKPOINT)
    if (
        waf_threshold.get("manifest_sha256")
        != digest({k: v for k, v in waf_threshold.items() if k != "manifest_sha256"})
        or waf_fit["plan_sha256"] != waf_plan["plan_sha256"]
        or waf_threshold["plan_sha256"] != waf_plan["plan_sha256"]
        or loaded.state["plan_sha256"] != waf_plan["plan_sha256"]
        or file_sha256(loaded.path / "manifest.json")
        != waf_threshold["final_checkpoint_manifest_sha256"]
        or waf_plan["encoder_version"] != "rich_content_v2"
        or waf_plan["feature_count"] != 588
        or loaded.model.input_dim != 588
    ):
        raise PipelineError("Frozen Request Intelligence v2 integrity mismatch")
    plan = {
        "format_version": 1,
        "purpose": "one frozen cross-source publisher-label retrospective evaluation",
        "source": preparation["source"],
        "source_revision": "Zenodo ModSec-WP v2, DOI 10.5281/zenodo.21872151",
        "source_license": "CC BY 4.0 publisher metadata; research scoring only",
        "source_workbook_sha256": SOURCE_SHA,
        "source_audit_sha256": file_sha256(SOURCE_AUDIT),
        "cohort_sha256": file_sha256(tensor),
        "preparation_report_sha256": file_sha256(output / "preparation-report.json"),
        "inclusion": "2024 workbook rows only; valid transaction ID/method/URL and six publisher classes",
        "exclusion": "2026 gap-remediation rows; invalid/unprojectable; conflicting transaction IDs, complete method/URL/body identities, or v2 feature views",
        "dedup": "one observation per transaction ID; request-level uses ID proxies, unique-view metrics dedup float32 feature bytes",
        "primary": "publisher-label rows with zero exact method/URL/body, exact feature-view, or exact safe-template overlap with WAF train",
        "near_duplicate": "fixed-seed 512x512 cosine>=0.995 probe; not exhaustive; no blind claim",
        "label_semantics": preparation["label_semantics"],
        "metrics": [
            "publisher-label precision/sensitivity/normal flagged fraction/AP",
            "unique-view and transaction-proxy counts",
            "Clopper-Pearson95 descriptive intervals",
            "per-method/family false negatives",
            "latency/model-only CPU-RSS",
        ],
        "threshold_rule": "frozen v2 score > publisher-NORMAL calibration p99, no external recalibration",
        "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
        "threshold_file_sha256": file_sha256(WAF_THRESHOLD),
        "threshold": waf_threshold["threshold"],
        "waf_train_sha256": WAF_RAW_SHA,
        "waf_train_tensor_sha256": file_sha256(WAF_TENSOR),
        "waf_plan_sha256": file_sha256(WAF_PLAN),
        "v1_numeric_checkpoint_manifest_sha256": file_sha256(
            load_checkpoint(WAF_V1_NUMERIC).path / "manifest.json"
        ),
        "v1_numeric_report_sha256": file_sha256(WAF_V1_REPORT),
        "code_sha256": _code_hashes(),
        "evaluator_sha256": file_sha256(__file__),
        "development_shortcut_controls": "method posterior from v2 train with Laplace1; frozen v1 numeric MLP; unweighted five request-structure features; same v2 development, never external tuning",
        "primary_two_class_counts": {
            "publisher_normal": int(np.sum(primary & (label == 0))),
            "publisher_attack_family": int(np.sum(primary & (label == 1))),
        },
        "external_scores_seen_before_freeze": False,
        "no_training_or_threshold_change": True,
        "formal_admitted": 0,
    }
    plan["plan_sha256"] = digest(plan)
    atomic_json(plan_path, plan)
    plan_path.chmod(0o600)
    return plan


def _frozen(output, plan_path):
    output, plan_path = Path(output), Path(plan_path)
    plan = _verified_json(plan_path, "plan_sha256")
    if (
        plan["evaluator_sha256"] != file_sha256(__file__)
        or plan["code_sha256"] != _code_hashes()
        or plan["cohort_sha256"] != file_sha256(output / "cohort.npz")
        or plan["preparation_report_sha256"] != file_sha256(output / "preparation-report.json")
        or plan["source_workbook_sha256"] != file_sha256(SOURCE)
        or plan["source_audit_sha256"] != file_sha256(SOURCE_AUDIT)
        or plan["waf_train_sha256"] != file_sha256(WAF_RAW)
        or plan["waf_train_tensor_sha256"] != file_sha256(WAF_TENSOR)
        or plan["waf_plan_sha256"] != file_sha256(WAF_PLAN)
        or plan["threshold_file_sha256"] != file_sha256(WAF_THRESHOLD)
    ):
        raise PipelineError("Cross-source evaluation plan/input changed")
    checkpoint = load_checkpoint(WAF_CHECKPOINT)
    if (
        file_sha256(checkpoint.path / "manifest.json") != plan["checkpoint_manifest_sha256"]
        or checkpoint.model.input_dim != 588
        or checkpoint.model.steps != 3072
    ):
        raise PipelineError("Frozen v2 checkpoint changed")
    with np.load(output / "cohort.npz", allow_pickle=False) as z:
        cohort = {name: z[name].copy() for name in z.files}
    return plan, checkpoint.model, cohort


def _score(model, x):
    return np.concatenate([model.predict(x[i : i + 4096])[0] for i in range(0, len(x), 4096)])


def _interval(success, total):
    if total == 0:
        return None
    return [
        0.0 if success == 0 else float(beta.ppf(0.025, success, total - success + 1)),
        1.0 if success == total else float(beta.ppf(0.975, success + 1, total - success)),
    ]


def _metrics(label, score, threshold):
    if len(label) == 0 or min(np.bincount(label, minlength=2)) == 0:
        return {"status": "INSUFFICIENT_TWO_CLASS_PUBLISHER_LABELS", "rows": len(label)}
    flagged = score > threshold
    positive, negative = label == 1, label == 0
    tp = int(np.sum(flagged & positive))
    fp = int(np.sum(flagged & negative))
    n_pos, n_neg = int(np.sum(positive)), int(np.sum(negative))
    total_flagged = int(np.sum(flagged))
    return {
        "publisher_normal": n_neg,
        "publisher_attack_family": n_pos,
        "publisher_positive_flagged": tp,
        "publisher_normal_flagged": fp,
        "publisher_label_precision": tp / total_flagged if total_flagged else None,
        "publisher_positive_sensitivity": tp / n_pos,
        "publisher_normal_flagged_fraction": fp / n_neg,
        "publisher_normal_flags_per_10000": 10000 * fp / n_neg,
        "publisher_label_pr_auc": float(average_precision_score(label, score)),
        "descriptive_binomial_95_interval": {
            "precision": _interval(tp, total_flagged),
            "positive_sensitivity": _interval(tp, n_pos),
            "normal_flagged_fraction": _interval(fp, n_neg),
            "warning": "Clopper-Pearson treats observations as IID; repeated templates, one lab/source and weak labels invalidate independent-population coverage.",
        },
    }


def _development_controls(model):
    with np.load(WAF_TENSOR, allow_pickle=False) as z:
        numeric, content, labels, roles = (
            z[name] for name in ("numeric", "content", "label", "role")
        )
    cols = bounded_spec()["columns"]
    methods = [i for i, name in enumerate(cols) if name.startswith("method_")]
    train, cal, dev = (roles == role for role in (0, 1, 2))
    method_id = np.argmax(numeric[:, methods], axis=1)
    table = {}
    for index in range(len(methods)):
        selected = train & (method_id == index)
        positive = int(np.sum(labels[selected] == 1))
        negative = int(np.sum(labels[selected] == 0))
        table[index] = (positive + 1) / (positive + negative + 2)
    method_score = np.asarray([table[int(i)] for i in method_id], np.float32)
    structure_columns = (
        "decoded_uri_length",
        "decoded_query_length",
        "boolean_operator_count",
        "comparison_operator_count",
        "quote_single",
    )
    structure = numeric[:, [cols.index(name) for name in structure_columns]].mean(axis=1)
    numeric_checkpoint = load_checkpoint(WAF_V1_NUMERIC)
    v1_report = _verified_json(WAF_V1_REPORT)
    if (
        file_sha256(numeric_checkpoint.path / "manifest.json")
        != v1_report["arms"]["numeric_mlp"]["checkpoint_manifest_sha256"]
        or numeric_checkpoint.model.input_dim != 76
    ):
        raise PipelineError("Frozen numeric-only control integrity mismatch")
    numeric_score = _score(numeric_checkpoint.model, numeric[dev])
    rich_score = _score(model, np.concatenate((numeric[dev], content[dev]), axis=1))
    return {
        "scope": "same WAF train-source development roles, not cross-source validation",
        "method_only": {
            "train_class_posterior": {
                cols[methods[i]]: {
                    "publisher_anomalous_probability": table[i],
                    "train_rows": int(np.sum(train & (method_id == i))),
                }
                for i in range(len(methods))
            },
            "development_pr_auc": float(average_precision_score(labels[dev], method_score[dev])),
        },
        "request_length_structure_only": {
            "columns": list(structure_columns),
            "development_pr_auc": float(average_precision_score(labels[dev], structure[dev])),
        },
        "numeric_only_frozen_v1_checkpoint": {
            "different_fit_cohort": True,
            "development_pr_auc": float(average_precision_score(labels[dev], numeric_score)),
        },
        "rich_v2_frozen": {
            "development_pr_auc": float(average_precision_score(labels[dev], rich_score)),
            "score_by_method": {
                cols[methods[i]]: {
                    "rows": int(np.sum(dev & (method_id == i))),
                    "median": float(np.median(rich_score[method_id[dev] == i])),
                }
                for i in range(len(methods))
                if np.any(dev & (method_id == i))
            },
        },
        "interpretation": "Controls are descriptive; method/length association is a shortcut risk, not proof of model reliance. Numeric v1 used a different fit cohort. No external scores used to fit controls.",
    }


def score(output, plan_path):
    output = Path(output)
    destination = output / "evaluation-report.json"
    if destination.exists():
        raise PipelineError("Cross-source result already exists")
    plan, model, cohort = _frozen(output, plan_path)
    values = np.concatenate((cohort["numeric"], cohort["content"]), axis=1)
    if values.shape[1] != 588 or not np.isfinite(values).all():
        raise PipelineError("Cross-source input contract mismatch")
    controls = _development_controls(model)
    threshold = float(plan["threshold"])
    start = time.perf_counter()
    scores = _score(model, values)
    elapsed_ms = 1000 * (time.perf_counter() - start)
    if not np.isfinite(scores).all():
        raise PipelineError("Cross-source score nonfinite")
    labels = cohort["label"]
    primary = (
        (cohort["raw_overlap"] == 0)
        & (cohort["view_overlap"] == 0)
        & (cohort["template_overlap"] == 0)
    )
    if (
        int(np.sum(primary & (labels == 0))) != plan["primary_two_class_counts"]["publisher_normal"]
        or int(np.sum(primary & (labels == 1)))
        != plan["primary_two_class_counts"]["publisher_attack_family"]
    ):
        raise PipelineError("Primary cross-source cohort changed after freeze")
    _, unique_index = np.unique(cohort["view"], return_index=True)
    unique_index = np.sort(unique_index)
    primary_indices = np.flatnonzero(primary)
    _, primary_unique_local = np.unique(cohort["view"][primary], return_index=True)
    primary_unique_index = np.sort(primary_indices[primary_unique_local])
    by_method = {}
    for meth in sorted(set(cohort["method"].astype(str))):
        selected = primary & (cohort["method"].astype(str) == meth)
        by_method[meth] = _metrics(labels[selected], scores[selected], threshold)
    by_family = {}
    for family in sorted(set(cohort["family"].astype(str))):
        selected = primary & (cohort["family"].astype(str) == family)
        vals = scores[selected]
        by_family[family] = {
            "transaction_proxies": len(vals),
            "flagged": int(np.sum(vals > threshold)),
            "missed": int(np.sum(vals <= threshold)) if family != "normal" else None,
            "median_score": float(np.median(vals)) if len(vals) else None,
        }
    flagged = scores > threshold
    false_negatives = primary & (labels == 1) & ~flagged
    fn_groups = {
        "by_family": dict(Counter(cohort["family"][false_negatives].astype(str))),
        "by_method": dict(Counter(cohort["method"][false_negatives].astype(str))),
        "body_present": int(np.sum(cohort["body_present"][false_negatives])),
        "user_agent_missing": int(np.sum(1 - cohort["ua_present"][false_negatives])),
        "score_margin_below_threshold_median": float(np.median(threshold - scores[false_negatives]))
        if np.any(false_negatives)
        else None,
    }
    route_groups = defaultdict(set)
    for idx in np.flatnonzero(primary):
        route_groups[cohort["route"][idx]].add(int(labels[idx]))
    mixed_routes = {route for route, members in route_groups.items() if len(members) == 2}
    route_mixed = np.asarray([route in mixed_routes for route in cohort["route"]], bool) & primary
    report = {
        "format_version": 1,
        "scope": plan["purpose"],
        "plan_file_sha256": file_sha256(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "source": plan["source"],
        "source_audit_level": "publisher labels/hybrid scenario+regex+manual, no per-row independent intent proof",
        "raw_workbook_rows": 108883,
        "prepared_transaction_id_proxies": len(labels),
        "prepared_unique_request_representations": len(set(cohort["raw"])),
        "prepared_unique_v2_feature_views": len(unique_index),
        "primary_no_exact_raw_view_template_overlap": int(np.sum(primary)),
        "primary_unique_v2_views": len(primary_unique_index),
        "all_prepared_transaction_proxy_metrics": _metrics(labels, scores, threshold),
        "primary_transaction_proxy_metrics": _metrics(labels[primary], scores[primary], threshold),
        "primary_unique_view_metrics": _metrics(
            labels[primary_unique_index], scores[primary_unique_index], threshold
        ),
        "publisher_family_primary": by_family,
        "http_method_primary": by_method,
        "false_negatives_primary": fn_groups,
        "same_method_path_mixed_label_route_groups": len(mixed_routes),
        "same_method_path_mixed_label_transaction_proxies": int(np.sum(route_mixed)),
        "development_shortcut_controls": controls,
        "missingness": {
            "body_absent": int(np.sum(1 - cohort["body_present"])),
            "user_agent_absent": int(np.sum(1 - cohort["ua_present"])),
            "host_absent": int(np.sum(1 - cohort["host_present"])),
            "other_header_values": "not observed in workbook; no invented values",
        },
        "overlap": {
            "raw_method_url_body_rows": int(np.sum(cohort["raw_overlap"])),
            "exact_v2_view_rows": int(np.sum(cohort["view_overlap"])),
            "exact_safe_template_rows": int(np.sum(cohort["template_overlap"])),
        },
        "latency": {
            "model_only_batch_all_ms": elapsed_ms,
            "model_only_amortized_ms_per_transaction_proxy": elapsed_ms / len(labels),
            "encoder_and_workbook_io_excluded": True,
        },
        "resource": {
            "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "max_cpus": 4,
            "cgroup_memory_cap_gib": 16,
        },
        "limits": [
            "Publisher labels mix scenario/time, regex and manual review; no per-row independent ground truth",
            "One WordPress testbed with repeated transactions and near-duplicate requests",
            "Source was previously audited, so this is retrospective cross-source, not blind evaluation",
            "Exact raw/view/template overlap checked against WAF train; near-duplicate probe is sampled only",
            "WAF train may share upstream patterns with this source despite distinct publishers",
            "User-Agent/Host only; other HTTP header values unavailable, causing input missingness/domain shift",
            "Clopper-Pearson intervals assume IID and are descriptive only under this clustering",
            "No external threshold tuning, model fitting, champion selection or formal admission",
        ],
        "formal_admitted": 0,
    }
    report["report_sha256"] = digest(report)
    atomic_json(destination, report)
    destination.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "freeze", "score"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--plan")
    args = parser.parse_args()
    with resource_envelope(4, 16):
        if args.mode == "prepare":
            result = prepare(args.output)
        elif args.mode == "freeze":
            if not args.plan:
                parser.error("freeze requires --plan")
            result = freeze(args.output, args.plan)
        else:
            if not args.plan:
                parser.error("score requires --plan")
            result = score(args.output, args.plan)
    print(
        {"mode": args.mode, "status": "PASS", "scope": result.get("scope", result.get("purpose"))}
    )
