use super::*;
use axum::{body::Body, http::Request};
use http_body_util::BodyExt;
use std::path::PathBuf;
use tower::ServiceExt;
fn state(pool: PgPool) -> AppState {
    AppState {
        pool,
        auth: auth::test_auth(),
        policy: PolicyEngine::new(true, vec![1000002], true),
        firewall_cmd: "/not-installed".into(),
        whitelist: Arc::new(vec!["192.168.10.20".parse().unwrap()]),
        watchers: Default::default(),
    }
}
async fn request(
    app: Router,
    method: &str,
    path: &str,
    token: Option<&str>,
    body: serde_json::Value,
) -> (StatusCode, serde_json::Value) {
    let mut req = Request::builder()
        .method(method)
        .uri(path)
        .header("Content-Type", "application/json");
    if let Some(token) = token {
        req = req.header("Authorization", format!("Bearer {token}"));
    }
    let response = app
        .oneshot(req.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null),
    )
}
async fn login(app: Router, user: &str) -> String {
    let (status, body) = request(
        app,
        "POST",
        "/api/auth/login",
        None,
        serde_json::json!({"username":user,"password":"test-password-long"}),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    body["token"].as_str().unwrap().into()
}
#[sqlx::test(migrations = "./migrations")]
async fn authentication_roles_and_audit(pool: PgPool) {
    let state = state(pool);
    let app = router(state.clone());
    assert_eq!(
        request(
            app.clone(),
            "GET",
            "/api/alerts",
            None,
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        request(
            app.clone(),
            "POST",
            "/api/auth/login",
            None,
            serde_json::json!({"username":"admin","password":"wrong"})
        )
        .await
        .0,
        StatusCode::UNAUTHORIZED
    );
    let viewer = login(app.clone(), "viewer").await;
    assert_eq!(
        request(
            app.clone(),
            "GET",
            "/api/alerts",
            Some(&viewer),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::OK
    );
    let payload = serde_json::json!({"ip":"192.168.10.10","reason":"test"});
    assert_eq!(
        request(
            app.clone(),
            "POST",
            "/api/blocked-ips",
            Some(&viewer),
            payload.clone()
        )
        .await
        .0,
        StatusCode::FORBIDDEN
    );
    let admin = login(app.clone(), "admin").await;
    assert_eq!(
        request(
            app.clone(),
            "POST",
            "/api/blocked-ips",
            Some(&admin),
            serde_json::json!({"ip":"192.168.10.20","reason":"test"})
        )
        .await
        .0,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        request(
            app.clone(),
            "POST",
            "/api/blocked-ips",
            Some(&admin),
            payload
        )
        .await
        .0,
        StatusCode::ACCEPTED
    );
    firewall::process_one(&state, |_, _| async {
        anyhow::bail!("simulated firewall failure")
    })
    .await
    .unwrap();
    let (actor, status): (String, String) =
        sqlx::query_as("SELECT actor,status FROM firewall_actions")
            .fetch_one(&state.pool)
            .await
            .unwrap();
    assert_eq!((actor.as_str(), status.as_str()), ("admin", "ERROR"));
    request(
        app.clone(),
        "POST",
        "/api/auth/logout",
        Some(&admin),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(
        request(
            app,
            "GET",
            "/api/alerts",
            Some(&admin),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::UNAUTHORIZED
    );
}
struct TempLog(PathBuf);
impl TempLog {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!("pbl4-ingest-{}", rand::random::<u64>()));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn file(&self) -> PathBuf {
        self.0.join("eve.json")
    }
}
impl Drop for TempLog {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
fn event(ip: &str) -> String {
    format!(
        "{{\"timestamp\":\"2026-10-23T01:00:00.000000+0000\",\"event_type\":\"alert\",\"src_ip\":\"{ip}\",\"alert\":{{\"signature_id\":1000002,\"signature\":\"test SQLi\",\"severity\":1}}}}\n"
    )
}
async fn count(pool: &PgPool) -> i64 {
    sqlx::query_scalar("SELECT count(*) FROM security_alerts")
        .fetch_one(pool)
        .await
        .unwrap()
}
#[sqlx::test(migrations = "./migrations")]
async fn ingestion_rotation_restart_partial_and_dedup(pool: PgPool) {
    let s = state(pool);
    let temp = TempLog::new();
    let file = temp.file();
    let first = event("192.168.10.10");
    tokio::fs::write(&file, &first).await.unwrap();
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(count(&s.pool).await, 1);
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(count(&s.pool).await, 1);
    // Replay after checkpoint rollback still deduplicates by stable event identity.
    sqlx::query("UPDATE log_cursors SET byte_offset=0,anchor=''")
        .execute(&s.pool)
        .await
        .unwrap();
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(count(&s.pool).await, 1);
    std::fs::rename(&file, temp.0.join("eve.json.1")).unwrap();
    let second = event("192.168.10.11");
    std::fs::write(&file, second.trim_end()).unwrap();
    ingest::scan(&s, "SURICATA", file.to_str().unwrap())
        .await
        .unwrap();
    assert_eq!(count(&s.pool).await, 1);
    use std::io::Write;
    std::fs::OpenOptions::new()
        .append(true)
        .open(&file)
        .unwrap()
        .write_all(b"\n")
        .unwrap();
    ingest::scan(&s, "SURICATA", file.to_str().unwrap())
        .await
        .unwrap();
    assert_eq!(count(&s.pool).await, 2);
    std::fs::write(&file, event("192.168.10.12")).unwrap();
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(count(&s.pool).await, 3);
    let pending: i64 =
        sqlx::query_scalar("SELECT count(*) FROM firewall_actions WHERE status='PENDING'")
            .fetch_one(&s.pool)
            .await
            .unwrap();
    assert_eq!(pending, 3);
    firewall::process_one(&s, |_, _| async { Ok(()) })
        .await
        .unwrap();
    let actions: Vec<String> = sqlx::query_scalar("SELECT action FROM security_alerts ORDER BY id")
        .fetch_all(&s.pool)
        .await
        .unwrap();
    assert_eq!(actions, ["AUTO-BLOCK", "ALERT", "ALERT"]);
    firewall::process_one(&s, |_, _| async { anyhow::bail!("kernel failure") })
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, String>(
            "SELECT action FROM security_alerts ORDER BY id OFFSET 1 LIMIT 1"
        )
        .fetch_one(&s.pool)
        .await
        .unwrap(),
        "ALERT"
    );
    firewall::enqueue(
        &s.pool,
        "192.168.10.10".parse().unwrap(),
        "UNBLOCK",
        "admin",
        "test",
        None,
    )
    .await
    .unwrap();
    firewall::process_one(&s, |_, _| async { Ok(()) })
        .await
        .unwrap(); // remaining auto job
    firewall::process_one(&s, |_, _| async { Ok(()) })
        .await
        .unwrap();
    assert!(
        !sqlx::query_scalar::<_, bool>("SELECT active FROM blocked_ips WHERE ip='192.168.10.10'")
            .fetch_one(&s.pool)
            .await
            .unwrap()
    );
}
#[sqlx::test(migrations = "./migrations")]
async fn database_failure_retains_cursor_and_retries(pool: PgPool) {
    let s = state(pool);
    let temp = TempLog::new();
    let file = temp.file();
    std::fs::write(&file, event("192.168.10.10")).unwrap();
    sqlx::query(
        "ALTER TABLE security_alerts ADD CONSTRAINT simulated_failure CHECK (source != 'SURICATA')",
    )
    .execute(&s.pool)
    .await
    .unwrap();
    assert!(ingest::process_file(&s, "SURICATA", &file).await.is_err());
    assert_eq!(count(&s.pool).await, 0);
    sqlx::query("ALTER TABLE security_alerts DROP CONSTRAINT simulated_failure")
        .execute(&s.pool)
        .await
        .unwrap();
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(count(&s.pool).await, 1);
    std::fs::write(&file, "not json\n").unwrap();
    ingest::process_file(&s, "SURICATA", &file).await.unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("SELECT count(*) FROM ingestion_errors")
            .fetch_one(&s.pool)
            .await
            .unwrap(),
        1
    );
}

#[sqlx::test(migrations = false)]
async fn legacy_schema_upgrade_preserves_data(pool: PgPool) {
    sqlx::raw_sql(include_str!("../sql/schema.sql"))
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,rule_name,severity,action,evidence) VALUES(now(),'SURICATA','alert','legacy',2,'ALERT','legacy evidence')")
        .execute(&pool).await.unwrap();
    sqlx::migrate!("./migrations").run(&pool).await.unwrap();
    sqlx::migrate!("./migrations").run(&pool).await.unwrap();
    assert_eq!(count(&pool).await, 1);
    assert_eq!(
        sqlx::query_scalar::<_, String>("SELECT evidence FROM security_alerts")
            .fetch_one(&pool)
            .await
            .unwrap(),
        "legacy evidence"
    );
}
#[sqlx::test(migrations = "./migrations")]
async fn restore_does_not_override_pending_unblock(pool: PgPool) {
    let s = state(pool);
    sqlx::query("INSERT INTO blocked_ips(ip,reason) VALUES('192.168.10.10','test')")
        .execute(&s.pool)
        .await
        .unwrap();
    firewall::enqueue(
        &s.pool,
        "192.168.10.10".parse().unwrap(),
        "UNBLOCK",
        "admin",
        "test",
        None,
    )
    .await
    .unwrap();
    firewall::restore_jobs(&s.pool).await.unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("SELECT count(*) FROM firewall_actions")
            .fetch_one(&s.pool)
            .await
            .unwrap(),
        1
    );
    firewall::process_one(&s, |_, _| async { Ok(()) })
        .await
        .unwrap();
    assert!(
        !sqlx::query_scalar::<_, bool>("SELECT active FROM blocked_ips")
            .fetch_one(&s.pool)
            .await
            .unwrap()
    );
}
