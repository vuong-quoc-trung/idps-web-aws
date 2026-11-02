#!/usr/bin/env python3
"""Preregister and collect request-bound evidence on an AI-owned loopback lab."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data import evidence_campaign
from idps_ai.data.evidence_campaign import (
    audit_capture_set,
    collect,
    create_plan,
    verify_capture,
    verify_three_source_capture,
)
from idps_ai.data.snapshot import new_destination
from idps_ai.training.resources import resource_envelope


def _faculty_count(lab):
    marker = load_json(Path(lab) / "owned-lab.json")
    container = marker.get("database_container", "")
    if marker.get("purpose") != "ai-pretrain-disposable" or not container.startswith(
        "idps-ai-pretrain-"
    ):
        raise PipelineError("Application oracle requires the owned disposable DB")
    owner = subprocess.run(
        ["docker", "inspect", "--format", '{{ index .Config.Labels "idps.owner" }}', container],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if owner.returncode or owner.stdout.strip() != "ai-pretrain":
        raise PipelineError("Application oracle DB ownership label is missing")
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "ai_student_lab",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT count(*) FROM faculties WHERE short_code='GTPILOT01' "
            "AND faculty_name='Ground Truth Pilot' AND active=true",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode or result.stdout.strip() not in ("0", "1"):
        raise PipelineError("Owned application DB oracle query failed or was ambiguous")
    return int(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--output", required=True)
    plan.add_argument("--seeds", nargs="+", type=int, required=True)
    plan.add_argument(
        "--profile",
        choices=("legacy", "novel-v2", "gt-pilot-v1", "dev-oracle-v1"),
        default="legacy",
    )
    plan.add_argument("--exclude-plan", action="append", default=[])
    capture = sub.add_parser("collect")
    capture.add_argument("--plan", required=True)
    capture.add_argument("--lab", required=True)
    capture.add_argument("--output", required=True)
    capture.add_argument("--protocol-approval")
    capture.add_argument("--trusted-reviewer-key")
    signing = sub.add_parser("sign-protocol")
    signing.add_argument("--plan", required=True)
    signing.add_argument("--reviewer-id", required=True)
    signing.add_argument("--private-key", required=True)
    signing.add_argument("--trusted-reviewer-key", required=True)
    signing.add_argument("--output", required=True)
    approval_check = sub.add_parser("verify-protocol")
    approval_check.add_argument("--plan", required=True)
    approval_check.add_argument("--approval", required=True)
    approval_check.add_argument("--trusted-reviewer-key", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--plan", required=True)
    check.add_argument("--lab", required=True)
    check.add_argument("--capture", required=True)
    check.add_argument("--collector-source")
    lineage = sub.add_parser("audit-captures")
    lineage.add_argument(
        "--spec",
        nargs=4,
        action="append",
        required=True,
        metavar=("PLAN", "LAB", "CAPTURE", "COLLECTOR_SOURCE"),
    )
    lineage.add_argument("--output", required=True)
    lineage.add_argument("--historical-student-log", action="append", default=[])
    three = sub.add_parser("collect-three-source")
    three.add_argument("--plan", required=True)
    three.add_argument("--output", required=True)
    three.add_argument("--nginx-bin", required=True)
    three.add_argument("--suricata-runtime", required=True)
    three.add_argument("--protocol-approval")
    three.add_argument("--trusted-reviewer-key")
    stage = sub.add_parser("stage-protocol")
    for option in (
        "plan",
        "lab",
        "capture",
        "review",
        "three-source",
        "approval",
        "trusted-reviewer-key",
        "output",
    ):
        stage.add_argument("--" + option, required=True)
    stage.add_argument("--collector-source")
    stage.add_argument("--application-oracle")
    args = parser.parse_args()
    source = Path(evidence_campaign.__file__)
    try:
        if args.command == "plan":
            if args.profile == "dev-oracle-v1":
                from idps_ai.data.dev_oracle_pilot import create_development_plan

                if args.seeds != [901] or args.exclude_plan:
                    raise PipelineError(
                        "Dev oracle pilot requires exactly seed 901 and no exclusions"
                    )
                result = create_development_plan(args.output)
            else:
                result = create_plan(
                    args.output, source, args.seeds, args.profile, args.exclude_plan
                )
        elif args.command == "sign-protocol":
            from idps_ai.data.protocol_ground_truth import sign_protocol_in_private_terminal

            result = sign_protocol_in_private_terminal(
                Path(args.plan) / "plan.json",
                args.reviewer_id,
                args.private_key,
                args.trusted_reviewer_key,
                args.output,
            )
        elif args.command == "verify-protocol":
            from idps_ai.data.protocol_ground_truth import verify_signed_protocol

            result = verify_signed_protocol(
                Path(args.plan) / "plan.json",
                args.approval,
                args.trusted_reviewer_key,
                require_current_collector=True,
            )
        elif args.command == "collect":
            if (
                load_json(Path(args.plan) / "plan.json").get("case_profile")
                == "dev-oracle-observation-v1"
            ):
                raise PipelineError("Development oracle needs collect-three-source")
            with resource_envelope(2, 2):
                result = collect(
                    args.plan,
                    args.lab,
                    args.output,
                    source,
                    args.protocol_approval,
                    args.trusted_reviewer_key,
                )
        elif args.command == "verify":
            with resource_envelope(2, 2):
                result = verify_capture(
                    args.plan,
                    args.lab,
                    args.capture,
                    Path(args.collector_source) if args.collector_source else source,
                )
        elif args.command == "collect-three-source":
            from idps_ai.data.lab_runtime import start_lab, stop_lab, verify_lab_cleanup
            from idps_ai.data.sensor_decode import decode_pcap
            from idps_ai.data.sensor_lab import capture_lab

            plan_data = load_json(Path(args.plan) / "plan.json")
            gt_pilot = plan_data.get("case_profile") == "gt-pilot-v1"
            dev_oracle = plan_data.get("case_profile") == "dev-oracle-observation-v1"
            if gt_pilot:
                from idps_ai.data.protocol_ground_truth import verify_signed_protocol

                if not args.protocol_approval or not args.trusted_reviewer_key:
                    raise PipelineError("GT pilot needs a signed independent pre-capture protocol")
                verify_signed_protocol(
                    Path(args.plan) / "plan.json",
                    args.protocol_approval,
                    args.trusted_reviewer_key,
                    require_current_collector=True,
                )
            elif args.protocol_approval or args.trusted_reviewer_key:
                raise PipelineError("Protocol approval only applies to the GT pilot profile")
            if dev_oracle:
                from idps_ai.data.dev_oracle_pilot import (
                    SOURCE as DEV_SOURCE,
                )
                from idps_ai.data.dev_oracle_pilot import (
                    verify_development_observation,
                    verify_development_plan,
                )

                source = DEV_SOURCE
                verify_development_plan(Path(args.plan) / "plan.json", source)

            root = new_destination(args.output)
            if any(
                len(os.fsencode(str(root / socket))) >= 108
                for socket in ("lab/student.sock", "eve/eve.sock")
            ):
                raise PipelineError("Three-source output path is too long for Unix sockets")
            root.mkdir(mode=0o700)
            lab = root / "lab"
            with resource_envelope(4, 12):
                start_lab(lab, args.nginx_bin, campaigns=15, input_profile="safe_query_numeric_v2")
                try:
                    before = _faculty_count(lab) if gt_pilot or dev_oracle else None
                    if (gt_pilot or dev_oracle) and before != 0:
                        raise PipelineError("GT pilot faculty marker already exists before capture")
                    if gt_pilot or dev_oracle:
                        atomic_json(
                            root / "application-oracle-before.json",
                            {
                                "format_version": 1,
                                "kind": "ai_owned_dev_db_pre_capture_observation"
                                if dev_oracle
                                else "ai_owned_lab_db_pre_capture_observation",
                                "plan_sha256": plan_data["plan_sha256"],
                                "approval_file_sha256": file_sha256(args.protocol_approval)
                                if gt_pilot
                                else None,
                                "marker": "GTPILOT01",
                                "before_count": before,
                                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    capture_lab(
                        lab,
                        evidence_plan=args.plan,
                        evidence_output=root / "capture",
                        collector_source=source,
                        protocol_approval=args.protocol_approval,
                        trusted_reviewer_key=args.trusted_reviewer_key,
                        development_oracle=dev_oracle,
                    )
                    if gt_pilot or dev_oracle:
                        after = _faculty_count(lab)
                        with (root / "capture/pending-evidence.jsonl").open() as stream:
                            rows = [json.loads(line) for line in stream]
                        created = [row for row in rows if row.get("case_id") == "faculty_create"]
                        if len(created) != 1:
                            raise PipelineError(
                                "GT pilot application oracle cannot bind one create request"
                            )
                        atomic_json(
                            root / "application-oracle.json",
                            {
                                "format_version": 1,
                                "kind": "ai_owned_dev_db_state_transition"
                                if dev_oracle
                                else "application_db_state_transition",
                                "observer": "ai_owned_lab_collector_read_only_query",
                                "capture_report_sha256": file_sha256(root / "capture/report.json"),
                                "request_id": created[0]["request_id"],
                                "marker": "GTPILOT01",
                                "before_file_sha256": file_sha256(
                                    root / "application-oracle-before.json"
                                ),
                                "before_count": before,
                                "after_count": after,
                                "observed_http_status_code": created[0]["status_code"],
                                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                                "result": "expected_benign_create_persisted"
                                if after == 1 and created[0]["status_code"] == 201
                                else "state_transition_not_verified",
                                "attack_exploit_outcome": "unknown",
                                "exploit_outcome": "unknown",
                            },
                        )
                finally:
                    stop_lab(lab)
                atomic_json(root / "cleanup-verification.json", verify_lab_cleanup(lab))
                decode_pcap(
                    lab / "traffic.pcap",
                    root / "eve",
                    args.suricata_runtime,
                    query_numeric=True,
                    query_version=2,
                )
                result = verify_three_source_capture(
                    args.plan, lab, root / "capture", root / "eve", source, root / "correlated"
                )
                if dev_oracle:
                    result = verify_development_observation(
                        args.plan, root, root / "oracle-verification"
                    )
        elif args.command == "stage-protocol":
            from idps_ai.data.protocol_ground_truth import stage_protocol_matches

            with resource_envelope(2, 2):
                result = stage_protocol_matches(
                    args.plan,
                    args.lab,
                    args.capture,
                    args.review,
                    args.collector_source or source,
                    args.three_source,
                    args.approval,
                    args.trusted_reviewer_key,
                    args.output,
                    args.application_oracle,
                )
        else:
            with resource_envelope(2, 2):
                result = audit_capture_set(args.spec, args.output, args.historical_student_log)
        print(json.dumps(result, sort_keys=True))
    except PipelineError as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
