import pytest

from idps_ai.data.split import temporal_groups


def test_temporal_split_never_shares_campaign_client_or_user():
    rows = [
        {
            "event_key": str(i),
            "timestamp": i * 1000.0,
            "campaign_key": f"campaign-{i}",
            "client_key": f"ip-{i}",
            "user_key": f"user-{i}",
            "session_key": None,
            "label": i % 2,
        }
        for i in range(15)
    ]
    assignment, report = temporal_groups(rows)
    partitions = {
        name: [r for r in rows if assignment[r["event_key"]][0] == name]
        for name in ("train", "val", "test")
    }
    assert max(r["timestamp"] for r in partitions["train"]) < min(
        r["timestamp"] for r in partitions["val"]
    )
    assert max(r["timestamp"] for r in partitions["val"]) < min(
        r["timestamp"] for r in partitions["test"]
    )
    assert report["embargo_seconds"] == 300
    for field in ("campaign_key", "client_key", "user_key"):
        assert not (
            {r[field] for r in partitions["train"]} & {r[field] for r in partitions["test"]}
        )
    for row in rows:
        row["client_key"] = "shared-nat"
    with pytest.raises(ValueError, match="group|partition"):
        temporal_groups(rows)
