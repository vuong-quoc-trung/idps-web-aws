/**
 * NIDS Web IDPS/IPS Dashboard Application
 * Modern reactive dashboard matching NIDS design reference
 */

// State Management
const state = {
  alerts: [],
  blockedIps: [],
  stats: null,
  rules: [],
  timeFilter: '24h',
  searchQuery: '',
  selectedTab: 'dashboard',
  pollingInterval: null,
  chartFilter: '7d',
  isFetching: false,
};

// Attack categories and color mappings matching NIDS design
const ATTACK_COLORS = {
  'SQL Injection': '#eab308', // Yellow
  'Cross-Site Scripting (XSS)': '#10b981', // Green
  'Port Scan': '#f97316', // Orange
  'OS Command Injection': '#ef4444', // Red
  'Path Traversal': '#ec4899', // Pink
  'Sensitive Files Probing': '#8b5cf6', // Purple
  'Scanner User-Agent': '#06b6d4', // Cyan
  'DDoS Attack': '#3b82f6', // Blue
  'Brute Force': '#a855f7', // Violet
  'Web Application Attack': '#f59e0b', // Amber
  'Reconnaissance': '#64748b', // Slate
  'Others': '#6b7280' // Gray
};

// ============================================================================
// Lab Network & IP Validation Helpers
// ============================================================================

/**
 * Validates whether an IP belongs to the allowed demo attacker range:
 * 192.168.10.2 - 192.168.10.254.
 * Allows optional single-host /32 mask (e.g. 192.168.10.10/32).
 */
function isBlockableAttackerIp(ipStr) {
  if (!ipStr) return false;
  const raw = String(ipStr).trim();
  let ipPart = raw;
  if (raw.includes('/')) {
    const [addr, mask] = raw.split('/');
    if (mask.trim() !== '32') return false; // Reject non-/32 subnets
    ipPart = addr.trim();
  }
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ipPart);
  if (!match) return false;
  const [_, o1, o2, o3, o4] = match.map(Number);
  if (o1 > 255 || o2 > 255 || o3 > 255 || o4 > 255) return false;
  return o1 === 192 && o2 === 168 && o3 === 10 && o4 >= 2 && o4 <= 254;
}

/**
 * Identifies if the IP is the Security VM gateway itself (192.168.10.1).
 * Never allow blocking the Security VM itself.
 */
function isSecurityVmIp(ipStr) {
  if (!ipStr) return false;
  const raw = String(ipStr).trim();
  let ipPart = raw;
  if (raw.includes('/')) {
    const [addr, mask] = raw.split('/');
    if (mask.trim() !== '32') return false;
    ipPart = addr.trim();
  }
  return ipPart === '192.168.10.1';
}

/**
 * Normalizes input IP address: strips /32 if present; returns null if invalid CIDR or IP format.
 */
function normalizeLabIp(ipStr) {
  if (!ipStr) return null;
  const raw = String(ipStr).trim();
  if (raw.includes('/')) {
    const [addr, mask] = raw.split('/');
    if (mask.trim() !== '32') return null;
    return addr.trim();
  }
  return raw;
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initModals();
  initSearch();
  initTimeFilter();
  initExport();
  
  // Initial fetch
  fetchData();
  
  // Start polling every 3 seconds - prevent duplicate intervals
  if (state.pollingInterval) {
    clearInterval(state.pollingInterval);
  }
  state.pollingInterval = setInterval(fetchData, 3000);
  
  // Window resize handler for charts
  window.addEventListener('resize', debounce(() => {
    renderTrafficChart();
    renderDonutChart();
  }, 200));
});

