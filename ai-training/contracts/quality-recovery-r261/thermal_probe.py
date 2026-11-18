# isort: skip_file

"""Injected boundary test on one owned sleep child, never a thermal stress test."""

import os
import sys
import time

from common import atomic_json, check, output_arg
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.delegated_guard import run, unit_root
from idps_ai.training.thermal_policy import admission


class BoundaryReader:
    def __init__(self, root):
        self.root, self.index, self.readbacks = root, 0, []
        self.values = [89, 90, 90.1, 99, 100, 100.1]

    def read(self, now):
        if self.index:
            worker = self.root / "ai-worker"
            self.readbacks.append(
                {
                    "previous_fixture_c": self.values[self.index - 1],
                    "cpu.max": (worker / "cpu.max").read_text().strip(),
                    "cgroup.events": (worker / "cgroup.events").read_text().strip(),
                }
            )
        value = self.values[self.index]
        self.index += 1
        return {
            "temperature_C": value,
            "hardware_emergency": False,
            "sampled_monotonic": now,
            "scope": "SYNTHETIC_CONTROLLER_BOUNDARY_ONLY_NOT_HOST_TEMPERATURE",
        }


def probe(out):
    real = admission(
        SensorReader(hardware_snapshot()), "R261_LIGHTWEIGHT_BOUNDARY_FIXTURE_PREFLIGHT"
    )
    check(real["decision"] == "ACCEPT", "Real host admission failed before sleep-only fixture")
    root = unit_root()
    reader = BoundaryReader(root)
    code = run([sys.executable, "-c", "import time; time.sleep(10)"], reader=reader)
    expected = ["400000 100000", "400000 100000", "200000 100000", "200000 100000", "200000 100000"]
    check(
        code == 78 and [r["cpu.max"] for r in reader.readbacks] == expected,
        "Thermal fixture kernel quota mismatch",
    )
    check(not (root / "ai-worker").exists(), "Sleep fixture cgroup not cleaned")
    atomic_json(
        out / "thermal-boundary-kernel.json",
        {
            "scope": "INJECTED_FIXTURE_ON_REAL_CGROUP_SLEEP_CHILD",
            "real_admission": real,
            "fixture_temperatures": reader.values,
            "kernel_readbacks": reader.readbacks,
            "software_stop_above_100": code == 78,
            "hardware_trip_bypass_in_production": False,
            "cleanup": True,
            "state": "PASS",
            "pid": os.getpid(),
            "wall_ns": time.time_ns(),
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    probe(output_arg())
