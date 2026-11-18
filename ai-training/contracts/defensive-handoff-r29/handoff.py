"""Verify a custodian-pinned bundle of R11 summaries and run the R28 lineage screen."""

import argparse
import json
import runpy
from pathlib import Path

from jsonschema import Draft202012Validator

from idps_ai.common import PipelineError, atomic_json, digest

HERE = Path(__file__).resolve().parent
CHECKS = runpy.run_path(str(HERE.parent / "native-defensive-r28/screen.py"))


def schema_check(data, kind=None):
    schema = json.loads((HERE / "handoff.schema.json").read_text())
    # Rights uses a definition as the root. Keep only the vocabulary and refs
    # shared with the envelope, so the envelope constraints don't apply twice.
    if kind:
        schema = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/" + kind,
        }
    if not Draft202012Validator(schema).is_valid(data):
        raise PipelineError("INVALID_" + (kind or "HANDOFF").upper() + "_SCHEMA")


def run(envelope_path, envelope_pin):
    read = CHECKS["read_pin"]
    envelope = read(envelope_path, envelope_pin)
    schema_check(envelope)

    def read_ref(ref):
        name = ref["file"]
        if Path(name).name != name or not name.endswith(".json"):
            raise PipelineError("HANDOFF_REFERENCE_MUST_BE_SIBLING_JSON")
        return read(envelope_path.parent / name, ref["sha256"])

    plan_ref = envelope["plan"]
    plan = read_ref(plan_ref)
    rights = read_ref(envelope["rights"])
    schema_check(rights, "rights")
    if rights["plan_sha256"] != plan_ref["sha256"]:
        raise PipelineError("RIGHTS_BOUND_TO_DIFFERENT_PLAN")
    grants = {g["manifest_sha256"]: g["role"] for g in rights["grants"]}
    if len(grants) != len(rights["grants"]):
        raise PipelineError("REPEATED_SOURCE_PERMISSION")
    audit = read_ref(envelope["lineage"])
    bundles = {ref["sha256"]: read_ref(ref) for ref in envelope["intake"]}
    manifest_roles = {
        bundle["manifest_sha256"]: plan["campaign_roles"].get(bundle["campaign"])
        for bundle in bundles.values()
    }
    if len(manifest_roles) != len(envelope["intake"]) or manifest_roles != grants:
        raise PipelineError("SOURCE_PERMISSION_OR_ROLE_NOT_GRANTED")
    protected = envelope["protected_partitions"]
    partition_pins = {partition["manifest_sha256"] for partition in protected.values()}
    if len(partition_pins) != len(protected) or partition_pins.intersection(manifest_roles):
        raise PipelineError("PROTECTED_MANIFEST_REUSE")
    result = CHECKS["screen"](
        plan, plan_ref["sha256"], audit, bundles, *CHECKS["protected_registry"]()
    )
    return {
        "version": "idps-r29-handoff-validation-v1",
        "handoff_sha256": envelope_pin,
        "plan_sha256": plan_ref["sha256"],
        "rights_sha256": envelope["rights"]["sha256"],
        "lineage_sha256": envelope["lineage"]["sha256"],
        "intake_summary_sha256": sorted(bundles),
        "protected_partitions": {
            role: "PIN_REGISTERED_AWAITING_CUSTODIAN" for role in sorted(protected)
        },
        "next_gate": "T02_NATIVE_EXPORT_AND_T07_ADMISSION",
        "development_screen": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("handoff_sha256", help="Trusted external pin for the envelope")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Require a fresh output path")
    report = run(args.handoff, args.handoff_sha256)
    report["report_content_sha256"] = digest(report)
    atomic_json(args.output, report)


if __name__ == "__main__":
    main()
