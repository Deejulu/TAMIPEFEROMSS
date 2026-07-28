document.addEventListener('DOMContentLoaded', function() {
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    function markAsRead(id) {
        fetch('/admin-dashboard/notifications/' + id + '/mark-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const item = document.querySelector('.notification-item[data-id="' + id + '"]');
                if (item) {
                    item.classList.remove('unread');
                    const msg = item.querySelector('.notification-message');
                    if (msg) msg.classList.remove('fw-semibold');
                    const btn = item.querySelector('.mark-read-btn');
                    if (btn) btn.remove();
                }
            }
        })
        .catch(() => {});
    }

    function markAllRead() {
        fetch('/admin-dashboard/notifications/mark-all-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.querySelectorAll('.notification-item.unread').forEach(item => {
                    item.classList.remove('unread');
                    const msg = item.querySelector('.notification-message');
                    if (msg) msg.classList.remove('fw-semibold');
                    const btn = item.querySelector('.mark-read-btn');
                    if (btn) btn.remove();
                });
                const btn = document.getElementById('markAllReadBtn');
                if (btn) btn.disabled = true;
            }
        })
        .catch(() => {});
    }

    document.querySelectorAll('.mark-read-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            markAsRead(this.dataset.id);
        });
    });

    const markAllBtn = document.getElementById('markAllReadBtn');
    if (markAllBtn) {
        markAllBtn.addEventListener('click', function() {
            markAllRead();
        });
    }
});
