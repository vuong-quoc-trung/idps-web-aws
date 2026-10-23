use argon2::{Argon2, PasswordHash, PasswordVerifier};
use axum::{
    Json,
    extract::{Request, State},
    http::{StatusCode, header},
    middleware::Next,
    response::{IntoResponse, Response},
};
use rand::{RngCore, rngs::OsRng};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, VecDeque},
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::sync::Mutex;

#[derive(Clone, Serialize)]
pub struct Identity {
    pub username: String,
    pub role: String,
}
#[derive(Clone)]
struct Session {
    identity: Identity,
    expires: Instant,
}
#[derive(Clone)]
pub struct Auth {
    users: Arc<Vec<(Identity, String)>>,
    sessions: Arc<Mutex<HashMap<String, Session>>>,
    attempts: Arc<Mutex<VecDeque<Instant>>>,
}
impl Auth {
    pub fn from_env() -> anyhow::Result<Self> {
        let mut users = Vec::new();
        for (prefix, role) in [("ADMIN", "admin"), ("VIEWER", "viewer")] {
            let hash = std::env::var(format!("{prefix}_PASSWORD_HASH")).unwrap_or_default();
            if hash.is_empty() && role == "viewer" {
                continue;
            }
            PasswordHash::new(&hash).map_err(|_| {
                anyhow::anyhow!("Set {prefix}_PASSWORD_HASH to a valid Argon2 hash (see README)")
            })?;
            let username =
                std::env::var(format!("{prefix}_USERNAME")).unwrap_or(prefix.to_lowercase());
            anyhow::ensure!(
                !users
                    .iter()
                    .any(|(i, _): &(Identity, String)| i.username == username),
                "Duplicate usernames"
            );
            users.push((
                Identity {
                    username,
                    role: role.into(),
                },
                hash,
            ));
        }
        Ok(Self {
            users: Arc::new(users),
            sessions: Default::default(),
            attempts: Default::default(),
        })
    }
    async fn identity(&self, token: &str) -> Option<Identity> {
        let mut sessions = self.sessions.lock().await;
        sessions.retain(|_, s| s.expires > Instant::now());
        sessions.get(&token_hash(token)).map(|s| s.identity.clone())
    }
}
fn token_hash(token: &str) -> String {
    format!("{:x}", Sha256::digest(token.as_bytes()))
}
fn token(req: &Request) -> Option<&str> {
    req.headers()
        .get(header::AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
}
pub async fn guard(State(state): State<crate::AppState>, mut req: Request, next: Next) -> Response {
    let Some(identity) = state.auth.identity(token(&req).unwrap_or("")).await else {
        return StatusCode::UNAUTHORIZED.into_response();
    };
    if !matches!(
        *req.method(),
        axum::http::Method::GET | axum::http::Method::HEAD
    ) && req.uri().path() != "/api/auth/logout"
        && identity.role != "admin"
    {
        return StatusCode::FORBIDDEN.into_response();
    }
    req.extensions_mut().insert(identity);
    let mut response = next.run(req).await;
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        header::HeaderValue::from_static("no-store"),
    );
    response
}
#[derive(Deserialize)]
pub struct Login {
    username: String,
    password: String,
}
pub async fn login(State(state): State<crate::AppState>, Json(input): Json<Login>) -> Response {
    // Global bounded rate limit also bounds expensive password verification. No proxy-IP trust.
    let mut attempts = state.auth.attempts.lock().await;
    while attempts
        .front()
        .is_some_and(|t| t.elapsed() > Duration::from_secs(60))
    {
        attempts.pop_front();
    }
    if attempts.len() >= 10 {
        return StatusCode::TOO_MANY_REQUESTS.into_response();
    }
    attempts.push_back(Instant::now());
    drop(attempts);
    if input.password.len() > 1024 || input.username.len() > 128 {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    let selected = state
        .auth
        .users
        .iter()
        .find(|(i, _)| i.username == input.username)
        .cloned();
    let hash = selected
        .as_ref()
        .map(|(_, h)| h.clone())
        .unwrap_or_else(|| state.auth.users[0].1.clone());
    let valid = tokio::task::spawn_blocking(move || {
        PasswordHash::new(&hash).ok().is_some_and(|h| {
            Argon2::default()
                .verify_password(input.password.as_bytes(), &h)
                .is_ok()
        })
    })
    .await
    .unwrap_or(false);
    let Some((identity, _)) = selected.filter(|_| valid) else {
        return StatusCode::UNAUTHORIZED.into_response();
    };
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let token: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    let mut sessions = state.auth.sessions.lock().await;
    sessions.retain(|_, s| s.expires > Instant::now());
    if sessions.len() >= 1000 {
        return StatusCode::TOO_MANY_REQUESTS.into_response();
    }
    sessions.insert(
        token_hash(&token),
        Session {
            identity: identity.clone(),
            expires: Instant::now() + Duration::from_secs(3600),
        },
    );
    (
        [(header::CACHE_CONTROL, "no-store")],
        Json(serde_json::json!({"token": token, "user": identity, "expires_in": 3600})),
    )
        .into_response()
}
pub async fn logout(State(state): State<crate::AppState>, req: Request) -> StatusCode {
    state
        .auth
        .sessions
        .lock()
        .await
        .remove(&token_hash(token(&req).unwrap_or("")));
    StatusCode::NO_CONTENT
}
pub fn print_password_hash() -> anyhow::Result<()> {
    use argon2::{PasswordHasher, password_hash::SaltString};
    use std::io::Read;
    let mut password = String::new();
    std::io::stdin().read_to_string(&mut password)?;
    let password = password.trim_end_matches(['\r', '\n']);
    anyhow::ensure!(
        password.len() >= 12,
        "Password must contain at least 12 characters"
    );
    let salt = SaltString::generate(&mut OsRng);
    println!(
        "{}",
        Argon2::default()
            .hash_password(password.as_bytes(), &salt)
            .map_err(|e| anyhow::anyhow!("{e}"))?
    );
    Ok(())
}

#[cfg(test)]
pub fn test_auth() -> Auth {
    use argon2::{PasswordHasher, password_hash::SaltString};
    let hash = Argon2::default()
        .hash_password(b"test-password-long", &SaltString::generate(&mut OsRng))
        .unwrap()
        .to_string();
    Auth {
        users: Arc::new(vec![
            (
                Identity {
                    username: "admin".into(),
                    role: "admin".into(),
                },
                hash.clone(),
            ),
            (
                Identity {
                    username: "viewer".into(),
                    role: "viewer".into(),
                },
                hash,
            ),
        ]),
        sessions: Default::default(),
        attempts: Default::default(),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn expired_session_is_rejected() {
        let auth = test_auth();
        auth.sessions.lock().await.insert(
            token_hash("expired"),
            Session {
                identity: Identity {
                    username: "admin".into(),
                    role: "admin".into(),
                },
                expires: Instant::now() - Duration::from_secs(1),
            },
        );
        assert!(auth.identity("expired").await.is_none());
        assert!(auth.sessions.lock().await.is_empty());
    }
}