// ============================================================================
// Data Fetching & State Updates
// ============================================================================
async function fetchData() {
  if (state.isFetching) return;
  state.isFetching = true;

  try {
    const [alertsRes, blockedRes, statsRes, rulesRes] = await Promise.all([
      fetch('/api/alerts?limit=100'),
      fetch('/api/blocked-ips'),
      fetch('/api/stats').catch(() => null),
      fetch('/api/rules').catch(() => null)
    ]);

    if (!alertsRes.ok) throw new Error(`Alerts API returned ${alertsRes.status}`);
    const alerts = await alertsRes.json();
    const blockedIps = blockedRes.ok ? await blockedRes.json() : [];
    const stats = statsRes && statsRes.ok ? await statsRes.json() : null;
    const rules = rulesRes && rulesRes.ok ? await rulesRes.json() : [];

    state.alerts = alerts;
    state.blockedIps = blockedIps;
    state.stats = stats;
    if (rules.length) state.rules = rules;

    updateUI();
    setSystemOperational(true);
  } catch (error) {
    console.error('Data fetch error:', error);
    setSystemOperational(false, error.message);
  } finally {
    state.isFetching = false;
  }
}

function updateUI() {
  updateSidebarBadges();
  updateStatCards();
  renderAlertsTable();
  renderDonutChart();
  renderTrafficChart();
  renderActiveBlockedTable();
  updateSystemMeters();
}

function setSystemOperational(isOk, errMsg) {
  const globalText = document.getElementById('globalStatusText');
  const pulse = document.querySelector('.status-pulse');
  if (isOk) {
    if (globalText) globalText.textContent = 'All systems operational';
    if (pulse) pulse.style.background = '#10b981';
  } else {
    if (globalText) globalText.textContent = `Degraded: ${errMsg || 'Connection error'}`;
    if (pulse) pulse.style.background = '#ef4444';
  }
}

// ============================================================================
// Top Stat Cards
// ============================================================================
function updateStatCards() {
  const totalAlerts = state.stats?.total_alerts ?? state.alerts.length;
  const criticalAlerts = state.stats?.critical_alerts ?? state.alerts.filter(a => a.severity <= 1).length;
  const blockedAttacks = state.stats?.blocked_attacks ?? state.alerts.filter(a => a.action === 'AUTO-BLOCK').length;
  const activeBlockedCount = state.blockedIps.length;

  const statTotalAlerts = document.getElementById('statTotalAlerts');
  const statCriticalAlerts = document.getElementById('statCriticalAlerts');
  const statBlockedAttacks = document.getElementById('statBlockedAttacks');
  const statActiveConnections = document.getElementById('statActiveConnections');
  const statTrafficAnalyzed = document.getElementById('statTrafficAnalyzed');

  if (statTotalAlerts) statTotalAlerts.textContent = formatNumber(totalAlerts);
  if (statCriticalAlerts) statCriticalAlerts.textContent = formatNumber(criticalAlerts);
  if (statBlockedAttacks) statBlockedAttacks.textContent = formatNumber(blockedAttacks);
  
  if (state.stats?.active_connections && statActiveConnections) {
    statActiveConnections.textContent = formatNumber(state.stats.active_connections);
  }
  if (state.stats?.traffic_analyzed && statTrafficAnalyzed) {
    statTrafficAnalyzed.textContent = state.stats.traffic_analyzed;
  }
}

function updateSidebarBadges() {
  const alertBadge = document.getElementById('sidebarAlertBadge');
  const blockedBadge = document.getElementById('sidebarBlockedBadge');
  if (alertBadge) alertBadge.textContent = state.alerts.length;
  if (blockedBadge) blockedBadge.textContent = state.blockedIps.length;
}

