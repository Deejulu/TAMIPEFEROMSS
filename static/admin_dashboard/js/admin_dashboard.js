(function () {
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie) {
            document.cookie.split(';').some(function (cookie) {
                var trimmedCookie = cookie.trim();
                if (trimmedCookie.substring(0, name.length + 1) === name + '=') {
                    cookieValue = decodeURIComponent(trimmedCookie.substring(name.length + 1));
                    return true;
                }
                return false;
            });
        }
        return cookieValue;
    }

    function updateUnreadBadge(unreadCount) {
        var bell = document.querySelector('.admin-notification-bell');
        if (!bell) {
            return;
        }

        var badge = bell.querySelector('.admin-notification-badge');
        if (unreadCount > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'admin-notification-badge';
                bell.appendChild(badge);
            }
            badge.textContent = unreadCount;
        } else if (badge) {
            badge.remove();
        }
    }

    function markNotificationRead(id, csrfToken) {
        fetch('/admin-dashboard/notifications/' + id + '/mark-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (!data.success) {
                    return;
                }

                updateUnreadBadge(data.unread_count);
                var item = document.querySelector('.notification-item[data-id="' + id + '"]');
                if (item) {
                    item.classList.remove('unread');
                    var message = item.querySelector('.notification-message');
                    if (message) {
                        message.classList.remove('fw-semibold');
                    }
                    var button = item.querySelector('.mark-read-btn');
                    if (button) {
                        button.remove();
                    }
                }
            });
    }

    function markAllNotificationsRead(csrfToken) {
        fetch('/admin-dashboard/notifications/mark-all-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (!data.success) {
                    return;
                }

                updateUnreadBadge(data.unread_count);
                document.querySelectorAll('.notification-item.unread').forEach(function (item) {
                    item.classList.remove('unread');
                    var message = item.querySelector('.notification-message');
                    if (message) {
                        message.classList.remove('fw-semibold');
                    }
                    var button = item.querySelector('.mark-read-btn');
                    if (button) {
                        button.remove();
                    }
                });

                var markAllButton = document.getElementById('markAllReadBtn');
                if (markAllButton) {
                    markAllButton.disabled = true;
                }
            });
    }

    function initializeNotificationControls() {
        var csrfToken = getCookie('csrftoken');
        document.querySelectorAll('.mark-read-btn').forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                markNotificationRead(this.dataset.id, csrfToken);
            });
        });

        var markAllButton = document.getElementById('markAllReadBtn');
        if (markAllButton) {
            markAllButton.addEventListener('click', function () {
                markAllNotificationsRead(csrfToken);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeNotificationControls);
    } else {
        initializeNotificationControls();
    }
}());
