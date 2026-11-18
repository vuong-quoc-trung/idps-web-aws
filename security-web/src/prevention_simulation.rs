//! C3 actuator simulation only: no subprocess, networking or production policy bypass.
use std::collections::HashMap;
#[derive(Default)]
struct Model {
    active: HashMap<String, i64>,
}
impl Model {
    fn block(
        &mut self,
        ip: &str,
        now: i64,
        deadline: i64,
        current_eligibility: bool,
        ai_valid: bool,
        firewall_ok: bool,
    ) -> bool {
        if !current_eligibility
            || !ai_valid
            || deadline <= now
            || deadline.saturating_sub(now) > 300
        {
            return false;
        }
        if let Some(old) = self.active.get(ip) {
            return *old == deadline;
        }
        if !firewall_ok {
            return false;
        }
        self.active.insert(ip.into(), deadline);
        true
    }
    fn unblock(&mut self, ip: &str, firewall_ok: bool) -> bool {
        if !self.active.contains_key(ip) {
            return true;
        }
        if !firewall_ok {
            return false;
        }
        self.active.remove(ip);
        true
    }
    fn expire(&mut self, now: i64, firewall_ok: bool) {
        if firewall_ok {
            self.active.retain(|_, expiry| *expiry > now);
        }
    }
}
#[test]
fn ttl_idempotency_rollback_and_failure_simulation() {
    let mut m = Model::default();
    assert!(!m.block("8.8.8.8", 100, 150, true, false, true));
    assert!(!m.block("8.8.8.8", 100, 150, false, true, true));
    assert!(!m.block("8.8.8.8", 100, 150, true, true, false));
    assert!(m.active.is_empty());
    assert!(m.block("8.8.8.8", 100, 150, true, true, true));
    assert!(m.block("8.8.8.8", 110, 150, true, true, true));
    assert!(!m.block("8.8.8.8", 110, 160, true, true, true)); // no retry extension
    assert!(!m.unblock("8.8.8.8", false));
    assert_eq!(m.active.len(), 1);
    assert!(m.unblock("8.8.8.8", true));
    assert!(m.unblock("8.8.8.8", true));
    assert!(!m.block("8.8.8.8", 150, 150, true, true, true));
    assert!(m.block("8.8.8.8", 100, 150, true, true, true));
    m.expire(151, false);
    assert_eq!(m.active.len(), 1); // not falsely report kernel success
    m.expire(151, true);
    assert!(m.active.is_empty());
}
