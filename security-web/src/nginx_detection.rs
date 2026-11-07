//! Proxy observations only. Transactional bounded state; never calls an actuator.
use crate::*;
use events::CanonicalEvent;
use serde_json::json;
pub const RULES: [(&str, &str, i64, i64); 7] = [
    ("HTTP_REQUEST_BURST", "HTTP Request Burst", 120, 30),
    ("HTTP_REJECTION_BURST", "HTTP Rejection Burst", 10, 60),
    ("LARGE_RESPONSE_BURST", "Large API Response Burst", 30, 60),
    ("GATEWAY_ERROR_BURST", "Gateway Error Burst", 10, 60),
    ("UNEXPECTED_HTTP_METHOD", "Unexpected HTTP Method", 1, 0),
    ("SENSITIVE_PATH_PROBE", "Sensitive Path Probe", 1, 0),
    (
        "PATH_ENUMERATION_BURST",
        "Distinct Path Enumeration Burst",
        20,
        60,
    ),
];
pub fn unexpected_method(method: Option<&str>) -> bool {
    matches!(
        method,
        Some(
            "TRACE"
                | "CONNECT"
                | "PROPFIND"
                | "PROPPATCH"
                | "MKCOL"
                | "COPY"
                | "MOVE"
                | "LOCK"
                | "UNLOCK"
                | "REPORT"
                | "SEARCH"
                | "MKACTIVITY"
                | "CHECKOUT"
                | "MERGE"
        )
    )
}
pub fn sensitive_path(path: &str) -> bool {
    let path = path
        .split('?')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    path == "/.env"
        || path.starts_with("/.env.")
        || path.starts_with("/.env/")
        || path.starts_with("/.git/")
        || matches!(path.as_str(), "/actuator/env" | "/actuator/heapdump")
        || path.starts_with("/actuator/env/")
        || path.starts_with("/actuator/heapdump/")
}
fn enumeration_path(e: &CanonicalEvent) -> Option<&str> {
    let p = e.uri_path.as_deref()?;
    (e.status_code == Some(404)
        && p.starts_with('/')
        && !p.contains("[REDACTED")
        && !["/assets/", "/static/", "/images/"]
            .iter()
            .any(|prefix| p.starts_with(prefix))
        && ![
            ".css", ".js", ".png", ".jpg", ".ico", ".svg", ".woff2", ".map",
        ]
        .iter()
        .any(|ext| p.ends_with(ext)))
    .then_some(p)
}
fn flags(e: &CanonicalEvent) -> [bool; 4] {
    let path = e.uri_path.as_deref().unwrap_or_default();
    let excluded = matches!(
        path,
        "/health"
            | "/healthz"
            | "/readyz"
            | "/api/health"
            | "/actuator/health"
            | "/favicon.ico"
            | "/robots.txt"
    ) || ["/assets/", "/static/", "/images/"]
        .iter()
        .any(|p| path.starts_with(p));
    // Explicit API allowlist; no downloads, reports or export routes.
    let selected = matches!(path, "/api/users" | "/api/students" | "/api/access-logs");
    [
        !path.is_empty() && !excluded,
        matches!(e.status_code, Some(400 | 413 | 414 | 431)),
        selected
            && e.http_method.as_deref() == Some("GET")
            && e.status_code.is_some_and(|s| (200..300).contains(&s))
            && e.response_bytes.is_some(),
        matches!(e.status_code, Some(502 | 504)),
    ]
}
pub async fn observe(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    e: &CanonicalEvent,
    key: &str,
) -> Result<()> {
    if e.source != "NGINX"
        || e.event_type != "http_request"
        || e.timestamp > Utc::now() + chrono::Duration::seconds(5)
    {
        return Ok(());
    }
    let f = flags(e);
    sqlx::query("SELECT pg_advisory_xact_lock(7141003)")
        .execute(&mut **tx)
        .await?;
    sqlx::query(
        "DELETE FROM nginx_behavior_observations WHERE received_at<now()-interval '5 minutes'",
    )
    .execute(&mut **tx)
    .await?;
    let inserted=sqlx::query("INSERT INTO nginx_behavior_observations(event_key,source_instance,client_ip,occurred_at,burst,rejection,large_response,gateway,response_bytes,enumeration_path) VALUES($1,$2,$3::inet,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT DO NOTHING")
        .bind(key).bind(&e.source_instance).bind(e.client_ip.map(|v|v.to_string())).bind(e.timestamp).bind(f[0]).bind(f[1]).bind(f[2]).bind(f[3]).bind(e.response_bytes.unwrap_or(0).min(i64::MAX as u64) as i64).bind(enumeration_path(e)).execute(&mut **tx).await?.rows_affected();
    if inserted == 0 {
        return Ok(());
    }
    sqlx::query("DELETE FROM nginx_behavior_observations WHERE event_key IN (SELECT event_key FROM nginx_behavior_observations ORDER BY received_at DESC,event_key DESC OFFSET 100000)").execute(&mut **tx).await?;
    for i in [0usize, 1, 2, 3, 6] {
        let (code, name, threshold, seconds) = &RULES[i];
        if !(if i == 6 {
            enumeration_path(e).is_some()
        } else {
            f[i]
        }) {
            continue;
        }
        let global = i == 3;
        let subject = if global {
            "proxy".to_owned()
        } else {
            let Some(ip) = e.client_ip else {
                continue;
            };
            ip.to_string()
        };
        let watermark:DateTime<Utc>=sqlx::query_scalar("SELECT max(occurred_at) FROM nginx_behavior_observations WHERE source_instance=$1 AND ($2 OR host(client_ip)=$3)").bind(&e.source_instance).bind(global).bind(&subject).fetch_one(&mut **tx).await?;
        let column = if i == 6 {
            "enumeration_path IS NOT NULL"
        } else {
            ["burst", "rejection", "large_response", "gateway"][i]
        };
        let count_expr = if i == 6 {
            "count(DISTINCT enumeration_path)"
        } else {
            "count(*)"
        }; // trusted constants only
        let query = format!(
            "SELECT {count_expr}::bigint,COALESCE(sum(response_bytes),0)::text FROM nginx_behavior_observations WHERE source_instance=$1 AND ($2 OR host(client_ip)=$3) AND occurred_at>$4 AND occurred_at<=$5 AND {column}"
        );
        let (count, bytes): (i64, String) = sqlx::query_as(&query)
            .bind(&e.source_instance)
            .bind(global)
            .bind(&subject)
            .bind(watermark - chrono::Duration::seconds(*seconds))
            .bind(watermark)
            .fetch_one(&mut **tx)
            .await?;
        let bytes: u128 = bytes.parse()?;
        if count < *threshold || (i == 2 && bytes < 10 * 1024 * 1024) {
            continue;
        }
        let existing:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM security_alerts WHERE source='NGINX' AND signature=$1 AND evidence::jsonb->>'source_instance'=$2 AND evidence::jsonb->>'subject'=$3 AND occurred_at>$4 AND occurred_at<=$5)").bind(code).bind(&e.source_instance).bind(&subject).bind(watermark-chrono::Duration::seconds(*seconds)).bind(watermark).fetch_one(&mut **tx).await?;
        if existing {
            continue;
        }
        let evidence = json!({"rule_code":code,"source_instance":e.source_instance,"subject":subject,"window_seconds":seconds,"event_count":count,"response_bytes":bytes.to_string(),"last_seen":watermark,"recommended_action":"ALERT_ONLY","scope":if global {"proxy"} else {"client_ip"},"reason":if global {"Upstream availability issue; not proof of an attack"} else {"Lab threshold exceeded; investigate before enforcement"}});
        sqlx::query("INSERT INTO security_alerts(occurred_at,source,event_type,src_ip,proto,rule_name,signature,category,severity,action,evidence,event_key) VALUES($1,'NGINX','alert',$2::inet,'HTTP',$3,$4,'Proxy Behavior',2,'ALERT',$5,$6) ON CONFLICT(event_key) DO NOTHING")
            .bind(watermark).bind(if global {None} else {e.client_ip.map(|v|v.to_string())}).bind(format!("NGINX: {name}")).bind(code).bind(evidence.to_string()).bind(format!("{key}:{code}")).execute(&mut **tx).await?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[sqlx::test(migrations = "./migrations")]
    async fn enumeration_counts_distinct_sanitized_paths(pool: PgPool) {
        let mut tx = pool.begin().await.unwrap();
        let mut e = CanonicalEvent::new("NGINX", Utc::now());
        e.client_ip = Some("192.0.2.1".parse().unwrap());
        e.status_code = Some(404);
        for i in 0..40 {
            e.uri_path = Some("/same-path".into());
            observe(&mut tx, &e, &format!("same-{i}")).await.unwrap();
        }
        for i in 0..19 {
            e.uri_path = Some(format!("/probe-{i}"));
            observe(&mut tx, &e, &format!("path-{i}")).await.unwrap();
            observe(&mut tx, &e, &format!("path-{i}")).await.unwrap();
            let n: i64 = sqlx::query_scalar(
                "SELECT count(*) FROM security_alerts WHERE signature='PATH_ENUMERATION_BURST'",
            )
            .fetch_one(&mut *tx)
            .await
            .unwrap();
            assert_eq!(n, i64::from(i == 18));
        }
        e.uri_path = Some("/assets/missing.js".into());
        assert!(enumeration_path(&e).is_none());
        for p in [
            "/.env",
            "/.git/config",
            "/actuator/env",
            "/actuator/heapdump",
        ] {
            assert!(sensitive_path(p));
        }
        for p in ["/api/students", "/actuator/health", "/.environment"] {
            assert!(!sensitive_path(p));
        }
    }
    #[test]
    fn methods_and_routes_are_precise() {
        assert!(unexpected_method(Some("PROPFIND")));
        assert!(!unexpected_method(Some("OTHER")));
        assert!(!unexpected_method(Some("OPTIONS")));
        let parsed=events::parse("NGINX",r#"{"timestamp":"2026-11-06T00:00:00Z","http_method":"PROPFIND","uri_path":"/","status":405}"#).unwrap();
        assert!(
            parsed
                .detections
                .iter()
                .any(|r| r.rule_id == "UNEXPECTED_HTTP_METHOD")
        );
        let mut e = CanonicalEvent::new("NGINX", Utc::now());
        e.uri_path = Some("/assets/app.js".into());
        assert!(!flags(&e)[0]);
        e.uri_path = Some("/api/users/export".into());
        e.http_method = Some("GET".into());
        e.status_code = Some(200);
        e.response_bytes = Some(20000000);
        assert!(!flags(&e)[2]);
        e.uri_path = Some("/api/users".into());
        assert!(flags(&e)[2]);
        e.response_bytes = None;
        assert!(!flags(&e)[2]);
    }
    #[sqlx::test(migrations = "./migrations")]
    async fn thresholds_replay_and_proxy_scope(pool: PgPool) {
        for (code, status, n, bytes) in [
            ("HTTP_REQUEST_BURST", 200, 120, 0),
            ("HTTP_REJECTION_BURST", 413, 10, 0),
            ("LARGE_RESPONSE_BURST", 200, 30, 350000),
            ("GATEWAY_ERROR_BURST", 502, 10, 0),
        ] {
            let mut tx = pool.begin().await.unwrap();
            for i in 0..n {
                let mut e = CanonicalEvent::new("NGINX", Utc::now());
                e.source_instance = code.into();
                e.uri_path = Some("/api/users".into());
                e.http_method = Some("GET".into());
                e.status_code = Some(status);
                e.response_bytes = Some(bytes);
                e.client_ip = Some(
                    if code == "GATEWAY_ERROR_BURST" {
                        format!("192.0.2.{}", i + 1)
                    } else {
                        "192.0.2.1".into()
                    }
                    .parse()
                    .unwrap(),
                );
                if i == n - 1 {
                    e.timestamp -= chrono::Duration::seconds(1);
                }
                let key = format!("{code}-{i}");
                observe(&mut tx, &e, &key).await.unwrap();
                observe(&mut tx, &e, &key).await.unwrap();
                let count: i64 =
                    sqlx::query_scalar("SELECT count(*) FROM security_alerts WHERE signature=$1")
                        .bind(code)
                        .fetch_one(&mut *tx)
                        .await
                        .unwrap();
                assert_eq!(count, i64::from(i == n - 1), "{code}-{i}");
            }
            tx.commit().await.unwrap();
        }
        let count:i64=sqlx::query_scalar("SELECT count(*) FROM security_alerts WHERE action!='ALERT' OR (signature='GATEWAY_ERROR_BURST' AND src_ip IS NOT NULL)").fetch_one(&pool).await.unwrap();
        assert_eq!(count, 0);
    }
}
