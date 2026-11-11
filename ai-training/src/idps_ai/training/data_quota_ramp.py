"""Measured, job-scoped data CPU ramp. Thermal controller retains precedence."""

import json
import time
from pathlib import Path

from idps_ai.common import atomic_json
from idps_ai.training.heartbeat import process_identity


class DataQuotaRamp:
    def __init__(self, plan, output):
        self.plan = json.loads(Path(plan).read_text())
        if self.plan["steps"] != [5, 10, 20, 30, 50] or self.plan["window_seconds"] < 60:
            raise ValueError("Only measured half-of-one-core data ramp is authorized")
        self.path = Path(output) / "cpu-ramp.json"
        self.ceiling = 5
        self.index = 0
        self.rows = []
        self.history = []
        self.previous_rate = None
        self.halted = False
        self.last_status_read = 0
        self.worker = {}
        self.last_publish = 0
        self.last_state = None

    def observe(self, now, temperature, paused, pressure, own_cpu, cgroup_pids, actual_quota=None):
        if now - self.last_status_read >= 0.5:
            try:
                self.worker = json.loads(Path(self.plan["worker_status"]).read_text())
            except (OSError, ValueError):
                self.worker = {}
            self.last_status_read = now
        w = self.worker
        identity = w.get("pid") in cgroup_pids and process_identity(w.get("pid", 0)) == w.get(
            "start_ticks"
        )
        healthy = (
            identity
            and 0 <= time.time() - w.get("heartbeat", 0) < 3
            and w.get("state") == "RUNNING"
        )
        if w.get("phase") != "SYNTHETIC_REQUEST_GENERATION":
            self.rows = []
            # Qualification never inherits the unmeasured training allocation.
            return (
                self.ceiling
                if w.get("phase") not in ["REAL_10M_TRAINING", "TRAINING_PREFLIGHT"]
                else min(5, self.ceiling)
            )
        if not healthy or paused or pressure or temperature >= 75:
            self.rows = []
            self.ceiling = 5
            self.index = 0
            self.previous_rate = None
            self.publish("WAIT_UNHEALTHY_PAUSED_OR_PRESSURE", None)
            return self.ceiling
        if actual_quota is not None and actual_quota != self.ceiling:
            self.rows = []
            self.publish("WAIT_KERNEL_QUOTA_READBACK_WINDOW", None)
            return self.ceiling
        row = {
            "time": now,
            "candidates": w.get("completed", 0),
            "receipts": w.get("verified_distinct_HTTP_requests", 0),
            "staging": w.get("new_staging_TRAIN_views", 0),
            "eligible": w.get("new_eligible_TRAIN_examples", 0),
            "temperature": temperature,
            "own_cpu": own_cpu,
            "errors": w.get("receipt_errors"),
            "feature_cpu_seconds": w.get("feature_cpu_seconds", 0),
            "http_wall_seconds": w.get("http_wall_seconds", 0),
        }
        self.rows.append(row)
        if now - self.rows[0]["time"] < self.plan["window_seconds"]:
            self.publish("MEASURING", None)
            return self.ceiling
        a, b = self.rows[0], self.rows[-1]
        dt = b["time"] - a["time"]
        metrics = {
            key + "_per_second": (b[key] - a[key]) / dt
            for key in ["candidates", "receipts", "staging", "eligible"]
        }
        metrics.update(
            window_seconds=dt,
            quota_percent_one_core=self.ceiling,
            average_temperature=sum(
                a["temperature"] * (b["time"] - a["time"]) for a, b in zip(self.rows, self.rows[1:])
            )
            / dt,
            maximum_temperature=max(v["temperature"] for v in self.rows),
            own_cpu_percent_one_core=sum(v["own_cpu"] for v in self.rows) / len(self.rows),
            error_count_delta=None
            if a["errors"] is None or b["errors"] is None
            else b["errors"] - a["errors"],
        )
        metrics["feature_cpu_seconds_delta"] = b["feature_cpu_seconds"] - a["feature_cpu_seconds"]
        metrics["http_wall_seconds_delta"] = b["http_wall_seconds"] - a["http_wall_seconds"]
        safe = (
            metrics["maximum_temperature"] < 75
            and metrics["error_count_delta"] == 0
            and metrics["candidates_per_second"] > 0
            and metrics["receipts_per_second"] > 0
        )
        action = "HOLD_TEMPERATURE_OR_NO_HEALTHY_PROGRESS"
        if safe and not self.halted:
            rate = metrics["candidates_per_second"]
            if self.previous_rate is not None and rate < self.previous_rate * 1.10:
                self.halted = True
                action = "STOP_RAMP_NO_MEASURED_THROUGHPUT_GAIN"
                metrics["bottleneck"] = (
                    "CPU_BUDGET_SATURATED_WITHOUT_RATE_GAIN"
                    if metrics["own_cpu_percent_one_core"] >= self.ceiling * 0.8
                    else "HTTP_OR_IO_WAIT_SUSPECTED; not proven from wall time alone"
                )
                self.index = max(0, self.index - 1)
                self.ceiling = self.plan["steps"][self.index]
            elif self.index < len(self.plan["steps"]) - 1:
                self.previous_rate = rate
                self.index += 1
                self.ceiling = self.plan["steps"][self.index]
                action = "AUTHORIZE_NEXT_MEASURED_QUOTA"
            else:
                action = "TARGET_50_PERCENT_ONE_CORE_VERIFIED"
        self.history.append(
            dict(metrics, action=action, next_ceiling=self.ceiling, wall_time=time.time())
        )
        self.rows = []
        self.publish(action, metrics)
        return self.ceiling

    def publish(self, state, metrics):
        if state == self.last_state and time.monotonic() - self.last_publish < 1:
            return
        self.last_publish = time.monotonic()
        self.last_state = state
        atomic_json(
            self.path,
            {
                "state": state,
                "ceiling_percent_one_core": self.ceiling,
                "steps": self.plan["steps"],
                "window_seconds": self.plan["window_seconds"],
                "last_window": metrics,
                "history": self.history,
                "thermal_controller_has_precedence": True,
                "heartbeat": time.time(),
            },
        )
