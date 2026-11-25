"""Run the Rust development decision and existing R38 actuator in disposable namespaces."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("outer_network_namespace")
parser.add_argument("rust_test_binary", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
harness = Path(__file__).resolve().parents[1] / "local-r38/firewall_acceptance.py"
spec = importlib.util.spec_from_file_location("r38", harness)
r38 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r38)


def decide(peer, target):
    run = subprocess.run(
        [args.rust_test_binary.resolve(), "--ignored", "--exact",
         "hybrid_review::direct_peer_fixture", "--nocapture"],
        env=os.environ | {"WS_FIXTURE_PEER": peer, "WS_FIXTURE_TARGET": target},
        capture_output=True, text=True, check=True, timeout=5,
    )
    record, = [line.removeprefix("WS_DEV_REVIEW=") for line in run.stdout.splitlines()
               if line.startswith("WS_DEV_REVIEW=")]
    return json.loads(record)


r38.acceptance(args.outer_network_namespace, args.output, review_block=decide)
