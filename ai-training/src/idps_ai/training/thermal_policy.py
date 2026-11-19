"""Common host CPU policy. Firmware alarms and hardware limits take precedence."""

import math
import time
from datetime import UTC, datetime

from idps_ai.common import PipelineError

THROTTLE_C = 90.0
STOP_C = 100.0
CPU_FACTOR = 0.5
HARDWARE_MARGIN_C = 5.0
VERSION = "idps-host-thermal-2.0.0"


def cpu_state(temperature, hardware_alarm=False):
    if type(hardware_alarm) is not bool:
        return "SENSOR_FAILURE"
    if type(temperature) not in (float, int) or not math.isfinite(temperature) or not 0 < temperature < 130:
        return "SENSOR_FAILURE"
    if hardware_alarm or temperature > STOP_C:
        return "THERMAL_EMERGENCY"
    return "THROTTLE" if temperature > THROTTLE_C else "NORMAL"


def quota_for_state(base_quota, state):
    if state == "NORMAL":
        return base_quota
    if state == "THROTTLE":
        return base_quota * CPU_FACTOR
    raise PipelineError(state)


def admission(reader, source):
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "sampled_monotonic": time.monotonic(),
        "source": source,
        "sensor_source": "idps_ai.training.adaptive_thermal.SensorReader",
        "policy": VERSION,
        "throttle_above_C": THROTTLE_C,
        "stop_above_C": STOP_C,
    }
    try:
        reading = reader.read(result["sampled_monotonic"])
        state = cpu_state(reading["temperature_C"], reading["hardware_emergency"])
    except (OSError, KeyError, ValueError, PipelineError) as exc:
        return result | {"decision": "REFUSE", "state": "SENSOR_FAILURE",
                         "predicates": {"sensor_read_failed": True}, "error_type": type(exc).__name__}
    return result | {
        "reading": reading,
        "state": state,
        "decision": "ACCEPT" if state in {"NORMAL", "THROTTLE"} else "REFUSE",
        "predicates": {
            "temperature_above_software_stop": (
                state != "SENSOR_FAILURE" and reading["temperature_C"] > STOP_C
            ),
            "hardware_alarm": reading["hardware_emergency"],
            "sensor_read_failed": state == "SENSOR_FAILURE",
        },
    }
