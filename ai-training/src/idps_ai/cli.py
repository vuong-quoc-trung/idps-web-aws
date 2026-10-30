"""Public command boundary. Resource/thread setup precedes NumPy/BLAS imports."""

import argparse
import json
import os
import sys
from pathlib import Path

from idps_ai.common import AI_ROOT, REPO_ROOT, PipelineError, file_sha256


def check_contract():
    import yaml

    contract = yaml.safe_load((AI_ROOT / "configs/schema_contract.yaml").read_text())
    if (
        file_sha256(REPO_ROOT / "contracts/canonical-event-v1.schema.json")
        != contract["canonical_schema_sha256"]
    ):
        raise PipelineError("Frozen schema changed; review the AI adapter contract")
    for name, expected in contract["protected_source_hashes"].items():
        if file_sha256(REPO_ROOT / name) != expected:
            raise PipelineError(
                "Producer/ingest contract changed; review the read-only AI adapter snapshot"
            )
    return {
        "schema_version": contract["schema_version"],
        "canonical_schema_sha256": contract["canonical_schema_sha256"],
    }


def key_from_args(args):
    if args.hmac_key_file:
        key = Path(args.hmac_key_file).read_bytes()
    else:
        key = os.environ.get(getattr(args, "hmac_key_env", "IDPS_TRAINING_HMAC_KEY"), "").encode()
    if len(key) < 32:
        raise PipelineError(
            "Provide an independent >=32-byte training HMAC key via file/environment; never copy a service secret"
        )
    return key


