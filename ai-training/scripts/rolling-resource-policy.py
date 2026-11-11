"""Time-weighted host heat policy. No changes to firmware or OS protection."""

from collections import deque


class HeatWindow:
    def __init__(self):
        self.intervals = deque()
        self.previous = None
        self.total = self.active_total = self.paused_total = 0.0
        self.seconds = self.active_seconds = self.paused_seconds = 0.0

    def add(self, now, temperature, paused):
        if not 0 < temperature < 130:
            raise ValueError("Unreliable temperature")
        if self.previous:
            t, value, was_paused = self.previous
            dt = now - t
            if dt <= 0 or dt > 5:
                raise ValueError("Unreliable sensor sampling interval")
            self.intervals.append((t, now, value))
            self.total += value * dt
            self.seconds += dt
            if was_paused:
                self.paused_total += value * dt
                self.paused_seconds += dt
            else:
                self.active_total += value * dt
                self.active_seconds += dt
        self.previous = now, temperature, paused
        cutoff = now - 300
        while self.intervals and self.intervals[0][1] <= cutoff:
            self.intervals.popleft()
        area = duration = 0.0
        for a, b, value in self.intervals:
            dt = b - max(a, cutoff)
            area += value * dt
            duration += dt
        return {
            "current_c": temperature,
            "rolling_300s_c": area / duration if duration else temperature,
            "full_run_time_weighted_c": self.total / self.seconds if self.seconds else temperature,
            "active_time_weighted_c": self.active_total / self.active_seconds
            if self.active_seconds
            else None,
            "paused_time_weighted_c": self.paused_total / self.paused_seconds
            if self.paused_seconds
            else None,
            "active_seconds": self.active_seconds,
            "paused_seconds": self.paused_seconds,
            "window_seconds": duration,
            "sensor_health": "OK",
        }


def action(temp, rolling, rate, paused, cool_seconds, pressure=False, cutoff=100):
    if temp >= cutoff:
        return "KILL"
    if pressure:
        return "WAIT" if paused else "FREEZE"
    if paused and temp < cutoff and cool_seconds >= 5:
        return "THAW"
    return "WAIT"


def cpu_budget(current, ceiling, host_percent, own_one_cpu_percent, cpus):
    """Quota is percent of ONE CPU, host_percent is normalized across host CPUs."""
    external = max(0, host_percent - own_one_cpu_percent / cpus)
    available = max(1, (50 - external) * cpus)
    return min(ceiling, available, current + 25)


def memory_pressure(psi_text, swap_in_delta, swap_out_delta, elapsed):
    lines = [line for line in psi_text.splitlines() if line.startswith("full ")]
    full = 0.0
    if lines:
        full = float(dict(v.split("=", 1) for v in lines[0].split()[1:])["avg10"])
    return full >= 1 or (swap_in_delta + swap_out_delta) / max(elapsed, 0.1) >= 16 * 1024**2
