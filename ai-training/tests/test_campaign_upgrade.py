from collections import Counter

from idps_ai.data.campaigns import campaign_plan


def test_diverse_campaigns_have_independent_order_and_at_least_eight_views_per_family():
    a = campaign_plan(0, 1536, 480, campaign_index=1, diverse=True)
    b = campaign_plan(0, 1536, 480, campaign_index=2, diverse=True)
    assert [r["family"] for r in a] != [r["family"] for r in b]
    assert len(a) == len(b) == 1536
    assert a[-1]["at_seconds"] >= 479
    counts = Counter(r["family"] for r in a)
    assert all(counts[f] == 64 for f in counts if f != "benign")
    for family in ("sqli", "xss", "path_traversal", "cmd_injection"):
        assert {r["view"] for r in a if r["family"] == family} == set(range(8))
    assert any(r["scenario"] == "benign_authorized_batch" for r in a)
    assert any(r["scenario"] == "benign_public" for r in a)


def test_owned_lab_cli_explicitly_selects_a_larger_capture_without_reusing_old_defaults():
    from idps_ai.cli import parser

    args = parser().parse_args(
        ["lab-start", "--output", "new-lab", "--nginx-bin", "/usr/sbin/nginx", "--campaigns", "30"]
    )
    assert args.campaigns == 30
