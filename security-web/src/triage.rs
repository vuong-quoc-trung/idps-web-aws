use crate::*;
use serde_json::{Value, json};

pub fn valid_status(value: &str) -> bool {
    matches!(
        value,
        "NEW" | "INVESTIGATING" | "RESOLVED" | "FALSE_POSITIVE"
    )
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Update {
    status: String,
    version: i64,
    note: String,
}
pub async fn update(
    State(state): State<AppState>,
    Extension(actor): Extension<auth::Identity>,
    Path(id): Path<i64>,
    Json(input): Json<Update>,
) -> Result<Json<Value>, ApiError> {
    let note = input.note.trim();
    if !valid_status(&input.status)
        || input.version < 0
        || note.is_empty()
        || note.chars().count() > 1000
    {
        return Err(bad_request(
            "Trạng thái không hợp lệ hoặc ghi chú cần có 1–1000 ký tự.",
        ));
    }
    let mut tx = state.pool.begin().await.map_err(api_error)?;
    let previous: Option<(String, i64)> = sqlx::query_as(
        "SELECT triage_status,triage_version FROM security_alerts WHERE id=$1 FOR UPDATE",
    )
    .bind(id)
    .fetch_optional(&mut *tx)
    .await
    .map_err(api_error)?;
    let Some((previous_status, version)) = previous else {
        return Err((
            StatusCode::NOT_FOUND,
            Json(json!({"message":"Không tìm thấy cảnh báo"})),
        ));
    };
    if version != input.version {
        return Err((
            StatusCode::CONFLICT,
            Json(
                json!({"message":"Cảnh báo đã được người khác cập nhật. Tải lại chi tiết trước khi lưu."}),
            ),
        ));
    }
    sqlx::query("UPDATE security_alerts SET triage_status=$2,triage_version=triage_version+1,triage_actor=$3,triage_updated_at=now() WHERE id=$1")
        .bind(id).bind(&input.status).bind(&actor.username).execute(&mut *tx).await.map_err(api_error)?;
    sqlx::query("INSERT INTO alert_triage_history(alert_id,version,previous_status,status,actor,note) VALUES($1,$2,$3,$4,$5,$6)")
        .bind(id).bind(version+1).bind(previous_status).bind(&input.status).bind(&actor.username).bind(note)
        .execute(&mut *tx).await.map_err(api_error)?;
    tx.commit().await.map_err(api_error)?;
    Ok(Json(json!({"version":version+1,"status":input.status})))
}