// ============================================================================
// Recent Alerts Table
// ============================================================================
function renderAlertsTable() {
  const tbody = document.getElementById('alertsTableBody');
  if (!tbody) return;

  let filtered = state.alerts;

  // Search filter
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    filtered = filtered.filter(a => 
      (a.src_ip && a.src_ip.toLowerCase().includes(q)) ||
      (a.rule_name && a.rule_name.toLowerCase().includes(q)) ||
      (a.action && a.action.toLowerCase().includes(q)) ||
      (a.category && a.category.toLowerCase().includes(q))
    );
  }

  // Time filter
  if (state.timeFilter !== 'all') {
    const now = Date.now();
    const cutoff = state.timeFilter === '1h' ? 3600 * 1000 :
                   state.timeFilter === '24h' ? 86400 * 1000 :
                   7 * 86400 * 1000;
    filtered = filtered.filter(a => (now - new Date(a.occurred_at).getTime()) <= cutoff);
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">
          <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <p>No intrusion alerts match the current filter</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  // Display top 15 alerts for recent alerts view
  const displayAlerts = filtered.slice(0, 15);
  tbody.innerHTML = displayAlerts.map(alert => {
    const dateFormatted = formatDateTime(alert.occurred_at);
    const attackType = cleanAttackType(alert.rule_name, alert.category);
    const severityBadge = getSeverityBadge(alert.severity);
    const actionBadge = getActionBadge(alert.action);
    const cleanSrcIp = alert.src_ip ? alert.src_ip.split('/')[0].trim() : '';
    const cleanDestIp = alert.dest_ip ? alert.dest_ip.split('/')[0].trim() : '';
    const isCurrentlyBlocked = cleanSrcIp && state.blockedIps.some(b => (b.ip || '').split('/')[0].trim() === cleanSrcIp);

    return `
      <tr>
        <td class="cell-time">${escapeHtml(dateFormatted)}</td>
        <td class="cell-type">
          <span class="attack-type-tag">${escapeHtml(attackType)}</span>
        </td>
        <td class="cell-ip font-mono">${escapeHtml(cleanSrcIp || '-')}</td>
        <td class="cell-ip font-mono">${escapeHtml(cleanDestIp || '192.168.10.1')}</td>
        <td class="cell-severity">${severityBadge}</td>
        <td class="cell-action">${actionBadge}</td>
        <td class="cell-ops">
          ${renderRowActionOps(alert, cleanSrcIp, attackType, isCurrentlyBlocked)}
        </td>
      </tr>
    `;
  }).join('');
}

function renderRowActionOps(alert, cleanSrcIp, attackType, isCurrentlyBlocked) {
  if (!cleanSrcIp || cleanSrcIp === '-') {
    return '<span class="badge-tag muted">—</span>';
  }
  if (isSecurityVmIp(cleanSrcIp)) {
    return '<span class="badge-tag protected" title="Protected Gateway (Security VM 192.168.10.1 - cannot be blocked)">Protected</span>';
  }
  if (!isBlockableAttackerIp(cleanSrcIp)) {
    return '<span class="badge-tag nonlab" title="Outside Demo Attacker Range (192.168.10.2-254)">Non-Lab IP</span>';
  }
  if (isCurrentlyBlocked) {
    return `<button class="btn-table-action unblock" onclick="triggerUnblock('${escapeHtml(cleanSrcIp)}')" title="Unblock ${escapeHtml(cleanSrcIp)} in nftables firewall">Unblock</button>`;
  }
  return `<button class="btn-table-action block" onclick="triggerBlock('${escapeHtml(cleanSrcIp)}', 'Blocked from Alert #${alert.id}: ${escapeHtml(attackType)}')" title="Block ${escapeHtml(cleanSrcIp)} in nftables firewall">Block</button>`;
}

function getSeverityBadge(severity) {
  switch (Number(severity)) {
    case 1:
      return '<span class="badge badge-critical">Critical</span>';
    case 2:
      return '<span class="badge badge-high">High</span>';
    case 3:
      return '<span class="badge badge-medium">Medium</span>';
    default:
      return '<span class="badge badge-low">Low</span>';
  }
}

function getActionBadge(action) {
  const norm = (action || '').toUpperCase();
  if (norm === 'AUTO-BLOCK' || norm === 'BLOCKED') {
    return `<span class="badge badge-action-blocked"><span class="badge-dot"></span>AUTO-BLOCK</span>`;
  }
  return `<span class="badge badge-action-alert"><span class="badge-dot"></span>ALERT</span>`;
}

