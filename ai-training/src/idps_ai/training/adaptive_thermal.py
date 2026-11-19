"""Job-scoped adaptive heat policy and read-only, explicitly mapped CPU sensors."""

import math
from pathlib import Path

from idps_ai.common import PipelineError, digest
from idps_ai.training.thermal_policy import HARDWARE_MARGIN_C, STOP_C, cpu_state, quota_for_state


def hardware_snapshot(sysroot=Path("/sys"), cpuinfo=Path("/proc/cpuinfo")):
    sensors = []
    for hw in sorted((sysroot / "class/hwmon").glob("hwmon*")):
        if (hw / "name").read_text().strip() != "coretemp":
            continue
        for p in sorted(hw.glob("temp*_input")):
            stem = p.name.removesuffix("_input")
            label = (hw / (stem + "_label")).read_text().strip()
            if not (label.startswith("Core ") or label.startswith("Package id ")):
                raise PipelineError("Unknown CPU sensor mapping")
            critical = int((hw / (stem + "_crit")).read_text()) / 1000
            sensors.append(
                {
                    "path": str(p),
                    "label": label,
                    "critical_C": critical,
                    "initial_C": int(p.read_text()) / 1000,
                    "alarm": str(hw / (stem + "_crit_alarm")),
                }
            )
    if not sensors or not any(s["label"].startswith("Package id ") for s in sensors):
        raise PipelineError("No verified package/core sensor mapping")
    zones = []
    for z in sorted((sysroot / "class/thermal").glob("thermal_zone*")):
        limits = []
        for p in sorted(z.glob("trip_point_*_type")):
            kind = p.read_text().strip()
            v = int(p.with_name(p.name.replace("_type", "_temp")).read_text()) / 1000
            if kind in {"critical", "hot"} and 0 < v < 130:
                limits.append({"kind": kind, "C": v})
        if limits:
            zones.append(
                {
                    "path": str(z / "temp"),
                    "type": (z / "type").read_text().strip(),
                    "initial_C": int((z / "temp").read_text()) / 1000,
                    "limits": limits,
                }
            )
    auxiliary = []
    for hw in sorted((sysroot / "class/hwmon").glob("hwmon*")):
        if (hw / "name").read_text().strip() == "coretemp":
            continue
        for p in sorted(hw.glob("temp*_crit")):
            critical = int(p.read_text()) / 1000
            source = p.with_name(p.name.replace("_crit", "_input"))
            if 0 < critical < 130 and source.exists():
                auxiliary.append(
                    {
                        "path": str(source),
                        "critical_C": critical,
                        "driver": (hw / "name").read_text().strip(),
                    }
                )
    model = next(
        line.split(":", 1)[1].strip()
        for line in cpuinfo.read_text().splitlines()
        if line.startswith("model name")
    )
    if model != "Intel(R) Core(TM) Ultra 9 285H":
        raise PipelineError("New processor requires a reviewed hardware policy")
    limit = min(s["critical_C"] for s in sensors)
    # Domain-specific SEN/NVMe limits are never interpreted as CPU junction limits.
    cpu_zones = [
        trip["C"]
        for z in zones
        if z["type"] in {"TCPU", "x86_pkg_temp", "TCPU_PCI"}
        for trip in z["limits"]
    ]
    hardware_stop = min([limit - HARDWARE_MARGIN_C] + [v - HARDWARE_MARGIN_C for v in cpu_zones])
    effective = min(STOP_C, hardware_stop)
    if effective <= 0:
        raise PipelineError("Invalid platform thermal limits")
    result = {
        "processor": model,
        "cpu_sensors": sensors,
        "platform_zones": zones,
        "auxiliary_sensors": auxiliary,
        "requested_emergency_C": STOP_C,
        "hardware_protection_C": hardware_stop,
        "effective_emergency_C": effective,
        "lowest_coretemp_critical_C": limit,
        "sensor_scope": "coretemp cores/package for CPU; other thermal domains retain own hot/critical limits",
        "unmapped_SEN_warning": "50 millidegree readings are not interpreted as CPU temperature; own reported trips still monitored",
        "official_max_operating_C": 110,
        "sources": [
            "https://www.intel.com/content/www/us/en/products/sku/241747/intel-core-ultra-9-processor-285h-24m-cache-up-to-5-40-ghz/specifications.html",
            "https://www.kernel.org/doc/html/latest/hwmon/coretemp.html",
        ],
    }
    result["fingerprint"] = digest(result)
    return result


