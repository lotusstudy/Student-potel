// Lotus Academy — shared client-side utilities

// Generic table search
function filterTable(inputId, tableId) {
  const q = document.getElementById(inputId).value.toLowerCase();
  document.querySelectorAll(`#${tableId} tbody tr`).forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

// Show a toast notification
function showToast(msg, ok = true) {
  let t = document.getElementById('toast');
  if (!t) return;
  document.getElementById('toast-msg').textContent = msg;
  t.className = ok ? 'show ok' : 'show err';
  t.querySelector('i').className = ok
    ? 'fas fa-circle-check'
    : 'fas fa-circle-exclamation';
  setTimeout(() => { t.className = ''; }, 4000);
}
