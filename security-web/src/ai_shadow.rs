//! Read-only observation boundary: never calls policy evaluation or firewall.
use crate::*;
use serde_json::{Value, json};

const MODEL: &str = "request-intelligence-v2-frozen-step3072";
const THRESHOLD: f64 = 0.8826237916946411;
const MANIFEST: &str = "b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Availability {
    uri_observed: bool,
    headers_observed: bool,
    headers_complete: bool,
    body_observed: bool,
    numeric_dropped_query_fields: u64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Metrics {
    processed: u64,
    rejected: u64,
    queue_dropped: u64,
    inference_errors: u64,
    queue_depth: u64,
    cpu_temperature_c: Option<f64>,
    system_used_bytes: u64,
    worker_rss_bytes: u64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema_version: String,
    kind: String,
    event_id: String,
    worker_id: String,
    request_id: Option<String>,
    observed_at: DateTime<Utc>,
    model_version: String,
    manifest_sha256: String,
    threshold: f64,
    score: Option<f64>,
    above_threshold: Option<bool>,
    status: String,
    mode: String,
    enforcement_actions: u64,
    latency_ms: Option<f64>,
    feature_availability: Option<Availability>,
    telemetry_source: String,
    feature_profile: String,
    metrics: Metrics,
}

fn opaque(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

fn decode(raw: &[u8]) -> Result<Record> {
    let r: Record = serde_json::from_slice(raw).context("Invalid AI metadata")?;
    anyhow::ensure!(
        r.schema_version == "ai-shadow-1"
            && r.model_version == MODEL
            && r.manifest_sha256 == MANIFEST
            && r.threshold == THRESHOLD
            && r.mode == "shadow"
            && r.enforcement_actions == 0
            && r.telemetry_source == "NGINX_UNIX_SYSLOG"
            && r.feature_profile == "selected_headers_no_body"
            && opaque(&r.event_id)
            && opaque(&r.worker_id),
        "AI identity/contract mismatch"
    );
    anyhow::ensure!(
        r.observed_at <= Utc::now() + chrono::Duration::seconds(30),
        "Future AI event"
    );
    anyhow::ensure!(r.metrics.queue_depth <= 64, "Invalid queue metric");
    anyhow::ensure!(
        r.metrics
            .cpu_temperature_c
            .is_none_or(|t| t.is_finite() && (0.0..130.0).contains(&t)),
        "Invalid temperature"
    );
    if r.kind == "inference" {
        anyhow::ensure!(
            r.request_id.as_deref().is_some_and(opaque),
            "Missing correlation"
        );
        if r.status == "SCORED" {
            anyhow::ensure!(
                r.score
                    .is_some_and(|s| s.is_finite() && (0.0..=1.0).contains(&s)),
                "Invalid score"
            );
            anyhow::ensure!(
                r.above_threshold == r.score.map(|s| s > THRESHOLD),
                "Threshold mismatch"
            );
            anyhow::ensure!(
                r.latency_ms
                    .is_some_and(|v| v.is_finite() && (0.0..=60_000.0).contains(&v)),
                "Invalid latency"
            );
            let a = r
                .feature_availability
                .as_ref()
                .context("Missing availability")?;
            anyhow::ensure!(
                a.uri_observed && a.headers_observed && !a.headers_complete && !a.body_observed,
                "Invalid availability"
            );
        } else {
            anyhow::ensure!(
                r.status == "INFERENCE_ERROR"
                    && r.score.is_none()
                    && r.above_threshold.is_none()
                    && r.latency_ms.is_none()
                    && r.feature_availability.is_none(),
                "Invalid inference status"
            );
        }
    } else {
        anyhow::ensure!(
            r.kind == "heartbeat"
                && r.request_id.is_none()
                && r.score.is_none()
                && r.above_threshold.is_none()
                && r.latency_ms.is_none()
                && r.feature_availability.is_none(),
            "Invalid heartbeat"
        );
        anyhow::ensure!(
            [
                "STARTING",
                "READY",
                "THERMAL_PAUSED",
                "THERMAL_STOP",
                "RAM_STOP",
                "THERMAL_CONTROL_NOT_VERIFIED",
                "MODEL_UNAVAILABLE",
                "STOPPED"
            ]
            .contains(&r.status.as_str()),
            "Invalid worker status"
        );
    }
    Ok(r)
}

pub async fn ingest(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    key: &str,
    raw: &[u8],
) -> Result<()> {
    let r = match decode(raw) {
        Ok(r) => r,
        Err(_) => {
            sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,'AI_SHADOW','AI metadata rejected; raw content suppressed') ON CONFLICT DO NOTHING")
                .bind(key).execute(&mut **tx).await?;
            return Ok(());
        }
    };
    let safe = serde_json::to_value(&r)?;
    if r.kind == "heartbeat" {
        sqlx::query("INSERT INTO ai_shadow_worker(singleton,observed_at,report) VALUES(true,$1,$2) ON CONFLICT(singleton) DO UPDATE SET observed_at=$1,report=$2,received_at=now() WHERE ai_shadow_worker.observed_at <= $1")
            .bind(r.observed_at).bind(safe).execute(&mut **tx).await?;
    } else {
        let inserted = sqlx::query("INSERT INTO ai_shadow_results(event_id,request_id,observed_at,result) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING")
            .bind(&r.event_id).bind(&r.request_id).bind(r.observed_at).bind(&safe).execute(&mut **tx).await?.rows_affected();
        if inserted == 1 && r.above_threshold == Some(true) {
            // No client IP/auto response candidate is passed through this path.
            sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,rule_name,category,severity,action,evidence,event_key) VALUES($1,'AI_SHADOW','ai_observation','AI: Request Intelligence v2 research threshold','AI research score',3,'ALERT',$2,$3) ON CONFLICT(event_key) DO NOTHING")
                .bind(r.observed_at).bind(safe.to_string()).bind(format!("AI:{}", r.request_id.as_deref().unwrap())).execute(&mut **tx).await?;
        }
    }
    Ok(())
}

