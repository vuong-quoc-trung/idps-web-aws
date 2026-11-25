//! Optional development assessment. This module has no queue or actuator.
use crate::*;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Rule {
    source: String,
    rule: String,
    weight: u8,
    standalone: bool,
    max_severity: u8,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    rules: Vec<Rule>,
    combined: u16,
    standalone: u8,
    fresh_seconds: u16,
    r37_weight: u8,
}

#[derive(Clone, Copy)]
pub enum Target {
    Unverified,
    // No runtime constructor until verified ingress AND a routable enforcement
    // point can be demonstrated. An arbitrary IP must never grant eligibility.
    #[cfg(test)]
    DirectFixture {
        peer: std::net::Ipv4Addr,
        expected: std::net::Ipv4Addr,
        exclusive: bool,
        impact_approved: bool,
    },
}

impl Target {
    fn eligible(self) -> bool {
        match self {
            Self::Unverified => false,
            #[cfg(test)]
            Self::DirectFixture {
                peer,
                expected,
                exclusive,
                impact_approved,
            } => {
                peer == expected
                    && exclusive
                    && !peer.is_loopback()
                    && !peer.is_unspecified()
                    && !peer.is_link_local()
                    && !peer.is_multicast()
                    && !peer.is_broadcast()
                    && (peer.is_private() || impact_approved)
            }
        }
    }
}

impl Policy {
    pub fn load() -> Result<Option<Self>> {
        match std::env::var("WS_DEV_HYBRID_MODE").as_deref() {
            Err(std::env::VarError::NotPresent) | Ok("LOG_ONLY") => return Ok(None),
            Ok("REVIEW") => (),
            _ => bail!("Unsupported development mode; ENFORCEMENT is locked"),
        }
        let policy: Self = serde_json::from_str(&std::env::var("WS_DEV_HYBRID_POLICY")?)?;
        let mut keys = BTreeSet::new();
        anyhow::ensure!(
            (1..=200).contains(&policy.combined)
                && (1..=100).contains(&policy.standalone)
                && (1..=120).contains(&policy.fresh_seconds)
                && policy.r37_weight <= 100
                && policy.rules.len() <= 128
                && policy.rules.iter().all(|r| matches!(
                    r.source.as_str(),
                    "NGINX" | "SURICATA" | "STUDENT_AUDIT"
                ) && !r.rule.is_empty()
                    && (1..=100).contains(&r.weight)
                    && (1..=2).contains(&r.max_severity)
                    && keys.insert((&r.source, &r.rule))),
            "Invalid development policy"
        );
        Ok(Some(policy))
    }

