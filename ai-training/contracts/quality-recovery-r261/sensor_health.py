# isort: skip_file

"""One bounded traced SensorReader probe; no retries of a blocked sysfs read."""

import os
import time
from pathlib import Path

from common import atomic_json, output_arg
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.thermal_policy import admission


def run(out):
    log = out / "sensor-read-trace.jsonl"
    original = Path.read_text

    def traced(path, *args, **kwargs):
        if str(path).startswith("/sys/"):
            import json

            began = time.monotonic()
            with log.open("a") as stream:
                stream.write(
                    json.dumps({"phase": "READ_START", "path": str(path), "monotonic": began})
                    + "\n"
                )
            value = original(path, *args, **kwargs)
            with log.open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "phase": "READ_END",
                            "path": str(path),
                            "seconds": time.monotonic() - began,
                        }
                    )
                    + "\n"
                )
            return value
        return original(path, *args, **kwargs)

    Path.read_text = traced
    began = time.monotonic()
    hardware = hardware_snapshot()
    reader = SensorReader(hardware)
    samples = []
    for _ in range(5):
        start = time.monotonic()
        receipt = admission(reader, "R261_HOST_RECOVERY_PROBE")
        receipt["read_seconds"] = time.monotonic() - start
        samples.append(receipt)
        atomic_json(
            out / "sensor-health.json",
            {"hardware": hardware, "samples": samples, "complete": False},
        )
        if receipt["decision"] != "ACCEPT":
            raise RuntimeError("Sensor admission refused")
        time.sleep(0.25)
    atomic_json(
        out / "sensor-health.json",
        {
            "hardware": hardware,
            "samples": samples,
            "complete": True,
            "seconds": time.monotonic() - began,
            "pid": os.getpid(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())
