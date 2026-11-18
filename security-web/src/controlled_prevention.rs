//! Durable signed intake + shared transactional worker. Production actuator stays closed.
use crate::*;
use hmac::{Hmac, Mac};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
#[derive(serde::Deserialize, serde::Serialize, Clone)]
#[serde(deny_unknown_fields)]
pub struct Verdict {
    pub version: u8,
    pub key_id: String,
    pub issuer: String,
    pub epoch: String,
    pub nonce: String,
    pub alert_id: i64,
    pub generation: String,
    pub flow_id: String,
    pub tx_id: i64,
    pub request_id: Option<String>,
    pub client_ip: String,
    pub issued_at: i64,
    pub expires_at: i64,
    pub recommend_block: bool,
}
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    payload: String,
    mac: String,
}
fn decode(s: &str) -> Result<Vec<u8>> {
    anyhow::ensure!(
        s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()),
        "Invalid MAC"
    );
    (0..64)
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).map_err(Into::into))
        .collect()
}
async fn alert(tx: &mut sqlx::Transaction<'_, sqlx::Postgres>, id: i64) -> Result<Value> {
    Ok(sqlx::query_scalar("SELECT to_jsonb(a)||jsonb_build_object('client_ip',host(client_ip)) FROM security_alerts a WHERE id=$1 FOR SHARE").bind(id).fetch_one(&mut **tx).await?)
}
async fn binding(tx: &mut sqlx::Transaction<'_, sqlx::Postgres>, v: &Verdict) -> Result<bool> {
    let link=sqlx::query_as::<_,(String,Option<String>,Option<i64>,Option<String>)>("SELECT source_instance,flow_id,tx_id,request_id FROM detector_alert_links WHERE alert_id=$1 FOR SHARE").bind(v.alert_id).fetch_optional(&mut **tx).await?;
    Ok(link.is_some_and(|(g, f, t, r)| {
        g == format!("suricata-{}", v.generation)
            && f.as_deref() == Some(&v.flow_id)
            && t == Some(v.tx_id)
            && r == v.request_id
    }))
}
pub async fn accept(state: &AppState, raw: &str, tag: &[u8], secret: &[u8]) -> Result<i64> {
    anyhow::ensure!(raw.len() <= 4096 && secret.len() >= 32, "Invalid envelope");
    let mut mac = Hmac::<Sha256>::new_from_slice(secret)?;
    mac.update(b"WebSentinel-AI-verdict-v1\0");
    mac.update(raw.as_bytes());
    mac.verify_slice(tag)
        .map_err(|_| anyhow::anyhow!("Invalid signature"))?;
    let v: Verdict = serde_json::from_str(raw)?;
    anyhow::ensure!(
        v.version == 1
            && v.recommend_block
            && v.nonce.len() == 32
            && v.nonce.bytes().all(|b| b.is_ascii_hexdigit())
            && v.generation.len() == 32
            && v.generation.bytes().all(|b| b.is_ascii_hexdigit())
            && v.tx_id >= 0,
        "Invalid verdict"
    );
    let mut tx = state.pool.begin().await?;
    let now: i64 =
        sqlx::query_scalar("SELECT floor(extract(epoch from clock_timestamp()))::bigint")
            .fetch_one(&mut *tx)
            .await?;
    anyhow::ensure!(
        v.issued_at <= now && v.expires_at > now && v.expires_at.saturating_sub(v.issued_at) <= 60,
        "Expired verdict"
    );
    let keyrow=sqlx::query_as::<_,(String,String,bool,DateTime<Utc>,DateTime<Utc>)>("SELECT issuer,epoch,revoked,not_before,expires_at FROM prevention_ai_keys WHERE key_id=$1 FOR SHARE").bind(&v.key_id).fetch_one(&mut *tx).await?;
    anyhow::ensure!(
        keyrow.0 == v.issuer
            && keyrow.1 == v.epoch
            && !keyrow.2
            && keyrow.3.timestamp() <= now
            && keyrow.4.timestamp() > v.expires_at,
        "Key unavailable/revoked"
    );
    let a = alert(&mut tx, v.alert_id).await?;
    anyhow::ensure!(
        prevention::assess(state, &a)["decision"] == "ALLOW"
            && a["client_ip"] == v.client_ip
            && binding(&mut tx, &v).await?,
        "Binding or policy denied"
    );
    let digest = format!("{:x}", Sha256::digest(raw.as_bytes()));
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
        .bind(format!("ai:{}:{}", v.key_id, v.nonce))
        .execute(&mut *tx)
        .await?;
    if let Some((id, old)) = sqlx::query_as::<_, (i64, String)>(
        "SELECT id,digest FROM prevention_ai_verdicts WHERE key_id=$1 AND nonce=$2",
    )
    .bind(&v.key_id)
    .bind(&v.nonce)
    .fetch_optional(&mut *tx)
    .await?
    {
        anyhow::ensure!(old == digest, "Nonce conflict");
        return Ok(id);
    }
    let id=sqlx::query_scalar("INSERT INTO prevention_ai_verdicts(key_id,nonce,digest,alert_id,binding,expires_at) VALUES($1,$2,$3,$4,$5,to_timestamp($6)) RETURNING id").bind(&v.key_id).bind(&v.nonce).bind(digest).bind(v.alert_id).bind(serde_json::to_value(&v)?).bind(v.expires_at as f64).fetch_one(&mut *tx).await?;
    sqlx::query(
        "INSERT INTO prevention_execution_audit(verdict_id,decision) VALUES($1,'AI_ACCEPTED')",
    )
    .bind(id)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(id)
}

