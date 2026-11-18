"""Install on the already verified, private guest collector only."""

import hashlib
import json
import time

from context import category, encode, snapshot


def install(campaign):
    original = campaign.CampaignCapture

    class ContextCapture(original):
        def __init__(self, *args):
            super().__init__(*args)
            self.context_candidates = []
            self.context_versions = []
            self.context_seen = {}
            self.context_error = None
            self.context_category = "OTHER"
            self.context_method = "GET"
            self.context_first_clock = campaign.timing.clock_sample()

        def resolve(self, scenario, sent, wire):
            pending = list(self.pending)
            before = len(self.facts)
            super().resolve(scenario, sent, wire)
            if wire is None:
                return
            self.context_category = category(scenario["method"], scenario["path"])
            self.context_method = scenario["method"]
            for fact in self.facts[before:]:
                if fact["source"] != "A":
                    continue
                matches = [
                    row
                    for source, offset, _, row in pending
                    if source == "A" and offset == fact["byte_offset"]
                ]
                if len(matches) != 1:
                    self.context_error = "AUDIT_CONTEXT_AMBIGUITY"
                    continue
                try:
                    raw_sha = hashlib.sha256(
                        json.dumps(matches[0], sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    event_id = fact["native_event_id"]
                    if event_id in self.context_seen:
                        if self.context_seen[event_id] != raw_sha:
                            self.context_error = "AUDIT_CONTEXT_EVENT_CONFLICT"
                        continue  # identical duplicate is idempotent, never a new actor
                    self.context_seen[event_id] = raw_sha
                    value = snapshot(
                        matches[0],
                        fact,
                        wire.rid,
                        self.scope,
                        fact["receipt_offset_ns"],
                        time.monotonic_ns() - sent,
                    )
                    self.context_candidates.append(value)
                except ValueError as error:
                    self.context_error = str(error)
            if len(self.facts) != before and self.context_candidates:
                # Compute an ACTUAL 20-field vector while the collector and HTTP
                # client are running, not after the 3s diagnostic drain or Oracle.
                current = super().result(
                    sent, self.context_first_clock, campaign.timing.clock_sample()
                )
                observation = dict(self.context_candidates[0], request_key=current["request_key"])
                binding = self.binding(current, observation)
                encoded = encode(observation, binding)
                # Timestamp AFTER encoding. Changes to availability flags when S
                # arrives produce a new version; cutoff selects an immutable one.
                observation["available_offset_ns"] = time.monotonic_ns() - sent
                encoded = encode(observation, binding)
                completed = time.monotonic_ns() - sent
                observation["available_offset_ns"] = completed
                # Across-boundary completion must not retain an eligible vector.
                if completed > 999_000_000:
                    encoded = encode(observation, binding)
                self.context_versions.append(
                    {
                        "observation": observation,
                        "binding": binding,
                        "encoded": encoded,
                        "encoding_completed_offset_ns": completed,
                    }
                )

        def binding(self, result, observation):
            fact = next(
                (
                    e
                    for e in result["events"]
                    if e["source"] == "A"
                    and observation
                    and e["proof_sha256"] == observation["proof_sha256"]
                ),
                {},
            )
            return {
                "request_key": result["request_key"],
                "scope": self.scope,
                "event_id": fact.get("native_event_id"),
                "proof_sha256": fact.get("proof_sha256"),
                "identity_verified": result["identity_verified"],
                "clock_valid": result["clock_valid"],
                "source_mask": result["native_mask"],
                "category": self.context_category,
                "method": self.context_method,
                "disposition": "UNTRUSTED"
                if self.context_error or len(self.context_candidates) > 1
                else "AVAILABLE_BEFORE_CUTOFF",
            }

        def result(self, sent, first_clock, last_clock):
            result = super().result(sent, first_clock, last_clock)
            observations = [
                dict(o, request_key=result["request_key"]) for o in self.context_candidates
            ]
            observation = observations[0] if len(observations) == 1 else None
            binding = self.binding(result, observation)
            versions = [v for v in self.context_versions if v["binding"] == binding]
            early = [v for v in versions if v["encoding_completed_offset_ns"] <= 999_000_000]
            selected = (early or versions)[-1] if versions else None
            if selected:
                observation = selected["observation"]
            encoded = encode(observation, binding)
            if selected and encoded != selected["encoded"]:
                raise ValueError("Frozen context vector changed after cutoff")
            return result | {
                "trusted_context": {
                    "observation": observation,
                    "binding": binding,
                    "encoded": encoded,
                    "encoding_completed_offset_ns": selected["encoding_completed_offset_ns"]
                    if selected
                    else None,
                    "availability_timestamp_scope": "AFTER_ACTUAL_20_FIELD_ENCODING"
                    if selected
                    else "NO_MATCHING_IMMUTABLE_VERSION",
                    "source_event_sha256": list(self.context_seen.values()),
                    "projection_error": self.context_error,
                    "producer_phase": "AUDIT_COMPLETION_FOR_CURRENT_PROTECTED_GET_ONLY",
                    "owner_relationship": "GROUND_TRUTH_ONLY",
                    "session_history": "WITHHELD",
                    "no_cached_principal": True,
                }
            }

    campaign.CampaignCapture = ContextCapture