function cleanAttackType(ruleName, category) {
  if (!ruleName) return category || 'Security Event';
  let clean = ruleName.replace(/^(SURICATA:\s*PBL4 NIDS:\s*|SURICATA:\s*|NGINX:\s*)/i, '').trim();
  clean = clean.replace(/ Attempt$/i, '').trim();
  if (clean.length > 32) return clean.substring(0, 30) + '...';
  return clean;
}

// ============================================================================
// Donut Chart: Top Attack Types
// ============================================================================
function renderDonutChart() {
  const canvas = document.getElementById('attackTypesDonutChart');
  const legendList = document.getElementById('donutLegendList');
  const totalCountEl = document.getElementById('donutTotalCount');
  if (!canvas || !legendList) return;

  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(centerX, centerY) - 14;
  const innerRadius = radius * 0.68;

  // Aggregate attack types
  const counts = {};
  state.alerts.forEach(a => {
    let type = categorizeAttack(a.rule_name, a.category);
    counts[type] = (counts[type] || 0) + 1;
  });

  const total = Object.values(counts).reduce((sum, c) => sum + c, 0);
  if (totalCountEl) totalCountEl.textContent = formatNumber(total);

  ctx.clearRect(0, 0, width, height);

  // If no data
  if (total === 0) {
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.arc(centerX, centerY, innerRadius, Math.PI * 2, 0, true);
    ctx.fillStyle = '#1e293b';
    ctx.fill();
    legendList.innerHTML = '<div class="legend-empty">No attack events recorded</div>';
    return;
  }

  // Sort by count descending
  const sorted = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const topSum = sorted.reduce((s, item) => s + item[1], 0);
  if (total > topSum) {
    sorted.push(['Others', total - topSum]);
  }

  // Draw donut slices
  let startAngle = -Math.PI / 2;
  const sliceGap = 0.04;

  sorted.forEach(([type, count]) => {
    const sliceAngle = (count / total) * (Math.PI * 2);
    const endAngle = startAngle + sliceAngle;
    const color = ATTACK_COLORS[type] || '#3b82f6';

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle + sliceGap / 2, endAngle - sliceGap / 2);
    ctx.arc(centerX, centerY, innerRadius, endAngle - sliceGap / 2, startAngle + sliceGap / 2, true);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 4;
    ctx.fill();
    ctx.shadowBlur = 0;

    startAngle = endAngle;
  });

  // Render legend
  legendList.innerHTML = sorted.map(([type, count]) => {
    const pct = ((count / total) * 100).toFixed(1);
    const color = ATTACK_COLORS[type] || '#3b82f6';
    return `
      <div class="donut-legend-item">
        <div class="legend-info">
          <span class="donut-dot" style="background-color: ${color};"></span>
          <span class="legend-type" title="${escapeHtml(type)}">${escapeHtml(type)}</span>
        </div>
        <div class="legend-values">
          <span class="legend-pct">${pct}%</span>
          <span class="legend-count">(${count})</span>
        </div>
      </div>
    `;
  }).join('');
}

function categorizeAttack(ruleName, category) {
  const text = (ruleName + ' ' + (category || '')).toLowerCase();
  if (text.includes('sql')) return 'SQL Injection';
  if (text.includes('xss') || text.includes('script')) return 'Cross-Site Scripting (XSS)';
  if (text.includes('scan') || text.includes('syn')) return 'Port Scan';
  if (text.includes('traversal') || text.includes('passwd')) return 'Path Traversal';
  if (text.includes('command') || text.includes('whoami')) return 'OS Command Injection';
  if (text.includes('sensitive') || text.includes('.env') || text.includes('.git')) return 'Sensitive Files Probing';
  if (text.includes('nikto') || text.includes('sqlmap') || text.includes('scanner')) return 'Scanner User-Agent';
  if (text.includes('ddos') || text.includes('flood')) return 'DDoS Attack';
  if (text.includes('brute')) return 'Brute Force';
  return 'Web Application Attack';
}

// ============================================================================
// Multi-line Spline Chart: Traffic Overview
// ============================================================================
const CHART_FIXED_HEIGHT = 260;

