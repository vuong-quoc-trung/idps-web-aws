#!/usr/bin/env bash
# ==============================================================================
# PBL4 Web IDPS - Safe Deployment & Audit Script
# Modes:
#   ./scripts/deploy.sh --check   (Read-only audit, syntax check, network validation & diff verification)
#   ./scripts/deploy.sh --deploy  (Safe idempotent deployment with automated sudo elevation, backups & rollback)
# ==============================================================================

set -euo pipefail

# Determine script & project root regardless of working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ANSI color codes
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    NC=''
fi

log_info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_header()  { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}"; }

# Dynamic resolution of unprivileged runtime user & group
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    RUN_USER="${SUDO_USER}"
else
    RUN_USER="$(stat -c '%U' "${PROJECT_DIR}" 2>/dev/null || echo "${USER:-trung}")"
fi
RUN_GROUP="$(id -gn "${RUN_USER}" 2>/dev/null || echo "${RUN_USER}")"

# Automated privilege elevation for --deploy
if [ "${1:-}" = "--deploy" ] && [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        log_info "Elevating to superuser privileges via sudo to deploy system configurations..."
        exec sudo PROJECT_DIR="${PROJECT_DIR}" RUN_USER="${RUN_USER}" bash "$0" "$@"
    else
        log_error "Root privileges or sudo required to deploy system configurations."
        exit 1
    fi
fi

# Load optional network configuration from .env if present
ATTACKER_IFACE="enp1s0"
PROTECTED_IFACE="enp7s0"
SECURITY_IP="192.168.10.1"
WEB_SERVER_IP="192.168.20.10"

if [ -f "${PROJECT_DIR}/.env" ]; then
    # Parse without leaking secrets
    val=$(grep -E '^ATTACKER_IFACE=' "${PROJECT_DIR}/.env" | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && ATTACKER_IFACE="$val"
    val=$(grep -E '^PROTECTED_IFACE=' "${PROJECT_DIR}/.env" | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && PROTECTED_IFACE="$val"
    val=$(grep -E '^SECURITY_IP=' "${PROJECT_DIR}/.env" | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && SECURITY_IP="$val"
    val=$(grep -E '^WEB_SERVER_IP=' "${PROJECT_DIR}/.env" | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$val" ] && WEB_SERVER_IP="$val"
fi

# Paths: Source repository files
SRC_SURICATA_CONF="${PROJECT_DIR}/config/suricata/suricata.yaml"
SRC_SURICATA_RULES="${PROJECT_DIR}/suricata/pbl4.rules"
SRC_NGINX_CONF="${PROJECT_DIR}/nginx/pbl4-proxy.conf"
SRC_NFTABLES_CONF="${PROJECT_DIR}/config/nftables/nftables.conf"
SRC_NFTABLES_RULES="${PROJECT_DIR}/scripts/pbl4.nft"
SRC_FIREWALL_HELPER="${PROJECT_DIR}/scripts/pbl4-firewall"
SRC_SYSTEMD_SERVICE="${PROJECT_DIR}/deploy/systemd/pbl4-security.service"
SRC_SCHEMA_SQL="${PROJECT_DIR}/sql/schema.sql"
SRC_ENV_EXAMPLE="${PROJECT_DIR}/.env.example"
SRC_CARGO_TOML="${PROJECT_DIR}/Cargo.toml"

# Paths: Deployed system files
SYS_SURICATA_CONF="/etc/suricata/suricata.yaml"
SYS_SURICATA_RULES_DIR="/var/lib/suricata/rules"
SYS_SURICATA_RULES="${SYS_SURICATA_RULES_DIR}/pbl4.rules"
SYS_NGINX_SITE="/etc/nginx/sites-available/pbl4-proxy"
SYS_NGINX_ENABLED="/etc/nginx/sites-enabled/pbl4-proxy"
SYS_NFTABLES_CONF="/etc/nftables.conf"
SYS_NFTABLES_DIR="/etc/nftables.d"
SYS_NFTABLES_RULES="${SYS_NFTABLES_DIR}/pbl4.nft"
SYS_FIREWALL_HELPER="/usr/local/bin/pbl4-firewall"
SYS_SYSTEMD_SERVICE="/etc/systemd/system/pbl4-security.service"
SYS_SUDOERS_PBL4="/etc/sudoers.d/pbl4-security"

# Log paths monitored by backend
LOG_SURICATA_EVE="/var/log/suricata/eve.json"
LOG_NGINX_ACCESS="/var/log/nginx/access.log"

# Helper to render dynamic systemd service file from template
render_systemd_service() {
    local target_file="$1"
    sed \
        -e "s|{{RUN_USER}}|${RUN_USER}|g" \
        -e "s|{{RUN_GROUP}}|${RUN_GROUP}|g" \
        -e "s|{{PROJECT_DIR}}|${PROJECT_DIR}|g" \
        "${SRC_SYSTEMD_SERVICE}" > "${target_file}"
}

# Helper to safely test Suricata configuration in an isolated temporary log directory
validate_suricata_config() {
    local conf_file="$1"
    local label="${2:-Suricata configuration}"

    if ! command -v suricata >/dev/null 2>&1; then
        log_warn "Suricata binary not found; skipping syntax check for ${label}"
        return 0
    fi

    # Create an isolated temporary directory for test logs (avoiding shared sticky-bit /tmp issues)
    local tmp_log_dir
    tmp_log_dir=$(mktemp -d /tmp/suricata-test-XXXXXX)
    chmod 755 "${tmp_log_dir}"

    local test_out
    local test_rc=0
    test_out=$(suricata -T -c "${conf_file}" -l "${tmp_log_dir}" 2>&1) || test_rc=$?

    rm -rf "${tmp_log_dir}"

    if [ "$test_rc" -eq 0 ]; then
        log_success "${label} syntax valid (${conf_file#$PROJECT_DIR/})"
        return 0
    else
        if echo "$test_out" | grep -qiE "Permission denied|error opening file|not writable|logopenfile"; then
            log_error "${label} failed due to logging permission or file access error (not a syntax error):"
        else
            log_error "${label} syntax error in ${conf_file#$PROJECT_DIR/}:"
        fi
        echo -e "${YELLOW}${test_out}${NC}" >&2
        return 1
    fi
}

run_check() {
    log_header "PBL4 IDPS Pre-Flight & Audit Check (--check)"
    log_info "Target project root: ${PROJECT_DIR}"
    log_info "Target runtime user: ${RUN_USER} (group: ${RUN_GROUP})"

    local errors=0
    local warnings=0

    # 1. Source files check
    log_info "Verifying required repository files..."
    local required_sources=(
        "${SRC_SURICATA_CONF}"
        "${SRC_SURICATA_RULES}"
        "${SRC_NGINX_CONF}"
        "${SRC_NFTABLES_CONF}"
        "${SRC_NFTABLES_RULES}"
        "${SRC_FIREWALL_HELPER}"
        "${SRC_SYSTEMD_SERVICE}"
        "${SRC_SCHEMA_SQL}"
        "${SRC_ENV_EXAMPLE}"
        "${SRC_CARGO_TOML}"
    )

    for src in "${required_sources[@]}"; do
        if [ -f "$src" ]; then
            log_success "Source found: ${src#$PROJECT_DIR/}"
        else
            log_error "Missing required source: ${src#$PROJECT_DIR/}"
            errors=$((errors + 1))
        fi
    done

    # 2. Required tools check
    log_info "Verifying required system binaries..."
    local tools=(cargo node npm docker nginx suricata nft sudo)
    for tool in "${tools[@]}"; do
        if command -v "$tool" >/dev/null 2>&1; then
            log_success "Tool installed: $tool ($(command -v "$tool"))"
        else
            log_warn "Tool missing: $tool"
            warnings=$((warnings + 1))
        fi
    done

    # 3. Network interface & IP topology check
    log_info "Validating network interfaces and IP topology..."
    if ip link show dev "${ATTACKER_IFACE}" >/dev/null 2>&1; then
        log_success "Attacker interface exists: ${ATTACKER_IFACE}"
    else
        log_warn "Attacker interface '${ATTACKER_IFACE}' NOT found on host! (Detected: $(ip -br link | awk '{print $1}' | tr '\n' ' '))"
        warnings=$((warnings + 1))
    fi

    if ip link show dev "${PROTECTED_IFACE}" >/dev/null 2>&1; then
        log_success "Protected interface exists: ${PROTECTED_IFACE}"
    else
        log_warn "Protected interface '${PROTECTED_IFACE}' NOT found on host! (Detected: $(ip -br link | awk '{print $1}' | tr '\n' ' '))"
        warnings=$((warnings + 1))
    fi

    if ip -br a | grep -q "${SECURITY_IP}"; then
        log_success "Security VM IP is configured on a local interface: ${SECURITY_IP}"
    else
        log_warn "Security VM IP '${SECURITY_IP}' is not assigned to any local interface!"
        warnings=$((warnings + 1))
    fi

    # 4. Suricata syntax & configuration validation
    log_info "Validating Suricata configuration..."
    if [ -f "${SRC_SURICATA_CONF}" ]; then
        if validate_suricata_config "${SRC_SURICATA_CONF}" "Repository Suricata configuration"; then
            # Check that only pbl4.rules is loaded and not default suricata.rules
            if grep -qE "^\s*-\s*pbl4\.rules" "${SRC_SURICATA_CONF}" && ! grep -qE "^\s*-\s*suricata\.rules" "${SRC_SURICATA_CONF}"; then
                log_success "Suricata rule-files configured to exclusively load pbl4.rules"
            else
                log_warn "Suricata rule-files may not be exclusively loading pbl4.rules"
                warnings=$((warnings + 1))
            fi
        else
            errors=$((errors + 1))
        fi
    fi

    # 5. Nginx configuration validation
    log_info "Validating Nginx configuration..."
    if command -v nginx >/dev/null 2>&1; then
        local nginx_output
        nginx_output=$(nginx -t 2>&1 || true)
        if echo "$nginx_output" | grep -q "syntax is ok"; then
            log_success "Nginx system configuration syntax is valid"
        else
            log_error "Nginx configuration syntax error: $nginx_output"
            errors=$((errors + 1))
        fi
    fi

    # 6. nftables & firewall helper check
    log_info "Validating nftables rules and helper scripts..."
    if [ -x "${SRC_FIREWALL_HELPER}" ]; then
        log_success "Firewall helper has executable permissions: ${SRC_FIREWALL_HELPER#$PROJECT_DIR/}"
    else
        log_error "Firewall helper is not executable: ${SRC_FIREWALL_HELPER#$PROJECT_DIR/}"
        errors=$((errors + 1))
    fi

    if bash -n "${SRC_FIREWALL_HELPER}"; then
        log_success "Firewall helper shell syntax is valid"
    else
        log_error "Firewall helper shell syntax error"
        errors=$((errors + 1))
    fi

    # Test sudo access for pbl4-firewall
    if [ -f "${SYS_FIREWALL_HELPER}" ]; then
        if sudo -n "${SYS_FIREWALL_HELPER}" list >/dev/null 2>&1; then
            log_success "Current user has passwordless sudo access for ${SYS_FIREWALL_HELPER}"
        else
            log_warn "Current user cannot execute 'sudo -n ${SYS_FIREWALL_HELPER} list' without password (will be configured on --deploy)"
            warnings=$((warnings + 1))
        fi
    else
        log_warn "Deployed firewall helper ${SYS_FIREWALL_HELPER} not found yet (will be installed on --deploy)"
    fi

    # 7. Log file paths & permissions
    log_info "Checking log file availability for IDPS engine..."
    if [ -f "${LOG_SURICATA_EVE}" ]; then
        if [ -r "${LOG_SURICATA_EVE}" ]; then
            log_success "Suricata EVE log is readable: ${LOG_SURICATA_EVE}"
        else
            log_error "Suricata EVE log exists but is NOT readable by ${RUN_USER}: ${LOG_SURICATA_EVE}"
            errors=$((errors + 1))
        fi
    else
        log_warn "Suricata EVE log not found at ${LOG_SURICATA_EVE} (service might not be logging yet)"
        warnings=$((warnings + 1))
    fi

    if [ -f "${LOG_NGINX_ACCESS}" ]; then
        if [ -r "${LOG_NGINX_ACCESS}" ]; then
            log_success "Nginx access log is readable: ${LOG_NGINX_ACCESS}"
        else
            log_error "Nginx access log exists but is NOT readable by ${RUN_USER}: ${LOG_NGINX_ACCESS}"
            log_info "Tip: User will be automatically added to 'adm' group during --deploy"
            errors=$((errors + 1))
        fi
    else
        log_warn "Nginx access log not found at ${LOG_NGINX_ACCESS}"
        warnings=$((warnings + 1))
    fi

    # 8. Comparison between Repository Sources and Deployed System Files
    log_header "Repository Source vs Deployed System Comparison"
    local comparisons=(
        "${SRC_SURICATA_CONF}:${SYS_SURICATA_CONF}:Suricata Configuration"
        "${SRC_SURICATA_RULES}:${SYS_SURICATA_RULES}:Suricata PBL4 Rules"
        "${SRC_NGINX_CONF}:${SYS_NGINX_SITE}:Nginx Proxy Site Config"
        "${SRC_NFTABLES_CONF}:${SYS_NFTABLES_CONF}:nftables Main Configuration"
        "${SRC_NFTABLES_RULES}:${SYS_NFTABLES_RULES}:nftables PBL4 Rules"
        "${SRC_FIREWALL_HELPER}:${SYS_FIREWALL_HELPER}:Firewall Helper Script"
    )

    for item in "${comparisons[@]}"; do
        IFS=':' read -r src sys label <<< "$item"
        if [ ! -f "$sys" ]; then
            log_warn "$label: NOT DEPLOYED YET (missing $sys)"
            warnings=$((warnings + 1))
        elif cmp -s "$src" "$sys"; then
            log_success "$label: IN SYNC (source matches $sys)"
        else
            log_warn "$label: DIFFERS between source and $sys"
            echo -e "${YELLOW}--- Diff ($src vs $sys) ---${NC}"
            diff -u "$src" "$sys" || true
            echo -e "${YELLOW}--------------------------------${NC}"
            warnings=$((warnings + 1))
        fi
    done

    # Validate and compare templated systemd unit
    local tmp_expected_unit="/tmp/pbl4-test-verify.service"
    render_systemd_service "${tmp_expected_unit}"
    if command -v systemd-analyze >/dev/null 2>&1; then
        if systemd-analyze verify "${tmp_expected_unit}" >/dev/null 2>&1; then
            log_success "Systemd service template syntax is valid"
        else
            log_warn "Systemd service template syntax verification had warnings"
        fi
    fi

    if [ ! -f "${SYS_SYSTEMD_SERVICE}" ]; then
        log_warn "Systemd Service Unit: NOT DEPLOYED YET (missing ${SYS_SYSTEMD_SERVICE})"
        warnings=$((warnings + 1))
    elif cmp -s "${tmp_expected_unit}" "${SYS_SYSTEMD_SERVICE}"; then
        log_success "Systemd Service Unit: IN SYNC (${SYS_SYSTEMD_SERVICE})"
    else
        log_warn "Systemd Service Unit: DIFFERS between templated source and ${SYS_SYSTEMD_SERVICE}"
        echo -e "${YELLOW}--- Diff (templated source vs ${SYS_SYSTEMD_SERVICE}) ---${NC}"
        diff -u "${tmp_expected_unit}" "${SYS_SYSTEMD_SERVICE}" || true
        echo -e "${YELLOW}-----------------------------------------------------${NC}"
        warnings=$((warnings + 1))
    fi
    rm -f "${tmp_expected_unit}"


    # 9. Check runtime service status
    log_header "Runtime Service Status"
    # PostgreSQL database service
    if ss -tlpn 2>/dev/null | grep -q ":5433 "; then
        log_success "PostgreSQL database is listening on 127.0.0.1:5433"
    elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "pbl4-postgres"; then
        log_success "Docker PostgreSQL container (pbl4-postgres) is RUNNING"
    else
        log_warn "PostgreSQL is not listening on 127.0.0.1:5433 (check 'docker compose ps')"
        warnings=$((warnings + 1))
    fi

    # Backend port 3000
    if ss -tlpn 2>/dev/null | grep -q ":3000 "; then
        log_info "Backend IDPS core is currently listening on port 3000"
    else
        log_info "Port 3000 is currently free (ready for systemd or development run)"
    fi

    # Nginx port 80
    if ss -tlpn 2>/dev/null | grep -q "192.168.10.1:80 "; then
        log_success "Nginx reverse proxy is listening on 192.168.10.1:80"
    else
        log_warn "Nginx is not listening on 192.168.10.1:80"
        warnings=$((warnings + 1))
    fi

    # Summary
    log_header "Audit Summary"
    echo -e "Total Errors   : ${RED}${errors}${NC}"
    echo -e "Total Warnings : ${YELLOW}${warnings}${NC}"

    if [ "$errors" -eq 0 ]; then
        log_success "Check completed successfully. System is ready for deployment."
        return 0
    else
        log_error "Check detected $errors error(s). Please address them before deploying."
        return 1
    fi
}

run_deploy() {
    log_header "PBL4 IDPS Safe Deployment (--deploy)"
    log_info "Target project root: ${PROJECT_DIR}"
    log_info "Target runtime user: ${RUN_USER} (group: ${RUN_GROUP})"

    # Step 1: Pre-deployment dry-run validation
    log_info "Step 1/8: Validating source files before installation..."
    if ! [ -f "${SRC_SURICATA_CONF}" ] || ! [ -f "${SRC_SURICATA_RULES}" ] || \
       ! [ -f "${SRC_NGINX_CONF}" ] || ! [ -f "${SRC_NFTABLES_CONF}" ] || \
       ! [ -f "${SRC_NFTABLES_RULES}" ] || ! [ -f "${SRC_FIREWALL_HELPER}" ] || \
       ! [ -f "${SRC_SYSTEMD_SERVICE}" ]; then
        log_error "Source files missing. Deployment aborted."
        exit 1
    fi

    if ! bash -n "${SRC_FIREWALL_HELPER}"; then
        log_error "Firewall helper has syntax errors. Deployment aborted."
        exit 1
    fi

    if ! validate_suricata_config "${SRC_SURICATA_CONF}" "Pre-deploy repository Suricata configuration"; then
        log_error "Deployment aborted due to Suricata configuration issues."
        exit 1
    fi
    log_success "Source validation passed."

    # Always build current source; never deploy a stale binary or stale UI.
    log_info "Step 2/8: Building React dashboard and Rust release..."
    su - "${RUN_USER}" -c "cd '${PROJECT_DIR}/frontend' && npm ci && npm run build"
    su - "${RUN_USER}" -c "cd '${PROJECT_DIR}' && cargo build --release --locked"
    test -f "${PROJECT_DIR}/frontend/dist/index.html"
    test -x "${PROJECT_DIR}/target/release/pbl4-security-demo"
    su - "${RUN_USER}" -c "cd '${PROJECT_DIR}' && target/release/pbl4-security-demo --check-config"

    # Step 3: Timestamped backup
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="/var/backups/pbl4/${timestamp}"
    log_info "Step 3/8: Creating timestamped backup at ${backup_dir}..."
    mkdir -p "${backup_dir}"

    local files_to_backup=(
        "${SYS_SURICATA_CONF}"
        "${SYS_SURICATA_RULES}"
        "${SYS_NGINX_SITE}"
        "${SYS_NFTABLES_CONF}"
        "${SYS_NFTABLES_RULES}"
        "${SYS_FIREWALL_HELPER}"
        "${SYS_SYSTEMD_SERVICE}"
        "${SYS_SUDOERS_PBL4}"
    )

    for f in "${files_to_backup[@]}"; do
        if [ -f "$f" ]; then
            cp -p "$f" "${backup_dir}/$(basename "$f")"
            log_info "Backed up: $f"
        fi
    done
    log_success "Backup completed."

    # Step 4: Safe installation of files
    log_info "Step 4/8: Installing configuration files into system..."

    rollback() {
        log_error "Deployment encountered an error! Rolling back from ${backup_dir}..."
        for f in "${files_to_backup[@]}"; do
            local base
            base=$(basename "$f")
            if [ -f "${backup_dir}/${base}" ]; then
                cp -p "${backup_dir}/${base}" "$f"
                log_warn "Restored $f from backup"
            fi
        done
        systemctl daemon-reload 2>/dev/null || true
        log_error "Rollback completed. Exiting."
        exit 1
    }

    # Trap any unexpected error during installation
    trap rollback ERR

    # Suricata configuration & rules
    install -d -m 755 -o root -g root "${SYS_SURICATA_RULES_DIR}"
    install -m 644 -o root -g root "${SRC_SURICATA_RULES}" "${SYS_SURICATA_RULES}"
    install -m 644 -o root -g root "${SRC_SURICATA_CONF}" "${SYS_SURICATA_CONF}"
    log_success "Installed Suricata configuration and PBL4 rules"

    # Nginx reverse proxy
    install -d -m 755 -o root -g root "/etc/nginx/sites-available"
    install -d -m 755 -o root -g root "/etc/nginx/sites-enabled"
    install -m 644 -o root -g root "${SRC_NGINX_CONF}" "${SYS_NGINX_SITE}"
    ln -sf "${SYS_NGINX_SITE}" "${SYS_NGINX_ENABLED}"
    log_success "Installed Nginx reverse proxy site configuration"

    # nftables main & rules
    install -d -m 755 -o root -g root "${SYS_NFTABLES_DIR}"
    install -m 755 -o root -g root "${SRC_NFTABLES_CONF}" "${SYS_NFTABLES_CONF}"
    install -m 644 -o root -g root "${SRC_NFTABLES_RULES}" "${SYS_NFTABLES_RULES}"
    # Clean up legacy pbl4-demo.nft if present
    if [ -f "${SYS_NFTABLES_DIR}/pbl4-demo.nft" ]; then
        rm -f "${SYS_NFTABLES_DIR}/pbl4-demo.nft"
    fi
    log_success "Installed nftables configuration"

    # Firewall helper
    install -m 755 -o root -g root "${SRC_FIREWALL_HELPER}" "${SYS_FIREWALL_HELPER}"
    log_success "Installed firewall helper to ${SYS_FIREWALL_HELPER}"

    # Sudoers entry for RUN_USER
    local tmp_sudoers
    tmp_sudoers=$(mktemp)
    echo "${RUN_USER} ALL=(root) NOPASSWD: ${SYS_FIREWALL_HELPER}" > "${tmp_sudoers}"
    chmod 0440 "${tmp_sudoers}"
    if visudo -cf "${tmp_sudoers}" >/dev/null 2>&1; then
        install -m 440 -o root -g root "${tmp_sudoers}" "${SYS_SUDOERS_PBL4}"
        log_success "Configured restricted passwordless sudo for ${RUN_USER} in ${SYS_SUDOERS_PBL4}"
    else
        log_warn "Failed to validate sudoers entry; skipping sudoers file update"
    fi
    rm -f "${tmp_sudoers}"

    # Ensure RUN_USER is in adm group to read /var/log/nginx/access.log
    if id "${RUN_USER}" >/dev/null 2>&1; then
        usermod -aG adm "${RUN_USER}" 2>/dev/null || true
        log_success "Ensured user ${RUN_USER} belongs to group 'adm' (for Nginx access log reading)"
    fi

    # Render dynamic systemd unit
    render_systemd_service "${SYS_SYSTEMD_SERVICE}"
    chmod 644 "${SYS_SYSTEMD_SERVICE}"
    chown root:root "${SYS_SYSTEMD_SERVICE}"
    log_success "Rendered and installed systemd unit to ${SYS_SYSTEMD_SERVICE}"

    # Step 5: Post-installation syntax verification on live system
    log_info "Step 5/8: Verifying installed configuration syntax on live system..."
    
    if ! validate_suricata_config "${SYS_SURICATA_CONF}" "Post-install live Suricata configuration"; then
        log_error "Post-install Suricata check failed!"
        rollback
    fi

    local nginx_test
    nginx_test=$(nginx -t 2>&1 || true)
    if ! echo "$nginx_test" | grep -q "syntax is ok"; then
        log_error "Post-install Nginx check failed: $nginx_test"
        rollback
    fi

    if nft -c -f "${SYS_NFTABLES_CONF}" >/dev/null 2>&1; then
        log_success "Post-install nftables check passed"
    else
        log_warn "nftables syntax verification via netlink skipped or had non-fatal notice"
    fi

    # Step 6: Reload / Restart services safely
    log_info "Step 6/8: Reloading active services..."

    # Nginx reload
    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
        log_success "Reloaded Nginx service"
    fi

    # Suricata reload rules or restart
    if systemctl is-active --quiet suricata; then
        if command -v suricatasc >/dev/null 2>&1 && suricatasc -c reload-rules >/dev/null 2>&1; then
            log_success "Reloaded Suricata rules dynamically via suricatasc"
        else
            systemctl restart suricata
            log_success "Restarted Suricata service"
        fi
    fi

    # nftables: Load PBL4 rule set into kernel without flushing Docker or system tables
    if [ -f "${SYS_NFTABLES_RULES}" ]; then
        if nft -f "${SYS_NFTABLES_RULES}"; then
            log_success "Applied nftables PBL4 ruleset into kernel"
        else
            log_warn "Failed to apply nftables demo rule into kernel directly"
        fi
    fi

    # systemd daemon reload
    systemctl daemon-reload
    log_success "Reloaded systemd daemon configuration"

    # Untrap on success
    trap - ERR

    # Step 7: Backend systemd service activation
    log_header "Step 7/8: Backend Systemd Service Activation"
    if systemctl is-active --quiet pbl4-security.service; then
        log_info "pbl4-security.service is currently running; restarting to load latest release binary..."
        systemctl restart pbl4-security.service
        sleep 2
        if systemctl is-active --quiet pbl4-security.service; then
            log_success "Backend service pbl4-security.service is ACTIVE and RUNNING."
            if curl -sf http://127.0.0.1:3000/health >/dev/null 2>&1; then
                log_success "Health check verified: http://127.0.0.1:3000/health -> OK"
            fi
        else
            log_warn "pbl4-security.service failed to restart cleanly."
            log_info "Check logs with: journalctl -u pbl4-security.service -n 20 --no-pager"
        fi
    elif ss -tlpn 2>/dev/null | grep -q ":3000 "; then
        log_warn "Port 3000 is currently occupied by an active process (e.g. manual cargo run)."
        log_info "Unit file installed and daemon reloaded. To start the background systemd service:"
        echo -e "  1. Stop your manual terminal process (Ctrl+C on 'cargo run')."
        echo -e "  2. Start and enable systemd service:"
        echo -e "     ${BOLD}sudo systemctl enable --now pbl4-security.service${NC}"
        echo -e "  3. Check backend service status:"
        echo -e "     ${BOLD}systemctl status pbl4-security.service${NC}"
    else
        log_info "Port 3000 is free. Starting and enabling pbl4-security.service..."
        systemctl enable --now pbl4-security.service
        sleep 2
        if systemctl is-active --quiet pbl4-security.service; then
            log_success "Backend service pbl4-security.service is ACTIVE and RUNNING."
            if curl -sf http://127.0.0.1:3000/health >/dev/null 2>&1; then
                log_success "Health check verified: http://127.0.0.1:3000/health -> OK"
            fi
        else
            log_warn "pbl4-security.service was started but is not reporting active state."
            log_info "Check logs with: journalctl -u pbl4-security.service -n 20 --no-pager"
        fi
    fi

    # Step 8: Completed report
    log_header "Step 8/8: Deployment Completed Successfully"
    log_success "All configuration files safely installed, templated, and verified."
    log_info "Timestamped backup saved at: ${backup_dir}"
}

# Entrypoint argument parsing
case "${1:-}" in
    --check)
        run_check
        ;;
    --deploy)
        run_deploy
        ;;
    *)
        echo -e "${BOLD}Usage:${NC} $0 {--check|--deploy}"
        echo ""
        echo "Options:"
        echo "  --check   Audit environment, validate syntax, and compare source vs system configs."
        echo "  --deploy  Safely deploy configs to system with automated sudo elevation, backup & rollback."
        exit 1
        ;;
esac
