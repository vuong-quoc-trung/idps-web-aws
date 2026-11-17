"""Shared R26 pins and finite execution helpers. Historical artifacts are read-only."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BULK = HERE.parent / "development-bulk-v1"
sys.path.insert(0, str(BULK))

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json  # noqa: E402
from idps_ai.common import file_sha256 as file_sha256  # noqa: E402

ARTIFACTS = REPO_ROOT / "ai-training/.artifacts"
R24 = ARTIFACTS / "t09-r24-readiness-msurbJkS"
R25 = ARTIFACTS / "t09-r25-quality-EsMMItaJ"
R24_DATA_SHA = "249f7810b3bbdfef2e898bac120b42ef9857c3da6cf35b8302092e996114a4f5"
R25_ONNX_SHA = "9933a43d1ff7c8eef7667164750d7d7977ab35695d236d996c4980570580c987"
NOTES_REVISION = "1b4d732b3c227fe2345240cbb7e6c30e936ed81b"
NOTES_SHA = "78a2aca0816824b42cfc1083d863427d10577087ac0283186c366cadbf1e6fcf"
NOTES_BYTES = 1_637_726
SEED = 2601


def check(value, message):
    if not value:
        raise PipelineError(message)


def read(path):
    return json.loads(Path(path).read_text())


def status(out, state, phase, **fields):
    atomic_json(
        Path(out) / "status.json",
        {
            "run_id": Path(out).name,
            "state": state,
            "phase": phase,
            "heartbeat_utc": datetime.now(UTC).isoformat(),
            **fields,
        },
    )
