// 全局状态
window.API_BASE = '';
window.currentAccount = null;
window.currentEmailFolder = 'all';
window.currentEmailPage = 1;
window.accounts = [];
window.currentApiKey = null;
window.securityStats = {
    failed_password_attempts: 0,
    failed_api_key_attempts: 0,
    locked_login_ips: [],
    locked_api_key_ips: [],
};

window.accountsCurrentPage = 1;
window.accountsPageSize = 10;
window.accountsTotalPages = 0;
window.accountsTotalCount = 0;
window.accountEmailSearchTerm = '';
window.accountTagSearchTerm = '';

window.allEmails = [];
window.filteredEmails = [];
window.emailSearchTimeout = null;
window.contextMenuTarget = null;

// 工具函数
function formatEmailDate(dateString) {
    try {
        if (!dateString) return '未知时间';

        let date = new Date(dateString);

        if (Number.isNaN(date.getTime())) {
            if (dateString.includes('T') && !dateString.includes('Z') && !dateString.includes('+')) {
                date = new Date(`${dateString}Z`);
            }
            if (Number.isNaN(date.getTime())) {
                return '日期格式错误';
            }
        }

        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }
        if (diffDays === 1) {
            return `昨天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
        }
        if (diffDays < 7) {
            return `${diffDays}天前`;
        }
        if (diffDays < 365) {
            return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
        }
        return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (error) {
        console.error('格式化时间失败:', error);
        return '时间解析失败';
    }
}

function showNotification(message, type = 'info', title = '', duration = 5000) {
    const container = document.getElementById('notificationContainer');
    if (!container) return;

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const titles = {
        success: title || '成功',
        error: title || '错误',
        warning: title || '警告',
        info: title || '提示',
    };

    notification.innerHTML = `
        <div class="notification-icon">${icons[type] || icons.info}</div>
        <div class="notification-content">
            <div class="notification-title">${titles[type]}</div>
            <div class="notification-message">${message}</div>
        </div>
        <button class="notification-close" onclick="closeNotification(this)">×</button>
    `;

    container.appendChild(notification);

    if (duration > 0) {
        setTimeout(() => {
            closeNotification(notification.querySelector('.notification-close'));
        }, duration);
    }
}

function closeNotification(closeBtn) {
    if (!closeBtn) return;
    const notification = closeBtn.closest('.notification');
    if (!notification) return;
    notification.classList.add('slide-out');
    setTimeout(() => notification.remove(), 300);
}

async function apiRequest(url, options = {}) {
    const { skipApiKey = false, useSession = false, ...fetchOptions } = options;
    const headers = { 'Content-Type': 'application/json', ...(fetchOptions.headers || {}) };

    if (!skipApiKey && window.currentApiKey) {
        headers.Authorization = `Key ${window.currentApiKey}`;
    }

    const requestOptions = { ...fetchOptions, headers };
    if (!('credentials' in fetchOptions)) {
        requestOptions.credentials = useSession ? 'include' : 'omit';
    }

    const response = await fetch(window.API_BASE + url, requestOptions);
    let data = null;

    try {
        if (response.status !== 204) {
            data = await response.json();
        }
    } catch (error) {
        // 允许空或非JSON响应
    }

    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('未登录');
    }
    if (response.status === 403) {
        throw new Error((data && data.detail) || '禁止访问');
    }
    if (!response.ok) {
        throw new Error((data && data.detail) || `HTTP ${response.status}`);
    }

    return data ?? {};
}

async function checkSession() {
    await apiRequest('/auth/session', { skipApiKey: true, useSession: true });
}

function setButtonLoading(button, loadingText) {
    if (!button) return;
    if (!button.dataset.originalText) {
        button.dataset.originalText = button.innerHTML;
    }
    button.disabled = true;
    button.innerHTML = `<span>⏳</span> ${loadingText}`;
}

function resetButtonLoading(button) {
    if (!button) return;
    button.disabled = false;
    if (button.dataset.originalText) {
        button.innerHTML = button.dataset.originalText;
        delete button.dataset.originalText;
    }
}

function formatSyncMessage(result, fallbackMessage) {
    if (result && result.message) {
        return result.message;
    }

    if (!result) {
        return fallbackMessage;
    }

    const parts = [];
    const mappings = [
        ['added', '新增'],
        ['updated', '更新'],
        ['marked_deleted', '标记删除'],
        ['removed', '移除'],
        ['skipped', '跳过'],
    ];

    mappings.forEach(([key, label]) => {
        const value = Number(result[key] ?? 0);
        if (!Number.isNaN(value) && value > 0) {
            parts.push(`${label}${value}`);
        }
    });

    return parts.length ? `${fallbackMessage}：${parts.join('，')}` : fallbackMessage;
}

function fallbackCopyText(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.select();
    try {
        document.execCommand('copy');
        showNotification('链接已复制到剪贴板', 'success');
    } catch (err) {
        showNotification('复制失败，请手动复制', 'error');
    }
    document.body.removeChild(textArea);
}

// 将工具函数暴露给其他脚本
window.formatEmailDate = formatEmailDate;
window.showNotification = showNotification;
window.closeNotification = closeNotification;
window.apiRequest = apiRequest;
window.checkSession = checkSession;
window.setButtonLoading = setButtonLoading;
window.resetButtonLoading = resetButtonLoading;
window.formatSyncMessage = formatSyncMessage;
window.fallbackCopyText = fallbackCopyText;