pub async fn intake(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Json(e): Json<Envelope>,
) -> Result<Json<Value>, ApiError> {
    if actor.role != "admin" {
        return Err((
            StatusCode::FORBIDDEN,
            Json(json!({"message":"Admin required"})),
        ));
    }
    // No configuration => endpoint fails closed. Keys never supplied by callers.
    let run = async {
        let v: Verdict = serde_json::from_str(&e.payload)?;
        anyhow::ensure!(
            !v.key_id.is_empty()
                && v.key_id.len() <= 64
                && v.key_id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-'),
            "Invalid key ID"
        );
        let dir = env::var("AI_VERDICT_KEY_DIR")?;
        let path = std::path::Path::new(&dir).join(&v.key_id);
        use std::os::unix::fs::PermissionsExt;
        let meta = std::fs::symlink_metadata(&path)?;
        anyhow::ensure!(
            meta.is_file() && meta.permissions().mode() & 0o077 == 0 && meta.len() == 32,
            "Unsafe key file"
        );
        let key = std::fs::read(path)?;
        accept(&state, &e.payload, &decode(&e.mac)?, &key).await
    };
    match run.await {
        Ok(id) => Ok(Json(json!({"verdict_id":id,"execution_allowed":false}))),
        Err(_) => {
            sqlx::query("INSERT INTO prevention_execution_audit(decision) VALUES('AI_REJECTED')")
                .execute(&state.pool)
                .await
                .map_err(api_error)?;
            Err(bad_request("AI verdict rejected; no execution"))
        }
    }
}

