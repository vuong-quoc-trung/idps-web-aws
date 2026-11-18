# isort: skip_file

"""R26.1 paths and immutable parent binding helpers."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "quality-acceleration-r26"))

from r26_common import ARTIFACTS, check, file_sha256, read, status  # noqa: E402, F401
from idps_ai.common import atomic_json  # noqa: E402, F401

PARENT = ARTIFACTS / "t09-r26-acceleration-zfyPqyt3"


def output_arg():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    return parser.parse_args().out


def record(out, name, value):
    atomic_json(out / name, value)
    print(json.dumps({"artifact": name}), flush=True)
