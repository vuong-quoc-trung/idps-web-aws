"""Offline Suricata over real PCAP, derived from unchanged repository config/rules."""

import json
import os
import socketserver
import subprocess
import threading
from collections import Counter
from pathlib import Path

import yaml

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, file_sha256
from idps_ai.data.privacy import safe_agent, safe_route
from idps_ai.data.query_numeric import project_query
from idps_ai.data.readers import eve_request_id
from idps_ai.data.snapshot import new_destination


def redact_eve(value, query_numeric=False, query_version=1, request_structure=False):
    # Suricata supports only a fixed custom-header list. Receive response
    # headers through a private Unix socket, retaining only the generated ID.
    # No raw response headers ever reach a file or diagnostic output.
    if query_numeric or request_structure:
        # AI bridge output is a separate, explicit allowlist. In particular,
        # never retain packet/body dumps or free-form alert text from an input.
        value = {
            name: item
            for name, item in value.items()
            if name
            in (
                "timestamp",
                "event_type",
                "src_ip",
                "dest_ip",
                "src_port",
                "dest_port",
                "proto",
                "app_proto",
                "flow_id",
                "http",
                "flow",
                "alert",
            )
        }
        if isinstance(value.get("alert"), dict):
            value["alert"] = {
                k: v
                for k, v in value["alert"].items()
                if k in ("signature_id", "severity", "gid", "rev")
                and isinstance(v, int)
                and not isinstance(v, bool)
                and 0 <= v <= 2**32
            }
        if isinstance(value.get("flow"), dict):
            value["flow"] = {
                k: v
                for k, v in value["flow"].items()
                if k
                in (
                    "start",
                    "end",
                    "age",
                    "bytes_toserver",
                    "bytes_toclient",
                    "pkts_toserver",
                    "pkts_toclient",
                )
            }
    http = value.get("http")
    if isinstance(http, dict):
        allowed = {
            "url",
            "http_method",
            "status",
            "length",
            "http_user_agent",
            "protocol",
            "http_port",
            "response_headers",
        }
        http = {name: item for name, item in http.items() if name in allowed}
        value["http"] = http
        if "response_headers" in http:
            http["response_headers"] = [
                {"name": "X-Request-Id", "value": h.get("value")}
                for h in http["response_headers"]
                if isinstance(h, dict) and str(h.get("name", "")).lower() == "x-request-id"
            ]
        if "url" in http and request_structure and value.get("event_type") == "http":
            from idps_ai.features.request_view import project_request

            value["ai_request_view"] = project_request(
                http["url"], http.get("http_method", "OTHER")
            )
        if "url" in http and query_numeric and value.get("event_type") == "http":
            value["ai_query_numeric"] = project_query(http["url"], version=query_version)
        if "url" in http:
            http["url"] = safe_route(http["url"])
        if "http_user_agent" in http:
            http["http_user_agent"] = safe_agent(http["http_user_agent"])
    return value


class _EveServer(socketserver.UnixStreamServer):
    pass


class _EveHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            while line := self.rfile.readline(65537):
                if len(line) > 65536 or not line.endswith(b"\n"):
                    raise PipelineError("Oversized/partial sensor record")
                value = redact_eve(
                    json.loads(line),
                    query_numeric=self.server.query_numeric,
                    query_version=self.server.query_version,
                    request_structure=self.server.request_structure,
                )
                self.server.destination.write(
                    json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n"
                )
        except (OSError, ValueError, TypeError):
            self.server.failed = True
        finally:
            self.server.completed.set()