#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageQuery {
    request_id: Option<String>,
    limit: Option<i64>,
}

pub async fn list(
    State(state): State<AppState>,
    Query(q): Query<PageQuery>,
) -> Result<Json<Value>, ApiError> {
    if q.request_id.as_deref().is_some_and(|id| !opaque(id))
        || !(1..=200).contains(&q.limit.unwrap_or(50))
    {
        return Err(bad_request("Invalid request ID or limit"));
    }
    let worker: Option<Value> = sqlx::query_scalar("SELECT report || jsonb_build_object('received_at',received_at,'stale',received_at < now()-interval '10 seconds' OR observed_at < now()-interval '10 seconds') FROM ai_shadow_worker WHERE singleton")
        .fetch_optional(&state.pool).await.map_err(api_error)?;
    let items: Vec<Value> = sqlx::query_scalar("SELECT r.result || jsonb_build_object('id',r.id,'correlated_sources',COALESCE((SELECT jsonb_agg(DISTINCT n.source) FROM normalized_events n WHERE n.request_id=r.request_id),'[]'::jsonb)) FROM ai_shadow_results r WHERE ($1::text IS NULL OR r.request_id=$1) ORDER BY r.observed_at DESC,r.id DESC LIMIT $2")
        .bind(q.request_id.as_deref()).bind(q.limit.unwrap_or(50)).fetch_all(&state.pool).await.map_err(api_error)?;
    let delivery: Value = sqlx::query_scalar(include_str!("ai_delivery.sql"))
        .bind(state.ingestion.collect_all)
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
    let correlation =
        three_source::list(&state.pool, q.request_id.as_deref(), q.limit.unwrap_or(50))
            .await
            .map_err(api_error)?;
    Ok(Json(
        json!({"items": items, "worker": worker, "delivery": delivery, "three_source":correlation, "mode": "shadow", "enforcement": "DISABLED", "GLU207": "CONTRACT_GATED_PER_REQUEST", "quality_scope": "Research score, not attack probability or Ground Truth"}),
    ))
}