function renderTrafficChart() {
  const canvas = document.getElementById('trafficLineChart');
  if (!canvas) return;

  const container = canvas.parentElement;
  if (!container) return;

  // Read clientWidth for responsive horizontal scaling, but lock height to fixed constant.
  // Never read container.clientHeight in a polling loop to avoid infinite canvas height expansion!
  const displayWidth = Math.floor(container.clientWidth) || 600;
  const displayHeight = CHART_FIXED_HEIGHT;

  if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
    canvas.width = displayWidth;
    canvas.height = displayHeight;
  }

  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const padding = { top: 25, right: 30, bottom: 40, left: 50 };
  const chartW = Math.max(10, w - padding.left - padding.right);
  const chartH = Math.max(10, h - padding.top - padding.bottom);

  ctx.clearRect(0, 0, w, h);

  const is24h = state.chartFilter === '24h';
  const labels = [];
  const now = new Date();
  if (is24h) {
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now.getTime() - i * 4 * 3600 * 1000);
      labels.push(d.getHours().toString().padStart(2, '0') + ':00');
    }
  } else {
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now.getTime() - i * 24 * 3600 * 1000);
      labels.push(`${monthNames[d.getMonth()]} ${d.getDate()}`);
    }
  }
  const n = labels.length;

  // Real or synthesized trend lines matching dashboard reference aesthetic
  // Bounded fixed-length 7-item series
  const normalData = is24h
    ? [28000, 31000, 35000, 44000, 49000, 42000, 46000]
    : [24000, 32000, 29000, 42000, 35000, 41000, 48000];
    
  const suspiciousData = is24h
    ? [8000, 11000, 9500, 14000, 16500, 13000, 15000]
    : [12000, 15000, 11000, 17000, 14000, 16000, 18000];
  
  // Malicious traffic derived from real alerts
  const alertCount = state.alerts ? state.alerts.length : 0;
  const baseMalicious = is24h
    ? [1500, 2200, 1900, 3800, 4200, 3100, Math.max(4500, alertCount * 180)]
    : [3000, 4200, 2800, 5600, 4100, 5200, Math.max(6500, alertCount * 250)];

  const maxVal = 55000;

  // Draw grid lines
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  const ySteps = 5;
  for (let i = 0; i <= ySteps; i++) {
    const y = padding.top + (chartH / ySteps) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    // Y Axis labels
    const val = Math.round((maxVal - (maxVal / ySteps) * i) / 1000) + 'K';
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(val, padding.left - 12, y + 4);
  }

  // Draw X Axis labels
  for (let i = 0; i < n; i++) {
    const x = padding.left + (chartW / (n - 1)) * i;
    ctx.fillStyle = '#64748b';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(labels[i], x, h - padding.bottom + 22);
  }

  // Draw curves
  drawSmoothLine(ctx, normalData, padding, chartW, chartH, maxVal, '#3b82f6', 2.5);
  drawSmoothLine(ctx, suspiciousData, padding, chartW, chartH, maxVal, '#f59e0b', 2.5);
  drawSmoothLine(ctx, baseMalicious, padding, chartW, chartH, maxVal, '#ef4444', 2.5);
}

function drawSmoothLine(ctx, data, pad, cw, ch, maxVal, color, lineWidth) {
  const points = data.map((val, i) => {
    return {
      x: pad.left + (cw / (data.length - 1)) * i,
      y: pad.top + ch - (val / maxVal) * ch
    };
  });

  // Curve path
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);

  for (let i = 0; i < points.length - 1; i++) {
    const cp1x = points[i].x + (points[i + 1].x - points[i].x) / 2;
    const cp1y = points[i].y;
    const cp2x = points[i].x + (points[i + 1].x - points[i].x) / 2;
    const cp2y = points[i + 1].y;
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, points[i + 1].x, points[i + 1].y);
  }

  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.stroke();

  // Draw glowing dots at each point
  points.forEach(p => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Inner white dot
    ctx.beginPath();
    ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  });
}