class SensorReader:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.last_platform = 0
        self.platform = []

    def read(self, now):
        values = []
        for s in self.snapshot["cpu_sensors"]:
            p = Path(s["path"])
            v = int(p.read_text()) / 1000
            critical = int(p.with_name(p.name.replace("_input", "_crit")).read_text()) / 1000
            if not 0 < v < 130 or not math.isfinite(v):
                raise PipelineError("CPU sensor unavailable or unreliable")
            if not 40 <= critical <= 130 or critical < s.get("critical_C", self.snapshot["effective_emergency_C"]):
                raise PipelineError("CPU critical limit now below configured emergency")
            alarm = int(Path(s["alarm"]).read_text())
            if alarm not in (0, 1):
                raise PipelineError("Unreliable CPU hardware alarm")
            values.append({"path": s["path"], "label": s["label"], "C": v, "alarm": alarm})
        if now - self.last_platform >= 1 or not self.platform:
            self.platform = []
            for z in self.snapshot["platform_zones"]:
                value = int(Path(z["path"]).read_text()) / 1000
                if not -20 < value < 130:
                    raise PipelineError("Platform sensor invalid")
                # Re-read every reported domain trip; never write/raise trip points.
                current_limits = []
                for p in Path(z["path"]).parent.glob("trip_point_*_type"):
                    kind = p.read_text().strip()
                    c = int(p.with_name(p.name.replace("_type", "_temp")).read_text()) / 1000
                    if kind in {"hot", "critical"} and 0 < c < 130:
                        current_limits.append(c)
                limit = min([trip["C"] for trip in z["limits"]] + current_limits)
                self.platform.append({"type": z["type"], "C": value, "limit_C": limit})
            for aux in self.snapshot["auxiliary_sensors"]:
                p = Path(aux["path"])
                value = int(p.read_text()) / 1000
                critical = int(p.with_name(p.name.replace("_input", "_crit")).read_text()) / 1000
                if not -20 < value < 130 or not 0 < critical < 130:
                    raise PipelineError("Auxiliary sensor unavailable")
                self.platform.append(
                    {"type": aux["driver"], "C": value, "limit_C": min(critical, aux["critical_C"])}
                )
            self.last_platform = now
        maximum = max(values, key=lambda x: x["C"])
        hardware_stop = self.snapshot.get("hardware_protection_C")
        emergency = (hardware_stop is not None and maximum["C"] >= hardware_stop) or any(v["alarm"] for v in values) or any(
            z["C"] >= z["limit_C"] or z.get("alarm", 0) for z in self.platform
        )
        return {
            "temperature_C": maximum["C"],
            "maximum_sensor": maximum["label"],
            "readings": values,
            "platform": self.platform,
            "hardware_emergency": emergency,
            "hardware_protection_C": hardware_stop,
            "sampled_monotonic": now,
        }


class ThermalMachine:
    """Thermal quota and independent memory-pressure freeze for an owned job."""

    def __init__(self, *, ceiling=20, maximum_ceiling=20, cooldown=15, cooling_timeout=300):
        values = ceiling, maximum_ceiling, cooldown, cooling_timeout
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
            raise PipelineError("Invalid thermal configuration")
        if ceiling > maximum_ceiling:
            raise PipelineError("Unsafe quota")
        self.ceiling = ceiling
        self.emergency = STOP_C
        self.cooldown, self.cooling_timeout = cooldown, cooling_timeout
        self.pause_since = self.clear_since = self.last = None
        self.band = "NORMAL"
        self.terminal = None

    def update(self, now, temperature, *, supervisor_healthy=True,
               memory_pressure=False, hardware_emergency=False):
        if self.terminal:
            return self.stop(self.terminal)
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            return self.stop("SENSOR_SAMPLING_STALE")
        band = cpu_state(temperature, hardware_emergency)
        if band in {"SENSOR_FAILURE", "THERMAL_EMERGENCY"}:
            return self.stop(band)
        if supervisor_healthy is not True:
            return self.stop("SUPERVISOR_HEARTBEAT_LOST")
        if self.last is not None and not 0 < now - self.last <= 2:
            return self.stop("SENSOR_SAMPLING_STALE")
        self.last = now
        self.band = band
        if memory_pressure:
            self.clear_since = None
            if self.pause_since is None:
                self.pause_since = now
        elif self.pause_since is not None:
            if self.clear_since is None:
                self.clear_since = now
            if now - self.clear_since >= self.cooldown:
                self.pause_since = None
        paused = self.pause_since is not None
        if paused and now - self.pause_since >= self.cooling_timeout:
            return self.stop("COOLING_TIMEOUT")
        return {
            "state": "MEMORY_PRESSURE_PAUSE" if paused else band,
            "band": band,
            "paused": paused,
            "quota": quota_for_state(self.ceiling, band),
            "stop": False,
            "reason": None,
        }

    def stop(self, reason):
        self.terminal = reason
        return {"state": reason, "band": self.band, "paused": True, "quota": 0,
                "stop": True, "reason": reason}
