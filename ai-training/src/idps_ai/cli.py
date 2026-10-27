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
        key = os.environ.get(args.hmac_key_env, "").encode()
    if len(key) < 32:
        raise PipelineError(
            "Provide an independent >=32-byte training HMAC key via file/environment; never copy a service secret"
        )
    return key


def parser():
    root = argparse.ArgumentParser(prog="idps-ai")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("check-contract")
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
    collection.add_argument("--hmac-key-file")
    collection.add_argument("--hmac-key-env", default="IDPS_TRAINING_HMAC_KEY")
    prep = commands.add_parser("prepare")
    prep.add_argument("--dataset", required=True)
    prep.add_argument("--output", required=True)
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
    training.add_argument("--max-duration-minutes", type=float)
    training.add_argument("--checkpoint-every-seconds", type=float)
    training.add_argument("--max-steps", type=int)
    export = commands.add_parser("export")
    export.add_argument("--dataset", required=True)
    export.add_argument("--checkpoint", required=True)
    export.add_argument("--output", required=True)
    smoke = commands.add_parser("s0")
    smoke.add_argument("--output", required=True)
    smoke.add_argument("--campaigns", type=int, default=15)
    smoke.add_argument("--requests-per-campaign", type=int, default=64)
    for command in (collection, prep, training, export, smoke):
        command.add_argument("--max-threads", type=int)
        command.add_argument("--memory-limit-gib", type=float)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--dataset", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    from idps_ai.training.resources import configure_threads

    configure_threads(getattr(args, "max_threads", None) or 4)
    try:
        check_contract()
        if args.command == "check-contract":
            result = check_contract()
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
                args.max_threads if args.max_threads is not None else 4,
                args.memory_limit_gib if args.memory_limit_gib is not None else 12,
            ):
                result = collect(inputs, args.output, key_from_args(args), args.labels)
        elif args.command == "prepare":
            from idps_ai.data.split import prepare
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(
                args.max_threads if args.max_threads is not None else 4,
                args.memory_limit_gib if args.memory_limit_gib is not None else 12,
            ):
                result = prepare(
                    args.dataset,
                    args.output,
                    args.labels,
                    key_from_args(args) if args.labels else None,
                )
        elif args.command == "train":
            import yaml

            from idps_ai.training.runner import train

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
                else envelope.get("max_threads", 4),
                memory_limit_gib=args.memory_limit_gib
                if args.memory_limit_gib is not None
                else envelope.get("memory_limit_gib", 12),
                checkpoint_every_seconds=args.checkpoint_every_seconds
                if args.checkpoint_every_seconds is not None
                else envelope.get("checkpoint_every_seconds", 300),
                max_steps=args.max_steps,
            )
        elif args.command == "export":
            from idps_ai.export.onnx import export_bundle
            from idps_ai.training.resources import resource_envelope

            with resource_envelope(
                args.max_threads if args.max_threads is not None else 2,
                args.memory_limit_gib if args.memory_limit_gib is not None else 12,
            ) as (_, resources):
                result = export_bundle(
                    args.dataset, args.checkpoint, args.output, resources["max_threads"]
                )
        elif args.command == "s0":
            from idps_ai.smoke import run_s0

            result = run_s0(
                args.output,
                args.campaigns,
                args.requests_per_campaign,
                args.max_threads if args.max_threads is not None else 2,
                args.memory_limit_gib if args.memory_limit_gib is not None else 12,
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
