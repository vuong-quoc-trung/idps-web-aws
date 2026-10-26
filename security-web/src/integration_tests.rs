use super::*;
use axum::{body::Body, http::Request};
use http_body_util::BodyExt;
use std::path::PathBuf;
use tower::ServiceExt;

fn application_event(
    source: &str,
    timestamp: &str,
    request_id: Option<&str>,
) -> events::CanonicalEvent {
    let mut event = events::CanonicalEvent::new(source, timestamp.parse().unwrap());
    event.event_id = format!("test-{}", rand::random::<u64>());
    event.request_id = request_id.map(str::to_owned);
    event.client_ip = Some("198.51.100.8".parse().unwrap());
    event.http_method = Some("GET".into());
    event.uri_path = Some("/api/students/123".into());
    event.status_code = Some(200);
    event.latency_ms = Some(12.5);
    event.role = Some("ANONYMOUS".into());
    event.outcome = "success".into();
    event
}

async fn insert_application_event(pool: &PgPool, e: events::CanonicalEvent) -> i64 {
    sqlx::query_scalar("INSERT INTO normalized_events(event_key,schema_version,source,source_instance,source_event_id,occurred_at,request_id,client_ip,event_type,http_method,uri_path,status_code,canonical) VALUES($1,'1.0',$2,$3,$1,$4,$5,$6::inet,$7,$8,$9,$10,$11) RETURNING id")
        .bind(&e.event_id).bind(&e.source).bind(&e.source_instance).bind(e.timestamp)
        .bind(&e.request_id).bind(e.client_ip.map(|ip|ip.to_string())).bind(&e.event_type)
        .bind(&e.http_method).bind(&e.uri_path).bind(e.status_code.map(i32::from))
        .bind(serde_json::to_value(&e).unwrap()).fetch_one(pool).await.unwrap()
}

