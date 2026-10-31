use crate::*;
use events::CanonicalEvent;
use serde_json::json;
use std::path::{Path, PathBuf};

fn state(pool: PgPool, collect_all: bool) -> AppState {
    AppState {
        pool,
        auth: auth::test_auth(),
        policy: PolicyEngine::new(false, vec![], false),
        firewall_cmd: "/not-installed".into(),
        whitelist: Arc::new(vec!["192.168.1.1".parse().unwrap()]),
        watchers: Default::default(),
        ingestion: Arc::new(ingest::Config {
            collect_all,
            auth_threshold: 3,
            ..Default::default()
        }),
        sensor_id: "foundation-test".into(),
        safety: Arc::new(network::Safety::test()),
    }
}
struct Logs(PathBuf);
impl Logs {
    fn new() -> Self {
        let p = env::temp_dir().join(format!("foundation-ingest-{}", rand::random::<u64>()));
        std::fs::create_dir(&p).unwrap();
        Self(p)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Logs {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
fn audit(id: &str, request: &str, status: u16, time: DateTime<Utc>) -> String {
    let mut event = CanonicalEvent::new("STUDENT_AUDIT", time);
    event.event_id = id.into();
    event.source_instance = "student-web".into();
    event.client_ip = Some("192.168.1.50".parse().unwrap());
    event.request_id = Some(request.into());
    event.http_method = Some("POST".into());
    event.uri_path = Some("/api/auth/login".into());
    event.status_code = Some(status);
    event.latency_ms = Some(1.0);
    event.outcome = if status >= 400 { "failure" } else { "success" }.into();
    event.redacted = true;
    serde_json::to_string(&event).unwrap() + "\n"
}
async fn append(s: &AppState, source: &str, path: &Path, line: &str) {
    use std::io::Write;
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .unwrap()
        .write_all(line.as_bytes())
        .unwrap();
    ingest::process_file(s, source, path).await.unwrap();
}
async fn count(pool: &PgPool, table: &str) -> i64 {
    sqlx::query_scalar(&format!("SELECT count(*) FROM {table}"))
        .fetch_one(pool)
        .await
        .unwrap()
}

#[sqlx::test(migrations = "./migrations")]
async fn captures_benign_audit_nginx_and_eve_with_stable_identity(pool: PgPool) {
    let s = state(pool, true);
    let logs = Logs::new();
    let path = logs.path("audit.log");
    let event = audit("event-1", "edge-1", 204, Utc::now());
    append(&s, "STUDENT_AUDIT", &path, &event).await;
    let copy = logs.path("audit.log.1");
    append(&s, "STUDENT_AUDIT", &copy, &event).await;
    assert_eq!(count(&s.pool, "normalized_events").await, 1);
    append(&s,"NGINX",&logs.path("access.log"),&format!("{}\n",json!({"timestamp":Utc::now(),"client_ip":"192.168.1.50","request_id":"edge-1","http_method":"POST","uri_path":"/api/auth/login","status":204,"latency_seconds":0.001,"user_agent":"Mozilla/5.0"}))).await;
    append(&s,"SURICATA",&logs.path("eve.json"),&format!("{}\n",json!({"timestamp":Utc::now(),"event_type":"flow","src_ip":"192.0.2.1","dest_ip":"192.0.2.2","proto":"TCP","flow":{"age":10,"bytes_toserver":100,"pkts_toserver":2}}))).await;
    assert_eq!(count(&s.pool, "normalized_events").await, 3);
    assert_eq!(count(&s.pool, "security_alerts").await, 0);
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "SELECT count(*) FROM normalized_events WHERE request_id='edge-1'"
        )
        .fetch_one(&s.pool)
        .await
        .unwrap(),
        2
    );
    let value: serde_json::Value =
        sqlx::query_scalar("SELECT canonical FROM normalized_events WHERE event_type='flow'")
            .fetch_one(&s.pool)
            .await
            .unwrap();
    assert_eq!(value["flow"]["bytes_to_server"], 100);
    assert_eq!(value["transport"], "TCP");
}
#[sqlx::test(migrations = "./migrations")]
async fn dataset_off_keeps_detections_and_uses_no_normal_event_rows(pool: PgPool) {
    let s = state(pool, false);
    let logs = Logs::new();
    let path = logs.path("access.log");
    append(&s,"NGINX",&path,r#"192.168.10.10 - - [26/Oct/2026:12:00:00 +0000] "GET /api/students?q=UNION%20SELECT%201&token=CANARY_SECRET HTTP/1.1" 200 10 "-" "nuclei""#).await;
    // Partial final line is not acknowledged before newline.
    assert_eq!(count(&s.pool, "security_alerts").await, 0);
    append(&s, "NGINX", &path, "\n").await;
    assert_eq!(count(&s.pool, "normalized_events").await, 0);
    assert_eq!(count(&s.pool, "security_alerts").await, 2);
    let evidence: Vec<String> = sqlx::query_scalar("SELECT evidence FROM security_alerts")
        .fetch_all(&s.pool)
        .await
        .unwrap();
    assert!(evidence.iter().all(|e| !e.contains("CANARY_SECRET")));
}
#[sqlx::test(migrations = "./migrations")]
async fn malformed_oversized_partial_and_rotation_do_not_poison_later_events(pool: PgPool) {
    let mut s = state(pool, true);
    Arc::make_mut(&mut s.ingestion).max_line_bytes = 1024;
    let logs = Logs::new();
    let path = logs.path("audit.log");
    append(&s, "STUDENT_AUDIT", &path, &"X".repeat(4096)).await;
    assert_eq!(count(&s.pool, "normalized_events").await, 0);
    append(
        &s,
        "STUDENT_AUDIT",
        &path,
        &format!(
            "\n{{\"secret\":\"CANARY_SECRET\"}}\n{}",
            audit("valid-1", "edge-1", 204, Utc::now())
        ),
    )
    .await;
    assert_eq!(count(&s.pool, "normalized_events").await, 1);
    assert!(count(&s.pool, "ingestion_quarantine").await >= 2);
    let reasons: Vec<String> = sqlx::query_scalar("SELECT reason FROM ingestion_errors")
        .fetch_all(&s.pool)
        .await
        .unwrap();
    assert!(reasons.iter().all(|s| !s.contains("CANARY_SECRET")));
    std::fs::rename(&path, logs.path("audit.log.1")).unwrap();
    std::fs::write(&path, audit("valid-2", "edge-2", 204, Utc::now())).unwrap();
    ingest::scan(&s, "STUDENT_AUDIT", path.to_str().unwrap())
        .await
        .unwrap();
    assert_eq!(count(&s.pool, "normalized_events").await, 2);
    // Replaying source cursor does not repeat a normalized effect.
    sqlx::query("UPDATE log_cursors SET byte_offset=0,anchor='',discarding_oversized=false")
        .execute(&s.pool)
        .await
        .unwrap();
    ingest::scan(&s, "STUDENT_AUDIT", path.to_str().unwrap())
        .await
        .unwrap();
    assert_eq!(count(&s.pool, "normalized_events").await, 2);
}
#[sqlx::test(migrations = "./migrations")]
async fn normalized_insert_failure_rolls_back_receipt_alert_and_cursor(pool: PgPool) {
    let s = state(pool, true);
    let logs = Logs::new();
    let path = logs.path("audit.log");
    std::fs::write(&path, audit("valid-1", "edge-1", 204, Utc::now())).unwrap();
    sqlx::query("ALTER TABLE normalized_events ADD CONSTRAINT simulated_outage CHECK(source!='STUDENT_AUDIT')").execute(&s.pool).await.unwrap();
    assert!(
        ingest::process_file(&s, "STUDENT_AUDIT", &path)
            .await
            .is_err()
    );
    assert_eq!(count(&s.pool, "log_cursors").await, 0);
    assert_eq!(count(&s.pool, "source_event_receipts").await, 0);
    sqlx::query("ALTER TABLE normalized_events DROP CONSTRAINT simulated_outage")
        .execute(&s.pool)
        .await
        .unwrap();
    ingest::process_file(&s, "STUDENT_AUDIT", &path)
        .await
        .unwrap();
    assert_eq!(count(&s.pool, "normalized_events").await, 1);
}
#[sqlx::test(migrations = "./migrations")]
async fn authentication_counter_correlates_two_sources_and_resets_on_success(pool: PgPool) {
    let s = state(pool, false);
    let logs = Logs::new();
    let nginx = logs.path("access.log");
    let student = logs.path("audit.log");
    let start = Utc::now();
    for i in 0..3 {
        let time = start + chrono::Duration::seconds(i);
        let id = format!("edge-{i}");
        let status = if i % 2 == 0 { 401 } else { 403 };
        append(&s,"NGINX",&nginx,&format!("{}\n",json!({"timestamp":time,"client_ip":"192.168.1.50","request_id":id,"http_method":"POST","uri_path":"/api/auth/login","status":status}))).await;
        append(
            &s,
            "STUDENT_AUDIT",
            &student,
            &audit(&format!("audit-{i}"), &id, status, time),
        )
        .await;
    }
    assert_eq!(count(&s.pool, "auth_observations").await, 3);
    assert_eq!(count(&s.pool, "security_alerts").await, 1);
    assert_eq!(count(&s.pool, "firewall_actions").await, 0);
    append(
        &s,
        "STUDENT_AUDIT",
        &student,
        &audit(
            "success-1",
            "success-1",
            204,
            start + chrono::Duration::seconds(65),
        ),
    )
    .await;
    for i in 0..2 {
        append(
            &s,
            "STUDENT_AUDIT",
            &student,
            &audit(
                &format!("retry-{i}"),
                &format!("retry-{i}"),
                401,
                start + chrono::Duration::seconds(66 + i),
            ),
        )
        .await;
    }
    assert_eq!(count(&s.pool, "security_alerts").await, 1);
    append(
        &s,
        "STUDENT_AUDIT",
        &student,
        &audit(
            "retry-3",
            "retry-3",
            401,
            start + chrono::Duration::seconds(68),
        ),
    )
    .await;
    // Student now uses APP-1001 threshold10, not the legacy threshold3.
    assert_eq!(count(&s.pool, "security_alerts").await, 1);
}
#[sqlx::test(migrations = "./migrations")]
async fn off_switch_blocks_pending_work_and_expired_blocks_are_not_restored(pool: PgPool) {
    let mut s = state(pool, false);
    Arc::make_mut(&mut s.safety).mode = "OFF".into();
    firewall::enqueue(
        &s.pool,
        "192.168.1.50".parse().unwrap(),
        "BLOCK",
        "admin",
        "test",
        None,
    )
    .await
    .unwrap();
    assert!(
        !firewall::process_one(&s, |_, _, _| async { panic!("OFF must never execute") })
            .await
            .unwrap()
    );
    assert_eq!(
        sqlx::query_scalar::<_, String>("SELECT status FROM firewall_actions")
            .fetch_one(&s.pool)
            .await
            .unwrap(),
        "PENDING"
    );
    sqlx::query("INSERT INTO blocked_ips(ip,reason,expires_at) VALUES('192.168.1.51','expired',now()-interval '1 second'),('192.168.1.52','legacy',NULL)").execute(&s.pool).await.unwrap();
    firewall::restore_jobs(&s.pool).await.unwrap();
    assert_eq!(count(&s.pool, "firewall_actions").await, 1);
    assert!(firewall::validate(&s, "192.168.1.1").is_err());
}
#[test]
fn nft_timeout_elements_are_understood() {
    assert_eq!(firewall::parse_set(r#"{"nftables":[{"set":{"name":"blocked_ips","elem":[{"elem":{"val":"192.168.1.50","timeout":300000,"expires":250000}}]}}]}"#).unwrap().len(),1);
}

#[sqlx::test(migrations = "./migrations")]
async fn extended_sensor_rules_use_audited_bounded_response_only_when_enabled(pool: PgPool) {
    let mut s = state(pool, true);
    let sids = vec![1000008, 1000010, 1000011, 1000012, 1000013, 1000014];
    let logs = Logs::new();
    let path = logs.path("eve.json");
    for sid in &sids {
        append(
            &s,
            "SURICATA",
            &path,
            &format!(
                "{}\n",
                json!({
                    "timestamp":Utc::now(), "event_type":"alert", "src_ip":"192.168.1.50",
                    "alert":{"signature_id":sid,"severity":1}
                })
            ),
        )
        .await;
    }
    assert_eq!(count(&s.pool, "security_alerts").await, 6);
    assert_eq!(count(&s.pool, "firewall_actions").await, 0);

    s.policy = PolicyEngine::new(true, sids.clone(), false);
    Arc::make_mut(&mut s.safety).mode = "OFF".into();
    for sid in sids {
        append(
            &s,
            "SURICATA",
            &path,
            &format!(
                "{}\n",
                json!({
                    "timestamp":Utc::now(), "event_type":"alert", "src_ip":"192.168.1.50",
                    "alert":{"signature_id":sid,"severity":1}
                })
            ),
        )
        .await;
    }
    assert_eq!(count(&s.pool, "firewall_actions").await, 6);
    assert!(
        !firewall::process_one(&s, |_, _, _| async { panic!("OFF must not call a helper") })
            .await
            .unwrap()
    );

    Arc::make_mut(&mut s.safety).mode = "ENFORCE".into();
    for _ in 0..6 {
        assert!(
            firewall::process_one(&s, |_, _, ttl| async move {
                assert!(ttl.is_some_and(|seconds| (1..=300).contains(&seconds)));
                Ok(()) // Mock actuator: never invokes the real helper or kernel.
            })
            .await
            .unwrap()
        );
    }
    let successful: i64 = sqlx::query_scalar("SELECT count(*) FROM firewall_actions WHERE status='SUCCESS' AND actor='system' AND event_id IS NOT NULL")
        .fetch_one(&s.pool).await.unwrap();
    assert_eq!(successful, 6);
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "SELECT count(*) FROM security_alerts WHERE action='AUTO-BLOCK'"
        )
        .fetch_one(&s.pool)
        .await
        .unwrap(),
        6
    );
}

#[sqlx::test(migrations = "./migrations")]
async fn historical_alerts_and_expired_pending_jobs_never_enforce(pool: PgPool) {
    let mut s = state(pool, true);
    s.policy = PolicyEngine::new(true, vec![1000002], true);
    let logs = Logs::new();
    let path = logs.path("eve.json");
    for (index, time) in [Utc::now() - chrono::Duration::hours(1), Utc::now()]
        .into_iter()
        .enumerate()
    {
        append(&s,"SURICATA",&path,&format!("{}\n",json!({"timestamp":time,"event_type":"alert","src_ip":"192.168.1.50","alert":{"signature_id":1000002,"severity":1}}))).await;
        assert_eq!(count(&s.pool, "firewall_actions").await, index as i64);
    }
    sqlx::query("UPDATE firewall_actions SET expires_at=now()-interval '1 second'")
        .execute(&s.pool)
        .await
        .unwrap();
    assert!(
        firewall::process_one(&s, |_, _, _| async {
            panic!("expired job must not execute")
        })
        .await
        .unwrap()
    );
    assert_eq!(
        sqlx::query_scalar::<_, String>("SELECT status FROM firewall_actions")
            .fetch_one(&s.pool)
            .await
            .unwrap(),
        "ERROR"
    );
}
#[sqlx::test(migrations = "./migrations")]
async fn restore_preserves_original_deadline_instead_of_renewing_block(pool: PgPool) {
    let s = state(pool, false);
    let expiry = Utc::now() + chrono::Duration::seconds(30);
    sqlx::query("INSERT INTO blocked_ips(ip,reason,expires_at) VALUES('192.168.1.50','test',$1)")
        .bind(expiry)
        .execute(&s.pool)
        .await
        .unwrap();
    firewall::restore_jobs(&s.pool).await.unwrap();
    firewall::process_one(&s, |_, _, ttl| async move {
        assert!((1..=30).contains(&ttl.unwrap()));
        Ok(())
    })
    .await
    .unwrap();
    let applied: DateTime<Utc> = sqlx::query_scalar("SELECT expires_at FROM blocked_ips")
        .fetch_one(&s.pool)
        .await
        .unwrap();
    assert!((applied - expiry).num_milliseconds().abs() < 1);
}

fn app_line(id: &str, ip: Option<&str>, path: &str, status: u16, at: DateTime<Utc>) -> String {
    let mut v: serde_json::Value = serde_json::from_str(&audit(id, id, status, at)).unwrap();
    v["client_ip"] = json!(ip);
    v["uri_path"] = json!(path);
    v["http_method"] = json!("GET");
    v.to_string() + "\n"
}
async fn app_alerts(pool: &PgPool, code: &str) -> Vec<(i16, String)> {
    sqlx::query_as("SELECT severity,evidence FROM security_alerts WHERE signature=$1 ORDER BY id")
        .bind(code)
        .fetch_all(pool)
        .await
        .unwrap()
}
#[sqlx::test(migrations = "./migrations")]
async fn app_auth_threshold_dedup_escalation_and_no_auto(pool: PgPool) {
    let mut s = state(pool, false); // Detection must not depend on dataset storage.
    s.policy = PolicyEngine::new(true, vec![1000009], true);
    let logs = Logs::new();
    let p = logs.path("audit.log");
    let at = Utc::now();
    let lines = (0..9)
        .map(|i| {
            app_line(
                &format!("a{i}"),
                Some("192.168.1.50"),
                "/api/auth/me",
                401,
                at,
            )
        })
        .collect::<String>();
    append(&s, "STUDENT_AUDIT", &p, &lines).await;
    assert!(app_alerts(&s.pool, "APP-1001").await.is_empty());
    append(
        &s,
        "STUDENT_AUDIT",
        &p,
        &app_line("a9", Some("192.168.1.50"), "/api/auth/login", 401, at),
    )
    .await;
    assert_eq!(app_alerts(&s.pool, "APP-1001").await.len(), 1);
    append(&s, "STUDENT_AUDIT", &p, &lines).await; // repeated transport deliveries
    let rest = (10..25)
        .map(|i| {
            app_line(
                &format!("a{i}"),
                Some("192.168.1.50"),
                "/api/auth/me",
                401,
                at,
            )
        })
        .collect::<String>();
    append(&s, "STUDENT_AUDIT", &p, &rest).await;
    let rows = app_alerts(&s.pool, "APP-1001").await;
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, 1);
    let evidence: serde_json::Value = serde_json::from_str(&rows[0].1).unwrap();
    assert_eq!(evidence["event_count"], 25);
    assert_eq!(evidence["recommended_action"], "BLOCK");
    assert_eq!(count(&s.pool, "firewall_actions").await, 0);
}
#[sqlx::test(migrations = "./migrations")]
async fn app_burst_loopback_null_ipv6_and_sources(pool: PgPool) {
    let s = state(pool, true);
    let logs = Logs::new();
    let p = logs.path("audit.log");
    let at = Utc::now();
    let lines = (0..300)
        .map(|i| {
            app_line(
                &format!("b{i}"),
                Some("127.0.0.1"),
                "/api/students",
                200,
                at,
            )
        })
        .collect::<String>();
    // Boundary99 must not fire, then100 creates one,300 escalates same episode.
    let parts: Vec<_> = lines.split_inclusive('\n').collect();
    append(&s, "STUDENT_AUDIT", &p, &parts[..99].concat()).await;
    assert!(app_alerts(&s.pool, "APP-1004").await.is_empty());
    append(&s, "STUDENT_AUDIT", &p, parts[99]).await;
    assert_eq!(app_alerts(&s.pool, "APP-1004").await.len(), 1);
    append(&s, "STUDENT_AUDIT", &p, &parts[100..].concat()).await;
    let rows = app_alerts(&s.pool, "APP-1004").await;
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, 1);
    let evidence: serde_json::Value = serde_json::from_str(&rows[0].1).unwrap();
    assert_eq!(evidence["recommended_action"], "ALERT_ONLY");
    append(
        &s,
        "STUDENT_AUDIT",
        &p,
        &app_line("null-ip", None, "/api/auth/me", 401, at),
    )
    .await;
    let v6 = (0..20)
        .map(|i| app_line(&format!("v{i}"), Some("::1"), "/api/auth/me", 401, at))
        .collect::<String>();
    append(&s, "STUDENT_AUDIT", &p, &v6).await;
    assert_eq!(app_alerts(&s.pool, "APP-1001").await.len(), 1);
    append(&s,"SURICATA",&logs.path("eve.json"),&format!("{}\n",json!({"timestamp":at,"event_type":"alert","src_ip":"127.0.0.1","alert":{"signature_id":1000009,"severity":2}}))).await;
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "SELECT count(*) FROM security_alerts WHERE source='SURICATA'"
        )
        .fetch_one(&s.pool)
        .await
        .unwrap(),
        1
    );
    assert_eq!(app_alerts(&s.pool, "APP-1004").await.len(), 1);
    assert_eq!(count(&s.pool, "firewall_actions").await, 0);
}
#[sqlx::test(migrations = "./migrations")]
async fn app_authorization_probing_failures_and_redacted_paths(pool: PgPool) {
    let s = state(pool, true);
    let logs = Logs::new();
    let p = logs.path("audit.log");
    let at = Utc::now();
    for i in 0..15 {
        append(
            &s,
            "STUDENT_AUDIT",
            &p,
            &app_line(
                &format!("f{i}"),
                Some("192.168.1.50"),
                "/api/users",
                403,
                at,
            ),
        )
        .await;
        if i == 6 {
            assert!(app_alerts(&s.pool, "APP-1002").await.is_empty());
        }
    }
    assert_eq!(app_alerts(&s.pool, "APP-1002").await.len(), 1);
    assert_eq!(app_alerts(&s.pool, "APP-1005").await[0].0, 2);
    for i in 0..8 {
        append(
            &s,
            "STUDENT_AUDIT",
            &p,
            &app_line(
                &format!("red{i}"),
                Some("192.168.1.51"),
                "/[redacted]",
                404,
                at,
            ),
        )
        .await;
    }
    assert!(app_alerts(&s.pool, "APP-1003").await.is_empty());
    for (i, path) in [
        "/api/users",
        "/api/access-logs",
        "/api/students",
        "/api/classes",
        "/api/majors",
    ]
    .iter()
    .enumerate()
    {
        append(
            &s,
            "STUDENT_AUDIT",
            &p,
            &app_line(&format!("probe{i}"), Some("192.168.1.52"), path, 404, at),
        )
        .await;
    }
    assert_eq!(app_alerts(&s.pool, "APP-1003").await.len(), 1);
}
#[sqlx::test(migrations = "./migrations")]
async fn app_windows_late_events_and_restart(pool: PgPool) {
    let s = state(pool.clone(), false);
    let logs = Logs::new();
    let p = logs.path("audit.log");
    let at = Utc::now() - chrono::Duration::seconds(120);
    let rows = (0..10)
        .map(|i| {
            app_line(
                &format!("old{i}"),
                Some("192.168.1.50"),
                "/api/auth/me",
                401,
                at,
            )
        })
        .collect::<String>();
    append(&s, "STUDENT_AUDIT", &p, &rows).await;
    let restarted = state(pool, false);
    // Gap >60s starts a new episode, not mixed with old observations.
    let newer = at + chrono::Duration::seconds(61);
    let rows = (0..9)
        .map(|i| {
            app_line(
                &format!("new{i}"),
                Some("192.168.1.50"),
                "/api/auth/me",
                401,
                newer,
            )
        })
        .collect::<String>();
    append(&restarted, "STUDENT_AUDIT", &p, &rows).await;
    assert_eq!(app_alerts(&s.pool, "APP-1001").await.len(), 1);
    append(
        &restarted,
        "STUDENT_AUDIT",
        &p,
        &app_line("late", Some("192.168.1.50"), "/api/auth/me", 401, at),
    )
    .await;
    assert_eq!(app_alerts(&s.pool, "APP-1001").await.len(), 1);
    append(
        &restarted,
        "STUDENT_AUDIT",
        &p,
        &app_line("new9", Some("192.168.1.50"), "/api/auth/me", 401, newer),
    )
    .await;
    assert_eq!(app_alerts(&s.pool, "APP-1001").await.len(), 2);
}

