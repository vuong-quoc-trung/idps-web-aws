use crate::{AppState, auth};
use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{
        IntoResponse, Response, Sse,
        sse::{Event, KeepAlive},
    },
};
use futures_util::stream;
use sqlx::{PgPool, postgres::PgListener};
use std::{convert::Infallible, sync::LazyLock, time::Duration};
use tokio::sync::broadcast;

static BUS: LazyLock<broadcast::Sender<Option<i64>>> = LazyLock::new(|| broadcast::channel(256).0);

pub async fn listen(pool: PgPool) {
    loop {
        if let Ok(mut pg) = PgListener::connect_with(&pool).await {
            if pg.listen("ws_alert_created").await.is_ok() {
                let _ = BUS.send(None);
                while let Ok(Some(msg)) = pg.try_recv().await {
                    if let Ok(id) = msg.payload().parse::<i64>() {
                        let _ = BUS.send(Some(id));
                    }
                }
            }
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

pub async fn events(
    State(state): State<AppState>,
    headers: HeaderMap,
    axum::Extension(user): axum::Extension<auth::Identity>,
) -> Response {
    if !matches!(user.role.as_str(), "admin" | "viewer") {
        return StatusCode::FORBIDDEN.into_response();
    }
    let token = headers
        .get("authorization")
        .and_then(|h| h.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .unwrap_or("")
        .to_owned();
    let rx = BUS.subscribe();
    // Each connection starts with an authoritative snapshot; IDs are diagnostics,
    // never interpreted as PostgreSQL commit order or a durable replay cursor.
    let generation = rand::random::<u64>();
    let events = stream::unfold(
        (rx, state, token, 0u64),
        move |(mut rx, state, token, seq)| async move {
            let event = if seq == 0 {
                Event::default().event("resync").data("{}")
            } else {
                match tokio::time::timeout(Duration::from_secs(15), rx.recv()).await {
                    Ok(Ok(Some(id))) => {
                        Event::default().event("alert.created").data(id.to_string())
                    }
                    Ok(Ok(None) | Err(broadcast::error::RecvError::Lagged(_))) => {
                        Event::default().event("resync").data("{}")
                    }
                    Ok(Err(broadcast::error::RecvError::Closed)) => return None,
                    Err(_) => Event::default().comment("heartbeat"),
                }
            };
            state.auth.identity(&token).await?;
            Some((
                Ok::<_, Infallible>(event.id(format!("{generation}-{seq}"))),
                (rx, state, token, seq + 1),
            ))
        },
    );
    let mut response = Sse::new(events)
        .keep_alive(KeepAlive::default())
        .into_response();
    response
        .headers_mut()
        .insert("x-accel-buffering", "no".parse().unwrap());
    response
}
