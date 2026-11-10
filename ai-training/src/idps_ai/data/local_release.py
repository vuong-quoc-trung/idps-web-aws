"""Finite local-release rules, separate from the immutable100K admission policy."""

import hashlib

NEW_WINDOWS = ((49964, 99964), (1098539, 1148539))
OLD_WINDOWS = ((0, 49964), (1048576, 1098539))


def verify_windows(windows=NEW_WINDOWS):
    assert sum(b - a for a, b in windows) == 100000
    assert all(0 <= a < b <= 1924461 for a, b in windows)
    assert all(max(a, c) >= min(b, d) for a, b in windows for c, d in OLD_WINDOWS)
    assert all(
        max(a, c) >= min(b, d) for i, (a, b) in enumerate(windows) for c, d in windows[i + 1 :]
    )
    return windows


def role_for_component(minimum_row, contains_old, seed=17):
    # Recovered old rows are TRAIN-only. Never turn exposed/recovered old rows
    # into new evaluation; joined new rows inherit that entire component's role.
    if contains_old:
        return "TRAIN"
    bucket = (
        int.from_bytes(
            hashlib.sha256(f"local200k-v1:{seed}:{minimum_row}".encode()).digest()[:8], "big"
        )
        % 100
    )
    return "TRAIN" if bucket < 70 else "CALIBRATION" if bucket < 85 else "EVALUATION"


def requalified_reasons(original, *, candidate, exact_protected, legacy_near, new_heldout):
    reasons = set(original)
    if candidate and not exact_protected and not legacy_near and not new_heldout:
        reasons.discard("PROTECTED_EXISTING_TEMPLATE_VIEW_OR_ROUTE")
    if legacy_near:
        reasons.add("PROTECTED_LEGACY_HELDOUT_NEAR")
    if new_heldout:
        reasons.add("PROTECTED_COMPLETED_PILOT_HOLDOUT")
    return sorted(reasons)
