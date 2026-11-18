import json
from types import SimpleNamespace

import pytest
import supervisor

from idps_ai.common import file_sha256


def setup(root):
    complete = []
    for family in supervisor.FAMILIES:
        directory = root / family
        path = directory / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text('{"kind":"ATTEMPT","fixture_only":true}\n')
        (directory / "checkpoint.json").write_text(json.dumps({"ledger_sha256": file_sha256(path)}))
        complete.append({"family": family, "state": "CAPTURED", "exit_code": 0})
    (root / "admission.json").write_text("{}\n")
    (root / "native-source-role-registry.json").write_text("{}\n")
    cp = {
        "completed": complete,
        "admission_sha256": file_sha256(root / "admission.json"),
        "role_registry_sha256": file_sha256(root / "native-source-role-registry.json"),
    }
    (root / "checkpoint.json").write_text(json.dumps(cp))


def test_offline_resume_never_dispatches_or_creates_worker(tmp_path, monkeypatch):
    setup(tmp_path)
    calls = []

    def no_managed(*args):
        raise AssertionError("Offline finalization launched compute/capture")

    monkeypatch.setattr(supervisor, "managed", no_managed)
    monkeypatch.setattr(
        supervisor.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0),
    )
    assert supervisor.finish(tmp_path, reuse=True) == 0
    assert [c[2].split("/")[-1] for c in calls] == ["information.py", "finalize.py"]
    assert json.loads((tmp_path / "offline-resume-proof.json").read_text())["HTTP_dispatched"] == 0


def test_corrupt_commit_refuses_before_subprocess(tmp_path, monkeypatch):
    setup(tmp_path)
    (tmp_path / "native-source-role-registry.json").write_text('{"tampered":true}\n')
    monkeypatch.setattr(
        supervisor.subprocess,
        "run",
        lambda *a, **k: pytest.fail("Dispatched after corrupt role checkpoint"),
    )
    with pytest.raises(ValueError, match="state changed"):
        supervisor.finish(tmp_path, reuse=True)
