// One-shot migration; never starts HTTP, ingestion or enforcement.
use anyhow::{Result, ensure};
use sqlx::postgres::PgPoolOptions;

#[tokio::main]
async fn main() -> Result<()> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&std::env::var("DATABASE_URL")?)
        .await?;
    let valid: bool = sqlx::query_scalar("SELECT current_database() = 'ws_native_security' AND current_user = 'ws_native_security' AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole FROM pg_roles WHERE rolname=current_user")
        .fetch_one(&pool).await?;
    ensure!(valid, "unexpected native migration target or role");
    sqlx::migrate!("./migrations").run(&pool).await?;
    Ok(())
}
