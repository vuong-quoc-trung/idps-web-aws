"""Screen existing reviewed defensive intake summaries for native TRAIN/DEV lineage."""

import argparse
import hashlib
import json
import re
import runpy
from collections import Counter
from pathlib import Path

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, digest
from idps_ai.data.http_curation import require_development_source

CONTRACTS = Path(__file__).resolve().parents[1]
close = runpy.run_path(str(CONTRACTS / "native-independent-r27/lineage.py"))["close"]
VERSION = "idps-r28-defensive-lineage-v1"
INTAKE = "idps-native-uri76-defensive-intake-v1"
ROLES = ("TRAIN", "DEV")
LABELS = ("BENIGN_VERIFIED", "ATTACK_VERIFIED")
ALL_LABELS = (*LABELS, "ATTACK_INTENT_ONLY", "UNKNOWN")
MASKS = ("N", "S", "A", "NS", "NA", "SA", "NSA", "NONE")
SHA = re.compile("[0-9a-f]{64}")
MAX_ROWS = 10_000
CLEARANCE = ("cross_domain_resolved", "near_complete", "protected_role_screen_complete")


def need(ok, reason):
    if not ok:
        raise PipelineError(reason)


def is_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def read_pin(path, expected):
    need(is_sha(expected), "INVALID_EXTERNAL_PIN")
    need(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_INPUT")
    require_development_source(path)
    need(path.is_file(), "MISSING_PINNED_FILE")
    with path.open("rb") as stream:
        raw = stream.read(16 * 1024**2 + 1)
    need(len(raw) <= 16 * 1024**2, "METADATA_BUDGET_EXCEEDED")
    need(hashlib.sha256(raw).hexdigest() == expected, "PIN_MISMATCH")
    return json.loads(raw)


def protected_registry():
    # R27 published this pin separately from the private registry.
    handoff = json.loads((CONTRACTS / "native-independent-r27/r27-evidence.json").read_text())
    name = "native-source-role-registry.json"
    pin = handoff["evidence_sha256"][name]
    registry = read_pin(REPO_ROOT / handoff["artifact_root"] / name, pin)
    need(
        registry["version"] == "idps-r27-native-source-role-registry-v1"
        and registry["DEV_protected_from_future_TRAIN"] is True,
        "R27_PROTECTION_INVALID",
    )
    return pin, {
        row["request_key"] for row in registry["canonical"].values() if row["role"] == "DEV"
    }


def screen(plan, plan_sha, audit, bundles, registry_sha, protected_keys):
    """Use only pinned audit summaries; never read, dispatch or score HTTP."""
    need(
        plan["version"] == VERSION
        and plan["task"] == "ATTACK_INTENT"
        and plan["scope"] == "EXISTING_DEFENSIVE_CAPTURE"
        and plan["cutoff_ns"] == 1_000_000_000
        and plan["guard_ns"] == 1_000_000
        and all(
            is_sha(plan[key]) for key in ("population_sha256", "sampling_sha256", "profile_sha256")
        ),
        "INVALID_LOCKED_PLAN",
    )
    roles = plan["campaign_roles"]
    need(
        isinstance(roles, dict) and roles and set(roles.values()) <= set(ROLES),
        "ONLY_LOCKED_TRAIN_DEV_ROLES_SUPPORTED",
    )
    need(
        audit["version"] == VERSION
        and audit["plan_sha256"] == plan_sha
        and audit["r27_registry_sha256"] == registry_sha
        and audit["profile_sha256"] == plan["profile_sha256"]
        and 0 < len(bundles) <= 8
        and set(audit["intake_sha256"]) == set(bundles),
        "LINEAGE_INPUT_BINDING_MISMATCH",
    )

    rows, scopes, receipt_pins = {}, set(), set()
    label_counts, masks = Counter(), Counter()
    lineage = audit["rows"]
    aliases_seen, duplicate_alias_keys = {}, set()
    for bundle in bundles.values():
        campaign, boot_scope = bundle["campaign"], bundle["boot_scope"]
        scope = (campaign, boot_scope)
        need(
            bundle["version"] == INTAKE
            and bundle["source_role"] in ("DEVELOPMENT", "TRAIN_RESEARCH_CANDIDATE_QUARANTINED")
            and campaign in roles
            and (bundle["source_role"] != "DEVELOPMENT" or roles[campaign] == "DEV")
            and isinstance(boot_scope, str)
            and boot_scope
            and scope not in scopes
            and all(
                is_sha(bundle[key])
                for key in ("manifest_sha256", "review_sha256", "receipts_sha256")
            )
            and bundle["receipts_sha256"] not in receipt_pins,
            "DUPLICATE_SCOPE_OR_INELIGIBLE_INTAKE",
        )
        scopes.add(scope)
        receipt_pins.add(bundle["receipts_sha256"])
        for record in bundle["requests"]:
            key = record["request_key"]
            need(
                len(rows) < MAX_ROWS and is_sha(key) and key not in rows and key in lineage,
                "INCOMPLETE_OR_DUPLICATE_REQUEST_ROSTER",
            )
            label, mask = record["label"], record["mask"]
            view = record["uri76_sha256_at_cutoff"]
            need(
                label in ALL_LABELS
                and mask in MASKS
                and (view is None or is_sha(view))
                and is_sha(record["receipt_sha256"])
                and record["disposition"] in ("REVIEW_FOR_LINEAGE", "QUARANTINE"),
                "INVALID_REVIEWED_RECEIPT_SUMMARY",
            )
            linked = lineage[key]
            need(
                linked["receipt_sha256"] == record["receipt_sha256"]
                and is_sha(linked["material_template"])
                and is_sha(linked["session"])
                and (linked["actor_alias"] is None or is_sha(linked["actor_alias"]))
                and type(linked["actor_scope_resolved"]) is bool
                and type(linked["protected_overlap"]) is bool
                and isinstance(linked["physical_aliases"], list)
                and all(is_sha(alias) for alias in linked["physical_aliases"])
                and isinstance(linked["verified_near_keys"], list)
                and all(is_sha(other) for other in linked["verified_near_keys"]),
                "INVALID_REQUEST_LINEAGE_EVIDENCE",
            )
            aliases = set(linked["physical_aliases"]) | {key}
            for alias in aliases:
                other = aliases_seen.setdefault(alias, key)
                if other != key:
                    duplicate_alias_keys.update((key, other))
            if linked["protected_overlap"] or aliases & protected_keys:
                protected_keys = protected_keys | {key}
            rows[key] = {
                "key": key,
                "role": roles[campaign],
                "campaign": campaign,
                "population": "TARGET",
                "task": plan["task"],
                "ABI": "URI76",
                "profile": plan["profile_sha256"],
                "primary_view_sha256": view,
                "label": label if label in LABELS else None,
                "identity_verified": True,
                "actor_scope_resolved": linked["actor_scope_resolved"],
                "material_template": linked["material_template"],
                "session": linked["session"],
                "actor_alias": linked["actor_alias"],
                "physical_aliases": aliases,
                "verified_near_keys": linked["verified_near_keys"],
                "eligible": (
                    record["disposition"] == "REVIEW_FOR_LINEAGE"
                    and label in LABELS
                    and view is not None
                    and mask != "NONE"
                ),
            }
            label_counts[label] += 1
            masks[mask] += 1
    need(rows and set(rows) == set(lineage), "INCOMPLETE_OR_DUPLICATE_REQUEST_ROSTER")
    need(
        all(set(row["verified_near_keys"]) <= rows.keys() for row in rows.values()),
        "UNRESOLVED_NEAR_EDGE",
    )

    missing = [name for name in CLEARANCE if audit.get(name) is not True]
    components = close(list(rows.values()), protected=protected_keys)
    canonical = {role: set() for role in ROLES}
    counts = {role: Counter(dict.fromkeys(LABELS, 0)) for role in ROLES}
    reasons = Counter()
    for component in components:
        if duplicate_alias_keys.intersection(component["keys"]):
            component["reasons"].append("DUPLICATE_PHYSICAL_ALIAS")
        component["blocked"] = bool(component["reasons"] or missing)
        reasons.update(component["reasons"])
        if component["blocked"]:
            continue
        for key in component["keys"]:
            row = rows[key]
            if row["eligible"]:
                role = row["role"]
                label = row["label"]
                canonical_key = (row["primary_view_sha256"], label)
                if canonical_key not in canonical[role]:
                    canonical[role].add(canonical_key)
                    counts[role][label] += 1
    both_classes = all(counts[role][label] for role in ROLES for label in LABELS)
    return {
        "version": VERSION,
        "state": "ELIGIBLE_FOR_CONTRACT_REVIEW" if both_classes else "BLOCKED",
        "next_gate": "T02_NATIVE_EXPORT_AND_T07_ADMISSION",
        "scope": "EXISTING_REVIEWED_DEVELOPMENT_METADATA",
        "request_count": len(rows),
        "labels_before_lineage": dict(label_counts),
        "native_masks": dict(masks),
        "candidate_unique_views_by_role_and_class": {role: dict(c) for role, c in counts.items()},
        "missing_clearance": missing,
        "blocked_component_reasons": dict(reasons),
        "structural_components": len(components),
        "components": sorted(components, key=lambda entry: entry["keys"]),
        "formal_canonical_counts": dict.fromkeys(("TRAIN", "DEV", "CAL_FIT", "CAL_OP", "TEST"), 0),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", nargs=2, required=True, metavar=("FILE", "SHA256"))
    parser.add_argument("--lineage", nargs=2, required=True, metavar=("FILE", "SHA256"))
    parser.add_argument(
        "--intake", nargs=2, required=True, action="append", metavar=("FILE", "SHA256")
    )
    args = parser.parse_args()
    need(not args.output.exists() and not args.output.is_symlink(), "REQUIRE_NEW_OUTPUT")
    need(1 <= len(args.intake) <= 8, "INTAKE_COUNT_BUDGET")
    plan, audit = [read_pin(Path(path), pin) for path, pin in (args.plan, args.lineage)]
    bundles = {pin: read_pin(Path(path), pin) for path, pin in args.intake}
    need(len(bundles) == len(args.intake), "REPEATED_INTAKE")
    report = screen(plan, args.plan[1], audit, bundles, *protected_registry())
    report["provenance_sha256"] = {
        "plan": args.plan[1],
        "lineage": args.lineage[1],
        "intake": sorted(bundles),
    }
    report["report_content_sha256"] = digest(report)
    atomic_json(args.output, report)


if __name__ == "__main__":
    main()