def decode_pcap(
    pcap, output, runtime, query_numeric=False, query_version=1, request_structure=False
):
    if query_version not in (1, 2) or (query_version == 2 and not query_numeric):
        raise PipelineError("Numeric projection v2 requires opt-in query telemetry")
    pcap, runtime = Path(pcap).resolve(), Path(runtime).resolve()
    output = new_destination(output)
    if len(os.fsencode(str(output / "eve.sock"))) >= 108:
        raise PipelineError("Suricata Unix socket path is too long; use a shorter output directory")
    if not pcap.is_file() or pcap.stat().st_size < 25:
        raise PipelineError("A nonempty real PCAP is required")
    binary = runtime / "usr/bin/suricata"
    if not binary.is_file():
        raise PipelineError("Provide an extracted trusted Suricata runtime, not a system install")
    original = REPO_ROOT / "security-web/config/suricata/suricata.yaml"
    rules = REPO_ROOT / "security-web/suricata/pbl4.rules"
    config = yaml.safe_load(original.read_text())
    config["vars"]["address-groups"]["HOME_NET"] = "[127.0.0.0/8]"
    config["vars"]["port-groups"]["HTTP_PORTS"] = "18881"
    config["outputs"] = [
        {
            "eve-log": {
                "enabled": True,
                "filetype": "unix_stream",
                "filename": str(output / "eve.sock"),
                "types": [
                    {
                        "alert": {
                            "payload": False,
                            "packet": False,
                            "http-body": False,
                            "http-body-printable": False,
                        }
                    },
                    {"http": {"extended": True, "dump-all-headers": "response"}},
                    "flow",
                    {"stats": {"totals": True, "threads": False}},
                ],
            }
        }
    ]
    config["default-rule-path"] = str(rules.parent)
    config["rule-files"] = [str(rules)]
    config["classification-file"] = str(runtime / "etc/suricata/classification.config")
    config["reference-config-file"] = str(runtime / "etc/suricata/reference.config")
    config["unix-command"] = {"enabled": False}
    config["threshold-file"] = str(runtime / "etc/suricata/threshold.config")
    config.setdefault("detect", {})["sgh-mpm-caching"] = False
    config.setdefault("flow-timeouts", {}).setdefault("tcp", {})["closed"] = 60
    # Consumers reserve 65 seconds before using completed-flow context. Live
    # ingestion must additionally respect actual receipt time, never packet time alone.
    config["logging"] = {"default-log-level": "notice", "outputs": [{"console": {"enabled": True}}]}
    output.mkdir(mode=0o700)
    config["default-log-dir"] = str(output)
    target = output / "suricata.yaml"
    target.write_text("%YAML 1.1\n---\n" + yaml.safe_dump(config, sort_keys=False))
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = str(runtime / "usr/lib/x86_64-linux-gnu")
    command = [
        str(binary),
        "-c",
        str(target),
        "--runmode",
        "single",
        "-k",
        "none",
        "-r",
        str(pcap),
        "-l",
        str(output),
        "--set",
        "detect.profile=low",
        "--set",
        "max-pending-packets=1024",
    ]
    with (output / "eve.json").open("x") as destination:
        (output / "eve.json").chmod(0o600)
        server = _EveServer(str(output / "eve.sock"), _EveHandler)
        (output / "eve.sock").chmod(0o600)
        server.destination = destination
        server.query_numeric = query_numeric
        server.query_version = query_version
        server.request_structure = request_structure
        server.completed = threading.Event()
        server.failed = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (output / "decode.log").open("wb") as log:
                result = subprocess.run(command, env=env, stdout=log, stderr=log, timeout=300)
            if not server.completed.wait(10) or server.failed:
                raise PipelineError("Sensor stream redaction incomplete; output is not certified")
            destination.flush()
            os.fsync(destination.fileno())
        finally:
            server.shutdown()
            server.server_close()
            (output / "eve.sock").unlink(missing_ok=True)
    if result.returncode:
        raise PipelineError("Suricata offline decode failed; inspect private decode.log")
    counts, ids, sids = Counter(), set(), Counter()
    for line in (output / "eve.json").open():
        value = json.loads(line)
        counts[value["event_type"]] += 1
        rid = eve_request_id(value.get("http") or {})
        if rid:
            ids.add(rid)
        if value.get("alert"):
            sids[value["alert"]["signature_id"]] += 1
    if not counts["http"] or not counts["flow"]:
        raise PipelineError("Real HTTP and flow EVE are required; no synthetic replacement")
    for file in output.iterdir():
        if file.is_file():
            file.chmod(0o600)
    report = {
        "format_version": 1,
        "input_profile": "request-structure-v1"
        if request_structure
        else "safe_query_numeric_v2"
        if query_numeric and query_version == 2
        else "safe_query_numeric_v1"
        if query_numeric
        else "edge_masked_v1",
        "status": "PASS",
        "source": "offline real packet capture",
        "pcap_sha256": file_sha256(pcap),
        "eve_sha256": file_sha256(output / "eve.json"),
        "binary_sha256": file_sha256(binary),
        "config_sha256": file_sha256(target),
        "repository_config_sha256": file_sha256(original),
        "rules_sha256": file_sha256(rules),
        "event_counts": dict(counts),
        "request_ids": len(ids),
        "signature_counts": dict(sids),
        "checksum_validation": "disabled only for loopback capture/offload checksums",
        "http_headers": "response headers transiently through private Unix socket; only X-Request-Id persisted; query/UA redacted before disk; no body dump",
        "limits": [
            "Real TCP over loopback, not a production network benchmark",
            "Closed flow totals are available only after flow close; pipeline uses past completed client flow context",
        ],
    }
    if request_structure:
        from idps_ai.features.request_view import fingerprint

        report["request_structure_implementation_sha256"] = fingerprint()
    atomic_json(output / "decode-manifest.json", report)
    return report
