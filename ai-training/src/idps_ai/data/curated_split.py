"""Conservative grouped development assembly; no future role promotion.

A physical record keeps its proposed temporal/campaign role. If a related group
or model view spans roles, retain only its earliest-role observations and record
later exclusions. Contradictory vector labels quarantine every member. This is
research admission for publisher/runner annotations, never production labeling.
"""

import json
import math
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.data.dataset import write_rows
from idps_ai.data.request_corpus import SCHEMA, assemble_requests
from idps_ai.data.snapshot import new_destination
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import validate_numbers

ROLES = ("train", "calibration", "val")
DECISIONS = pa.schema(
    [
        ("event_key", pa.string()),
        ("source_id", pa.string()),
        ("proposed_split", pa.string()),
        ("group_key", pa.string()),
        ("feature_key", pa.string()),
        ("model_key", pa.string()),
        ("original_label", pa.int8()),
        ("decision", pa.string()),
        ("reasons", pa.list_(pa.string())),
    ]
)


def assemble_curated(
    records,
    output,
    provenance,
    min_sources=2,
    embargo_seconds=300,
    cap_per_source_role=None,
    minimum_class_rows=1,
):
    if not 1 <= min_sources <= 16 or embargo_seconds < 300 or not 1 <= minimum_class_rows <= 1024:
        raise PipelineError("Invalid research admission source/embargo policy")
    output = new_destination(output)
    caps = cap_per_source_role or {"train": 60000, "calibration": 10000, "val": 10000}
    if set(caps) != set(ROLES) or any(not 1 <= v <= 100000 for v in caps.values()):
        raise PipelineError("Explicit bounded pilot caps required")
    with tempfile.TemporaryDirectory(prefix=".curated-assembly-", dir=output.parent) as temporary:
        work = Path(temporary)
        db = sqlite3.connect(work / "index.sqlite")
        db.execute("PRAGMA cache_size=-32768")
        db.execute("PRAGMA temp_store=FILE")
        db.executescript("""CREATE TABLE r(id TEXT PRIMARY KEY,s TEXT,p INT,g TEXT,rel TEXT,t REAL,y INT,f TEXT,k TEXT,m TEXT);
        CREATE TABLE vectors(k TEXT PRIMARY KEY,n TEXT);CREATE INDEX rg ON r(g);CREATE INDEX rr ON r(rel);CREATE INDEX rm ON r(m);""")
        spec = bounded_spec()
        count = 0
        for r in records:
            if (
                r.get("proposed_split") not in ROLES
                or r.get("label") not in (0, 1)
                or r.get("timestamp") is None
                or not math.isfinite(r["timestamp"])
            ):
                raise PipelineError(
                    "Only structurally admitted known-label/time requests may be assembled"
                )
            validate_numbers(r["numbers"])
            k = digest(r["numbers"])
            m = digest(encode_request(spec, r["numbers"]).tolist())
            db.execute(
                "INSERT OR IGNORE INTO vectors VALUES(?,?)",
                (k, json.dumps(r["numbers"], sort_keys=True, separators=(",", ":"))),
            )
            try:
                db.execute(
                    "INSERT INTO r VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        r["event_key"],
                        r["source_id"],
                        ROLES.index(r["proposed_split"]),
                        r["group_key"],
                        r.get("related_key", r["group_key"]),
                        r["timestamp"],
                        r["label"],
                        r.get("attack_family"),
                        k,
                        m,
                    ),
                )
            except sqlite3.IntegrityError:
                raise PipelineError(
                    "Duplicate physical request identity across source shards"
                ) from None
            count += 1
            if count % 4096 == 0:
                db.commit()
        db.commit()
        db.executescript("""CREATE TABLE groups AS SELECT g,min(p) p FROM r GROUP BY g;CREATE UNIQUE INDEX gg ON groups(g);
        CREATE TABLE related AS SELECT rel,min(p) p FROM r GROUP BY rel;CREATE UNIQUE INDEX rl ON related(rel);
        CREATE TABLE views AS SELECT m,min(p) p,max(y=0) z,max(y=1) o FROM r GROUP BY m;CREATE UNIQUE INDEX vm ON views(m);
        CREATE TABLE admitted(id TEXT PRIMARY KEY);""")
        decisions = Counter()
        reasons_count = Counter()

        def ledger():
            q = """SELECT r.*,groups.p,related.p,views.p,views.z,views.o FROM r JOIN groups USING(g) JOIN related USING(rel) JOIN views USING(m) ORDER BY id"""
            for id, s, p, g, rel, t, y, f, k, m, gp, rp, vp, z, o in db.execute(q):
                reasons = []
                if z and o:
                    reasons.append("cross_source_model_view_label_conflict")
                if p != gp or p != rp:
                    reasons.append("related_group_cross_partition")
                if p != vp:
                    reasons.append("model_view_cross_partition")
                decision = "quarantine" if reasons else "accepted_research"
                decisions[decision] += 1
                reasons_count.update(reasons)
                if not reasons:
                    db.execute("INSERT INTO admitted VALUES(?)", (id,))
                yield dict(
                    event_key=id,
                    source_id=s,
                    proposed_split=ROLES[p],
                    group_key=g,
                    feature_key=k,
                    model_key=m,
                    original_label=y,
                    decision=decision,
                    reasons=reasons,
                )

        write_rows(work / "split-decisions.parquet", ledger(), DECISIONS)
        db.commit()
        totals = Counter()
        source_roles = Counter()
        positive_sources = set()
        benign_sources = set()
        times = defaultdict(lambda: defaultdict(list))

        def accepted():
            q = """SELECT r.*,vectors.n FROM r JOIN admitted USING(id) JOIN vectors USING(k) ORDER BY s,p,id"""
            for id, s, p, g, rel, t, y, f, k, m, n in db.execute(q):
                totals[ROLES[p]] += 1
                source_roles[(s, ROLES[p], y)] += 1
                if p == 0:
                    (positive_sources if y else benign_sources).add(s)
                times[s][ROLES[p]].append(t)
                yield dict(
                    event_key=id,
                    source_id=s,
                    group_key=g,
                    split=ROLES[p],
                    label=y,
                    evaluation_label=y,
                    attack_family=f,
                    visibility="structurally_curated; publisher_or_runner_annotation; no independent humanreview",
                    feature_key=k,
                    timestamp=t,
                    numeric_json=n,
                )

        write_rows(work / "full-curated.parquet", accepted(), SCHEMA)
        gaps = {}
        failed = []
        for source, roles in times.items():
            gaps[source] = {}
            if not all(role in roles for role in ROLES):
                failed.append("source_role_coverage")
            for a, b in zip(ROLES, ROLES[1:]):
                if a in roles and b in roles:
                    gap = min(roles[b]) - max(roles[a])
                    gaps[source][a + "->" + b] = gap
                    if gap < embargo_seconds:
                        failed.append("temporal_embargo")
        if len(positive_sources) < min_sources or len(benign_sources) < min_sources:
            failed.append("multisource_class_support")
        for role in ROLES:
            if not all(
                sum(n for (s, p, y), n in source_roles.items() if p == role and y == label) > 0
                for label in [0, 1]
            ):
                failed.append("binary_role_coverage")
        for source in times:
            for role in ROLES:
                if not all(source_roles[(source, role, label)] > 0 for label in (0, 1)):
                    failed.append("source_role_class_coverage")
                if any(
                    source_roles[(source, role, label)] < minimum_class_rows for label in (0, 1)
                ):
                    failed.append("source_role_minimum_support")
        cross_vectors = db.execute(
            "SELECT count(*) FROM (SELECT m FROM r JOIN admitted USING(id) GROUP BY m HAVING count(DISTINCT p)>1)"
        ).fetchone()[0]
        cross_groups = db.execute(
            "SELECT count(*) FROM (SELECT g FROM r JOIN admitted USING(id) GROUP BY g HAVING count(DISTINCT p)>1)"
        ).fetchone()[0]
        if cross_vectors or cross_groups:
            failed.append("cross_partition_overlap")
        admission = {
            "policy_version": "curated-development-1",
            "research_training_permitted": not failed,
            "formal_training_permitted": False,
            "production_admitted": False,
            "failed_gates": sorted(set(failed)),
            "cross_partition_model_vectors": cross_vectors,
            "cross_partition_groups": cross_groups,
            "embargo_seconds": embargo_seconds,
            "per_source_temporal_gaps_seconds": gaps,
            "positive_training_sources": sorted(positive_sources),
            "benign_training_sources": sorted(benign_sources),
            "label_basis": "Original publisher/runner annotations after structural gates, not independent humanreview",
            "source_day_sessions_not_persistent_client_holdout": True,
            "corpus_role": "development_exposed",
            "new_final_holdout_used": False,
            "input_records": count,
            "decisions": dict(decisions),
            "reason_counts_overlapping": dict(reasons_count),
            "full_curated_rows": dict(totals),
            "full_source_role_labels": [
                dict(source=s, split=p, label=y, rows=n)
                for (s, p, y), n in sorted(source_roles.items())
            ],
            "pilot_cap_per_source_role": caps,
            "minimum_records_per_source_role_class": minimum_class_rows,
            "selection": "Lexical HMACeventid order within each source/role; independent of label/prediction; not newHTTP",
        }
        unique_support = {
            (s, ROLES[p], y): n
            for s, p, y, n in db.execute(
                "SELECT s,p,y,count(DISTINCT m) FROM r JOIN admitted USING(id) GROUP BY s,p,y"
            )
        }
        if any(
            unique_support.get((s, role, y), 0) < minimum_class_rows
            for s in times
            for role in ROLES
            for y in (0, 1)
        ):
            admission["failed_gates"] = sorted(
                set(admission["failed_gates"]) | {"source_role_unique_view_support"}
            )
            admission["research_training_permitted"] = False
        admission["minimum_unique_model_views_per_source_role_class"] = minimum_class_rows
        admission["unique_model_views_by_source_role_label"] = [
            dict(source=s, split=p, label=y, views=n)
            for (s, p, y), n in sorted(unique_support.items())
        ]
        preview = Counter()
        preview_labels = Counter()
        for s, p, y in db.execute("SELECT s,p,y FROM r JOIN admitted USING(id) ORDER BY s,p,id"):
            if preview[(s, p)] < caps[ROLES[p]]:
                preview[(s, p)] += 1
                preview_labels[(ROLES[p], y)] += 1
        # The shared legacy assembler needs benign train rows even for fixed encoders.
        # Retain NOT_READY evidence if the label-blind cap removes all benign rows.
        empty_benign_train = preview_labels[("train", 0)] == 0
        if empty_benign_train:
            admission["failed_gates"] = sorted(
                set(admission["failed_gates"]) | {"pilot_source_role_support"}
            )
            admission["research_training_permitted"] = False
        atomic_json(work / "admission.json", admission)
        if empty_benign_train or any(totals.get(role, 0) == 0 for role in ROLES):
            # Still retain a complete traceable NOT_READY result; never fabricate a missing split.
            import shutil

            output.mkdir(mode=0o700)
            for f in ["admission.json", "split-decisions.parquet", "full-curated.parquet"]:
                shutil.copy2(work / f, output / f)
            return {"admission": admission, "dataset_sha256": None}
        selected_counts = Counter()

        def pilot_records():
            q = """SELECT r.*,vectors.n FROM r JOIN admitted USING(id) JOIN vectors USING(k) ORDER BY s,p,id"""
            for id, s, p, g, rel, t, y, f, k, m, n in db.execute(q):
                if selected_counts[(s, p)] >= caps[ROLES[p]]:
                    continue
                selected_counts[(s, p)] += 1
                yield dict(
                    event_key=id,
                    source_id=s,
                    group_key=g,
                    split=ROLES[p],
                    label=y,
                    evaluation_label=y,
                    attack_family=f,
                    timestamp=t,
                    visibility="curateddevelopment; originalannotations",
                    numbers=json.loads(n),
                )

        result = assemble_requests(
            pilot_records(),
            output,
            {
                "curated_admission_sha256": file_sha256(work / "admission.json"),
                "sources": provenance,
                "source_role": "development_exposed",
                "new_HTTP_requests": 0,
                "label_policy": "noinference_or_relabel",
                "admission_file": "admission.json",
            },
            encoding="bounded-request-v1",
        )
        import shutil

        for f in ["admission.json", "split-decisions.parquet", "full-curated.parquet"]:
            shutil.copy2(work / f, output / f)
        result["admission"] = admission
        for f in ["admission.json", "split-decisions.parquet", "full-curated.parquet"]:
            result["files"][f] = file_sha256(output / f)
        result.pop("dataset_sha256", None)
        result["dataset_sha256"] = digest(result)
        atomic_json(output / "manifest.json", result)
        # Caps may remove a rare class even when the full staging pool has support.
        pilot_audit = audit_curated_partitions(output)
        admission["pilot_source_role_support"] = pilot_audit["by_source_partition_label"]
        if not pilot_audit["source_role_class_coverage"]:
            admission["failed_gates"] = sorted(
                set(admission["failed_gates"]) | {"pilot_source_role_support"}
            )
            admission["research_training_permitted"] = False
        atomic_json(output / "admission.json", admission)
        result["provenance"]["curated_admission_sha256"] = file_sha256(output / "admission.json")
        result["files"]["admission.json"] = file_sha256(output / "admission.json")
        result["admission"] = admission
        result.pop("dataset_sha256")
        result["dataset_sha256"] = digest(result)
        atomic_json(output / "manifest.json", result)
        db.close()
        return result


