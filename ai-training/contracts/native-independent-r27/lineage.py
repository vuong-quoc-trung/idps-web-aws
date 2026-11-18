"""Task/ABI-scoped closure, retaining rejected targets and raw setup custody.

Structural disjointness is not a certificate of independent population sampling.
T07 final-confidence gates remain separate from internal research admission.
"""

from collections import defaultdict


def close(rows, protected=()):
    parent = {r["key"]: r["key"] for r in rows}
    if len(parent) != len(rows):
        raise ValueError("Duplicate physical request key")

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(a, b):
        parent[find(a)] = find(b)

    groups = defaultdict(list)
    for row in rows:
        for field in ("campaign", "session", "actor_alias", "material_template"):
            if row.get(field):
                groups[(field, row[field])].append(row["key"])
        if row["population"] == "TARGET" and row.get("primary_view_sha256"):
            groups[
                (
                    "primary_view",
                    row["task"],
                    row["ABI"],
                    row["profile"],
                    row["primary_view_sha256"],
                )
            ].append(row["key"])
        for alias in row.get("physical_aliases", []):
            groups[("physical_alias", alias)].append(row["key"])
    for keys in groups.values():
        for key in keys[1:]:
            union(keys[0], key)
    keys = set(parent)
    for row in rows:
        for other in row.get("verified_near_keys", []):
            if other not in keys:
                raise ValueError("Unresolved near lineage reference")
            union(row["key"], other)
    components = defaultdict(list)
    for row in rows:
        components[find(row["key"])].append(row)
    protected = set(protected)
    result = []
    for root, records in components.items():
        roles = {r["role"] for r in records}
        unresolved = any(
            not r.get("identity_verified") or not r.get("actor_scope_resolved") for r in records
        )
        protected_link = bool({r["key"] for r in records} & protected)
        labelgroups = defaultdict(set)
        for r in records:
            if r["population"] == "TARGET" and r.get("primary_view_sha256") and r.get("label"):
                labelgroups[(r["task"], r["ABI"], r["profile"], r["primary_view_sha256"])].add(
                    r["label"]
                )
        conflict = any(len(labels) > 1 for labels in labelgroups.values())
        reasons = []
        if len(roles) != 1:
            reasons.append("CROSS_ROLE_LINEAGE")
        if unresolved:
            reasons.append("UNRESOLVED_IDENTITY_OR_ALIAS_DOMAIN")
        if protected_link:
            reasons.append("PROTECTED_ROLE_DOMINANCE")
        if conflict:
            reasons.append("CONFLICTING_PRIMARY_VIEW_LABELS")
        result.append(
            {
                "component": root,
                "keys": sorted(r["key"] for r in records),
                "role": next(iter(roles)) if len(roles) == 1 else None,
                "target_count": sum(r["population"] == "TARGET" for r in records),
                "blocked": bool(reasons),
                "reasons": reasons,
            }
        )
    return result