def parser():
    root = argparse.ArgumentParser(prog="idps-ai")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("check-contract")
    rp = commands.add_parser(
        "request-prepare", help="Verified source registry -> separate request-only corpus"
    )
    rp.add_argument("--registry", required=True)
    rp.add_argument("--output", required=True)
    rt = commands.add_parser("request-train", help="Bounded2epoch request-only research candidate")
    rt.add_argument("--dataset", required=True)
    rt.add_argument("--run-dir", required=True)
    rt.add_argument("--config", required=True)
    rt.add_argument("--epochs", type=int, choices=(1, 2), default=2)
    rt.add_argument("--resume", action="store_true")
    rt.add_argument("--max-steps", type=int)
    rt.add_argument(
        "--diagnostic-updates",
        type=int,
        choices=(100, 300),
        help="Explicit bounded learning-curve diagnostic; max180seconds",
    )
    rt.add_argument("--cpus", type=int, choices=(1, 2, 4, 8), default=4)
    re = commands.add_parser(
        "request-export", help="Strict ONNX parity and benign-only calibration"
    )
    re.add_argument("--dataset", required=True)
    re.add_argument("--checkpoint", required=True)
    re.add_argument("--output", required=True)
    re.add_argument("--cpus", type=int, choices=(1, 2, 4, 8), default=4)
    fetch = commands.add_parser("http-fetch", help="Restartable pinned public raw HTTP download")
    fetch.add_argument("--output", required=True)
    http = commands.add_parser(
        "http-import", help="Verified raw HTTP benchmark; numeric-only, no invented flow"
    )
    http.add_argument("--registry", required=True)
    http.add_argument("--output", required=True)
    assembly = commands.add_parser(
        "corpus-assemble", help="Recompute compatible numeric shards with one train-only scaler"
    )
    assembly.add_argument("--registry", required=True)
    assembly.add_argument("--output", required=True)
    diagnostic = commands.add_parser(
        "shortcut-audit", help="Train-fitted development probes; final test stays sealed"
    )
    diagnostic.add_argument("--dataset", required=True)
    diagnostic.add_argument("--output", required=True)
    challenge = commands.add_parser(
        "http-challenge", help="Frozen missing-view public HTTP stress test; no tuning"
    )
    challenge.add_argument("--benchmark", required=True)
    challenge.add_argument(
        "--bundles", required=True, help="JSON mapping names to frozen bundle directories"
    )
    challenge.add_argument("--output", required=True)
    challenge.add_argument("--cpus", type=int, default=8)
    tree = commands.add_parser("tree-baseline", help="Bounded CPU reference; no deployment")
    tree.add_argument("--dataset", required=True)
    tree.add_argument("--output", required=True)
    tree.add_argument("--cpus", type=int, default=8)
    tree.add_argument("--iterations", type=int, default=32)
    shadow = commands.add_parser(
        "shadow-replay", help="Bounded offline inference; no Web/firewall actions"
    )
    shadow.add_argument("--dataset", required=True)
    shadow.add_argument("--bundle", required=True)
    shadow.add_argument("--output", required=True)
    shadow.add_argument("--partition", choices=("train", "val"), default="val")
    shadow.add_argument("--max-requests", type=int, default=512)
    shadow.add_argument("--cpus", type=int, default=8)
    catalog = commands.add_parser(
        "corpus-audit", help="Audit immutable source shards; never generates traffic"
    )
    catalog.add_argument("--registry", default=str(AI_ROOT / "configs/scale_sources.yaml"))
    catalog.add_argument("--output", required=True)
    projection = commands.add_parser(
        "project-eve", help="Opt-in numeric-only EVE bridge; '-' streams stdio"
    )
    projection.add_argument("--input", required=True)
    projection.add_argument("--output", required=True)
    projection.add_argument("--projection-version", type=int, choices=(1, 2), default=1)
    snap = commands.add_parser("snapshot", help="Copy bounded complete-line prefixes read-only")
    snap.add_argument("--input", action="append", required=True)
    snap.add_argument(
        "--data-kind",
        choices=(
            "lab_capture",
            "local_demo",
            "production_snapshot",
            "public_benchmark",
            "synthetic",
        ),
        required=True,
    )
    snap.add_argument("--output", required=True)
    review = commands.add_parser("review-export")
    review.add_argument("--dataset", required=True)
    review.add_argument("--output", required=True)
    review.add_argument("--offset", type=int, default=0)
    review.add_argument("--limit", type=int, default=1000)
    reviewed = commands.add_parser("review-import")
    reviewed.add_argument("--review-dir", required=True)
    reviewed.add_argument("--dataset", required=True)
    reviewed.add_argument("--output", required=True)
    reviewed.add_argument("--reviewer", required=True)
    reviewed.add_argument("--hmac-key-file", required=True)
    observed = commands.add_parser("observer-labels")
    observed.add_argument("--observer", required=True)
    observed.add_argument("--capture-result", required=True)
    observed.add_argument("--output", required=True)
    observed.add_argument("--hmac-key-file", required=True)
    gate = commands.add_parser("readiness")
    gate.add_argument("--dataset", required=True)
    gate.add_argument("--data-kind", required=True)
    gate.add_argument("--provenance")
    gate.add_argument("--policy")
    gate.add_argument("--output", required=True)
    capacity = commands.add_parser("capacity-check")
    capacity.add_argument("--dataset", required=True)
    capacity.add_argument("--output", required=True)
    capacity.add_argument("--max-threads", "--cpus", dest="max_threads", type=int, default=8)
    owned = commands.add_parser("lab-start", help="Create an AI-owned disposable fixture only")
    owned.add_argument("--output", required=True)
    owned.add_argument("--nginx-bin", required=True)
    owned.add_argument("--campaigns", type=int, choices=(15, 30, 45), default=15)
    cleanup = commands.add_parser("lab-stop")
    cleanup.add_argument("--lab-dir", required=True)
    finalize = commands.add_parser("lab-finish", help="Stop the lab and prepare data; never train")
    finalize.add_argument("--lab-dir", required=True)
    finalize.add_argument("--output", required=True)
    lab = commands.add_parser(
        "lab-capture", help="Run only against an explicitly owned disposable loopback lab"
    )
    lab.add_argument("--lab-dir", required=True)
    lab.add_argument("--requests-per-campaign", type=int, default=320)
    lab.add_argument("--gap-seconds", type=int, default=620)
    sensor = commands.add_parser(
        "lab-capture-eve", help="Capture real TCP in a private rootless namespace"
    )
    sensor.add_argument("--lab-dir", required=True)
    sensor.add_argument("--campaign-seconds", type=float, default=420)
    sensor.add_argument("--requests-per-campaign", type=int, default=1280)
    decode = commands.add_parser("decode-pcap")
    decode.add_argument("--pcap", required=True)
    decode.add_argument("--runtime", required=True)
    decode.add_argument("--output", required=True)
    decode.add_argument(
        "--query-numeric", action="store_true", help="Emit the opt-in numeric query contract"
    )
    decode.add_argument("--projection-version", type=int, choices=(1, 2), default=1)
    decode.add_argument(
        "--request-structure",
        action="store_true",
        help="Separate application-neutral request projection",
    )
    synth = commands.add_parser("synthetic")
    synth.add_argument("--output", required=True)
    synth.add_argument("--campaigns", type=int, default=15)
    synth.add_argument("--requests-per-campaign", type=int, default=64)
    collection = commands.add_parser("collect")
    collection.add_argument(
        "--input",
        action="append",
        required=True,
        help="student|nginx|suricata|canonical|postgres-export=PATH",
    )
    collection.add_argument("--output", required=True)
    collection.add_argument("--labels")
    collection.add_argument(
        "--input-profile",
        choices=("native", "edge_masked_v1", "safe_query_numeric_v1", "safe_query_numeric_v2"),
        default="native",
    )
    collection.add_argument("--hmac-key-file")
    collection.add_argument("--hmac-key-env", default="IDPS_TRAINING_HMAC_KEY")
    prep = commands.add_parser("prepare")
    prep.add_argument("--dataset", required=True)
    prep.add_argument("--output", required=True)
    prep.add_argument("--behavior-dynamics", action="store_true")
    prep.add_argument("--labels")
    prep.add_argument("--hmac-key-file")
    prep.add_argument("--hmac-key-env", default="IDPS_TRAINING_HMAC_KEY")
    training = commands.add_parser("train")
    training.add_argument("--dataset", required=True)
    training.add_argument("--run-dir", required=True)
    training.add_argument("--config", default=str(AI_ROOT / "configs/train_config.yaml"))
    training.add_argument(
        "--epochs", type=int, default=20, help="Total completed-epoch target, not additional epochs"
    )
    training.add_argument("--resume-from")
    training.add_argument(
        "--readiness-report",
        help="Verify a passed dataset/source-bound offline pilot gate before fitting",
    )
    training.add_argument("--max-duration-minutes", type=float)
    training.add_argument("--checkpoint-every-seconds", type=float)
    training.add_argument("--max-steps", type=int)
    export = commands.add_parser("export")
    export.add_argument("--dataset", required=True)
    export.add_argument("--checkpoint", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--validation-only", action="store_true")
    export.add_argument("--independent-validation", action="store_true")
    smoke = commands.add_parser("s0")
    smoke.add_argument("--output", required=True)
    smoke.add_argument("--campaigns", type=int, default=15)
    smoke.add_argument("--requests-per-campaign", type=int, default=64)
    for command in (collection, prep, training, export, smoke):
        command.add_argument("--max-threads", "--cpus", dest="max_threads", type=int)
        command.add_argument("--memory-limit-gib", type=float)
    pilot = commands.add_parser("pilot")
    pilot.add_argument("--dataset", required=True)
    pilot.add_argument("--readiness-report", required=True)
    pilot.add_argument("--output", required=True)
    pilot.add_argument("--max-threads", "--cpus", dest="max_threads", type=int, default=8)
    pilot.add_argument("--include-weighted-residual", action="store_true")
    pilot.add_argument(
        "--candidate-set", choices=("baseline", "expanded", "scale"), default="baseline"
    )
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--dataset", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    from idps_ai.training.resources import configure_threads

    configure_threads(getattr(args, "max_threads", None) or 8)
    try:
        check_contract()
        if args.command == "check-contract":
            result = check_contract()
        elif args.command == "request-prepare":
            from idps_ai.data.request_corpus import prepare_request_registry
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = prepare_request_registry(args.registry, args.output)
        elif args.command == "request-train":
            import yaml

            from idps_ai.training.request_training import train_request

            result = train_request(
                args.dataset,
                args.run_dir,
                yaml.safe_load(Path(args.config).read_text()),
                args.epochs,
                args.resume,
                args.max_steps,
                args.cpus,
                args.diagnostic_updates,
            )
        elif args.command == "request-export":
            from idps_ai.training.request_training import export_request
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(args.cpus, 16):
                result = export_request(args.dataset, args.checkpoint, args.output, args.cpus)
        elif args.command == "project-eve":
            from idps_ai.data.query_numeric import project_file

            result = project_file(args.input, args.output, args.projection_version)
            if args.output == "-":
                print(json.dumps(result), file=sys.stderr)
                return 0
        elif args.command == "snapshot":
            from idps_ai.data.readers import Input
            from idps_ai.data.snapshot import snapshot

            inputs = []
            for value in args.input:
                source, separator, path = value.partition("=")
                if not separator:
                    raise PipelineError("Expected adapter=PATH")
                inputs.append(Input(source, Path(path)))
            result = snapshot(inputs, args.output, args.data_kind)
        elif args.command == "review-export":
            from idps_ai.data.review import export_review

            result = export_review(args.dataset, args.output, args.offset, args.limit)
        elif args.command == "review-import":
            from idps_ai.data.review import import_review

            result = import_review(
                args.review_dir, args.dataset, args.output, key_from_args(args), args.reviewer
            )
        elif args.command == "observer-labels":
            from idps_ai.data.provenance import observer_labels

            result = observer_labels(
                args.observer, args.capture_result, args.output, key_from_args(args)
            )
        elif args.command == "readiness":
            from idps_ai.data.readiness import audit_readiness
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = audit_readiness(
                    args.dataset, args.output, args.data_kind, args.policy, args.provenance
                )
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0 if result["offline_pilot_training_permitted"] else 3
        elif args.command == "capacity-check":
            from idps_ai.data.capacity import capacity_check

            result = capacity_check(args.dataset, args.output, args.max_threads)
        elif args.command == "lab-start":
            from idps_ai.data.lab_runtime import start_lab

            result = start_lab(args.output, args.nginx_bin, args.campaigns)
        elif args.command == "lab-stop":
            from idps_ai.data.lab_runtime import stop_lab

            result = stop_lab(args.lab_dir)
        elif args.command == "lab-finish":
            from idps_ai.data.pretrain import finish_lab
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12) as (_, resources):
                result = finish_lab(args.lab_dir, args.output, resources)
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0 if result["status"] == "READY_FOR_OFFLINE_PILOT" else 3
        elif args.command == "lab-capture":
            from idps_ai.data.lab_capture import run_campaigns

            result = run_campaigns(args.lab_dir, args.requests_per_campaign, args.gap_seconds)
        elif args.command == "lab-capture-eve":
            from idps_ai.data.sensor_lab import capture_lab
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = capture_lab(
                    args.lab_dir, args.campaign_seconds, args.requests_per_campaign
                )
        elif args.command == "decode-pcap":
            from idps_ai.data.sensor_decode import decode_pcap
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = decode_pcap(
                    args.pcap,
                    args.output,
                    args.runtime,
                    args.query_numeric,
                    args.projection_version,
                    args.request_structure,
                )
        elif args.command == "synthetic":
            from idps_ai.data.synthetic import synthetic_s0

            result = synthetic_s0(
                args.output,
                campaigns=args.campaigns,
                requests_per_campaign=args.requests_per_campaign,
            )
        elif args.command == "collect":
            from idps_ai.data.dataset import collect
            from idps_ai.data.readers import Input

            inputs = []
            for value in args.input:
                source, separator, path = value.partition("=")
                if not separator or source not in (
                    "student",
                    "nginx",
                    "suricata",
                    "canonical",
                    "postgres-export",
                ):
                    raise PipelineError("Invalid --input; expected a supported adapter=PATH")
                inputs.append(Input(source, Path(path)))
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(
                args.max_threads if args.max_threads is not None else 8,
                args.memory_limit_gib if args.memory_limit_gib is not None else 16,
            ):
                result = collect(
                    inputs,
                    args.output,
                    key_from_args(args),
                    args.labels,
                    input_profile=args.input_profile,
                )
        elif args.command == "prepare":
            from idps_ai.data.split import prepare
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(
                args.max_threads if args.max_threads is not None else 8,
                args.memory_limit_gib if args.memory_limit_gib is not None else 16,
            ):
                result = prepare(
                    args.dataset,
                    args.output,
                    args.labels,
                    key_from_args(args) if args.labels else None,
                    behavior_dynamics=args.behavior_dynamics,
                )
        elif args.command == "train":
            import yaml

            from idps_ai.training.runner import train

            if args.readiness_report:
                from idps_ai.data.capacity import validate_training_report

                validate_training_report(args.readiness_report, args.dataset)

            config = yaml.safe_load(Path(args.config).read_text())
            envelope = config.get("resources", {})
            result = train(
                args.dataset,
                args.run_dir,
                config,
                epochs=args.epochs,
                resume_from=args.resume_from,
                max_duration_minutes=args.max_duration_minutes
                if args.max_duration_minutes is not None
                else envelope.get("max_duration_minutes", 150),
                max_threads=args.max_threads
                if args.max_threads is not None
                else envelope.get("max_threads", 8),
                memory_limit_gib=args.memory_limit_gib
                if args.memory_limit_gib is not None
                else envelope.get("memory_limit_gib", 16),
                checkpoint_every_seconds=args.checkpoint_every_seconds
                if args.checkpoint_every_seconds is not None
                else envelope.get("checkpoint_every_seconds", 300),
                max_steps=args.max_steps,
            )
        elif args.command == "export":
            from idps_ai.export.onnx import export_bundle
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(
                args.max_threads if args.max_threads is not None else 8,
                args.memory_limit_gib if args.memory_limit_gib is not None else 16,
            ) as (_, resources):
                result = export_bundle(
                    args.dataset,
                    args.checkpoint,
                    args.output,
                    resources["max_threads"],
                    evaluation_partition="val" if args.validation_only else "test",
                    independent_validation=args.independent_validation,
                )
        elif args.command == "tree-baseline":
            from idps_ai.training.tree_baseline import benchmark_tree

            result = benchmark_tree(args.dataset, args.output, args.cpus, args.iterations)
        elif args.command == "shadow-replay":
            from idps_ai.inference import shadow_replay

            result = shadow_replay(
                args.dataset, args.bundle, args.output, args.partition, args.max_requests, args.cpus
            )
        elif args.command == "http-fetch":
            from idps_ai.data.http_benchmark import fetch_public_http

            result = fetch_public_http(args.output)
        elif args.command == "shortcut-audit":
            from idps_ai.training.generalization import shortcut_audit
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = shortcut_audit(args.dataset, args.output)
        elif args.command == "http-challenge":
            from idps_ai.training.generalization import external_challenge
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(args.cpus, 16):
                result = external_challenge(
                    args.benchmark,
                    json.loads(Path(args.bundles).read_text()),
                    args.output,
                    args.cpus,
                )
        elif args.command == "corpus-assemble":
            from idps_ai.data.assembly import assemble
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = assemble(args.registry, args.output)
        elif args.command == "http-import":
            import yaml

            from idps_ai.data.http_benchmark import import_http
            from idps_ai.training.resources import resource_envelope

            registry = yaml.safe_load(Path(args.registry).read_text())
            with resource_envelope(2, 12):
                result = import_http(registry["sources"], args.output, registry["provenance"])
        elif args.command == "corpus-audit":
            from idps_ai.data.corpus import audit_catalog
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(2, 12):
                result = audit_catalog(args.registry, args.output)
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0 if result["status"] == "READY_FOR_SCALE_RESEARCH" else 3
        elif args.command == "pilot":
            from idps_ai.pilot import run_pilot

            result = run_pilot(
                args.dataset,
                args.readiness_report,
                args.output,
                args.max_threads,
                include_weighted_residual=args.include_weighted_residual,
                candidate_set=args.candidate_set,
            )
        elif args.command == "s0":
            from idps_ai.smoke import run_s0

            result = run_s0(
                args.output,
                args.campaigns,
                args.requests_per_campaign,
                args.max_threads if args.max_threads is not None else 8,
                args.memory_limit_gib if args.memory_limit_gib is not None else 16,
            )
        else:
            from idps_ai.data.dataset import verify_dataset

            result = verify_dataset(args.dataset)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, MemoryError):
        # Do not echo JSON parser exceptions, raw records, credentials or DSNs.
        message = (
            str(sys.exception())
            if isinstance(sys.exception(), PipelineError)
            else "Pipeline failed: missing/incompatible input or resource limit; inspect the private run artifacts"
        )
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
