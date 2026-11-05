"""Offline, read-only inference for the two frozen research checkpoints."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.common import AI_ROOT, PipelineError, digest, file_sha256, fsync_dir, load_json
from idps_ai.data.structure import STRUCTURE_KEYS
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import (
    NUMERIC_COLUMNS,
    FeatureExtractor,
    feature_columns,
    implementation_fingerprint,
    transform,
)
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope

ART = AI_ROOT / ".artifacts"
V2_ROOT = ART / "request_intelligence_v2_20261104/run"
V2_PLAN = ART / "request_intelligence_v2_20261104/frozen-plan.json"
GLU_ROOT = ART / "research_glu207_bounded_final_20261104"
GLU_SPEC = ART / "scale_upgrade_20261030/prepared-v5/feature_spec.json"
GLU_THRESHOLD = ART / "bc27_1104/threshold-manifest.json"
V2_CHECKPOINT_SHA = "acdc0a2c9bff24fa0e4720dfcdd97e4a315e39fc625cf603e06eecc5c07a92fc"
V2_THRESHOLD_SHA = "6d0fd376d0777f97fb61688b898556a4a9b9b94656738723e7b74e1d33061f6a"
GLU_CHECKPOINT_SHA = "e663b0979f6fd3222ce08922f7e50958d2111a59d8d72a59f470d292146c0636"
GLU_THRESHOLD_SHA = "d7b00aa9905400b583015452599bbb452a5009ea1e9099c9fc62eb1cd6efced2"
RECORD_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
FLOW_KEYS = (
    "duration_seconds",
    "bytes_to_server",
    "bytes_to_client",
    "packets_to_server",
    "packets_to_client",
)
REQUIRED_FUSED = frozenset(
    {
        "timestamp",
        "available_at",
        "request_key",
        "client_key",
        "user_key",
        "sources",
        "correlation",
        "http_method",
        "uri_path",
        "role",
        "user_agent",
        "status_code",
        "latency_ms",
        "request_bytes",
        "response_bytes",
        "numeric_json",
        "flow_json",
        "suricata_alert_counts",
    }
)


def _self_hashed(path, field):
    value = load_json(path)
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise PipelineError("Frozen research manifest failed integrity verification")
    return value


def _finite_nonnegative(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def validate_http(value):
    if not isinstance(value, dict) or not {"method", "url", "headers", "body"} <= value.keys():
        raise PipelineError("http_request requires method, url, headers and body")
    if (
        not isinstance(value["method"], str)
        or not 1 <= len(value["method"]) <= 16
        or not isinstance(value["url"], str)
        or not 1 <= len(value["url"]) <= 8192
        or value["headers"] is not None
        and (not isinstance(value["headers"], str) or len(value["headers"]) > 8192)
        or value["body"] is not None
        and (not isinstance(value["body"], str) or len(value["body"]) > 8192)
    ):
        raise PipelineError("Invalid or oversized HTTP request representation")
    return value


def validate_fused(value):
    if not isinstance(value, dict) or not REQUIRED_FUSED <= value.keys():
        raise PipelineError("fused_request is missing required post-response fields")
    if (
        not isinstance(value["sources"], list)
        or len(value["sources"]) != 3
        or any(not isinstance(source, str) for source in value["sources"])
        or set(value["sources"]) != {"STUDENT_AUDIT", "NGINX", "SURICATA"}
        or value["correlation"] != "request_id"
    ):
        raise PipelineError("GLU207 requires correlated Student, Nginx and Suricata observations")
    if (
        not isinstance(value["request_key"], str)
        or not value["request_key"]
        or not _finite_nonnegative(value["timestamp"])
        or not _finite_nonnegative(value["available_at"])
        or not isinstance(value["http_method"], str)
        or not isinstance(value["uri_path"], str)
        or not isinstance(value["status_code"], int)
        or isinstance(value["status_code"], bool)
        or not 100 <= value["status_code"] <= 599
        or any(
            not _finite_nonnegative(value[name])
            for name in ("latency_ms", "request_bytes", "response_bytes")
        )
    ):
        raise PipelineError("GLU207 requires valid identity, event time and response fields")
    if not isinstance(value["numeric_json"], str) or not isinstance(value["flow_json"], str):
        raise PipelineError("GLU207 numeric and flow bridges must be JSON strings")
    try:
        numeric = json.loads(value["numeric_json"])
        flow = json.loads(value["flow_json"])
    except (ValueError, TypeError):
        raise PipelineError("Invalid GLU207 numeric or flow JSON bridge") from None
    if (
        not isinstance(numeric, dict)
        or not set(NUMERIC_COLUMNS).union(STRUCTURE_KEYS) <= numeric.keys()
        or any(
            numeric.get(name) != 1.0
            for name in ("uri_lexical_available", "query_lexical_available", "structure_available")
        )
        or any(not _finite_nonnegative(numeric[name]) for name in NUMERIC_COLUMNS)
        or any(not _finite_nonnegative(numeric[name]) for name in STRUCTURE_KEYS)
    ):
        raise PipelineError("GLU207 requires the observed 207-feature numeric bridge")
    if (
        not isinstance(flow, dict)
        or not set(FLOW_KEYS) <= flow.keys()
        or any(v is not None and not _finite_nonnegative(v) for v in (flow[k] for k in FLOW_KEYS))
    ):
        raise PipelineError("GLU207 flow bridge must record observed values or explicit nulls")
    alerts = value["suricata_alert_counts"]
    if (
        not isinstance(alerts, list)
        or len(alerts) != 3
        or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in alerts)
    ):
        raise PipelineError("Invalid causal Suricata context counters")
    return value, numeric, flow


class ResearchMVP:
    def __init__(self, model, cpus=4):
        if model not in ("request-v2", "glu207", "both") or not 1 <= cpus <= 8:
            raise PipelineError("Select request-v2, glu207 or both with 1–8 CPUs")
        self.model = model
        self.cpus = cpus
        self.seen = set()
        if model in ("request-v2", "both"):
            plan = _self_hashed(V2_PLAN, "plan_sha256")
            report = _self_hashed(V2_ROOT / "fit-report.json", "report_sha256")
            threshold = _self_hashed(V2_ROOT / "threshold-manifest.json", "manifest_sha256")
            loaded = load_checkpoint(V2_ROOT / "model")
            if (
                file_sha256(V2_ROOT / "threshold-manifest.json") != V2_THRESHOLD_SHA
                or any(
                    file_sha256(AI_ROOT / name) != sha for name, sha in plan["code_sha256"].items()
                )
                or plan["feature_count"] != 588
                or plan["encoder_version"] != "rich_content_v2"
                or file_sha256(loaded.path / "manifest.json")
                != report["final_checkpoint_manifest_sha256"]
                or report["final_checkpoint_manifest_sha256"] != V2_CHECKPOINT_SHA
                or threshold["final_checkpoint_manifest_sha256"]
                != report["final_checkpoint_manifest_sha256"]
                or threshold["encoder_version"] != "rich_content_v2"
                or loaded.state["plan_sha256"] != threshold["plan_sha256"]
                or loaded.model.kind != "deep_mlp"
                or loaded.model.input_dim != 588
                or loaded.model.steps != 3072
                or sum(p.size for p in loaded.model.parameters.values()) != 50_696
            ):
                raise PipelineError("Frozen Request Intelligence v2 checkpoint contract mismatch")
            self.v2_model = loaded.model
            self.v2_threshold = float(threshold["threshold"])
            self.v2_manifest_sha = file_sha256(loaded.path / "manifest.json")
            self.vectorizer = HashingVectorizer(
                analyzer="char",
                ngram_range=(3, 5),
                n_features=512,
                alternate_sign=False,
                norm="l2",
                dtype=np.float32,
            )
            self.numeric_spec = bounded_spec()
        if model in ("glu207", "both"):
            report = load_json(GLU_ROOT / "report.json")
            threshold = load_json(GLU_THRESHOLD)
            loaded = load_checkpoint(GLU_ROOT / "run")
            self.glu_spec = load_json(GLU_SPEC)
            if (
                file_sha256(GLU_THRESHOLD) != GLU_THRESHOLD_SHA
                or report["final_checkpoint_manifest_sha256"] != GLU_CHECKPOINT_SHA
                or file_sha256(loaded.path / "manifest.json")
                != report["final_checkpoint_manifest_sha256"]
                or threshold["model_checkpoint_manifest_sha256"]
                != report["final_checkpoint_manifest_sha256"]
                or file_sha256(GLU_SPEC) != threshold["feature_spec_sha256"]
                or file_sha256(GLU_ROOT / "research-final.onnx") != threshold["onnx_sha256"]
                or self.glu_spec["implementation_sha256"] != implementation_fingerprint()
                or self.glu_spec["columns"]
                != feature_columns(input_profile="safe_query_numeric_v2", behavior_dynamics=True)
                or len(self.glu_spec["columns"]) != 207
                or loaded.model.kind != "residual_glu"
                or loaded.model.input_dim != 207
                or loaded.model.steps != 652
                or sum(p.size for p in loaded.model.parameters.values()) != 9_675_784
                or threshold["status"] != "PROVISIONAL_BENIGN_ONLY"
            ):
                raise PipelineError("Frozen GLU207 checkpoint/ONNX/feature contract mismatch")
            self.glu_model = loaded.model
            self.glu_session = cpu_session(GLU_ROOT / "research-final.onnx", cpus)
            self.glu_threshold = float(threshold["threshold"])
            self.glu_manifest_sha = file_sha256(loaded.path / "manifest.json")
            self.extractor = FeatureExtractor(**self.glu_spec["state_limits"])

    def predict(self, record):
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("record_id"), str)
            or not RECORD_ID.fullmatch(record["record_id"])
        ):
            raise PipelineError("record_id must be an opaque ASCII identifier of 1–128 characters")
        if record.get("schema_version") != "research-mvp-1":
            raise PipelineError("Unsupported input schema_version; expected research-mvp-1")
        request = record.get("http_request")
        fused = record.get("fused_request")
        if request is None and fused is None:
            raise PipelineError("At least one HTTP or fused request representation is required")
        if self.model == "request-v2" and request is None:
            raise PipelineError("request-v2 requires http_request")
        if self.model == "glu207" and fused is None:
            raise PipelineError("glu207 requires fused_request")
        result = {
            "schema_version": "research-mvp-1",
            "record_id": record["record_id"],
            "mode": "offline_shadow",
            "models": {},
            "combined_score": None,
            "enforcement_actions": 0,
        }
        if self.model in ("request-v2", "both"):
            if request is None:
                result["models"]["request_intelligence_v2"] = {
                    "status": "unavailable",
                    "reason": "http_request absent",
                }
            else:
                request = validate_http(request)
                numeric = encode_request(
                    self.numeric_spec,
                    project_request(request["url"], request["method"])["numbers"],
                )
                symbolic, availability = rich_request_v2(
                    request["method"], request["url"], request["headers"], request["body"]
                )
                content = self.vectorizer.transform([symbolic]).toarray().astype(np.float32)[0]
                vector = np.concatenate((numeric, content))[None, :]
                score = float(self.v2_model.predict(vector)[0][0])
                if not math.isfinite(score):
                    raise PipelineError("Nonfinite Request Intelligence v2 score")
                result["models"]["request_intelligence_v2"] = {
                    "status": "scored",
                    "score": score,
                    "above_research_threshold": score > self.v2_threshold,
                    "research_threshold": self.v2_threshold,
                    "model_version": f"request-intelligence-v2-step3072-{self.v2_manifest_sha[:12]}",
                    "encoder_version": "rich_content_v2+bounded-request-v1",
                    "feature_count": 588,
                    "feature_availability": {
                        "headers_observed": request["headers"] is not None,
                        "body_observed": request["body"] is not None,
                        **availability,
                    },
                }
        if self.model in ("glu207", "both"):
            if fused is None:
                result["models"]["glu207"] = {
                    "status": "unavailable",
                    "reason": "fused_request absent; no 207-feature padding",
                }
            else:
                fused, numeric, flow = validate_fused(fused)
                key = fused["request_key"]
                if key in self.seen:
                    raise PipelineError("Duplicate fused request cannot be scored twice")
                values = self.extractor.observe(fused)
                vector = transform(self.glu_spec, values)
                if vector.shape != (207,) or not np.isfinite(vector).all():
                    raise PipelineError("Invalid GLU207 feature vector")
                score_array, probabilities = self.glu_session.run(None, {"input": vector[None]})
                score = float(score_array[0])
                if not math.isfinite(score) or not np.isfinite(probabilities).all():
                    raise PipelineError("Nonfinite GLU207 inference output")
                self.seen.add(key)
                result["models"]["glu207"] = {
                    "status": "scored",
                    "score": score,
                    "above_research_threshold": score >= self.glu_threshold,
                    "research_threshold": self.glu_threshold,
                    "threshold_scope": "provisional_benign_lab_only",
                    "model_version": f"glu207-step652-{self.glu_manifest_sha[:12]}",
                    "encoder_version": "ai-features-5",
                    "feature_count": 207,
                    "feature_availability": {
                        "three_sources_correlated": True,
                        "post_response_fields_observed": True,
                        "numeric_bridge_observed": True,
                        "prior_flow_observed": any(flow[k] is not None for k in FLOW_KEYS),
                        "query_original_available": numeric.get("query_original_available") == 1.0,
                        "context_incomplete": any(
                            values[name] > 0
                            for name in self.glu_spec["columns"]
                            if name.endswith("context_incomplete")
                        ),
                    },
                }
        return result


def infer_jsonl(input_path, output_path, model="both", cpus=4):
    source = Path(input_path).resolve()
    output = Path(output_path).absolute()
    if output.is_symlink():
        raise PipelineError("Output cannot be a symbolic link")
    destination = output.parent.resolve() / output.name
    if source == destination or not source.is_file() or destination.exists():
        raise PipelineError("Input must exist and output must be a new, different JSONL file")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    count = 0
    record_ids = set()
    with resource_envelope(cpus, 16) as (guard, _):
        predictor = ResearchMVP(model, cpus)
        descriptor, temporary = tempfile.mkstemp(prefix=".mvp-", dir=destination.parent)
        try:
            # Own the newly created descriptor before opening the source so a
            # disappearing input cannot leave it open in a longer process.
            with os.fdopen(descriptor, "w") as outgoing, source.open("rb") as incoming:
                os.chmod(temporary, 0o600)
                for line_number, line in enumerate(incoming, 1):
                    if not line.strip() or len(line) > 256 * 1024:
                        raise PipelineError(f"Invalid/oversized JSONL record at line {line_number}")
                    try:
                        record = json.loads(line)
                    except ValueError:
                        raise PipelineError(f"Invalid JSON at line {line_number}") from None
                    if (
                        isinstance(record, dict)
                        and isinstance(record.get("record_id"), str)
                        and record["record_id"] in record_ids
                    ):
                        raise PipelineError(f"Duplicate record_id at line {line_number}")
                    try:
                        prediction = predictor.predict(record)
                    except PipelineError as error:
                        raise PipelineError(
                            f"Inference input at line {line_number}: {error}"
                        ) from None
                    except (KeyError, TypeError, ValueError):
                        raise PipelineError(
                            f"Incompatible inference input at line {line_number}; check model contract"
                        ) from None
                    outgoing.write(json.dumps(prediction, sort_keys=True, allow_nan=False) + "\n")
                    record_ids.add(record["record_id"])
                    count += 1
                    if guard.check() or guard.thermal_limit_reached:
                        raise PipelineError("Inference resource or thermal guard stopped the run")
                if count == 0:
                    raise PipelineError("Input JSONL contains no records")
                outgoing.flush()
                os.fsync(outgoing.fileno())
            # The hard link fails atomically if another process created the
            # destination after preflight. Never replace a user artifact.
            os.link(temporary, destination)
            fsync_dir(destination.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {"records": count, "output": str(destination), "mode": "offline_shadow"}