#[sqlx::test(migrations = "./migrations")]
async fn application_audit_permissions_history_and_missing_records(pool: PgPool) {
    let id = insert_application_event(
        &pool,
        application_event("STUDENT_AUDIT", "2026-10-26T00:00:00Z", None),
    )
    .await;
    let app = router(state(pool.clone())); // collection is OFF, history must remain readable
    for path in [
        "/api/application-audit".to_string(),
        format!("/api/application-audit/{id}"),
    ] {
        assert_eq!(
            request(app.clone(), "GET", &path, None, serde_json::Value::Null)
                .await
                .0,
            StatusCode::UNAUTHORIZED
        );
    }
    let viewer = login(app.clone(), "viewer").await;
    let (status, page) = request(
        app.clone(),
        "GET",
        "/api/application-audit",
        Some(&viewer),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(page["total"], 1);
    assert_eq!(page["collection"]["enabled"], false);
    assert_eq!(page["collection"]["watchers"], serde_json::json!({}));
    assert_eq!(page["items"][0]["uri_path"], "/api/students/[id]");
    let (_, detail) = request(
        app.clone(),
        "GET",
        &format!("/api/application-audit/{id}"),
        Some(&viewer),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(detail["related"], serde_json::json!([]));
    assert_eq!(
        request(
            app.clone(),
            "GET",
            "/api/application-audit/999999",
            Some(&viewer),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::NOT_FOUND
    );
    assert_eq!(
        request(
            app.clone(),
            "POST",
            "/api/application-audit",
            Some(&viewer),
            serde_json::json!({})
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
            "/api/application-audit",
            Some(&admin),
            serde_json::json!({})
        )
        .await
        .0,
        StatusCode::METHOD_NOT_ALLOWED
    );
    assert_eq!(
        request(
            app,
            "GET",
            "/api/audit",
            Some(&viewer),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::OK
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("SELECT count(*) FROM firewall_actions")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
}

#[sqlx::test(migrations = "./migrations")]
async fn application_audit_filters_pagination_and_snapshot_count(pool: PgPool) {
    let first = insert_application_event(
        &pool,
        application_event(
            "STUDENT_AUDIT",
            "2026-10-26T00:00:00Z",
            Some("request-shared"),
        ),
    )
    .await;
    let second = insert_application_event(
        &pool,
        application_event("NGINX", "2026-10-26T00:00:00Z", Some("request-shared")),
    )
    .await;
    let mut failed = application_event(
        "STUDENT_AUDIT",
        "2026-10-26T00:00:00Z",
        Some("request-failed"),
    );
    failed.status_code = Some(403);
    failed.outcome = "failure".into();
    let third = insert_application_event(&pool, failed).await;
    insert_application_event(
        &pool,
        application_event("STUDENT_AUDIT", "2026-10-26T00:01:00Z", None),
    )
    .await;
    insert_application_event(
        &pool,
        application_event("SURICATA", "2026-10-25T23:59:59Z", None),
    )
    .await;
    let mut s = state(pool);
    s.ingestion = Arc::new(ingest::Config {
        collect_all: true,
        ..Default::default()
    });
    s.watchers
        .write()
        .await
        .insert("STUDENT_AUDIT".into(), ingest::WatcherStatus::default());
    let app = router(s);
    let viewer = login(app.clone(), "viewer").await;
    let get = |path: String| {
        let app = app.clone();
        let viewer = viewer.clone();
        async move { request(app, "GET", &path, Some(&viewer), serde_json::Value::Null).await }
    };
    // Equal timestamps are ordered by id DESC; page count does not change with LIMIT/OFFSET.
    let (_, page) = get("/api/application-audit?limit=2&offset=1".into()).await;
    assert_eq!(page["total"], 5);
    assert_eq!(page["items"][0]["id"], third);
    assert_eq!(page["items"][1]["id"], second);
    assert_eq!(page["collection"]["enabled"], true);
    assert_eq!(
        page["collection"]["watchers"]["STUDENT_AUDIT"]["state"],
        "starting"
    );
    let (_, filtered) = get("/api/application-audit?from=2026-10-26T00:00:00Z&to=2026-10-26T00:01:00Z&source=STUDENT_AUDIT&client_ip=198.51.100.8&uri_path=%2Fapi%2Fstudents&status_code=200&http_method=GET&request_id=request-shared".into()).await;
    assert_eq!(filtered["total"], 1);
    assert_eq!(filtered["items"][0]["id"], first);
    for (filter, total) in [
        ("source=SURICATA", 1),
        ("source=STUDENT_AUDIT", 3),
        ("status_code=403", 1),
        ("request_id=request-shared", 2),
        ("from=2026-10-26T00:00:00Z&to=2026-10-26T00:01:00Z", 3),
    ] {
        let (status, page) = get(format!("/api/application-audit?{filter}")).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(page["total"], total, "filter: {filter}");
    }
    for filter in [
        "client_ip=2001%3Adb8%3A%3A1",
        "uri_path=%25",
        "uri_path=%27%20OR%201%3D1--",
        "http_method=POST",
        "offset=100",
    ] {
        let (status, empty) = get(format!("/api/application-audit?{filter}")).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(empty["items"], serde_json::json!([]));
    }
}

#[sqlx::test(migrations = "./migrations")]
async fn application_audit_rejects_invalid_filters(pool: PgPool) {
    let app = router(state(pool));
    let viewer = login(app.clone(), "viewer").await;
    for query in [
        "limit=0",
        "limit=201",
        "offset=-1",
        "offset=1000001",
        "source=RAW",
        "status_code=99",
        "status_code=600",
        "status_code=abc",
        "request_id=bad%20id",
        "request_id=",
        "uri_path=",
        "uri_path=%0A",
        "http_method=get",
        "client_ip=bad",
        "from=bad",
        "from=2026-10-26T00:00:00Z&to=2026-10-26T00:00:00Z",
        "unknown=secret",
    ] {
        assert_eq!(
            request(
                app.clone(),
                "GET",
                &format!("/api/application-audit?{query}"),
                Some(&viewer),
                serde_json::Value::Null
            )
            .await
            .0,
            StatusCode::BAD_REQUEST,
            "query: {query}"
        );
    }
    for query in [
        format!("uri_path={}", "a".repeat(513)),
        format!("request_id={}", "a".repeat(129)),
    ] {
        assert_eq!(
            request(
                app.clone(),
                "GET",
                &format!("/api/application-audit?{query}"),
                Some(&viewer),
                serde_json::Value::Null
            )
            .await
            .0,
            StatusCode::BAD_REQUEST
        );
    }
}

#[sqlx::test(migrations = "./migrations")]
async fn application_audit_display_redaction_and_strict_contract(pool: PgPool) {
    let mut e = application_event("STUDENT_AUDIT", "2026-10-26T00:00:00Z", None);
    e.uri_path = Some("/api/students/private-student-name".into());
    e.query_string = Some(
        "password=plaintext-password&token=plaintext-token&private-email=plaintext-email".into(),
    );
    e.user_agent = Some("Mozilla/5.0 Chrome/123 plaintext-ua-secret".into());
    e.username = Some(format!("hmac-sha256:{}", "a".repeat(64)));
    let id = insert_application_event(&pool, e).await;
    let app = router(state(pool.clone()));
    let viewer = login(app.clone(), "viewer").await;
    for path in [
        "/api/application-audit".to_string(),
        format!("/api/application-audit/{id}"),
    ] {
        let (status, body) = request(
            app.clone(),
            "GET",
            &path,
            Some(&viewer),
            serde_json::Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        for secret in ["plaintext-", "private-student-name", "private-email"] {
            assert!(!body.to_string().contains(secret));
        }
    }
    let (_, detail) = request(
        app.clone(),
        "GET",
        &format!("/api/application-audit/{id}"),
        Some(&viewer),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(
        detail["canonical"]["query_string"],
        "password=[REDACTED]&token=[REDACTED]&[key]=[REDACTED]"
    );
    assert_eq!(detail["canonical"]["redacted"], true);
    // The API is read-only: display sanitation must not rewrite stored training observations.
    let raw: serde_json::Value =
        sqlx::query_scalar("SELECT canonical FROM normalized_events WHERE id=$1")
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert!(raw.to_string().contains("plaintext-password"));
    let canonical: events::CanonicalEvent = serde_json::from_value(raw.clone()).unwrap();
    let safe = canonical.clone().display_view().unwrap();
    assert_eq!(
        serde_json::to_value(safe.clone()).unwrap(),
        serde_json::to_value(safe.display_view().unwrap()).unwrap()
    );
    let mut orphan_query = canonical;
    orphan_query.uri_path = None;
    assert_eq!(
        orphan_query.display_view().unwrap().query_string.as_deref(),
        Some("[REDACTED]")
    );
    for patch in [
        serde_json::json!({"body":"never-show-this-body"}),
        serde_json::json!({"username":"never-show-this-user"}),
    ] {
        sqlx::query("UPDATE normalized_events SET canonical=canonical || $1 WHERE id=$2")
            .bind(patch)
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
        let (status, body) = request(
            app.clone(),
            "GET",
            &format!("/api/application-audit/{id}"),
            Some(&viewer),
            serde_json::Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
        assert!(!body.to_string().contains("never-show"));
        let (status, body) = request(
            app.clone(),
            "GET",
            "/api/application-audit",
            Some(&viewer),
            serde_json::Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
        assert!(!body.to_string().contains("never-show"));
        sqlx::query("UPDATE normalized_events SET canonical=$1 WHERE id=$2")
            .bind(&raw)
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
    }
}

#[sqlx::test(migrations = "./migrations")]
async fn application_audit_request_id_correlation_is_bounded(pool: PgPool) {
    let id = insert_application_event(
        &pool,
        application_event(
            "STUDENT_AUDIT",
            "2026-10-26T00:00:00Z",
            Some("same-request"),
        ),
    )
    .await;
    for _ in 0..12 {
        insert_application_event(
            &pool,
            application_event("NGINX", "2026-10-26T00:00:00Z", Some("same-request")),
        )
        .await;
    }
    let unrelated = insert_application_event(
        &pool,
        application_event(
            "SURICATA",
            "2026-10-26T00:00:00Z",
            Some("different-request"),
        ),
    )
    .await;
    let app = router(state(pool));
    let viewer = login(app.clone(), "viewer").await;
    let (status, detail) = request(
        app.clone(),
        "GET",
        &format!("/api/application-audit/{id}"),
        Some(&viewer),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let related = detail["related"].as_array().unwrap();
    assert_eq!(related.len(), 10);
    assert!(
        related
            .iter()
            .all(|r| r["request_id"] == "same-request" && r["id"] != unrelated && r["id"] != id)
    );
    let (_, page) = request(
        app,
        "GET",
        "/api/application-audit?request_id=same-request",
        Some(&viewer),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(page["total"], 13);
}
fn state(pool: PgPool) -> AppState {
    AppState {
        pool,
        ingestion: Arc::new(ingest::Config::default()),
        sensor_id: "test-sensor".into(),
        safety: Arc::new(network::Safety::test()),
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
    firewall::process_one(&state, |_, _, _| async {
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
        "{{\"timestamp\":\"{}\",\"event_type\":\"alert\",\"src_ip\":\"{ip}\",\"alert\":{{\"signature_id\":1000002,\"signature\":\"test SQLi\",\"severity\":1}}}}\n",
        Utc::now().format("%Y-%m-%dT%H:%M:%S%.6f%z")
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
    firewall::process_one(&s, |_, _, _| async { Ok(()) })
        .await
        .unwrap();
    let actions: Vec<String> = sqlx::query_scalar("SELECT action FROM security_alerts ORDER BY id")
        .fetch_all(&s.pool)
        .await
        .unwrap();
    assert_eq!(actions, ["AUTO-BLOCK", "ALERT", "ALERT"]);
    firewall::process_one(&s, |_, _, _| async { anyhow::bail!("kernel failure") })
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
    firewall::process_one(&s, |_, _, _| async { Ok(()) })
        .await
        .unwrap(); // remaining auto job
    firewall::process_one(&s, |_, _, _| async { Ok(()) })
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
    firewall::process_one(&s, |_, _, _| async { Ok(()) })
        .await
        .unwrap();
    assert!(
        !sqlx::query_scalar::<_, bool>("SELECT active FROM blocked_ips")
            .fetch_one(&s.pool)
            .await
            .unwrap()
    );
}

#[sqlx::test(migrations = "./migrations")]
async fn overview_time_windows_and_aggregates(pool: PgPool) {
    sqlx::query("INSERT INTO security_alerts (occurred_at,source,event_type,src_ip,dest_ip,rule_name,severity,action,evidence) VALUES (now()-interval '10 minutes','NGINX','alert','192.0.2.1',NULL,'SQLi',2,'ALERT','test'), (now()-interval '20 minutes','SURICATA','alert','192.0.2.1','192.0.2.2','SQLi',1,'AUTO-BLOCK','test'), (now()-interval '2 days','SURICATA','alert','192.0.2.3',NULL,'Scan',3,'ALERT','test'), (now()-interval '8 days','NGINX','alert','192.0.2.4',NULL,'Old',1,'ALERT','test')")
        .execute(&pool).await.unwrap();
    sqlx::query("INSERT INTO firewall_actions (ip,action,source,reason,status,created_at) VALUES ('192.0.2.1','BLOCK','AUTO','test','PENDING',now()-interval '5 minutes'), ('192.0.2.1','UNBLOCK','MANUAL','test','SUCCESS',now()-interval '5 minutes'), ('192.0.2.1','BLOCK','AUTO','old','ERROR',now()-interval '8 days')")
        .execute(&pool).await.unwrap();
    for (seconds, buckets, expected) in [(3600_i64, 12_i64, 2_i64), (86400, 24, 2), (604800, 28, 3)]
    {
        let result = sqlx::query_scalar::<_, serde_json::Value>(include_str!("overview.sql"))
            .bind(seconds)
            .bind(buckets)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(result["total_alerts"], expected);
        assert_eq!(result["critical_alerts"], 1);
        assert_eq!(result["trend"].as_array().unwrap().len(), buckets as usize);
        let sum: i64 = result["trend"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x["count"].as_i64().unwrap())
            .sum();
        assert_eq!(sum, expected);
        assert_eq!(
            result["recent"].as_array().unwrap().len(),
            expected as usize
        );
        assert_eq!(result["source_ips"][0]["severity"], 1);
        assert_eq!(result["source_ips"][0]["count"], 2);
        assert_eq!(result["destination_ips"].as_array().unwrap().len(), 1);
        assert_eq!(result["unknown_destinations"], expected - 1);
        assert_eq!(
            result["jobs"],
            serde_json::json!([{"status":"PENDING","count":1}])
        );
    }
    sqlx::query("DELETE FROM security_alerts")
        .execute(&pool)
        .await
        .unwrap();
    let empty = sqlx::query_scalar::<_, serde_json::Value>(include_str!("overview.sql"))
        .bind(3600_i64)
        .bind(12_i64)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(empty["total_alerts"], 0);
    assert_eq!(empty["recent"], serde_json::json!([]));
    assert_eq!(empty["source_ips"], serde_json::json!([]));
}

#[sqlx::test(migrations = "./migrations")]
async fn alert_investigation_filters_and_links(pool: PgPool) {
    let id = sqlx::query_scalar::<_, i64>("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,dest_ip,proto,rule_name,signature,category,severity,action,evidence) VALUES ('2026-10-24T10:00:00Z','SURICATA','alert','192.0.2.1','192.0.2.2','TCP','SQLi','signature','Web',1,'ALERT','evidence') RETURNING id")
        .fetch_one(&pool).await.unwrap();
    sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,rule_name,severity,action,evidence) VALUES ('2026-10-23T10:00:00Z','NGINX','alert','192.0.2.1','Other',2,'ALERT','test')").execute(&pool).await.unwrap();
    sqlx::query("INSERT INTO firewall_actions(ip,action,source,reason,status,event_id) VALUES ('192.0.2.1','BLOCK','AUTO','linked','ERROR',$1),('192.0.2.1','BLOCK','MANUAL','unrelated','SUCCESS',NULL)").bind(id).execute(&pool).await.unwrap();
    let app = router(state(pool));
    for path in [
        "/api/alerts/search".to_string(),
        format!("/api/alerts/{id}"),
    ] {
        assert_eq!(
            request(app.clone(), "GET", &path, None, serde_json::Value::Null)
                .await
                .0,
            StatusCode::UNAUTHORIZED
        );
    }
    let token = login(app.clone(), "viewer").await;
    let path = "/api/alerts/search?from=2026-10-24T00:00:00Z&to=2026-10-25T00:00:00Z&source=SURICATA&action=ALERT&dest_ip=192.0.2.2&severity=1&limit=1";
    let (status, result) = request(
        app.clone(),
        "GET",
        path,
        Some(&token),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(result["total"], 1);
    assert_eq!(result["items"][0]["id"], id);
    let (_, empty_page) = request(
        app.clone(),
        "GET",
        &format!("{path}&offset=1"),
        Some(&token),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(empty_page["total"], 1);
    assert_eq!(empty_page["items"], serde_json::json!([]));
    let (_, detail) = request(
        app.clone(),
        "GET",
        &format!("/api/alerts/{id}"),
        Some(&token),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(detail["alert"]["proto"], "TCP");
    assert_eq!(detail["related"].as_array().unwrap().len(), 1);
    assert_eq!(detail["firewall"].as_array().unwrap().len(), 1);
    assert_eq!(detail["firewall"][0]["status"], "ERROR");
    let (audit_status, linked_audit) = request(
        app.clone(),
        "GET",
        &format!("/api/audit?event_id={id}"),
        Some(&token),
        serde_json::Value::Null,
    )
    .await;
    assert_eq!(audit_status, StatusCode::OK);
    assert_eq!(linked_audit.as_array().unwrap().len(), 1);
    assert_eq!(linked_audit[0]["event_id"], id);
    assert_eq!(linked_audit[0]["source"], "AUTO");
    assert!(linked_audit[0].get("completed_at").is_some());

    assert_eq!(
        request(
            app.clone(),
            "GET",
            "/api/alerts/999999",
            Some(&token),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::NOT_FOUND
    );
    assert_eq!(
        request(
            app.clone(),
            "GET",
            "/api/alerts/search?from=2026-10-25T00:00:00Z&to=2026-10-24T00:00:00Z",
            Some(&token),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        request(
            app,
            "GET",
            "/api/alerts/search?dest_ip=invalid",
            Some(&token),
            serde_json::Value::Null
        )
        .await
        .0,
        StatusCode::BAD_REQUEST
    );
}

#[sqlx::test(migrations = "./migrations")]
async fn collection_status_empty_partial_error_and_recovery(pool: PgPool) {
    let s = state(pool);
    let temp = TempLog::new();
    let file = temp.file();
    let path = file.to_str().unwrap();
    std::fs::write(&file, "").unwrap();
    ingest::scan(&s, "SURICATA", path).await.unwrap();
    let empty = s.watchers.read().await["SURICATA"].clone();
    assert!(empty.last_success_at.is_some());
    assert!(empty.last_data_at.is_none());
    assert_eq!(empty.pending_bytes, Some(0));
    std::fs::write(&file, "partial").unwrap();
    ingest::scan(&s, "SURICATA", path).await.unwrap();
    let partial = s.watchers.read().await["SURICATA"].clone();
    assert_eq!(partial.pending_bytes, Some(7));
    assert!(partial.last_data_at.is_some());
    ingest::scan(&s, "SURICATA", path).await.unwrap();
    assert_eq!(
        s.watchers.read().await["SURICATA"].last_data_at,
        partial.last_data_at
    );
    std::fs::write(&file, format!("invalid\n{}", event("192.168.10.10"))).unwrap();
    ingest::scan(&s, "SURICATA", path).await.unwrap();
    let (_, Json(report)) = metrics::readiness(State(s.clone())).await;
    assert_eq!(report["collection"]["SURICATA"]["error_count"], 1);
    assert!(report["collection"]["SURICATA"]["last_alert_at"].is_string());
    assert!(report["collection"]["SURICATA"]["last_error"]["reason"].is_string());
    let last_success = s.watchers.read().await["SURICATA"].last_success_at;
    std::fs::remove_file(&file).unwrap();
    assert!(ingest::scan(&s, "SURICATA", path).await.is_err());
    let failed = s.watchers.read().await["SURICATA"].clone();
    assert_eq!(failed.state, "error");
    assert_eq!(failed.pending_bytes, None);
    assert_eq!(failed.last_success_at, last_success);
    std::fs::write(&file, "").unwrap();
    ingest::scan(&s, "SURICATA", path).await.unwrap();
    assert_eq!(s.watchers.read().await["SURICATA"].state, "watching");
    assert!(s.watchers.read().await["SURICATA"].error.is_none());
}