/// Actuator contract: idempotent by proposal ID; block deadline is absolute and
/// must never be extended on retry. Errors may mean unknown external outcome.
#[allow(dead_code)] // integration seam; no production execution scheduler in this revision
pub trait Actuator: Send + Sync {
    fn apply(
        &self,
        proposal: i64,
        ip: IpAddr,
        block: bool,
        deadline: DateTime<Utc>,
    ) -> impl std::future::Future<Output = Result<()>> + Send;
}
/// Only wired production implementation: explicit refusal, never invokes nftables.
#[allow(dead_code)]
pub struct ClosedActuator;
impl Actuator for ClosedActuator {
    async fn apply(&self, _: i64, _: IpAddr, _: bool, _: DateTime<Utc>) -> Result<()> {
        anyhow::bail!("PRODUCTION_EXECUTION_DISABLED")
    }
}
/// One worker path used by injected isolated actuator tests. No background runtime
/// worker is started by this revision. Old enqueue/process routes remain closed.
#[allow(dead_code)]
pub async fn step<A: Actuator>(
    state: &AppState,
    proposal: i64,
    verdict: i64,
    rollback: bool,
    actuator: &A,
) -> Result<String> {
    let mut tx = state.pool.begin().await?;
    let p: Value =
        sqlx::query_scalar("SELECT to_jsonb(p) FROM prevention_proposals p WHERE id=$1 FOR UPDATE")
            .bind(proposal)
            .fetch_one(&mut *tx)
            .await?;
    let existing = sqlx::query_as::<_, (String, String, DateTime<Utc>)>(
        "SELECT host(ip),status,deadline FROM prevention_execution WHERE proposal_id=$1 FOR UPDATE",
    )
    .bind(proposal)
    .fetch_optional(&mut *tx)
    .await?;
    let vrow=sqlx::query_as::<_,(Value,bool,DateTime<Utc>,bool)>("SELECT v.binding,v.revoked,v.expires_at,k.revoked OR k.expires_at<=clock_timestamp() OR k.not_before>clock_timestamp() OR k.epoch<>v.binding->>'epoch' OR k.issuer<>v.binding->>'issuer' FROM prevention_ai_verdicts v JOIN prevention_ai_keys k ON k.key_id=v.key_id WHERE v.id=$1 FOR SHARE OF v,k").bind(verdict).fetch_one(&mut *tx).await?;
    let v: Verdict = serde_json::from_value(vrow.0)?;
    let a = alert(&mut tx, p["alert_id"].as_i64().context("Missing alert")?).await?;
    let eval = prevention::assess(state, &a);
    let now = Utc::now();
    let expiry = DateTime::parse_from_rfc3339(p["expires_at"].as_str().context("Missing expiry")?)?
        .with_timezone(&Utc);
    let review = p["reviewed_at"]
        .as_str()
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|t| t.with_timezone(&Utc));
    let valid = eval["decision"] == "ALLOW"
        && p["status"] == "APPROVED_DRY_RUN"
        && p["reviewer"].is_string()
        && p["reviewer"] != p["creator"]
        && expiry > now
        && review.is_some_and(|t| t <= now && (now - t).num_seconds() <= 300)
        && p["evaluation"]["policy_version"] == eval["policy_version"]
        && p["evaluation"]["client_ip"] == a["client_ip"]
        && p["alert_id"] == v.alert_id
        && a["client_ip"] == v.client_ip
        && !vrow.1
        && !vrow.3
        && vrow.2 > now
        && binding(&mut tx, &v).await?;
    let deadline = existing.as_ref().map(|x| x.2).unwrap_or(
        review.unwrap_or(now)
            + chrono::Duration::seconds(p["ttl_seconds"].as_i64().unwrap_or(0).clamp(0, 300)),
    );
    let rollback_latched:bool=sqlx::query_scalar("SELECT coalesce((SELECT rollback_requested FROM prevention_execution WHERE proposal_id=$1),false)").bind(proposal).fetch_one(&mut *tx).await?;
    let cleanup = existing.is_some() && (rollback || rollback_latched || !valid || deadline <= now);
    // Persist cleanup intent before any external call: a crash cannot turn a
    // failed rollback into a fresh BLOCK on the next retry.
    if cleanup && !rollback_latched {
        sqlx::query("UPDATE prevention_execution SET rollback_requested=true WHERE proposal_id=$1")
            .bind(proposal)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        return Box::pin(step(state, proposal, verdict, true, actuator)).await;
    }
    let outcome;
    if existing
        .as_ref()
        .is_some_and(|x| x.1 == "ROLLED_BACK" || x.1 == "DENIED")
    {
        return Ok("TERMINAL".into());
    }
    if (!valid || deadline <= now) && !cleanup || rollback && existing.is_none() {
        outcome = "DENIED";
    } else {
        let ip = existing
            .as_ref()
            .map(|x| x.0.as_str())
            .unwrap_or(&v.client_ip)
            .parse::<IpAddr>()?;
        if existing.is_none() {
            sqlx::query("INSERT INTO prevention_execution(proposal_id,verdict_id,ip,deadline,status) VALUES($1,$2,$3::inet,$4,'PENDING')").bind(proposal).bind(verdict).bind(ip.to_string()).bind(deadline).execute(&mut *tx).await?;
            // Durable outbox intent survives process/DB-commit uncertainty after
            // actuator success. Retry uses same target/id/deadline.
            sqlx::query("INSERT INTO prevention_execution_audit(proposal_id,verdict_id,decision) VALUES($1,$2,'INTENT')").bind(proposal).bind(verdict).execute(&mut *tx).await?;
            tx.commit().await?;
            return Box::pin(step(state, proposal, verdict, false, actuator)).await;
        } else {
            let same: bool = sqlx::query_scalar(
                "SELECT verdict_id=$2 FROM prevention_execution WHERE proposal_id=$1",
            )
            .bind(proposal)
            .bind(verdict)
            .fetch_one(&mut *tx)
            .await?;
            anyhow::ensure!(same, "Execution binding changed");
            if !cleanup && existing.as_ref().is_some_and(|x| x.1 == "ACTIVE") {
                return Ok("ACTIVE".into());
            }
        }
        let result = tokio::time::timeout(
            std::time::Duration::from_secs(5),
            actuator.apply(proposal, ip, !cleanup, deadline),
        )
        .await;
        outcome = match result {
            Ok(Ok(())) if cleanup => "ROLLED_BACK",
            Ok(Ok(())) => "ACTIVE",
            _ => "ERROR",
        };
        sqlx::query("UPDATE prevention_execution SET status=$2,attempts=attempts+1,rollback_requested=rollback_requested OR $3 WHERE proposal_id=$1").bind(proposal).bind(outcome).bind(cleanup).execute(&mut *tx).await?;
    }
    sqlx::query(
        "INSERT INTO prevention_execution_audit(proposal_id,verdict_id,decision) VALUES($1,$2,$3)",
    )
    .bind(proposal)
    .bind(verdict)
    .bind(outcome)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(outcome.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct Fake {
        calls: AtomicUsize,
        fail: bool,
    }
    impl Actuator for Fake {
        async fn apply(&self, _: i64, _: IpAddr, _: bool, _: DateTime<Utc>) -> Result<()> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            anyhow::ensure!(!self.fail, "isolated failure");
            Ok(())
        }
    }
    async fn fixture(pool: PgPool) -> (AppState, Verdict, i64) {
        let mut s = crate::integration_tests::state(pool.clone());
        let mut safety = network::Safety::test();
        safety.mode = "OFF".into();
        safety.allowed = vec![network::Subnet::parse("8.8.8.8/32").unwrap()];
        s.safety = Arc::new(safety);
        s.policy = PolicyEngine::new(false, vec![], false);
        let id:i64=sqlx::query_scalar("INSERT INTO security_alerts(occurred_at,source,event_type,rule_name,severity,action,evidence,client_ip,client_ip_verified,network_src_ip,suricata_post_proxy) VALUES(now(),'SURICATA','alert','SURICATA: SID 1000003',2,'ALERT','{}','8.8.8.8',true,'192.168.20.1',true) RETURNING id").fetch_one(&pool).await.unwrap();
        let g = "a".repeat(32);
        sqlx::query("INSERT INTO detector_alert_links(alert_id,source_instance,flow_id,tx_id,request_id,link_basis) VALUES($1,$2,'123',0,'rid','SENSOR_TRANSACTION')").bind(id).bind(format!("suricata-{g}")).execute(&pool).await.unwrap();
        sqlx::query("INSERT INTO prevention_ai_keys VALUES('key1','ai','epoch1',now()-interval '1 minute',now()+interval '1 hour',false)").execute(&pool).await.unwrap();
        let now = Utc::now().timestamp();
        let v = Verdict {
            version: 1,
            key_id: "key1".into(),
            issuer: "ai".into(),
            epoch: "epoch1".into(),
            nonce: "b".repeat(32),
            alert_id: id,
            generation: g,
            flow_id: "123".into(),
            tx_id: 0,
            request_id: Some("rid".into()),
            client_ip: "8.8.8.8".into(),
            issued_at: now,
            expires_at: now + 60,
            recommend_block: true,
        };
        let a=sqlx::query_scalar::<_,Value>("SELECT to_jsonb(a)||jsonb_build_object('client_ip',host(client_ip)) FROM security_alerts a WHERE id=$1").bind(id).fetch_one(&pool).await.unwrap();
        let eval = prevention::assess(&s, &a);
        let p:i64=sqlx::query_scalar("INSERT INTO prevention_proposals(alert_id,creator,idempotency_key,reason,ttl_seconds,status,evaluation,reviewer,reviewed_at) VALUES($1,'a','test','lab',30,'APPROVED_DRY_RUN',$2,'b',now()) RETURNING id").bind(id).bind(eval).fetch_one(&pool).await.unwrap();
        (s, v, p)
    }
    fn sign(v: &Verdict) -> (String, Vec<u8>) {
        let raw = serde_json::to_string(v).unwrap();
        let mut m = Hmac::<Sha256>::new_from_slice(&[7; 32]).unwrap();
        m.update(b"WebSentinel-AI-verdict-v1\0");
        m.update(raw.as_bytes());
        (raw, m.finalize().into_bytes().to_vec())
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn c3_persistent_ai_and_worker(pool: PgPool) {
        let (s, mut v, p) = fixture(pool.clone()).await;
        let (raw, tag) = sign(&v);
        let (a, b) = tokio::join!(
            accept(&s, &raw, &tag, &[7; 32]),
            accept(&s, &raw, &tag, &[7; 32])
        );
        let id = a.unwrap();
        assert_eq!(id, b.unwrap());
        assert!(accept(&s, &raw, &[0; 32], &[7; 32]).await.is_err());
        v.expires_at -= 1;
        let (other, mac) = sign(&v);
        assert!(accept(&s, &other, &mac, &[7; 32]).await.is_err());
        // New verifier/state instance shares persistent journal, no in-memory nonce cache.
        assert_eq!(accept(&s.clone(), &raw, &tag, &[7; 32]).await.unwrap(), id);
        let fail = Fake {
            calls: AtomicUsize::new(0),
            fail: true,
        };
        assert_eq!(step(&s, p, id, false, &fail).await.unwrap(), "ERROR");
        let before: DateTime<Utc> =
            sqlx::query_scalar("SELECT deadline FROM prevention_execution WHERE proposal_id=$1")
                .bind(p)
                .fetch_one(&pool)
                .await
                .unwrap();
        let ok = Fake {
            calls: AtomicUsize::new(0),
            fail: false,
        };
        let (a, b) = tokio::join!(step(&s, p, id, false, &ok), step(&s, p, id, false, &ok));
        assert_eq!(a.unwrap(), "ACTIVE");
        assert_eq!(b.unwrap(), "ACTIVE");
        assert_eq!(ok.calls.load(Ordering::SeqCst), 1);
        let after: DateTime<Utc> =
            sqlx::query_scalar("SELECT deadline FROM prevention_execution WHERE proposal_id=$1")
                .bind(p)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(before, after);
        sqlx::query("UPDATE prevention_ai_keys SET revoked=true")
            .execute(&pool)
            .await
            .unwrap();
        assert!(accept(&s, &raw, &tag, &[7; 32]).await.is_err());
        assert_eq!(step(&s, p, id, false, &ok).await.unwrap(), "ROLLED_BACK");
        assert_eq!(ok.calls.load(Ordering::SeqCst), 2);
        assert_eq!(step(&s, p, id, true, &ok).await.unwrap(), "TERMINAL");
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM prevention_execution_audit")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert!(count >= 4);
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn c3_denies_unverified_expired_changed_policy_and_closed_actuator(pool: PgPool) {
        let (s, v, p) = fixture(pool.clone()).await;
        let (raw, tag) = sign(&v);
        let id = accept(&s, &raw, &tag, &[7; 32]).await.unwrap();
        assert_eq!(
            step(&s, p, id, false, &ClosedActuator).await.unwrap(),
            "ERROR"
        );
        let fake = Fake {
            calls: AtomicUsize::new(0),
            fail: false,
        };
        sqlx::query("UPDATE security_alerts SET client_ip_verified=false")
            .execute(&pool)
            .await
            .unwrap();
        assert!(accept(&s, &raw, &tag, &[7; 32]).await.is_err());
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "ROLLED_BACK");
        // Failed/unknown block attempt is cleaned up, never retried as block on revocation.
        assert_eq!(fake.calls.load(Ordering::SeqCst), 1);
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn c3_rotation_expiry_policy_rollback_retry(pool: PgPool) {
        let (s, mut v, p) = fixture(pool.clone()).await;
        let (raw, tag) = sign(&v);
        let id = accept(&s, &raw, &tag, &[7; 32]).await.unwrap();
        // Key rotation invalidates old epoch; no journal reset or old replay acceptance.
        sqlx::query("UPDATE prevention_ai_keys SET epoch='epoch2'")
            .execute(&pool)
            .await
            .unwrap();
        assert!(accept(&s, &raw, &tag, &[7; 32]).await.is_err());
        let fake = Fake {
            calls: AtomicUsize::new(0),
            fail: false,
        };
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "DENIED");
        assert_eq!(fake.calls.load(Ordering::SeqCst), 0);
        v.epoch = "epoch2".into();
        v.nonce = "c".repeat(32);
        let (raw, tag) = sign(&v);
        let id = accept(&s, &raw, &tag, &[7; 32]).await.unwrap();
        sqlx::query("UPDATE prevention_proposals SET evaluation=jsonb_set(evaluation,'{policy_version}','\"obsolete\"') WHERE id=$1").bind(p).execute(&pool).await.unwrap();
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "DENIED");
        sqlx::query("UPDATE prevention_proposals SET evaluation=jsonb_set(evaluation,'{policy_version}','\"C2-v2\"') WHERE id=$1").bind(p).execute(&pool).await.unwrap();
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "ACTIVE");
        let fail = Fake {
            calls: AtomicUsize::new(0),
            fail: true,
        };
        assert_eq!(step(&s, p, id, true, &fail).await.unwrap(), "ERROR");
        // Restart/retry with rollback=false still honors durable cleanup intent.
        assert_eq!(
            step(&s.clone(), p, id, false, &fake).await.unwrap(),
            "ROLLED_BACK"
        );
        assert_eq!(fake.calls.load(Ordering::SeqCst), 2);
        v.nonce = "d".repeat(32);
        v.expires_at = Utc::now().timestamp() - 1;
        let (raw, tag) = sign(&v);
        assert!(accept(&s, &raw, &tag, &[7; 32]).await.is_err());
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn c3_deadline_expiry_is_cleanup_not_reblock(pool: PgPool) {
        let (s, v, p) = fixture(pool.clone()).await;
        let (raw, tag) = sign(&v);
        let id = accept(&s, &raw, &tag, &[7; 32]).await.unwrap();
        let fake = Fake {
            calls: AtomicUsize::new(0),
            fail: false,
        };
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "ACTIVE");
        sqlx::query("UPDATE prevention_execution SET deadline=now()-interval '1 second' WHERE proposal_id=$1").bind(p).execute(&pool).await.unwrap();
        assert_eq!(step(&s, p, id, false, &fake).await.unwrap(), "ROLLED_BACK");
        assert_eq!(fake.calls.load(Ordering::SeqCst), 2);
    }
}
