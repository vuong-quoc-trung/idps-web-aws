// Fixture-only regression. Compile the actual backend and call its real policy.
// This is not live inference evidence and never writes to an actuator or DB.
include!("../src/main.rs");

fn fixture_row(score: f64) -> serde_json::Value {
    serde_json::json!({
        "request_id":"0123456789abcdef0123456789abcdef",
        "rules":[{"id":7,"source":"NGINX","severity":3,"basis":"REQUEST_ID"}],
        "request_ai":{"status":"SCORED","model_version":"request-intelligence-v2-frozen-step3072",
            "manifest_sha256":"b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c",
            "feature_profile":"selected_headers_no_body","threshold":0.8826237916946411,
            "score":score,"event_id":"abcdef0123456789abcdef0123456789"},
        "correlation":{"status":"MATCHED","late_event":false}
    })
}

#[test]
fn policy_fixture_ai_changes_actual_rust_policy() {
    let config = hybrid::Config {
        approved_clients: vec!["10.203.17.2".into()],
        ..Default::default()
    };
    let low = fixture_row(0.1);
    let high = fixture_row(0.99);
    assert_eq!(low["rules"], high["rules"]);
    let a = hybrid::evaluate(&low, &config, false, Some("10.203.17.2"), 0, 0, true);
    let b = hybrid::evaluate(&high, &config, false, Some("10.203.17.2"), 0, 0, true);
    assert_eq!(a["policy_action"], "ALERT");
    assert_eq!(b["policy_action"], "REVIEW");
    assert_eq!(a["rule_risk_component"], b["rule_risk_component"]);
    assert_eq!(a["ai_risk_component"], 0);
    assert_eq!(b["ai_risk_component"], 10);
    assert_eq!(
        b["final_risk"].as_u64().unwrap(),
        a["final_risk"].as_u64().unwrap() + 10
    );
    assert_eq!(
        b,
        hybrid::evaluate(&high, &config, false, Some("10.203.17.2"), 0, 0, true)
    );
    let report = serde_json::json!({"state":"PASS","kind":"FIXTURE_ONLY_PRODUCTION_POLICY_COUNTERFACTUAL",
        "live_inference":false,"production_implementation":"security-web/src/hybrid.rs::evaluate",
        "held_constant":{"rules":low["rules"],"correlation":low["correlation"],"denials":0,
            "client_ip":"10.203.17.2","protected":false,"age_seconds":0,"worker_ready":true},
        "low":{"policy_inputs":low,"decision":a},"high":{"policy_inputs":high,"decision":b},
        "no_live_score_injection":true,"no_firewall_action":true});
    if let Ok(path) = std::env::var("IDPS_POLICY_EFFECT_REPORT") {
        let path = std::path::PathBuf::from(path);
        let temporary = path.with_extension("writing");
        std::fs::write(&temporary, serde_json::to_vec_pretty(&report).unwrap()).unwrap();
        std::fs::rename(temporary, path).unwrap();
    }
}

#[test]
fn policy_fixture_all_required_safety_scenarios() {
    let config = hybrid::Config {
        approved_clients: vec!["10.203.17.2".into()],
        ..Default::default()
    };
    let mut normal = fixture_row(0.1);
    normal["rules"] = serde_json::json!([]);
    assert_eq!(
        hybrid::evaluate(&normal, &config, false, Some("10.203.17.2"), 0, 0, true)["policy_action"],
        "LOG_ONLY"
    );
    normal["request_ai"]["score"] = serde_json::json!(0.99);
    assert_eq!(
        hybrid::evaluate(&normal, &config, false, Some("10.203.17.2"), 0, 0, true)["policy_action"],
        "ALERT"
    );
    let mut critical = fixture_row(0.1);
    critical["rules"][0]["severity"] = serde_json::json!(1);
    let failed = hybrid::evaluate(&critical, &config, false, Some("10.203.17.2"), 3, 0, false);
    assert_eq!(failed["policy_action"], "REVIEW");
    assert_eq!(failed["ai"]["signal"], "AI_UNAVAILABLE");
    critical["request_ai"]["score"] = serde_json::json!(0.99);
    assert_eq!(
        hybrid::evaluate(&critical, &config, false, Some("10.203.17.2"), 3, 0, true)["policy_action"],
        "PROPOSE_BLOCK"
    );
    for (protected, ip, age) in [
        (true, Some("10.203.17.2"), 0),
        (false, None, 0),
        (false, Some("10.203.17.2"), 121),
    ] {
        assert_ne!(
            hybrid::evaluate(&critical, &config, protected, ip, 3, age, true)["policy_action"],
            "PROPOSE_BLOCK"
        );
    }
    critical["correlation"]["late_event"] = serde_json::json!(true);
    let late = hybrid::evaluate(&critical, &config, false, Some("10.203.17.2"), 3, 0, true);
    assert_ne!(late["policy_action"], "PROPOSE_BLOCK");
    assert_eq!(
        late["http_timing"],
        "POST_OBSERVATION; no retroactive HTTP blocking"
    );
}
