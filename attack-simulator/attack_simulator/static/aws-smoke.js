'use strict';

function awsCell(row, value) {
  const cell = document.createElement('td');
  cell.textContent = value ?? '—';
  row.append(cell);
}

const awsButton = document.querySelector('#aws-smoke');
const awsMessage = document.querySelector('#aws-message');
const awsResults = document.querySelector('#aws-results');
awsButton.addEventListener('click', async () => {
  awsButton.disabled = true;
  awsMessage.textContent = 'Đang kiểm tra HTTPS…';
  awsResults.replaceChildren();
  try {
    const token = document.querySelector('meta[name="simulator-token"]').content;
    const response = await fetch('/api/aws-smoke', {
      method: 'POST', headers: {'X-Simulator-Token': token},
    });
    const {results, error} = await response.json();
    if (!response.ok) throw new Error(error || `HTTP ${response.status}`);
    for (const result of results) {
      const row = document.createElement('tr');
      awsCell(row, result.name);
      awsCell(row, result.status);
      awsCell(row, result.tls_verified ? 'Hợp lệ' : 'Chưa xác minh');
      awsCell(row, result.request_id);
      awsCell(row, `${result.elapsed_ms} ms`);
      awsCell(row, result.error ?? (result.pass ? 'Đạt' : 'HTTP ngoài dự kiến'));
      awsResults.append(row);
    }
    const count = results.filter(result => result.pass).length;
    awsMessage.textContent = `Đã kiểm tra HTTPS. ${count}/${results.length} website đạt.`;
  } catch (error) {
    awsMessage.textContent = error.message;
  } finally {
    awsButton.disabled = false;
  }
});
