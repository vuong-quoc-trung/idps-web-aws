//! The HTTPS research slot can contribute an observation or advisory alert only.
use crate::*;
use serde_json::{Value, json};
use std::sync::LazyLock;

static SLOTS: LazyLock<Value> = LazyLock::new(|| {
    serde_json::from_str(include_str!(
        "../../ai-training/contracts/quality-freeze-r37/slots.json"
    ))
    .expect("compiled release registry")
});

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Observation {
    request_id: String,
    version: String,
    model_sha256: String,
    schema: String,
    dispatch_ns: i64,
    receipt_ns: i64,
    available_ns: i64,
    cutoff_ns: i64,
    guard_ns: i64,
    status: String,
    score: Option<f64>,
    threshold: f64,
    enforcement: bool,
}

fn parse(raw: &[u8]) -> Result<Observation> {
    let r: Observation = serde_json::from_slice(raw)?;
    let valid_slot = SLOTS["slots"].as_object().unwrap().values().any(|s| {
        s["version"] == r.version
            && s["sha256"] == r.model_sha256
            && s["threshold"].as_f64() == Some(r.threshold)
    });
    anyhow::ensure!(
        valid_slot
            && !r.enforcement
            && SLOTS["abi"] == r.schema
            && r.request_id.len() == 32
            && r.request_id
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
            && r.guard_ns == 1_000_000
            && r.dispatch_ns > 0
            && r.dispatch_ns.checked_add(1_000_000_000) == Some(r.cutoff_ns),
        "Invalid research identity, release or clock"
    );
    match r.status.as_str() {
        "SCORED" => anyhow::ensure!(
            r.score.is_some_and(|s| (0.0..=1.0).contains(&s))
                && r.dispatch_ns <= r.receipt_ns
                && r.receipt_ns <= r.available_ns
                && r.available_ns <= r.cutoff_ns - r.guard_ns
                && r.available_ns <= Utc::now().timestamp_nanos_opt().unwrap_or(0) + 1_000_000,
            "Invalid score availability"
        ),
        "ABSTAIN" | "CONFLICT" | "INFERENCE_ERROR" => {
            anyhow::ensure!(r.score.is_none(), "Unusable score")
        }
        _ => anyhow::bail!("Unknown research state"),
    }
    Ok(r)
}

pub async fn ingest(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    key: &str,
    raw: &[u8],
) -> Result<()> {
    let Ok(r) = parse(raw) else {
        sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,'HTTPS_RESEARCH','Invalid research observation') ON CONFLICT DO NOTHING").bind(key).execute(&mut **tx).await?;
        return Ok(());
    };
    sqlx::query("INSERT INTO https_research_observations(request_id,observation,conflicted) VALUES($1,$2,$3) ON CONFLICT(request_id) DO UPDATE SET conflicted=true WHERE NOT https_research_observations.conflicted AND (https_research_observations.observation<>EXCLUDED.observation OR EXCLUDED.conflicted)")
        .bind(&r.request_id).bind(serde_json::to_value(&r)?).bind(r.status=="CONFLICT").execute(&mut **tx).await?;
    Ok(())
}

pub fn current_result(value: &Value) -> bool {
    let slot = &SLOTS["slots"]["candidate"];
    value["model_id"] == slot["version"] && value["model_sha256"] == slot["sha256"]
}

pub fn advisory(row: &Value) -> Option<Value> {
    let v = &row["https_research"];
    if v.is_null() {
        return None;
    }
    let scored = v["status"] == "SCORED"
        && v["request_id"] == row["request_id"]
        && row["correlation"]["status"] != "AMBIGUOUS"
        && row["status"] != "UNCERTAIN_CORRELATION";
    let high = scored
        && v["score"]
            .as_f64()
            .zip(v["threshold"].as_f64())
            .is_some_and(|(s, t)| s > t);
    let status = if scored {
        "SCORED"
    } else if v["status"] == "INFERENCE_ERROR" {
        "INFERENCE_ERROR"
    } else {
        "ABSTAIN"
    };
    Some(
        json!({"request_id":row["request_id"],"model_id":v["version"],"model_sha256":v["model_sha256"],
        "status":status, "score":if scored {v["score"].clone()} else {Value::Null},
        "threshold":v["threshold"],"signal":if !scored {"ABSTAIN"} else if high {"PUBLISHER_ABOVE"} else {"PUBLISHER_BELOW"},
        "action":if high {"ALERT"} else {"LOG_ONLY"},"enforcement":false}),
    )
}