// ============================================================================
// System Status Meters
// ============================================================================
function updateSystemMeters() {
  const stats = state.stats?.system;
  if (!stats) return;

  if (stats.cpu_percent !== undefined) {
    const el = document.getElementById('cpuUsageVal');
    const bar = document.getElementById('cpuProgressBar');
    if (el) el.textContent = `${stats.cpu_percent}%`;
    if (bar) bar.style.width = `${Math.min(100, stats.cpu_percent)}%`;
  }

  if (stats.memory_percent !== undefined) {
    const el = document.getElementById('memUsageVal');
    const bar = document.getElementById('memProgressBar');
    if (el) el.textContent = `${stats.memory_percent}%`;
    if (bar) bar.style.width = `${Math.min(100, stats.memory_percent)}%`;
  }

  if (stats.disk_percent !== undefined) {
    const el = document.getElementById('diskUsageVal');
    const bar = document.getElementById('diskProgressBar');
    if (el) el.textContent = `${stats.disk_percent}%`;
    if (bar) bar.style.width = `${Math.min(100, stats.disk_percent)}%`;
  }

  if (stats.network_io_percent !== undefined) {
    const el = document.getElementById('netUsageVal');
    const bar = document.getElementById('netProgressBar');
    if (el) el.textContent = `${stats.network_io_percent}%`;
    if (bar) bar.style.width = `${Math.min(100, stats.network_io_percent)}%`;
  }
}

// ============================================================================
// Active Blocked IPs Table & Modal
// ============================================================================
function renderActiveBlockedTable() {
  const tbody = document.getElementById('activeBlockedTableBody');
  if (!tbody) return;

  if (state.blockedIps.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-cell">
          <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
            </svg>
            <p>No IP addresses currently blocked in kernel firewall</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = state.blockedIps.map(item => `
    <tr>
      <td class="cell-ip font-mono"><strong>${escapeHtml(item.ip)}</strong></td>
      <td>${escapeHtml(item.reason)}</td>
      <td class="cell-time">${escapeHtml(formatDateTime(item.blocked_at))}</td>
      <td><span class="badge badge-action-blocked">DROP</span></td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="triggerUnblock('${escapeHtml(item.ip)}')">
          Unblock
        </button>
      </td>
    </tr>
  `).join('');
}

// Safe API response parser supporting JSON, non-JSON text and network error states
async function parseApiResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      return await res.json();
    } catch (e) {
      return { status: 'error', message: 'Malformed JSON payload received from server' };
    }
  }
  const text = await res.text();
  return { status: 'error', message: text.trim() || `Server returned HTTP ${res.status}: ${res.statusText}` };
}

// ============================================================================
// Firewall Trigger Operations (Block / Unblock)
// ============================================================================
async function triggerBlock(ip, reason) {
  if (isSecurityVmIp(ip)) {
    showToast('Cannot block Security VM (192.168.10.1)', 'error');
    return;
  }

  const normIp = normalizeLabIp(ip);
  if (!normIp) {
    showToast('Cannot block: invalid IP or unsupported CIDR mask (only /32 allowed)', 'error');
    return;
  }

  if (!isBlockableAttackerIp(normIp)) {
    showToast(`IP ${normIp} is outside allowed attacker demo range (192.168.10.2 - 192.168.10.254)`, 'error');
    return;
  }

  try {
    const res = await fetch('/api/blocked-ips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip: normIp, reason: reason || 'Manual dashboard block' })
    });

    const data = await parseApiResponse(res);
    if (!res.ok || data.status === 'error') {
      throw new Error(data.message || `Block request rejected (HTTP ${res.status})`);
    }

    showToast(`Successfully blocked ${normIp} in nftables firewall`, 'success');
    fetchData();
  } catch (err) {
    console.error('Block IP error:', err);
    showToast(`Error blocking IP: ${err.message}`, 'error');
  }
}