    pub fn assess(
        &self,
        row: &Value,
        audit: &[Value],
        now: DateTime<Utc>,
        target: Target,
    ) -> Value {
        let mut families = BTreeMap::<&str, u8>::new();
        let mut ids = BTreeSet::new();
        let mut actor_sessions = BTreeSet::new();
        let mut critical = false;
        let mut observed = false;
        let fresh = |at: DateTime<Utc>| {
            at <= now && now - at <= chrono::Duration::seconds(self.fresh_seconds.into())
        };
        let fresh_field = |field: &Value| {
            field
                .as_str()
                .and_then(|s| s.parse::<DateTime<Utc>>().ok())
                .is_some_and(fresh)
        };
        let correlation = &row["correlation"];
        let ambiguous =
            correlation["status"] == "AMBIGUOUS" || row["status"] == "UNCERTAIN_CORRELATION";
        for rule in row["rules"].as_array().into_iter().flatten().chain(audit) {
            let source = rule["source"].as_str().unwrap_or("");
            observed = true;
            let Some(id) = rule["id"].as_i64().filter(|id| *id > 0) else {
                continue;
            };
            let bound = match source {
                "SURICATA" => {
                    rule["basis"] == "SENSOR_TRANSACTION"
                        && correlation["status"] == "MATCHED"
                        && correlation["late_event"] == false
                }
                "NGINX" | "STUDENT_AUDIT" => rule["basis"] == "REQUEST_ID",
                _ => false,
            };
            if !bound || !fresh_field(&rule["occurred_at"]) {
                continue;
            }
            let Some(cfg) = self.rules.iter().find(|r| {
                r.source == source
                    && rule["rule"] == r.rule
                    && rule["severity"]
                        .as_u64()
                        .is_some_and(|v| (1..=u64::from(r.max_severity)).contains(&v))
            }) else {
                continue;
            };
            let family = if source == "STUDENT_AUDIT" {
                "application"
            } else {
                "payload"
            };
            let weight = families.entry(family).or_default();
            *weight = (*weight).max(cfg.weight);
            ids.insert(id);
            if source == "STUDENT_AUDIT"
                && matches!(
                    rule["rule"].as_str(),
                    Some("APP-1012" | "APP-1013" | "APP-1014" | "APP-1016")
                )
                && let (Some(actor), Some(session)) =
                    (rule["actor"].as_str(), rule["session"].as_str())
                && [actor, session].iter().all(|v| {
                    v.strip_prefix("hmac-sha256:")
                        .is_some_and(|h| h.len() == 64 && h.bytes().all(|b| b.is_ascii_hexdigit()))
                })
            {
                actor_sessions.insert((actor, session));
            }
            critical |= cfg.standalone && cfg.weight >= self.standalone && rule["severity"] == 1;
        }
        let ai = crate::https_research::advisory(row);
        let high = ai
            .as_ref()
            .is_some_and(|v| v["action"] == "ALERT" && v["model_id"] == "r37-hgb-uri100-v1");
        if high
            && row["https_research"]["dispatch_ns"]
                .as_i64()
                .is_some_and(|ns| fresh(DateTime::from_timestamp_nanos(ns)))
            && self.r37_weight > 0
        {
            let score = families.entry("payload").or_default();
            *score = (*score).max(self.r37_weight);
        }
        let total: u16 = families.values().map(|v| u16::from(*v)).sum();
        let eligible = !ambiguous && (critical || families.len() >= 2 && total >= self.combined);
        let action = if eligible && target.eligible() {
            "WOULD_BLOCK"
        } else if eligible || high || observed {
            "REVIEW"
        } else {
            "LOG_ONLY"
        };
        // Only application-confirmed bindings can suggest session revocation.
        // Keep the pseudonymous selectors out of the Dashboard.
        let recommendation = if !eligible {
            "NONE"
        } else if actor_sessions.len() == 1 {
            "BLOCK_SESSION"
        } else if target.eligible() {
            "BLOCK_IP"
        } else {
            "REVIEW"
        };
        json!({"recommended_action":recommendation,"phase":"POST_OBSERVATION","action":action,"evidence_eligible":eligible,"families":families,"evidence_alert_ids":ids,
            "request_id":row["request_id"],"r37_high":high,"ambiguous":ambiguous,"policy":self,
            "identity":if target.eligible() {"VERIFIED_TEST_TARGET"} else {"NO_VERIFIED_ENFORCEMENT_TARGET"},
            "execution_allowed":false,"automatic_block":false})
    }
}

