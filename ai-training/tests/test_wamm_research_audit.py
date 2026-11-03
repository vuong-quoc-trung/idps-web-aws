"""The research intake must quarantine label conflicts and never export raw HTTP."""

import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from idps_ai.common import PipelineError


def _auditor():
    path = Path(__file__).resolve().parents[1] / "scripts/audit-wamm-research.py"
    spec = importlib.util.spec_from_file_location("wamm_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wamm_intake_excludes_conflicting_views_and_raw_http(tmp_path):
    database = tmp_path / "source.db"
    db = sqlite3.connect(database)
    db.execute("CREATE TABLE combined_data (col1 TEXT, col2 TEXT)")
    conflict = "GET /private?q=1 HTTP/1.1\r\nHost: example\r\n\r\n"
    distinct = "GET /items?q=%3Csvg%3E HTTP/1.1\r\nHost: example\r\n\r\n"
    db.executemany(
        "INSERT INTO combined_data VALUES(?,?)",
        [
            (conflict, "000 - Normal"),
            (conflict, "000 - Normal"),
            (conflict, "66 - SQL Injection"),
            (distinct, "79 - Cross-Site Scripting"),
        ],
    )
    db.commit()
    db.close()
    archive = tmp_path / "source.xz"
    archive.write_bytes(b"test archive")
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Creative Commons Attribution 4.0 International License\n")
    readme = tmp_path / "README"
    readme.write_text("test schema")
    expected = hashlib.sha256(database.read_bytes()).hexdigest()
    report_path = tmp_path / "report.json"
    staging_path = tmp_path / "views.parquet"
    report = _auditor().audit(
        database, expected, archive, license_file, readme, report_path, staging_path
    )
    assert report["counts"]["raw_records"] == 4
    assert report["exact_text_representation"]["mixed_label_keys"] == 1
    assert report["exact_text_representation"]["minority_label_rows_on_mixed_keys"] == 1
    assert report["exact_float32_request_view"]["mixed_label_keys"] == 1
    assert report["exact_float32_request_view"]["minority_label_rows_on_mixed_keys"] == 1
    assert report["numeric_research_staging"]["rows_one_per_nonconflicting_float32_view"] == 1
    table = pq.read_table(staging_path)
    assert table.column("label").to_pylist() == [1]
    assert table.column("features").type.list_size == 76
    assert b"/private" not in report_path.read_bytes() + staging_path.read_bytes()
    with pytest.raises(PipelineError, match="already exists"):
        _auditor().audit(database, expected, archive, license_file, readme, report_path)


def test_overlap_filter_excludes_exposed_view_and_rejects_sealed_role(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/filter-request-view-overlap.py"
    spec = importlib.util.spec_from_file_location("view_filter", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    zero = np.zeros(76, dtype=np.float32)
    one = np.ones(76, dtype=np.float32)
    keys = [hashlib.sha256(v.tobytes()).hexdigest() for v in (zero, one)]
    candidate = tmp_path / "candidate.parquet"
    features = pa.FixedSizeListArray.from_arrays(pa.array(np.concatenate((zero, one))), 76)
    pq.write_table(
        pa.table(
            {
                "view_sha256": keys,
                "label": pa.array([0, 1], type=pa.int8()),
                "occurrence_rows": pa.array([1, 1], type=pa.int32()),
                "features": features,
            }
        ),
        candidate,
    )

    def reference(path, role):
        pq.write_table(
            pa.table(
                {
                    "source_id": ["old"],
                    "split": [role],
                    "label": pa.array([1], type=pa.int8()),
                    "x": pa.FixedSizeListArray.from_arrays(pa.array(zero), 76),
                }
            ),
            path,
        )

    old = tmp_path / "old.parquet"
    reference(old, "val")

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    report = module.filter_views(
        candidate,
        old,
        sha(candidate),
        sha(old),
        tmp_path / "filtered.parquet",
        tmp_path / "report.json",
    )
    assert report["filtered_views"] == 1
    assert report["overlap"]["label_disagreements"] == 1
    assert report["research_fit_staging_ready"] is True
    assert report["autonomous_research_ready"] is False
    assert report["formal_ready"] is False
    assert pq.read_table(tmp_path / "filtered.parquet").column("view_sha256").to_pylist() == [
        keys[1]
    ]
    sealed = tmp_path / "sealed.parquet"
    reference(sealed, "test")
    with pytest.raises(PipelineError, match="sealed/unknown"):
        module.filter_views(
            candidate,
            sealed,
            sha(candidate),
            sha(sealed),
            tmp_path / "forbidden.parquet",
            tmp_path / "forbidden.json",
        )
