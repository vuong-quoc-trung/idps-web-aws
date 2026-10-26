//! Authenticated, read-only views of canonical observations (not attack labels).
use crate::*;
use events::CanonicalEvent;
use serde_json::{Value, json};

#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditQuery {
    limit: Option<i64>,
    offset: Option<i64>,
    from: Option<DateTime<Utc>>,
    to: Option<DateTime<Utc>>,
    source: Option<String>,
    client_ip: Option<IpAddr>,
    uri_path: Option<String>,
    status_code: Option<i32>,
    request_id: Option<String>,
    http_method: Option<String>,
}

impl AuditQuery {
    fn validate(&self) -> Result<(i64, i64), ApiError> {
        let limit = self.limit.unwrap_or(25);
        let offset = self.offset.unwrap_or(0);
        if !(1..=200).contains(&limit) || !(0..=1_000_000).contains(&offset) {
            return Err(bad_request("limit phải từ 1–200; offset từ 0–1000000"));
        }
        if matches!((self.from, self.to), (Some(from), Some(to)) if from >= to) {
            return Err(bad_request(
                "Thời gian bắt đầu phải trước thời gian kết thúc",
            ));
        }
        if self
            .source
            .as_deref()
            .is_some_and(|s| !matches!(s, "STUDENT_AUDIT" | "NGINX" | "SURICATA"))
        {
            return Err(bad_request("Nguồn sự kiện không hợp lệ"));
        }
        if self.status_code.is_some_and(|s| !(100..=599).contains(&s)) {
            return Err(bad_request("Mã HTTP phải từ 100–599"));
        }
        if self
            .request_id
            .as_deref()
            .is_some_and(|s| !events::valid_request_id(s))
        {
            return Err(bad_request("Request ID không hợp lệ"));
        }
        if self
            .uri_path
            .as_deref()
            .is_some_and(|s| s.is_empty() || s.len() > 512 || s.chars().any(char::is_control))
        {
            return Err(bad_request(
                "Endpoint phải từ 1–512 byte, không chứa ký tự điều khiển",
            ));
        }
        if self.http_method.as_deref().is_some_and(|s| {
            !matches!(
                s,
                "GET"
                    | "HEAD"
                    | "OPTIONS"
                    | "POST"
                    | "PUT"
                    | "PATCH"
                    | "DELETE"
                    | "CONNECT"
                    | "TRACE"
                    | "OTHER"
            )
        }) {
            return Err(bad_request("HTTP method không hợp lệ"));
        }
        Ok((limit, offset))
    }
}

#[derive(Deserialize, FromRow)]
struct StoredEvent {
    id: i64,
    occurred_at: DateTime<Utc>,
    observed_at: DateTime<Utc>,
    canonical: Value,
}

impl StoredEvent {
    fn safe_event(&self) -> Result<CanonicalEvent, ApiError> {
        // Deserialize into the strict contract before returning anything. Unknown
        // fields, bodies, raw credentials and malformed identities never pass through.
        let event: CanonicalEvent = serde_json::from_value(self.canonical.clone())
            .map_err(|_| api_error("Stored canonical event does not match Schema v1"))?;
        event
            .display_view()
            .map_err(|_| api_error("Stored canonical event failed validation"))
    }

    fn summary(&self) -> Result<Value, ApiError> {
        let e = self.safe_event()?;
        Ok(
            json!({"id":self.id,"occurred_at":self.occurred_at,"observed_at":self.observed_at,
            "source":e.source,"request_id":e.request_id,"client_ip":e.client_ip,
            "http_method":e.http_method,"uri_path":e.uri_path,"status_code":e.status_code,
            "latency_ms":e.latency_ms,"event_type":e.event_type,"outcome":e.outcome,"role":e.role}),
        )
    }
}

pub async fn list(
    State(state): State<AppState>,
    Query(q): Query<AuditQuery>,
) -> Result<Json<Value>, ApiError> {
    let (limit, offset) = q.validate()?;
    // One statement gives the count and page the same PostgreSQL snapshot.
    let page = sqlx::query_scalar::<_, Value>(include_str!("application_audit.sql"))
        .bind(limit)
        .bind(offset)
        .bind(q.from)
        .bind(q.to)
        .bind(q.source)
        .bind(q.client_ip.map(|ip| ip.to_string()))
        .bind(q.uri_path)
        .bind(q.status_code)
        .bind(q.request_id)
        .bind(q.http_method)
        .fetch_one(&state.pool)
        .await
        .map_err(api_error)?;
    let rows: Vec<StoredEvent> = serde_json::from_value(page["items"].clone())
        .map_err(|_| api_error("Invalid application audit page"))?;
    let items = rows
        .iter()
        .map(StoredEvent::summary)
        .collect::<Result<Vec<_>, _>>()?;
    let watchers = state.watchers.read().await;
    let sources = watchers.iter().map(|(source, w)| (source.clone(), json!({
        "state":w.state,"last_success_at":w.last_success_at,"last_data_at":w.last_data_at,
        "pending_bytes":w.pending_bytes,"error_present":w.error.is_some()
    }))).collect::<BTreeMap<_, _>>();
    Ok(Json(
        json!({"items":items,"total":page["total"],"limit":limit,"offset":offset,
        "collection":{"enabled":state.ingestion.collect_all,
            "retention_days":state.ingestion.retention_days,"max_events":state.ingestion.max_events,
            "watchers":sources}}),
    ))
}

pub async fn detail(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Value>, ApiError> {
    let row = sqlx::query_as::<_, StoredEvent>(
        "SELECT id,occurred_at,observed_at,canonical FROM normalized_events WHERE id=$1",
    )
    .bind(id)
    .fetch_optional(&state.pool)
    .await
    .map_err(api_error)?
    .ok_or_else(|| {
        (
            StatusCode::NOT_FOUND,
            Json(json!({"message":"Không tìm thấy sự kiện audit"})),
        )
    })?;
    let event = row.safe_event()?;
    let related = if let Some(request_id) = &event.request_id {
        sqlx::query_as::<_, StoredEvent>("SELECT id,occurred_at,observed_at,canonical FROM normalized_events WHERE request_id=$1 AND id<>$2 ORDER BY occurred_at DESC,id DESC LIMIT 10")
            .bind(request_id).bind(id).fetch_all(&state.pool).await.map_err(api_error)?
            .iter().map(StoredEvent::summary).collect::<Result<Vec<_>, _>>()?
    } else {
        Vec::new()
    };
    Ok(Json(
        json!({"id":id,"occurred_at":row.occurred_at,"observed_at":row.observed_at,
        "canonical":event,"related":related}),
    ))
}
