/* ====
   RMG Mission Control — JavaScript
   ==== */

// --- Countdown Timer ---
function updateCountdown() {
    const deadline = new Date('2026-02-20T17:00:00-05:00');
    const now = new Date();
    const diff = deadline - now;

    if (diff <= 0) {
        document.getElementById('countdown').textContent = 'DEADLINE PASSED';
        document.getElementById('countdown').style.color = '#dc3545';
        return;
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    const el = document.getElementById('countdown');
    if (el) {
        el.textContent = `${days}d ${hours}h ${minutes}m ${seconds}s remaining`;
        if (days <= 1) {
            el.style.color = '#dc3545';
            el.style.fontWeight = '900';
        } else if (days <= 3) {
            el.style.color = '#ffc107';
        }
    }
}

// Run countdown every second
if (document.getElementById('countdown')) {
    updateCountdown();
    setInterval(updateCountdown, 1000);
}

// --- Mark Notification Read (AJAX) ---
document.querySelectorAll('form[action*="notifications/read/"]').forEach(form => {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        fetch(this.action, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.json())
            .then(data => {
                if (data.ok) {
                    this.closest('.list-group-item').classList.remove('list-group-item-light');
                    this.remove();
                    // Update badge count
                    const badge = document.querySelector('.notification-badge');
                    if (badge) {
                    const count = parseInt(badge.textContent) - 1;
                    if (count <= 0) badge.remove();
                    else badge.textContent = count;
                    }
                }
            });
    });
});

// --- Mark All Read (AJAX) ---
document.querySelectorAll('form[action*="notifications/read-all"]').forEach(form => {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        fetch(this.action, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.json())
            .then(data => {
                if (data.ok) {
                    document.querySelectorAll('.list-group-item-light').forEach(el => {
                    el.classList.remove('list-group-item-light');
                    });
                    const badge = document.querySelector('.notification-badge');
                    if (badge) badge.remove();
                }
            });
    });
});

// --- Auto-dismiss alerts after 5 seconds ---
document.querySelectorAll('.alert-dismissible').forEach(alert => {
    setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        bsAlert.close();
    }, 5000);
});

// --- Tooltip initialization ---
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
tooltipTriggerList.forEach(function (el) {
    new bootstrap.Tooltip(el);
});