#[derive(Deserialize)]
pub struct ReportQuery {
    request_id: Option<String>,
}

pub async fn report(
    State(state): State<AppState>,
    Query(query): Query<ReportQuery>,
) -> Result<Json<Value>, ApiError> {
    let slot = &SLOTS["slots"]["candidate"];
    let version = slot["version"]
        .as_str()
        .expect("compiled candidate version");
    let digest = slot["sha256"].as_str().expect("compiled candidate digest");
    if let Some(request_id) = query.request_id {
        if request_id.len() != 32
            || !request_id
                .bytes()
                .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        {
            return Err(bad_request("Request ID không hợp lệ"));
        }
        let result: Option<Value> = sqlx::query_scalar(include_str!("ai_lookup.sql"))
            .bind(request_id)
            .bind(version)
            .bind(digest)
            .fetch_optional(&state.pool)
            .await
            .map_err(api_error)?;
        return Ok(Json(json!({"result": result})));
    }
    let summary: Value = sqlx::query_scalar(include_str!("ai_report.sql"))
        .bind(version)
        .bind(digest)
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
    let operations = operations::snapshot().await;
    Ok(Json(json!({
        "summary":summary, "service":operations["services"]["r37"], "sampled_at":operations["sampled_at"],
    })))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[sqlx::test(migrations = "./migrations")]
    async fn recent_report_distinguishes_bound_results_and_unresolved_requests(pool: PgPool) {
        let slot = &SLOTS["slots"]["candidate"];
        for (i, status, score) in [
            (1, "SCORED", json!(0.9)),
            (2, "INFERENCE_ERROR", Value::Null),
            (3, "ABSTAIN", Value::Null),
            (4, "CONFLICT", Value::Null),
        ] {
            sqlx::query("INSERT INTO https_research_observations(request_id,observation,conflicted) VALUES($1,$2,$3)")
                .bind(format!("{i:032x}")).bind(json!({"version":slot["version"],"model_sha256":slot["sha256"],
                    "status":status,"score":score,"threshold":slot["threshold"]})).bind(status=="CONFLICT")
                .execute(&pool).await.unwrap();
        }
        for (i, expected) in [(1, true), (5, true), (6, false)] {
            let rid = format!("{i:032x}");
            sqlx::query("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,event_type,canonical) VALUES($1,'1.0','NGINX','fixture',$1,now(),$1,'http',$2)")
                .bind(rid).bind(json!({"schema_version":"1.0","ai_projection":expected})).execute(&pool).await.unwrap();
        }
        let report: Value = sqlx::query_scalar(include_str!("ai_report.sql"))
            .bind(slot["version"].as_str().unwrap())
            .bind(slot["sha256"].as_str().unwrap())
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(report["eligible"], 5);
        for key in [
            "scored",
            "anomalous",
            "pending",
            "abstained",
            "conflicts",
            "inference_errors",
        ] {
            assert_eq!(report[key], 1, "{key}");
        }
        assert_eq!(report["recent"].as_array().unwrap().len(), 5);
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn lookup_requires_active_digest_and_matching_hybrid(pool: PgPool) {
        let candidate = &SLOTS["slots"]["candidate"];
        let rollback = &SLOTS["slots"]["rollback"];
        for (id, slot) in [("a".repeat(32), candidate), ("b".repeat(32), rollback)] {
            sqlx::query("INSERT INTO https_research_observations(request_id,observation) VALUES($1,$2)")
                .bind(&id).bind(json!({"version":slot["version"],"model_sha256":slot["sha256"],"status":"SCORED","score":0.42}))
                .execute(&pool).await.unwrap();
            sqlx::query("INSERT INTO hybrid_incidents(request_id,evidence_fingerprint,policy_version,observed_at,decision) VALUES($1,'fixture','fixture',now(),$2)")
                .bind(id).bind(json!({"policy_action":"LOG_ONLY","https_research":{"model_id":slot["version"],"model_sha256":slot["sha256"]}}))
                .execute(&pool).await.unwrap();
        }
        let lookup = |key: String| {
            sqlx::query_scalar::<_, Value>(include_str!("ai_lookup.sql"))
                .bind(key)
                .bind(candidate["version"].as_str().unwrap())
                .bind(candidate["sha256"].as_str().unwrap())
        };
        let current = lookup("a".repeat(32)).fetch_one(&pool).await.unwrap();
        assert_eq!(
            current,
            json!({"request_id":"a".repeat(32),"status":"SCORED","score":0.42,"hybrid":"LOG_ONLY"})
        );
        assert!(
            lookup("b".repeat(32))
                .fetch_optional(&pool)
                .await
                .unwrap()
                .is_none()
        );
        sqlx::query("UPDATE hybrid_incidents SET decision=decision-'https_research'")
            .execute(&pool)
            .await
            .unwrap();
        assert!(lookup("a".repeat(32)).fetch_one(&pool).await.unwrap()["hybrid"].is_null());
    }

    #[test]
    fn r36_pinned_request_time_and_observation_only() {
        let s = &SLOTS["slots"]["candidate"];
        let now = Utc::now().timestamp_nanos_opt().unwrap();
        let rid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        let mut e = json!({"request_id":rid,"version":s["version"],"model_sha256":s["sha256"],"schema":SLOTS["abi"],
            "dispatch_ns":now-2_000_000,"receipt_ns":now-1_000_000,"available_ns":now,
            "cutoff_ns":now+998_000_000,"guard_ns":1_000_000,"status":"SCORED",
            "threshold":s["threshold"],"score":1.,"enforcement":false});
        let valid = |v: &Value| parse(&serde_json::to_vec(v).unwrap()).is_ok();
        assert!(valid(&e));
        let mut row = json!({"request_id":rid,"https_research":e,"correlation":{"status":"MATCHED","late_event":false}});
        let policy = |r: &Value| {
            crate::hybrid::evaluate(
                r,
                &crate::hybrid::Config::default(),
                false,
                Some("192.0.2.10"),
                0,
                0,
                true,
            )
        };
        let d = policy(&row);
        assert_eq!(d["ai"]["model_id"], s["version"]);
        assert_eq!(d["policy_action"], "ALERT");
        assert_eq!(d["ai_risk_component"], 0);
        let reasons = d["policy_reason"].as_array().unwrap();
        assert!(reasons.contains(&json!("REQUEST_BOUND_HTTPS_AI_ADVISORY")));
        assert!(!reasons.contains(&json!("AI_UNAVAILABLE_OR_FEATURE_UNSUPPORTED")));
        assert_eq!(d["automatic_block"], false);
        row["correlation"]["status"] = json!("AMBIGUOUS");
        assert_eq!(policy(&row)["ai"]["status"], "ABSTAIN");
        for (key, bad) in [
            ("enforcement", json!(true)),
            ("model_sha256", json!("deadbeef")),
            ("threshold", json!(-1)),
            ("available_ns", e["cutoff_ns"].clone()),
        ] {
            let mut invalid = e.clone();
            invalid[key] = bad;
            assert!(!valid(&invalid));
        }
        e["status"] = json!("ABSTAIN");
        e["score"] = Value::Null;
        assert!(valid(&e));
    }
}
