//! Strict metadata-only boundary, independent from RIv2 and enforcement.
use crate::*;
use serde_json::{Value, json};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Glu {
    model_version: String,
    score: f64,
    threshold: f64,
    above_threshold: bool,
    feature_count: u16,
    feature_sha256: String,
    latency_ms: f64,
    flow_observed: bool,
    context_incomplete: bool,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema_version: String,
    request_id: String,
    sensor_instance: String,
    observed_at: DateTime<Utc>,
    status: String,
    sources: Vec<String>,
    flow_id: Option<String>,
    tx_id: Option<u64>,
    duplicate_events: u64,
    flow_context_alerts: u64,
    late_event: bool,
    basis: String,
    proof_sha256: String,
    glu: Option<Glu>,
    enforcement_actions: u64,
}
fn hex(s: &str, n: usize) -> bool {
    s.len() == n
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn decode(raw: &[u8]) -> Result<Record> {
    let r: Record = serde_json::from_slice(raw)?;
    anyhow::ensure!(
        r.schema_version == "three-source-1"
            && hex(&r.request_id, 32)
            && hex(&r.sensor_instance, 32)
            && r.enforcement_actions == 0,
        "Invalid correlation identity"
    );
    anyhow::ensure!(hex(&r.proof_sha256, 64), "Invalid proof digest");
    anyhow::ensure!(
        r.tx_id.is_none_or(|n| n <= i64::MAX as u64),
        "Transaction ID outside database range"
    );
    anyhow::ensure!(
        r.observed_at <= Utc::now() + chrono::Duration::seconds(30),
        "Future observation"
    );
    anyhow::ensure!(
        ["MATCHED", "MISSING_SOURCE", "AMBIGUOUS"].contains(&r.status.as_str()),
        "Invalid state"
    );
    anyhow::ensure!(
        [
            "NO_IP_TIME_MATCH",
            "EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY",
            "RESPONSE_ID_CONFLICTING_HTTP_FIELDS"
        ]
        .contains(&r.basis.as_str()),
        "Invalid basis"
    );
    let sources: std::collections::BTreeSet<_> = r.sources.iter().map(String::as_str).collect();
    anyhow::ensure!(
        sources.len() == r.sources.len()
            && sources
                .iter()
                .all(|s| ["NGINX", "STUDENT_AUDIT", "SURICATA"].contains(s)),
        "Invalid sources"
    );
    anyhow::ensure!(
        r.flow_id.as_ref().is_none_or(|s| !s.is_empty()
            && s.len() <= 20
            && s.bytes().all(|c| c.is_ascii_digit())),
        "Invalid flow ID"
    );
    if r.status == "MATCHED" {
        anyhow::ensure!(
            sources.len() == 3
                && r.tx_id.is_some()
                && r.flow_id.is_some()
                && r.basis == "EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY",
            "Unsupported match"
        );
    }
    if let Some(g) = &r.glu {
        anyhow::ensure!(
            r.status == "MATCHED"
                && !r.late_event
                && g.model_version == "glu207-step652-e663b0979f6f"
                && g.feature_count == 207
                && hex(&g.feature_sha256, 64)
                && g.score.is_finite()
                && (0.0..=1.0).contains(&g.score)
                && g.threshold == 0.5396780371665955
                && g.above_threshold == (g.score >= g.threshold)
                && g.latency_ms.is_finite()
                && (0.0..=120000.0).contains(&g.latency_ms),
            "Invalid frozen GLU contract"
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
        Ok(v) => v,
        Err(_) => {
            sqlx::query("INSERT INTO ingestion_errors(event_key,source,reason) VALUES($1,'THREE_SOURCE','invalid correlation metadata; raw suppressed') ON CONFLICT DO NOTHING").bind(key).execute(&mut **tx).await?;
            return Ok(());
        }
    };
    if r.glu.is_some() {
        sqlx::query("INSERT INTO glu207_shadow_results(request_id,proof_sha256,result) VALUES($1,$2,$3) ON CONFLICT DO NOTHING").bind(&r.request_id).bind(&r.proof_sha256).bind(serde_json::to_value(&r)?).execute(&mut **tx).await?;
        sqlx::query("DELETE FROM glu207_shadow_results WHERE created_at<now()-interval '7 days' OR (request_id,proof_sha256) IN (SELECT request_id,proof_sha256 FROM glu207_shadow_results ORDER BY created_at DESC OFFSET 10000)").execute(&mut **tx).await?;
        return Ok(());
    }
    sqlx::query("INSERT INTO request_correlations(request_id,observed_at,result) VALUES($1,$2,$3) ON CONFLICT(request_id) DO UPDATE SET observed_at=excluded.observed_at,received_at=now(),result=excluded.result WHERE request_correlations.observed_at<=excluded.observed_at")
 .bind(&r.request_id).bind(r.observed_at).bind(serde_json::to_value(&r)?).execute(&mut **tx).await?;
    sqlx::query("DELETE FROM request_correlations WHERE received_at<now()-interval '7 days' OR request_id IN (SELECT request_id FROM request_correlations ORDER BY observed_at DESC OFFSET 10000)").execute(&mut **tx).await?;
    sqlx::query("DELETE FROM glu207_shadow_results WHERE created_at<now()-interval '7 days' OR (request_id,proof_sha256) IN (SELECT request_id,proof_sha256 FROM glu207_shadow_results ORDER BY created_at DESC OFFSET 10000)").execute(&mut **tx).await?;
    Ok(())
}
pub async fn list(pool: &PgPool, rid: Option<&str>, limit: i64) -> Result<Value> {
    let rows:Vec<Value>=sqlx::query_scalar("SELECT r.result || jsonb_build_object('received_at',r.received_at,'glu',CASE WHEN r.result->>'status'='MATCHED' AND r.result->>'late_event'='false' THEN g.result->'glu' ELSE NULL END) FROM request_correlations r LEFT JOIN glu207_shadow_results g ON g.request_id=r.request_id AND g.proof_sha256=r.result->>'proof_sha256' WHERE ($1::text IS NULL OR r.request_id=$1) ORDER BY r.observed_at DESC LIMIT $2").bind(rid).bind(limit).fetch_all(pool).await?;
    Ok(
        json!({"items":rows,"scope":"Opt-in IDS gateway only; flow alerts are context, never request Ground Truth; no score fusion"}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_fake_matches_and_raw_fields() {
        let mut r = json!({"schema_version":"three-source-1","request_id":"a".repeat(32),"sensor_instance":"b".repeat(32),"observed_at":Utc::now(),"status":"MISSING_SOURCE","sources":["NGINX"],"flow_id":null,"tx_id":null,"duplicate_events":0,"flow_context_alerts":0,"late_event":false,"basis":"NO_IP_TIME_MATCH","proof_sha256":"c".repeat(64),"glu":null,"enforcement_actions":0});
        assert!(decode(&serde_json::to_vec(&r).unwrap()).is_ok());
        let mut outside_range = r.clone();
        outside_range["tx_id"] = json!(u64::MAX);
        assert!(decode(&serde_json::to_vec(&outside_range).unwrap()).is_err());
        r["status"] = json!("MATCHED");
        assert!(decode(&serde_json::to_vec(&r).unwrap()).is_err());
        r["status"] = json!("MISSING_SOURCE");
        r["raw_body"] = json!("private");
        assert!(decode(&serde_json::to_vec(&r).unwrap()).is_err());
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn detector_view_preserves_transaction_and_late_reconciliation(pool: PgPool) {
        let rid = "a".repeat(32);
        let other = "b".repeat(32);
        let sensor = "c".repeat(32);
        for (id, txid) in [(&rid, 0), (&other, 1)] {
            let r = json!({"schema_version":"three-source-1","request_id":id,"sensor_instance":sensor,"observed_at":Utc::now(),"status":"MATCHED","sources":["NGINX","STUDENT_AUDIT","SURICATA"],"flow_id":"123","tx_id":txid,"duplicate_events":0,"flow_context_alerts":0,"late_event":false,"basis":"EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY","proof_sha256":"d".repeat(64),"glu":null,"enforcement_actions":0});
            let mut tx = pool.begin().await.unwrap();
            ingest(&mut tx, "receipt", &serde_json::to_vec(&r).unwrap())
                .await
                .unwrap();
            tx.commit().await.unwrap();
        }
        let view = |id: String| {
            sqlx::query_scalar::<_, Value>(include_str!("detector_view.sql"))
                .bind(Some(id))
                .bind(50_i64)
        };
        let before = view(rid.clone()).fetch_one(&pool).await.unwrap();
        assert_eq!(before["status"], "INCOMPLETE_DETECTOR_EVIDENCE");
        for (key, txid, basis) in [
            ("native", Some(0_i64), "SENSOR_TRANSACTION"),
            ("flow", None, "FLOW_CONTEXT"),
        ] {
            let id:i64=sqlx::query_scalar("INSERT INTO security_alerts(occurred_at,source,event_type,rule_name,severity,action,evidence,event_key) VALUES(now(),'SURICATA','alert','test metadata',2,'ALERT','{}',$1) RETURNING id").bind(key).fetch_one(&pool).await.unwrap();
            sqlx::query("INSERT INTO detector_alert_links(alert_id,source_instance,flow_id,tx_id,link_basis) VALUES($1,$2,'123',$3,$4)").bind(id).bind(format!("suricata-{sensor}")).bind(txid).bind(basis).execute(&pool).await.unwrap();
        }
        let a = view(rid.clone()).fetch_one(&pool).await.unwrap();
        let b = view(other.clone()).fetch_one(&pool).await.unwrap();
        assert_eq!(a["rules"].as_array().unwrap().len(), 1);
        assert!(b["rules"].as_array().unwrap().is_empty());
        assert_eq!(a["flow_context"].as_array().unwrap().len(), 1);
        assert_eq!(b["flow_context"].as_array().unwrap().len(), 1);
        assert_eq!(a["status"], "RULE_ALERT_ONLY_OBSERVED");
        // Simulate a conflicting current proof: late view no longer links sensor tx.
        sqlx::query("UPDATE request_correlations SET result=jsonb_set(result,'{status}','\"AMBIGUOUS\"') WHERE request_id=$1").bind(&rid).execute(&pool).await.unwrap();
        let a = view(rid).fetch_one(&pool).await.unwrap();
        assert_eq!(a["status"], "UNCERTAIN_CORRELATION");
        assert!(a["rules"].as_array().unwrap().is_empty());
        let n: i64 = sqlx::query_scalar("SELECT count(*) FROM firewall_actions")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(n, 0);
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn model_before_correlation_is_not_a_match_and_stale_proofs_cannot_restore_match(
        pool: PgPool,
    ) {
        let mut base = json!({"schema_version":"three-source-1","request_id":"a".repeat(32),"sensor_instance":"b".repeat(32),"observed_at":Utc::now(),"status":"MATCHED","sources":["NGINX","STUDENT_AUDIT","SURICATA"],"flow_id":"123","tx_id":0,"duplicate_events":0,"flow_context_alerts":0,"late_event":false,"basis":"EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY","proof_sha256":"c".repeat(64),"glu":null,"enforcement_actions":0});
        let mut scored = base.clone();
        scored["glu"] = json!({"model_version":"glu207-step652-e663b0979f6f","score":0.6,"threshold":0.5396780371665955,"above_threshold":true,"feature_count":207,"feature_sha256":"d".repeat(64),"latency_ms":10.0,"flow_observed":false,"context_incomplete":true});
        let mut tx = pool.begin().await.unwrap();
        for _ in 0..2 {
            ingest(&mut tx, "model", &serde_json::to_vec(&scored).unwrap())
                .await
                .unwrap();
        }
        tx.commit().await.unwrap();
        assert!(
            list(&pool, None, 50).await.unwrap()["items"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        let n: i64 = sqlx::query_scalar("SELECT count(*) FROM glu207_shadow_results")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(n, 1);
        let mut tx = pool.begin().await.unwrap();
        ingest(&mut tx, "proof", &serde_json::to_vec(&base).unwrap())
            .await
            .unwrap();
        tx.commit().await.unwrap();
        assert_eq!(
            list(&pool, None, 50).await.unwrap()["items"][0]["glu"]["score"],
            json!(0.6)
        );
        base["status"] = json!("AMBIGUOUS");
        base["basis"] = json!("RESPONSE_ID_CONFLICTING_HTTP_FIELDS");
        base["proof_sha256"] = json!("e".repeat(64));
        base["observed_at"] = json!(Utc::now() + chrono::Duration::seconds(1));
        let mut tx = pool.begin().await.unwrap();
        ingest(&mut tx, "conflict", &serde_json::to_vec(&base).unwrap())
            .await
            .unwrap();
        ingest(
            &mut tx,
            "stale-model",
            &serde_json::to_vec(&scored).unwrap(),
        )
        .await
        .unwrap();
        tx.commit().await.unwrap();
        let page = list(&pool, None, 50).await.unwrap();
        assert_eq!(page["items"][0]["status"], json!("AMBIGUOUS"));
        assert!(page["items"][0]["glu"].is_null());
        let actions: i64 = sqlx::query_scalar("SELECT count(*) FROM firewall_actions")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(actions, 0);
    }
}
