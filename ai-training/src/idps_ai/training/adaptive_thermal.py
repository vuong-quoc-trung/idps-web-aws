"""Job-scoped adaptive heat policy and read-only, explicitly mapped CPU sensors."""

import math
from pathlib import Path

from idps_ai.common import PipelineError, digest


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
    effective = min(96.0, limit - 1, *(v - 1 for v in cpu_zones))
    if effective <= 0:
        raise PipelineError("Invalid platform thermal limits")
    result = {
        "processor": model,
        "cpu_sensors": sensors,
        "platform_zones": zones,
        "auxiliary_sensors": auxiliary,
        "requested_emergency_C": 96,
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
            if critical < self.snapshot["effective_emergency_C"]:
                raise PipelineError("CPU critical limit now below configured emergency")
            alarm = int(Path(s["alarm"]).read_text())
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
        emergency = any(v["alarm"] for v in values) or any(
            z["C"] >= z["limit_C"] or z.get("alarm", 0) for z in self.platform
        )
        return {
            "temperature_C": maximum["C"],
            "maximum_sensor": maximum["label"],
            "readings": values,
            "platform": self.platform,
            "hardware_emergency": emergency,
            "sampled_monotonic": now,
        }


class ThermalMachine:
    def __init__(
        self,
        *,
        emergency=96,
        warning=85,
        throttle=90,
        strong=93,
        ceiling=20,
        minimum=1,
        cooldown=15,
        ramp_seconds=5,
        cooling_timeout=300,
    ):
        if not 0 < minimum <= ceiling <= 20 or not 0 < emergency <= 96:
            raise PipelineError("Unsafe thermal configuration")
        if not 0 < warning < throttle < strong <= 96:
            raise PipelineError("Invalid adaptive temperature bands")
        self.warning, self.throttle, self.strong = warning, throttle, strong
        self.emergency, self.ceiling, self.minimum = emergency, ceiling, minimum
        self.cooldown, self.ramp_seconds, self.cooling_timeout = (
            cooldown,
            ramp_seconds,
            cooling_timeout,
        )
        self.quota, self.paused = ceiling, False
        self.cool_since = self.pause_since = self.last = None
        self.last_ramp = 0
        self.band, self.band_since = "NORMAL", 0
        self.terminal = None

    def update(
        self,
        now,
        temperature,
        *,
        supervisor_healthy=True,
        memory_pressure=False,
        hardware_emergency=False,
    ):
        rate = 0
        if temperature is None or not math.isfinite(temperature) or not 0 < temperature < 130:
            return self.stop("SENSOR_FAILURE")
        if temperature >= self.emergency or hardware_emergency:
            return self.stop("THERMAL_EMERGENCY")
        if not supervisor_healthy:
            return self.stop("SUPERVISOR_HEARTBEAT_LOST")
        if self.last is not None:
            dt = now - self.last[0]
            if not 0 < dt <= 2:
                return self.stop("SENSOR_SAMPLING_STALE")
            rate = (temperature - self.last[1]) / dt
        self.last = (now, temperature)
        if self.terminal:
            return self.stop(self.terminal)
        band = (
            "STRONG_THROTTLE"
            if temperature >= self.strong
            else "THROTTLE"
            if temperature >= self.throttle
            else "WARNING"
            if temperature >= self.warning
            else "NORMAL"
        )
        changed = band != self.band
        if changed:
            self.band, self.band_since = band, now
        if temperature >= self.warning or memory_pressure:
            self.cool_since = None
        elif self.cool_since is None:
            self.cool_since = now
        if memory_pressure:
            self.paused = True
        elif band == "STRONG_THROTTLE":
            self.quota = self.minimum
            if (
                rate > 0.5
                or temperature >= min(self.strong + 2, self.emergency - 0.5)
                or now - self.band_since >= 2
            ):
                self.paused = True
        elif band == "THROTTLE":
            if changed:
                self.quota = max(self.minimum, self.quota / 2)
        elif band == "WARNING" and rate > 0:
            self.quota = min(self.quota, max(self.minimum, self.ceiling / 2))
        # Proactive response to a fast rise even before WARNING.
        elif band == "NORMAL" and temperature >= 80 and rate >= 10:
            self.quota = min(self.quota, max(self.minimum, self.ceiling / 2))
        cool = self.cool_since is not None and now - self.cool_since >= self.cooldown
        if self.paused:
            if self.pause_since is None:
                self.pause_since = now
            if now - self.pause_since >= self.cooling_timeout:
                return self.stop("COOLING_TIMEOUT")
            if cool and not memory_pressure:
                self.paused = False
                self.quota = self.minimum
                self.last_ramp = now
                self.pause_since = None
        elif band == "NORMAL" and cool and now - self.last_ramp >= self.ramp_seconds:
            self.quota = min(self.ceiling, self.quota + 2)
            self.last_ramp = now
        return {
            "state": "THERMAL_COOLDOWN" if self.paused else band,
            "band": band,
            "paused": self.paused,
            "quota": self.quota,
            "stop": False,
            "reason": None,
            "rise_C_per_second": rate,
        }

    def stop(self, reason):
        self.terminal = reason
        return {
            "state": reason,
            "band": self.band,
            "paused": True,
            "quota": self.minimum,
            "stop": True,
            "reason": reason,
            "rise_C_per_second": None,
        }