#[sqlx::test(migrations = "./migrations")]
async fn app_manual_response_links_actor_and_alert_without_auto_mode(pool: PgPool) {
    let mut s = state(pool, true);
    Arc::make_mut(&mut s.safety).mode = "MANUAL".into();
    let logs = Logs::new();
    let at = Utc::now();
    let rows = (0..10)
        .map(|i| {
            app_line(
                &format!("m{i}"),
                Some("192.168.1.50"),
                "/api/auth/login",
                401,
                at,
            )
        })
        .collect::<String>();
    append(&s, "STUDENT_AUDIT", &logs.path("audit.log"), &rows).await;
    let id: i64 = sqlx::query_scalar("SELECT id FROM security_alerts WHERE signature='APP-1001'")
        .fetch_one(&s.pool)
        .await
        .unwrap();
    let actor = auth::Identity {
        username: "admin".into(),
        role: "admin".into(),
    };
    let result = block_ip(
        State(s.clone()),
        Extension(actor.clone()),
        Json(BlockRequest {
            ip: "127.0.0.1".into(),
            reason: "test protected".into(),
            event_id: Some(id),
        }),
    )
    .await;
    assert!(result.is_err());
    assert_eq!(count(&s.pool, "firewall_actions").await, 0);
    let result = block_ip(
        State(s.clone()),
        Extension(actor.clone()),
        Json(BlockRequest {
            ip: "192.168.1.51".into(),
            reason: "mismatched alert".into(),
            event_id: Some(id),
        }),
    )
    .await;
    assert!(result.is_err());
    let _ = block_ip(
        State(s.clone()),
        Extension(actor),
        Json(BlockRequest {
            ip: "192.168.1.50".into(),
            reason: "APP-1001 reviewed manually".into(),
            event_id: Some(id),
        }),
    )
    .await
    .unwrap();
    assert!(
        firewall::process_one(&s, |_, _, _| async { Ok(()) })
            .await
            .unwrap()
    );
    let row: (String, String, String, i64) =
        sqlx::query_as("SELECT actor,source,status,event_id FROM firewall_actions")
            .fetch_one(&s.pool)
            .await
            .unwrap();
    assert_eq!(row, ("admin".into(), "API".into(), "SUCCESS".into(), id));
    assert_eq!(
        sqlx::query_scalar::<_, String>("SELECT action FROM security_alerts WHERE id=$1")
            .bind(id)
            .fetch_one(&s.pool)
            .await
            .unwrap(),
        "BLOCK"
    );
}