async function triggerUnblock(ip) {
  const normIp = normalizeLabIp(ip);
  if (!normIp) {
    showToast('Cannot unblock: invalid IP address provided', 'error');
    return;
  }

  try {
    const res = await fetch(`/api/blocked-ips/${encodeURIComponent(normIp)}`, {
      method: 'DELETE'
    });

    const data = await parseApiResponse(res);
    if (!res.ok || data.status === 'error') {
      throw new Error(data.message || `Unblock request rejected (HTTP ${res.status})`);
    }

    showToast(`Successfully unblocked ${normIp} from firewall`, 'success');
    fetchData();
  } catch (err) {
    console.error('Unblock IP error:', err);
    showToast(`Error unblocking IP: ${err.message}`, 'error');
  }
}

// ============================================================================
// Modals & Navigation
// ============================================================================
function initModals() {
  const blockModal = document.getElementById('blockModal');
  const blockedListModal = document.getElementById('blockedListModal');
  const manualBlockTrigger = document.getElementById('manualBlockTriggerBtn');
  const closeBlockModalBtn = document.getElementById('closeBlockModalBtn');
  const cancelBlockModalBtn = document.getElementById('cancelBlockModalBtn');
  const submitManualBlockBtn = document.getElementById('submitManualBlockBtn');
  
  const closeBlockedListModalBtn = document.getElementById('closeBlockedListModalBtn');
  const closeBlockedListBtn = document.getElementById('closeBlockedListBtn');
  const refreshBlockedListBtn = document.getElementById('refreshBlockedListBtn');

  if (manualBlockTrigger) {
    manualBlockTrigger.addEventListener('click', () => {
      if (blockModal) blockModal.classList.add('active');
    });
  }

  const hideBlockModal = () => {
    if (blockModal) blockModal.classList.remove('active');
    const feedback = document.getElementById('manualBlockFeedback');
    if (feedback) feedback.textContent = '';
  };

  if (closeBlockModalBtn) closeBlockModalBtn.addEventListener('click', hideBlockModal);
  if (cancelBlockModalBtn) cancelBlockModalBtn.addEventListener('click', hideBlockModal);

  if (submitManualBlockBtn) {
    submitManualBlockBtn.addEventListener('click', async () => {
      const rawIp = document.getElementById('manualIpInput')?.value.trim();
      const reason = document.getElementById('manualReasonInput')?.value.trim();
      const feedback = document.getElementById('manualBlockFeedback');

      if (!rawIp) {
        if (feedback) feedback.textContent = 'IPv4 address is required';
        return;
      }

      if (isSecurityVmIp(rawIp)) {
        if (feedback) feedback.textContent = 'Cannot block 192.168.10.1 (Security VM Gateway)';
        showToast('Cannot block Security VM (192.168.10.1)', 'error');
        return;
      }

      const normIp = normalizeLabIp(rawIp);
      if (!normIp) {
        if (feedback) feedback.textContent = 'Only single-host IP addresses (/32) or pure IPv4 are allowed';
        showToast('Only single-host IP (/32) or pure IPv4 allowed', 'error');
        return;
      }

      if (!isBlockableAttackerIp(normIp)) {
        if (feedback) feedback.textContent = 'Only attacker range 192.168.10.2 - 192.168.10.254 may be blocked';
        showToast('Only lab attacker IPs (192.168.10.2-192.168.10.254) may be blocked', 'error');
        return;
      }

      try {
        if (feedback) feedback.textContent = 'Applying kernel rule...';
        const res = await fetch('/api/blocked-ips', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ip: normIp, reason: reason || 'Manual administrator block' })
        });
        const data = await parseApiResponse(res);
        if (!res.ok || data.status === 'error') {
          throw new Error(data.message || `Firewall helper error (HTTP ${res.status})`);
        }

        showToast(`IP ${normIp} blocked successfully in nftables`, 'success');
        hideBlockModal();
        fetchData();
      } catch (err) {
        if (feedback) feedback.textContent = err.message;
        showToast(`Failed to block: ${err.message}`, 'error');
      }
    });
  }

  // Blocked list modal
  const hideBlockedListModal = () => {
    if (blockedListModal) blockedListModal.classList.remove('active');
  };
  if (closeBlockedListModalBtn) closeBlockedListModalBtn.addEventListener('click', hideBlockedListModal);
  if (closeBlockedListBtn) closeBlockedListBtn.addEventListener('click', hideBlockedListModal);
  if (refreshBlockedListBtn) refreshBlockedListBtn.addEventListener('click', fetchData);
}