// Episode rules have no detector_alert_link. Use the original normalized event key,
// request ID and server-confirmed security decision; later episode updates cannot
// reassign the episode to an unrelated request.
pub async fn application_evidence(
    pool: &PgPool,
    ids: &[&str],
) -> Result<BTreeMap<String, Vec<Value>>> {
    let rows = sqlx::query_as::<_, (String,Value)>(r#"
        SELECT n.request_id, jsonb_build_object('id',a.id,'source',a.source,
            'rule',a.signature,'severity',a.severity,'occurred_at',n.occurred_at,'basis','REQUEST_ID',
            'actor',CASE WHEN n.canonical->>'role' IN ('STUDENT','STAFF','ADMIN') THEN n.canonical->>'user_id' END,
            'session',n.canonical->>'session_hmac')
        FROM normalized_events n JOIN security_alerts a
            ON a.event_key=n.event_key||':'||a.signature
        WHERE n.source='STUDENT_AUDIT' AND n.request_id=ANY($1)
          AND a.source=n.source AND a.category='Application Security Decision'
          AND a.evidence::jsonb->>'request_id'=n.request_id
          AND a.evidence::jsonb->>'source_instance'=n.source_instance
          AND a.occurred_at=n.occurred_at
    "#).bind(ids).fetch_all(pool).await?;
    let mut grouped = BTreeMap::<String, Vec<Value>>::new();
    for (id, rule) in rows {
        grouped.entry(id).or_default().push(rule);
    }
    Ok(grouped)
}

/// Read-only handoff for a local operator. Replays use the original deadline.
/// Require an immutable authenticated event, current incident and one unambiguous
/// session. Never accept a username, cookie or target selector from the caller.
pub async fn action_plan(pool: &PgPool, rid: &str, action: &str) -> Result<Value> {
    if matches!(action, "BLOCK_SESSION" | "BLOCK_ACCOUNT") {
        let mut plan = bound_plan(pool, rid, action == "BLOCK_ACCOUNT").await?;
        if action == "BLOCK_ACCOUNT" {
            // Manual escalation only. The SQL binding below requires an authenticated
            // application decision and exactly one actor/session for this incident.
            let actor = plan["selector"]
                .as_str()
                .and_then(|s| s.split_once('.'))
                .map(|(actor, _)| actor)
                .context("Missing authenticated actor")?;
            plan["selector"] = json!(format!("account-{actor}"));
        }
        plan["action"] = json!(action);
        return Ok(plan);
    }
    anyhow::ensure!(
        action == "BLOCK_REQUEST",
        "Verified direct enforcement peer unavailable; action refused"
    );
    // Only authorize the reserved demo route for future requests. Never accept
    // a caller-supplied URI, IP, session or a lease with a sliding deadline.
    let times:Option<(i64,i64)>=sqlx::query_as(r#"
        SELECT floor(extract(epoch FROM observed_at))::bigint,
               floor(extract(epoch FROM observed_at))::bigint +
                  least(120,(decision#>>'{dev_prevention,policy,fresh_seconds}')::int)
        FROM hybrid_incidents WHERE request_id=$1
        AND decision#>>'{dev_prevention,request_id}'=$1
        AND decision#>>'{dev_prevention,evidence_eligible}'='true'
        AND decision#>>'{dev_prevention,ambiguous}'='false'
        AND decision#>>'{dev_prevention,execution_allowed}'='false'
        AND observed_at<=now() AND observed_at+
          least(120,(decision#>>'{dev_prevention,policy,fresh_seconds}')::int)*interval '1 second'>now()
    "#).bind(rid).fetch_optional(pool).await?;
    let (issued, expires) = times.context("No fresh eligible canary incident")?;
    Ok(
        json!({"action":action,"request_id":rid,"selector":"dev-canary","issued":issued,"expires":expires}),
    )
}

/// Read-only automatic proposals. Scope is exclusively the reserved guest canary.
pub async fn auto_canary(
    pool: &PgPool,
    rules: &[String],
    critical: &[String],
) -> Result<Option<Value>> {
    adaptive_plan(pool, rules, critical, None).await
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeThreshold {
    pub action: String,
    pub window_seconds: i32,
    pub events: i64,
    pub ttl: i64,
    pub source_instance: String,
}

pub async fn adaptive_plan(
    pool: &PgPool,
    rules: &[String],
    critical: &[String],
    native: Option<&NativeThreshold>,
) -> Result<Option<Value>> {
    if let Some(p) = native {
        anyhow::ensure!(
            matches!(
                p.action.as_str(),
                "BLOCK_REQUEST" | "BLOCK_SESSION" | "BLOCK_ACCOUNT" | "BLOCK_IP"
            ) && (1..=120).contains(&p.window_seconds)
                && (2..=12).contains(&p.events)
                && (1..=120).contains(&p.ttl)
                && !p.source_instance.is_empty(),
            "Invalid native threshold"
        );
    }
    anyhow::ensure!(
        !rules.is_empty()
            && rules.len() <= 4
            && rules.iter().all(|r| matches!(
                r.as_str(),
                "APP-1012" | "APP-1013" | "APP-1014" | "APP-1016"
            ))
            && critical.iter().all(|r| rules.contains(r)),
        "Invalid canary authorization"
    );
    if let Some(p) = native.filter(|p| p.action == "BLOCK_IP") {
        anyhow::ensure!(
            critical.is_empty() && p.events >= 10 && p.ttl <= 15 && p.window_seconds <= 60,
            "Unsafe IP authorization"
        );
        // Application alerts can coalesce into episodes. Count authenticated server
        // decisions per transaction rather than multiplying (or losing) alert rows.
        let row: Option<(Vec<String>, i64, i64)> = sqlx::query_as(r#"
          WITH requests AS (
            SELECT n.request_id, n.occurred_at, n.canonical->>'user_id' AS actor,
                   g.client_ip, row_number() OVER (
                     PARTITION BY n.canonical->>'user_id',g.client_ip
                     ORDER BY n.occurred_at DESC,n.request_id) AS rank
            FROM normalized_events n
            JOIN normalized_events g ON g.request_id=n.request_id AND g.source='NGINX'
            JOIN hybrid_incidents h ON h.request_id=n.request_id
            WHERE n.source='STUDENT_AUDIT' AND n.source_instance=$1
              AND n.request_id ~ '^[0-9a-f]{32}$'
              AND n.canonical->>'role' IN ('STUDENT','STAFF')
              AND n.canonical->>'user_id' ~ '^hmac-sha256:[0-9a-f]{64}$'
              AND h.decision#>>'{dev_prevention,request_id}'=n.request_id
              AND h.decision#>>'{dev_prevention,ambiguous}'='false'
              AND h.decision#>>'{dev_prevention,student_query_available}'='true'
              AND g.status_code=n.status_code AND g.client_ip IS NOT NULL
              AND n.occurred_at BETWEEN now()-$2::int*interval '1 second' AND now()
              AND abs(extract(epoch FROM g.occurred_at-n.occurred_at))<=2
              AND EXISTS (SELECT 1 FROM jsonb_array_elements(h.decision#>'{dev_prevention,policy,rules}') cfg
                  WHERE cfg->>'source'='STUDENT_AUDIT' AND cfg->>'rule'=ANY($4)
                  AND ((cfg->>'rule'='APP-1013' AND n.status_code=400
                    AND n.canonical#>'{security,reasons}' ? 'MASS_ASSIGNMENT'
                    AND jsonb_array_length(n.canonical#>'{security,forbidden_fields}')>0)
                    OR (cfg->>'rule'='APP-1014' AND n.status_code=403
                    AND n.canonical#>'{security,reasons}' ? 'PRIVILEGE_DENIED')))
              AND NOT EXISTS (SELECT 1 FROM normalized_events x WHERE x.request_id=n.request_id
                    AND ((x.source=n.source AND x.id<>n.id) OR (x.source=g.source AND x.id<>g.id)))
              AND (SELECT count(*)=1 AND bool_and(e.proof_present AND e.receipt_present AND NOT e.mismatched)
                    FROM suricata_lua_shadow e WHERE e.request_id=n.request_id)
          )
          SELECT array_agg(request_id ORDER BY occurred_at DESC,request_id),
                 floor(extract(epoch FROM min(occurred_at)))::bigint,
                 floor(extract(epoch FROM max(occurred_at)))::bigint
          FROM requests WHERE rank<=$3 GROUP BY actor,client_ip HAVING count(*)=$3
          ORDER BY max(occurred_at) DESC,actor,client_ip LIMIT 1
        "#).bind(&p.source_instance).bind(p.window_seconds).bind(p.events).bind(rules)
           .fetch_optional(pool).await?;
        return Ok(row.map(|(ids, oldest, issued)| {
            json!({"request_id":ids[0],"action":"BLOCK_IP",
            "selector":"","reason":"DISTINCT_OPERATIONS","oldest":oldest,"issued":issued,
            "expires":(issued+p.ttl).min(oldest+i64::from(p.window_seconds)),
            "rules":rules,"evidence":ids})
        }));
    }
    // A repeat with a new HTTP ID can still be a retry. In the absence of a trusted
    // operation ID count only distinct application decisions on distinct requests.
    let candidate: Option<(String, i64, i64, i64, Vec<String>, Vec<String>,String,String,bool,bool)> = sqlx::query_as(r#"
        WITH eligible AS (
            SELECT n.request_id, n.source_instance, n.canonical->>'user_id' AS actor,
                   n.canonical->>'session_hmac' AS sess, a.signature, n.occurred_at,
                   CASE WHEN $3 AND n.canonical#>>'{security,object_hmac}' ~ '^hmac-sha256:[a-f0-9]{64}$'
                     THEN n.canonical#>>'{security,object_hmac}' ELSE '' END AS operation,
                   n.occurred_at + least($4::int,(dv->'policy'->>'fresh_seconds')::int)*interval '1 second' AS deadline,
                   (a.signature=ANY($2) AND a.severity=1 AND cfg->>'standalone'='true'
                    AND (cfg->>'weight')::int >= (dv->'policy'->>'standalone')::int) AS immediate,
                   (dv->>'evidence_eligible'='true' AND (dv->'families'->>'application')::int>0
                    AND (dv->'families'->>'payload')::int>0
                    AND (dv->'families'->>'payload')::int + (cfg->>'weight')::int >= (dv->'policy'->>'combined')::int) AS corroborated
            FROM normalized_events n
            JOIN hybrid_incidents h ON h.request_id=n.request_id
            CROSS JOIN LATERAL (SELECT h.decision->'dev_prevention' AS dv) d
            CROSS JOIN LATERAL jsonb_array_elements(dv->'policy'->'rules') cfg
            CROSS JOIN security_alerts a
            WHERE n.source='STUDENT_AUDIT' AND n.source_instance <> ''
              AND (NOT $3 OR n.source_instance=$6)
              AND n.request_id ~ '^[a-f0-9]{32}$' AND dv->>'request_id'=n.request_id
              AND dv->>'ambiguous'='false' AND dv->>'execution_allowed'='false'
              AND dv->>'student_query_available'='true'
              AND n.canonical->>'role' IN ('STAFF','STUDENT')
              AND n.canonical->>'user_id' ~ '^hmac-sha256:[a-f0-9]{64}$'
              AND n.canonical->>'session_hmac' ~ '^hmac-sha256:[a-f0-9]{64}$'
              AND cfg->>'source'=n.source AND cfg->>'rule'=a.signature
              AND a.signature=ANY($1) AND a.severity BETWEEN 1 AND least(2,(cfg->>'max_severity')::int)
              AND a.event_key=n.event_key||':'||a.signature AND a.source=n.source
              AND a.category='Application Security Decision' AND a.occurred_at=n.occurred_at
              AND a.evidence::jsonb->>'source_instance'=n.source_instance
              AND a.evidence::jsonb->>'request_id'=n.request_id
              AND dv->'evidence_alert_ids' @> jsonb_build_array(a.id)
              AND n.occurred_at BETWEEN now()-least($4::int,(dv->'policy'->>'fresh_seconds')::int)*interval '1 second' AND now()
              AND NOT EXISTS (SELECT 1 FROM normalized_events x WHERE x.source=n.source
                              AND x.request_id=n.request_id AND x.event_key<>n.event_key)
        ), singles AS (
            SELECT request_id,source_instance,actor,sess,min(signature) AS sig,min(operation) AS op,
                   max(occurred_at) AS t,min(deadline) AS deadline,bool_or(immediate) AS urgent,bool_or(corroborated) AS combined
            FROM eligible GROUP BY request_id,source_instance,actor,sess
            HAVING count(DISTINCT signature)=1
        ), latest AS (
            SELECT DISTINCT ON(source_instance,actor,sess,sig,op) * FROM singles s WHERE op<>'' OR NOT EXISTS (
                SELECT 1 FROM singles k WHERE k.source_instance=s.source_instance AND k.actor=s.actor
                AND k.sess=s.sess AND k.sig=s.sig AND k.op<>'')
            ORDER BY source_instance,actor,sess,sig,op,t DESC,request_id
        )
        , bounded AS (
            SELECT *,row_number() OVER (PARTITION BY source_instance,actor,sess ORDER BY urgent DESC,t DESC,request_id) AS rank
            FROM latest
        )
        SELECT (array_agg(request_id ORDER BY urgent DESC,t DESC,request_id))[1],
               floor(extract(epoch FROM max(t)))::bigint, floor(extract(epoch FROM min(t)))::bigint, floor(extract(epoch FROM min(deadline)))::bigint,
               array_agg(request_id ORDER BY request_id),array_agg(sig ORDER BY request_id),actor,sess,bool_or(urgent),coalesce(bool_or(combined),false)
        FROM bounded WHERE rank<=12 GROUP BY source_instance,actor,sess
        HAVING count(*) >= $5 OR bool_or(urgent) OR (bool_or(combined) AND $7)
        ORDER BY max(t) DESC, min(request_id) LIMIT 1
    "#).bind(rules).bind(critical).bind(native.is_some()).bind(native.map_or(60,|p|p.window_seconds))
        .bind(native.map_or(2,|p|p.events)).bind(native.map_or("",|p|p.source_instance.as_str()))
        .bind(native.is_none()).fetch_optional(pool).await?;
    let Some((rid, issued, oldest, deadline, evidence, signatures, actor, sess, urgent, combined)) =
        candidate
    else {
        return Ok(None);
    };
    let action = native.map_or("BLOCK_REQUEST", |p| p.action.as_str());
    let selector = match action {
        "BLOCK_SESSION" => format!("{}.{}", &actor[12..], &sess[12..]),
        "BLOCK_ACCOUNT" => {
            if bound_plan(pool, &rid, true).await.is_err() {
                return Ok(None);
            }
            format!("account-{}", &actor[12..])
        }
        // No IP is exported by SQL. The actuator must bind every evidence ID
        // to the same transport peer at the approved direct listener.
        "BLOCK_IP" => String::new(),
        _ if native.is_some() => format!("request-{}", &sess[12..]),
        _ => "dev-canary".to_string(),
    };
    Ok(Some(
        json!({"request_id":rid,"action":action,"selector":selector,
        "reason": if urgent {"APPROVED_IMMEDIATE"} else if native.is_none() && combined && action=="BLOCK_REQUEST" {"CORROBORATED"} else {"DISTINCT_OPERATIONS"},
        "oldest":oldest,"issued":issued,"expires":deadline.min(issued+native.map_or(15,|p|p.ttl)),
        "evidence":evidence,"rules":signatures}),
    ))
}

#[cfg(test)]
pub async fn session_plan(pool: &PgPool, rid: &str) -> Result<Value> {
    bound_plan(pool, rid, false).await
}

async fn bound_plan(pool: &PgPool, rid: &str, account: bool) -> Result<Value> {
    let row: Option<(String,String,i64,i64)>=sqlx::query_as(r#"
        WITH bound AS (
          SELECT DISTINCT n.canonical->>'user_id' actor,n.canonical->>'session_hmac' sess,
                 n.source_instance
          FROM normalized_events n WHERE n.source='STUDENT_AUDIT' AND n.request_id=$1
        )
        SELECT b.actor,b.sess,floor(extract(epoch FROM h.observed_at))::bigint,
            floor(extract(epoch FROM h.observed_at))::bigint +
                least(120,(h.decision#>>'{dev_prevention,policy,fresh_seconds}')::bigint)
        FROM hybrid_incidents h JOIN bound b ON true
        WHERE h.request_id=$1 AND (SELECT count(*) FROM bound)=1
          AND b.actor ~ '^hmac-sha256:[a-f0-9]{64}$' AND b.sess ~ '^hmac-sha256:[a-f0-9]{64}$'
          AND h.decision#>>'{dev_prevention,recommended_action}'='BLOCK_SESSION'
          AND h.decision#>>'{dev_prevention,student_query_available}'='true'
          AND h.decision#>>'{dev_prevention,execution_allowed}'='false'
          AND h.observed_at <= now() AND h.observed_at +
            least(120,(h.decision#>>'{dev_prevention,policy,fresh_seconds}')::int) * interval '1 second' > now()
          AND EXISTS (SELECT 1 FROM normalized_events n JOIN security_alerts a
              ON a.event_key=n.event_key||':'||a.signature
              WHERE n.request_id=h.request_id AND n.source='STUDENT_AUDIT'
              AND n.canonical->>'role' IN ('STUDENT','STAFF','ADMIN')
              AND n.canonical->>'user_id'=b.actor AND n.canonical->>'session_hmac'=b.sess
              AND a.source=n.source AND a.category='Application Security Decision'
              AND a.signature IN ('APP-1012','APP-1013','APP-1014','APP-1016')
              AND a.evidence::jsonb->>'request_id'=n.request_id AND a.occurred_at=n.occurred_at
              AND a.evidence::jsonb->>'source_instance'=n.source_instance
              AND h.decision#>'{dev_prevention,evidence_alert_ids}' @> jsonb_build_array(a.id)
              AND (NOT $2 OR (
                  n.canonical->>'role' IN ('STAFF','STUDENT') AND a.severity=1 AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(h.decision#>'{dev_prevention,policy,rules}') cfg
                      WHERE cfg->>'source'=a.source AND cfg->>'rule'=a.signature AND cfg->>'standalone'='true'
                      AND (cfg->>'weight')::int >= greatest(95,(h.decision#>>'{dev_prevention,policy,standalone}')::int)
                  ))))
    "#).bind(rid).bind(account).fetch_optional(pool).await?;
    let (actor, session, issued, expires) =
        row.context("No fresh, bound session recommendation")?;
    Ok(
        json!({"selector":format!("{}.{}",&actor[12..],&session[12..]),"request_id":rid,"issued":issued,"expires":expires}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn decision_matrix() {
        let now = Utc::now();
        let p = Policy {
            rules: [
                ("SURICATA", "native", 95, true),
                ("NGINX", "edge", 70, false),
                ("STUDENT_AUDIT", "APP-1013", 60, false),
            ]
            .into_iter()
            .map(|(s, r, w, alone)| Rule {
                source: s.into(),
                rule: r.into(),
                weight: w,
                standalone: alone,
                max_severity: 2,
            })
            .collect(),
            combined: 120,
            standalone: 90,
            r37_weight: 60,
            fresh_seconds: 60,
        };
        let rule = |id, source, name, basis, severity| json!({"id":id,"source":source,"rule":name,"basis":basis,"severity":severity,"occurred_at":now});
        let native = rule(1, "SURICATA", "native", "SENSOR_TRANSACTION", 1);
        let edge = rule(2, "NGINX", "edge", "REQUEST_ID", 2);
        let app = rule(3, "STUDENT_AUDIT", "APP-1013", "REQUEST_ID", 2);
        let mut row = json!({"request_id":"abc","correlation":{"status":"MATCHED","late_event":false},"rules":[native]});
        let assess = |r: &Value, t| p.assess(r, &[], now, t);
        let target = |ip: &str, exclusive, impact_approved| {
            let peer = ip.parse().unwrap();
            Target::DirectFixture {
                peer,
                expected: peer,
                exclusive,
                impact_approved,
            }
        };
        let ok = target("10.198.38.2", true, false);
        for ip in ["127.77.0.1", "127.77.0.2"] {
            assert_eq!(assess(&row, target(ip, true, true))["action"], "REVIEW");
        }
        assert_eq!(
            assess(&row, target("203.0.113.2", false, true))["action"],
            "REVIEW"
        );
        assert_eq!(
            assess(&row, target("203.0.113.2", true, false))["action"],
            "REVIEW"
        );
        assert_eq!(
            assess(&row, target("203.0.113.2", true, true))["action"],
            "WOULD_BLOCK"
        );
        assert_eq!(assess(&row, ok)["action"], "WOULD_BLOCK");
        assert_eq!(assess(&row, Target::Unverified)["action"], "REVIEW");
        row["rules"] = json!([edge, app]);
        assert_eq!(assess(&row, ok)["action"], "WOULD_BLOCK");
        row["https_research"] = json!({"request_id":"abc","version":"r37-hgb-uri100-v1","status":"SCORED","score":0.99,"threshold":0.77,"dispatch_ns":now.timestamp_nanos_opt()});
        row["rules"] = json!([edge, app, native]);
        assert_eq!(assess(&row, ok)["action"], "WOULD_BLOCK");
        row["rules"] = json!([]);
        assert_eq!(assess(&row, ok)["action"], "REVIEW");
        row["https_research"] = Value::Null;
        assert_eq!(assess(&row, ok)["action"], "LOG_ONLY");
        row["rules"] = json!([edge]);
        let once = assess(&row, ok);
        row["rules"] = json!([edge, edge]);
        assert_eq!(assess(&row, ok), once);
        row["rules"] = json!([native]);
        row["rules"][0]["severity"] = json!(5);
        assert_eq!(assess(&row, ok)["action"], "REVIEW");
        row["rules"] = json!([native]);
        row["correlation"]["late_event"] = json!(true);
        assert_eq!(assess(&row, ok)["action"], "REVIEW");
        row["correlation"] = Value::Null;
        row["rules"] = json!([edge]);
        let independent = p.assess(&row, &[app], now, ok);
        assert_eq!(independent["action"], "WOULD_BLOCK");
        assert_eq!(independent["execution_allowed"], false);
        assert_eq!(independent["automatic_block"], false);
        assert_eq!(
            p.assess(&row, &[], now + chrono::Duration::seconds(121), ok)["families"],
            json!({})
        );
    }
}

#[cfg(test)]
#[test]
#[ignore = "requires direct peer observation in two fresh rootless network namespaces"]
fn direct_peer_fixture() {
    let peer = std::env::var("WS_FIXTURE_PEER")
        .unwrap()
        .parse::<IpAddr>()
        .unwrap();
    assert_eq!(
        peer,
        std::env::var("WS_FIXTURE_TARGET")
            .unwrap()
            .parse::<IpAddr>()
            .unwrap()
    );
    assert_eq!(peer.to_string(), "10.198.38.2"); // Only the isolated R38 fixture.
    let now = Utc::now();
    let policy:Policy=serde_json::from_value(json!({"rules":[{"source":"NGINX","rule":"fixture-edge","weight":70,"standalone":false,"max_severity":2},{"source":"STUDENT_AUDIT","rule":"fixture-app","weight":70,"standalone":false,"max_severity":2}],"combined":120,"standalone":95,"fresh_seconds":30,"r37_weight":50})).unwrap();
    let row = json!({"request_id":"f".repeat(32),"rules":[{"id":7,"source":"NGINX","rule":"fixture-edge","severity":2,"basis":"REQUEST_ID","occurred_at":now}]});
    let app = json!({"id":8,"source":"STUDENT_AUDIT","rule":"fixture-app","severity":2,"basis":"REQUEST_ID","occurred_at":now});
    let IpAddr::V4(peer_v4) = peer else {
        panic!("expected IPv4 lab peer")
    };
    let mut decision = policy.assess(
        &row,
        &[app],
        now,
        Target::DirectFixture {
            peer: peer_v4,
            expected: "10.198.38.2".parse().unwrap(),
            exclusive: true,
            impact_approved: false,
        },
    );
    assert_eq!(decision["action"], "WOULD_BLOCK");
    decision["target"] = json!(peer);
    println!("WS_DEV_REVIEW={decision}");
}

/// Optional, standalone listener of the development binary. The operator grants
/// a bounded lease on one reserved probe URI. No public routes, DB or R37 call.
pub async fn serve_edge_gate() -> Result<()> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let dir = std::path::PathBuf::from(env::var("WS_DEV_GATE_DIR")?);
    let meta = std::fs::symlink_metadata(&dir)?;
    anyhow::ensure!(
        dir.is_absolute()
            && dir.canonicalize()? == dir
            && meta.is_dir()
            && meta.uid() == std::fs::metadata("/proc/self")?.uid()
            && meta.mode() & 0o022 == 0,
        "Gate directory must be owned by the service and deny group/other writes"
    );
    let lease_dir = std::path::PathBuf::from(env::var("WS_DEV_GATE_LEASE_DIR")?);
    let owner = std::fs::metadata(&lease_dir)?.uid();
    anyhow::ensure!(
        lease_dir.is_absolute()
            && lease_dir.canonicalize()? == lease_dir
            && lease_dir.is_dir()
            && std::fs::metadata(&lease_dir)?.mode() & 0o022 == 0
            && (owner == 0
                || owner == meta.uid()
                || env::var("WS_NATIVE_LEASE_OWNER_UID")
                    .ok()
                    .and_then(|s| s.parse::<u32>().ok())
                    == Some(owner)),
        "Unsafe lease directory"
    );
    let state = match env::var_os("WS_NATIVE_SESSION_KEY_FILE") {
        Some(file) => {
            let key = std::fs::read_to_string(file)?;
            let key = key.trim_end_matches('\n');
            anyhow::ensure!(
                key.len() == 64
                    && key
                        .bytes()
                        .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
                "Invalid subject key"
            );
            Some(key.as_bytes().to_vec())
        }
        None => None,
    };
    let config = std::sync::Arc::new((lease_dir, state));
    let socket = dir.join("gate.sock");
    let listener = tokio::net::UnixListener::bind(&socket)?;
    std::fs::set_permissions(&socket, std::fs::Permissions::from_mode(0o660))?;
    // The internal NGINX location supplies the selector; client headers are stripped.
    let route = Router::new().route(
        "/check",
        get(move |headers: axum::http::HeaderMap| {
            let config = config.clone();
            async move {
                let Some(rid) = headers
                    .get("x-ws-request-id")
                    .and_then(|v| v.to_str().ok())
                    .filter(|v| events::valid_request_id(v))
                else {
                    return StatusCode::BAD_REQUEST;
                };
                let scope = headers.get("x-ws-selector").and_then(|v| v.to_str().ok());
                let lease = match (&config.1, scope) {
                    (None, Some("dev-canary")) => config.0.join("dev-canary"),
                    (Some(key), Some("native-session")) => {
                        use hmac::{Hmac, Mac};
                        let raw = headers.get("x-ws-session-cookie");
                        let Some(raw) = raw else {
                            return StatusCode::NO_CONTENT;
                        };
                        let Ok(raw) = raw.to_str() else {
                            return StatusCode::FORBIDDEN;
                        };
                        let mut sessions = raw
                            .split(';')
                            .filter_map(|pair| pair.trim().split_once('='))
                            .filter(|(name, _)| name.eq_ignore_ascii_case("JSESSIONID"));
                        let Some((name, sid)) = sessions.next() else {
                            return StatusCode::NO_CONTENT;
                        };
                        if name != "JSESSIONID"
                            || sessions.next().is_some()
                            || raw.contains(',')
                            || sid.len() != 32
                            || !sid.bytes().all(|c| c.is_ascii_hexdigit())
                        {
                            return StatusCode::FORBIDDEN;
                        }
                        let mut mac = Hmac::<sha2::Sha256>::new_from_slice(key).expect("HMAC key");
                        mac.update(b"session:");
                        mac.update(sid.as_bytes());
                        config
                            .0
                            .join(format!("request-{:x}", mac.finalize().into_bytes()))
                    }
                    _ => return StatusCode::BAD_REQUEST,
                };
                let metadata = match tokio::fs::symlink_metadata(&*lease).await {
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                        return StatusCode::NO_CONTENT;
                    }
                    Ok(m)
                        if m.is_file()
                            && m.uid() == owner
                            && m.mode() & 0o022 == 0
                            && m.len() <= 128 =>
                    {
                        m
                    }
                    _ => return StatusCode::SERVICE_UNAVAILABLE,
                };
                let Ok(record) = tokio::fs::read_to_string(&*lease).await else {
                    return StatusCode::SERVICE_UNAVAILABLE;
                };
                if record.len() as u64 != metadata.len() {
                    return StatusCode::SERVICE_UNAVAILABLE;
                }
                let parts: Vec<_> = record.split_whitespace().collect();
                let [origin, start, end] = parts.as_slice() else {
                    return StatusCode::SERVICE_UNAVAILABLE;
                };
                let (Ok(start), Ok(end)) = (start.parse::<i64>(), end.parse::<i64>()) else {
                    return StatusCode::SERVICE_UNAVAILABLE;
                };
                if !events::valid_request_id(origin)
                    || !(1..=120).contains(&end.saturating_sub(start))
                {
                    return StatusCode::SERVICE_UNAVAILABLE;
                }
                if (start..end).contains(&Utc::now().timestamp()) {
                    eprintln!("BLOCK_REQUEST trigger={origin} request={rid} expires={end}");
                    StatusCode::FORBIDDEN
                } else {
                    StatusCode::NO_CONTENT
                }
            }
        }),
    );
    axum::serve(listener, route).await?;
    Ok(())
}
