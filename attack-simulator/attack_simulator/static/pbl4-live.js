'use strict';

const liveButton = document.querySelector('#live-canary');
const liveStatus = document.querySelector('#live-status');
const liveAlerts = document.querySelector('#live-alerts');
const liveAlertRows = document.querySelector('#live-alert-rows');
const livePrevention = document.querySelector('#live-prevention');
const liveKey = new URLSearchParams(location.hash.slice(1)).get('live');

if (liveKey) {
  history.replaceState(null, '', `${location.pathname}${location.search}`);
} else {
  liveButton.disabled = true;
  liveStatus.textContent = 'Mở liên kết phiên live đã in trong Terminal.';
}

function liveDetail(label, value) {
  const pair = document.createElement('div');
  const term = document.createElement('dt');
  const detail = document.createElement('dd');
  term.textContent = label;
  detail.textContent = value;
  pair.append(term, detail);
  livePrevention.append(pair);
}

liveButton.addEventListener('click', async () => {
  liveButton.disabled = true;
  liveAlertRows.replaceChildren();
  livePrevention.replaceChildren();
  liveAlerts.hidden = true;
  livePrevention.hidden = true;
  liveStatus.textContent = 'Đang chạy qua SSM. Chờ canary thực thi chặn, gỡ chặn và kiểm tra TTL…';
  try {
    const csrf = document.querySelector('meta[name="simulator-token"]').content;
    const response = await fetch('/api/pbl4-canary', {
      method: 'POST', headers: {'X-Simulator-Token': csrf, 'X-PBL4-Session': liveKey},
    });
    const {result, error} = await response.json();
    if (!response.ok) throw new Error(error || `HTTP ${response.status}`);
    for (const observation of result.observations) {
      const row = document.createElement('tr');
      awsCell(row, `Suricata · SID ${observation.rule_sid}`);
      awsCell(row, observation.request_id);
      awsCell(row, observation.status);
      awsCell(row, observation.source);
      liveAlertRows.append(row);
      liveDetail(observation.source, `Chặn thật · tác vụ Audit #${observation.action_id}`);
    }
    liveDetail('Unblock', `Kết nối đã phục hồi · tác vụ Audit #${result.unblock_id}`);
    liveDetail('TTL', `Tối đa ${result.ttl_seconds} giây · kết nối đã phục hồi`);
    liveDetail('DB và nftables', `${result.db_kernel} · cleanup PASS`);
    liveDetail('Phiên AWS SSM', result.session_id);
    liveAlerts.hidden = false;
    livePrevention.hidden = false;
    liveStatus.textContent = 'Ca trực tiếp hoàn tất.';
  } catch (error) {
    liveStatus.textContent = error.message;
  } finally {
    liveButton.disabled = false;
  }
});