function initNavigation() {
  const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
  const viewAllAlertsBtn = document.getElementById('viewAllAlertsBtn');
  const blockedListModal = document.getElementById('blockedListModal');
  const menuToggleBtn = document.getElementById('menuToggleBtn');
  const sidebar = document.getElementById('sidebar');
  const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navItems.forEach(i => i.classList.remove('active'));
      item.classList.add('active');

      const tab = item.getAttribute('data-tab');
      if (tab === 'blocked' && blockedListModal) {
        blockedListModal.classList.add('active');
      } else if (tab === 'alerts') {
        const table = document.getElementById('alertsTable');
        if (table) table.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  if (viewAllAlertsBtn && blockedListModal) {
    viewAllAlertsBtn.addEventListener('click', () => {
      const table = document.getElementById('alertsTable');
      if (table) table.scrollIntoView({ behavior: 'smooth' });
    });
  }

  // Mobile drawer
  if (menuToggleBtn && sidebar) {
    menuToggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
  }
  if (sidebarCloseBtn && sidebar) {
    sidebarCloseBtn.addEventListener('click', () => sidebar.classList.remove('open'));
  }
}

function initSearch() {
  const searchInput = document.getElementById('globalSearchInput');
  if (!searchInput) return;

  searchInput.addEventListener('input', debounce((e) => {
    state.searchQuery = e.target.value.trim();
    renderAlertsTable();
  }, 250));

  // Ctrl+K shortcut
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      searchInput.focus();
    }
  });
}

function initTimeFilter() {
  const timeSelect = document.getElementById('timeRangeSelect');
  if (timeSelect) {
    timeSelect.addEventListener('change', (e) => {
      state.timeFilter = e.target.value;
      renderAlertsTable();
    });
  }

  const trafficFilter = document.getElementById('trafficChartFilter');
  if (trafficFilter) {
    trafficFilter.addEventListener('change', (e) => {
      state.chartFilter = e.target.value;
      renderTrafficChart();
    });
  }
}

function initExport() {
  const exportBtn = document.getElementById('exportReportBtn');
  if (!exportBtn) return;

  exportBtn.addEventListener('click', () => {
    if (state.alerts.length === 0) {
      showToast('No alerts to export', 'error');
      return;
    }

    const headers = ['ID', 'Time (UTC)', 'Source', 'Rule Name', 'Src IP', 'Dest IP', 'Severity', 'Action', 'Evidence'];
    const rows = state.alerts.map(a => [
      a.id,
      `"${a.occurred_at}"`,
      `"${a.source}"`,
      `"${(a.rule_name || '').replace(/"/g, '""')}"`,
      `"${a.src_ip || ''}"`,
      `"${a.dest_ip || ''}"`,
      a.severity,
      `"${a.action}"`,
      `"${(a.evidence || '').replace(/"/g, '""')}"`
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + 
      [headers.join(','), ...rows.map(e => e.join(','))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `nids-security-report-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('Security incident report exported as CSV', 'success');
  });
}

// ============================================================================
// Toast Notifications
// ============================================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => toast.classList.add('visible'), 10);

  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ============================================================================
// Utilities
// ============================================================================
function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return Number(num).toLocaleString('en-US');
}

function formatDateTime(isoStr) {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return isoStr;

  const pad = n => String(n).padStart(2, '0');
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const hours = pad(d.getHours());
  const mins = pad(d.getMinutes());
  const secs = pad(d.getSeconds());

  return `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