def audit_curated_partitions(dataset):
    """Recount the actual pilot, including its model inputs, without opening any test.

    Group IDs are provenance proxies, not independently verified attack campaigns.
    The output distinguishes row support from novel views and observed time blocks.
    """
    from idps_ai.data.dataset import iter_rows
    from idps_ai.data.http_curation import require_development_source
    from idps_ai.data.request_corpus import verify_requests

    dataset = Path(dataset)
    require_development_source(dataset)
    manifest = verify_requests(dataset)
    if "admission" not in manifest:
        raise PipelineError("Partition audit requires a bound curated admission")
    counts, families, groups = Counter(), Counter(), Counter()
    views, group_roles, view_roles = defaultdict(set), defaultdict(set), defaultdict(set)
    times = defaultdict(lambda: defaultdict(list))
    identities = set()
    for r in iter_rows(dataset / "features.parquet"):
        s, role, y, t = r["source_id"], r["split"], r["label"], r["timestamp"]
        if role not in ROLES or y not in (0, 1) or t is None or not math.isfinite(t):
            raise PipelineError("Invalid development role, label or clock")
        if r["event_key"] in identities:
            raise PipelineError("Duplicate physical request identity")
        identities.add(r["event_key"])
        m = digest(r["x"])
        counts[(s, role, y)] += 1
        families[(s, role, r["attack_family"], y)] += 1
        groups[(s, role, r["group_key"], y)] += 1
        views[(s, role, y)].add(m)
        group_roles[r["group_key"]].add(role)
        view_roles[m].add(role)
        times[s][role].append(t)
    expected = {
        (r["source"], r["split"], int(r["label"])): r["rows"]
        for r in manifest["source_partition_labels"]
    }
    if counts != expected:
        raise PipelineError("Actual pilot source/role labels differ from manifest")
    cross_groups = sum(len(p) > 1 for p in group_roles.values())
    cross_views = sum(len(p) > 1 for p in view_roles.values())
    gaps = {}
    for source, roles in times.items():
        gaps[source] = {
            a + "->" + b: min(roles[b]) - max(roles[a])
            for a, b in zip(ROLES, ROLES[1:])
            if a in roles and b in roles
        }
    leaked = (
        cross_groups
        or cross_views
        or any(
            gap < manifest["admission"]["embargo_seconds"]
            for source in gaps.values()
            for gap in source.values()
        )
    )
    floor = manifest["admission"].get("minimum_records_per_source_role_class", 1)
    deficits = [
        dict(source=s, split=p, label=y, rows=counts[(s, p, y)], unique_views=len(views[(s, p, y)]))
        for s in times
        for p in ROLES
        for y in (0, 1)
        if counts[(s, p, y)] < floor or len(views[(s, p, y)]) < floor
    ]
    return {
        "status": "NOT_READY" if leaked else "PASS",
        "scope": "technical partition audit, not independent label/campaign acceptance",
        "dataset_sha256": manifest["dataset_sha256"],
        "records": len(identities),
        "cross_partition_groups": cross_groups,
        "cross_partition_model_views": cross_views,
        "per_source_time_gaps_seconds": gaps,
        "source_role_class_coverage": not deficits,
        "support_deficits": deficits,
        "by_source_partition_label": [
            dict(
                source=s,
                split=p,
                label=y,
                rows=n,
                unique_model_views=len(views[(s, p, y)]),
                observed_groups=len({g for ss, pp, g, yy in groups if (ss, pp, yy) == (s, p, y)}),
            )
            for (s, p, y), n in sorted(counts.items())
        ],
        "by_source_partition_family": [
            dict(source=s, split=p, family=f, label=y, rows=n)
            for (s, p, f, y), n in sorted(
                families.items(), key=lambda item: tuple(str(v) for v in item[0])
            )
        ],
        "by_group": [
            dict(source=s, split=p, group=g, label=y, rows=n)
            for (s, p, g, y), n in sorted(groups.items())
        ],
        "group_semantics": "Registered campaign or source-client-day proxy; not inferred attacker identities",
        "fresh_final_test_quality_opened": False,
    }