pub async fn prune(state: &AppState) -> Result<()> {
    sqlx::query("DELETE FROM ai_shadow_results WHERE created_at < now()-interval '7 days' OR id IN (SELECT id FROM ai_shadow_results ORDER BY id DESC OFFSET 10000)")
        .execute(&state.pool).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scored(score: f64) -> Value {
        json!({
            "schema_version":"ai-shadow-1","kind":"inference",
            "event_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","worker_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "request_id":"cccccccccccccccccccccccccccccccc","observed_at":Utc::now(),
            "model_version":MODEL,"manifest_sha256":MANIFEST,"threshold":THRESHOLD,
            "score":score,"above_threshold":score>THRESHOLD,"status":"SCORED",
            "mode":"shadow","enforcement_actions":0,"latency_ms":1.5,
            "feature_availability":{"uri_observed":true,"headers_observed":true,"headers_complete":false,"body_observed":false,"numeric_dropped_query_fields":0},
            "telemetry_source":"NGINX_UNIX_SYSLOG","feature_profile":"selected_headers_no_body",
            "metrics":{"processed":1,"rejected":0,"queue_dropped":0,"inference_errors":0,"queue_depth":0,"cpu_temperature_c":50.0,"system_used_bytes":1000000000_u64,"worker_rss_bytes":100000000}
        })
    }

    #[test]
    fn rejects_forged_threshold_enforcement_raw_fields_and_version() {
        let good = scored(THRESHOLD);
        assert!(decode(&serde_json::to_vec(&good).unwrap()).is_ok());
        for (key, value) in [
            ("threshold", json!(0.5)),
            ("above_threshold", json!(true)),
            ("enforcement_actions", json!(1)),
            ("raw_request", json!("CANARY_SECRET")),
            ("model_version", json!("challenger")),
        ] {
            let mut bad = good.clone();
            bad[key] = value;
            assert!(decode(&serde_json::to_vec(&bad).unwrap()).is_err(), "{key}");
        }
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn ai_results_are_idempotent_alert_only_and_bounded_to_metadata(pool: PgPool) {
        let mut tx = pool.begin().await.unwrap();
        let raw = serde_json::to_vec(&scored(0.99)).unwrap();
        ingest(&mut tx, "physical-1", &raw).await.unwrap();
        ingest(&mut tx, "physical-2", &raw).await.unwrap();
        let mut bad = scored(0.99);
        bad["raw_request"] = json!("CANARY_SECRET");
        ingest(&mut tx, "physical-3", &serde_json::to_vec(&bad).unwrap())
            .await
            .unwrap();
        tx.commit().await.unwrap();
        for (table, expected) in [
            ("ai_shadow_results", 1_i64),
            ("security_alerts", 1),
            ("firewall_actions", 0),
            ("ingestion_errors", 1),
        ] {
            let count: i64 = sqlx::query_scalar(&format!("SELECT count(*) FROM {table}"))
                .fetch_one(&pool)
                .await
                .unwrap();
            assert_eq!(count, expected, "{table}");
        }
        let evidence: String = sqlx::query_scalar(
            "SELECT evidence FROM security_alerts WHERE source='AI_SHADOW' AND action='ALERT'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert!(!evidence.contains("CANARY_SECRET"));
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn delivery_counts_missing_and_pending_without_claiming_lossless(pool: PgPool) {
        let mut tx = pool.begin().await.unwrap();
        ingest(
            &mut tx,
            "one-score",
            &serde_json::to_vec(&scored(0.1)).unwrap(),
        )
        .await
        .unwrap();
        tx.commit().await.unwrap();
        for (id, age) in [
            ("cccccccccccccccccccccccccccccccc", 30),
            ("dddddddddddddddddddddddddddddddd", 30),
            ("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", 0),
        ] {
            sqlx::query("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,event_type,uri_path,canonical) VALUES($1,'1.0','NGINX','delivery-test',$1,now()-$2::int*interval '1 second',$1,'http_request','/api/auth/csrf','{\"schema_version\":\"1.0\"}'::jsonb)")
                .bind(id).bind(age).execute(&pool).await.unwrap();
        }
        let value: Value = sqlx::query_scalar(include_str!("ai_delivery.sql"))
            .bind(true)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(value["nginx_observed_requests"], 2);
        assert_eq!(value["scored"], 1);
        assert_eq!(value["unresolved_after_grace"], 1);
        assert!(value["scope"].as_str().unwrap().contains("Not a measured"));
    }
}
