#!/usr/bin/env python3
"""Validate independent review artifacts and bind decisions to actual requests."""

import argparse
import json

from idps_ai.common import PipelineError
from idps_ai.data.dataset import verify_dataset
from idps_ai.data.label_evidence import audit_label_evidence
from idps_ai.data.provenance import verify_provenance

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        proof = verify_provenance(args.provenance)
        if proof["dataset_sha256"] != verify_dataset(args.dataset)["dataset_sha256"]:
            raise PipelineError("Review provenance belongs to another dataset")
        result = audit_label_evidence(
            args.review, args.dataset, proof["provenance_sha256"], args.environment_id, args.output
        )
        print(json.dumps(result, sort_keys=True))
    except PipelineError as error:
        parser.exit(2, str(error) + "\n")
