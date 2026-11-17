"""Read allowlisted TRAIN transcripts only for external benign stress evaluation.

These corpora have synthetic publisher labels and unknown overlap with older
evaluation archives. They cannot establish independent attack recall or release.
Only aggregate numeric features and scores are persisted.
"""

import re
from pathlib import Path
from collections import Counter
import numpy as np
from idps_ai.common import REPO_ROOT, file_sha256, PipelineError
from idps_ai.data.http_benchmark import read_http
from idps_ai.features.request_time import from_request
from r16_waf import origin_view
from r23_features import numeric, sketch
from r25_features import lexical

SOURCES = {
    "csic_2010_normalTrafficTraining.txt": (
        "generalization_20261030/public-sources/csic_2010_normalTrafficTraining.txt",
        "d3344377d4721b03b906ca232ab44bfd81b9c1356f967ec9d348532ec420f000"),
    "xml_train.txt": (
        "request_view_20261030/public/xml_train.txt",
        "b4e85e85a315eb522f5175e11ed0d35d0e0aab5cd41c4618102b624772692a86"),
}


def source_path(name):
    if name not in SOURCES:
        raise ValueError("External role fence: only the two reviewed TRAIN files are allowed")
    relative, sha = SOURCES[name]
    path = REPO_ROOT / "ai-training/.artifacts" / relative
    if file_sha256(path) != sha:
        raise ValueError("External source digest changed")
    return path


def pkdd_requests(stream):
    state, identity = "start", None
    for line in stream:
        if len(line) > 65536:
            raise ValueError("PKDD line bound")
        if line.startswith(b"Start - Id: "):
            if state != "start":
                raise ValueError("Nested PKDD record")
            identity = line[12:].strip()
            state = "class"
        elif state == "class":
            if line.strip() != b"class: Valid":
                raise ValueError("PKDD TRAIN label is not publisher Valid")
            state = "request"
        elif state == "request":
            match = re.fullmatch(rb"([A-Z]+) (.{1,8192}) HTTP/[0-9]\.[0-9]\r?\n",line)
            if not match:
                raise ValueError("PKDD request envelope invalid")
            yield match[1].decode("ascii"), match[2].decode("latin-1")
            state = "body"
        elif line.startswith(b"End - Id: "):
            if state != "body" or line[10:].strip() != identity:
                raise ValueError("PKDD record identity mismatch")
            state = "start"
    if state != "start":
        raise ValueError("PKDD truncated record")


def load(name):
    path=source_path(name)
    vectors=[]; methods=[]; tally=Counter(); identities=set()
    def project(method,target):
        tally["raw_records"]+=1
        origin=origin_view(target)
        if origin is None:
            tally["unsupported_target"]+=1
            return
        try:
            target=origin[0]
            base=from_request(target,method)
            shape=numeric(*sketch(target))[0].astype(np.float32)/31
            vectors.append(np.r_[base,shape,lexical(target)].astype(np.float32))
            methods.append(0 if method=="GET" else 1 if method=="POST" else 2)
        except PipelineError:
            tally["unsupported_envelope"]+=1
    with path.open("rb") as f:
        if name == "xml_train.txt":
            for method,target in pkdd_requests(f):
                project(method,target)
        else:
            def callback(target,method,agent):
                project(method,target)
                return {"numbers": {}}
            for row in read_http(f,projector=callback):
                identities.add(row["event_key"])
    x=np.asarray(vectors,np.float32)
    report={
        "filename":name,"source_sha256":SOURCES[name][1],"role":"PUBLISHER_BENIGN_TRAIN_STRESS_ONLY",
        "label":"normal" if name.startswith("csic") else "Valid",
        "records":dict(tally),"projected":len(x),"unique_uri76":len(np.unique(x[:,:76],axis=0)),
        "unique_uri100":len(np.unique(x[:,:100],axis=0)),"unique_uri132":len(np.unique(x,axis=0)),
        "exact_original_identity_count":len(identities) if identities else None,
        "independent_dual_class_acceptance":False,"protected_roles_read":False,
        "missing_capabilities":["attack-labelled allowed TRAIN","native request-bound review","clock/campaign chronology"],
    }
    return x,np.asarray(methods,np.uint8),report
