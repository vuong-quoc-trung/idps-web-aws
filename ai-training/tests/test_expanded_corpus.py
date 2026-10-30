from idps_ai.data.campaigns import campaign_plan


def test_expanded_probe_and_hard_negative_identities_are_disjoint_across_temporal_bands():
    from idps_ai.data.campaigns import VIEWS
    from idps_ai.data.scenario_data import BENIGN_VIEWS, expanded_payload, payload_identity

    seen = set()
    for band in range(3):
        identities = {
            payload_identity(f, expanded_payload(f, band, v, base))
            for f, base in VIEWS.items()
            for v in range(16)
        }
        identities.update(payload_identity("hard_negative", v) for v in BENIGN_VIEWS[band])
        assert not identities & seen
        assert len(identities) == 76
        seen.update(identities)


def test_expanded_campaign_has_seeded_independent_nonuniform_timing_and_16_views():
    a = campaign_plan(0, 1536, 480, campaign_index=0, diverse=True, expanded=True, seed=712)
    b = campaign_plan(0, 1536, 480, campaign_index=1, diverse=True, expanded=True, seed=712)
    assert a == campaign_plan(0, 1536, 480, campaign_index=0, diverse=True, expanded=True, seed=712)
    assert [r["family"] for r in a] != [r["family"] for r in b]
    assert len(a) == 1536 and a[-1]["at_seconds"] >= 479
    assert {r["view"] for r in a if r["family"] == "sqli"} == set(range(16))
    gaps = [a[i + 1]["at_seconds"] - a[i]["at_seconds"] for i in range(len(a) - 1)]
    assert max(gaps) > 1 and min(gaps) < 0.05
