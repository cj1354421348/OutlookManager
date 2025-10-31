function viewAccountEmails(emailId) {
    const targetAccount = (window.accounts || []).find((acc) => acc.email_id === emailId);
    if (targetAccount && targetAccount.status === 'expired') {
        if (typeof window.showExpiredAccountNotice === 'function') {
            window.showExpiredAccountNotice(emailId);
        } else {
            showNotification(`邮箱 ${emailId} 授权已过期，请先重新验证凭据`, 'warning');
        }
        return;
    }

    window.currentAccount = emailId;
    const emailLabel = document.getElementById('currentAccountEmail');
    const emailsNav = document.getElementById('emailsNav');

    if (emailLabel) emailLabel.textContent = emailId;
    if (emailsNav) emailsNav.style.display = 'block';

    clearFilters();
    showPage('emails');
}

function backToAccounts() {
    window.currentAccount = null;
    const emailsNav = document.getElementById('emailsNav');
    if (emailsNav) emailsNav.style.display = 'none';
    showPage('accounts');
}

async function loadEmails(forceRefresh = false) {
    if (!window.currentAccount) return;

    const emailsList = document.getElementById('emailsList');
    const refreshBtn = document.getElementById('refreshBtn');

    if (emailsList) {
        emailsList.innerHTML = '<div class="loading"><div class="loading-spinner"></div>正在加载邮件...</div>';
    }
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span>⏳</span> 加载中...';
    }

    try {
        const refreshParam = forceRefresh ? '&refresh=true' : '';
        const url = `/emails/${window.currentAccount}?folder=${window.currentEmailFolder}&page=${window.currentEmailPage}&page_size=100${refreshParam}`;
        const data = await apiRequest(url);

        if (data && data.from_cache) {
            showNotification('上游网络错误', 'warning');
        }

        window.allEmails = data.emails || [];
        updateEmailStats(window.allEmails);
        applyFilters();

        const lastUpdateLabel = document.getElementById('lastUpdateTime');
        if (lastUpdateLabel) {
            lastUpdateLabel.textContent = new Date().toLocaleString();
        }

        updateEmailsPagination(data.total_emails || window.allEmails.length, data.page_size || 100);

        if (forceRefresh) {
            showNotification('邮件列表已刷新', 'success');
        }
    } catch (error) {
        if (error && typeof error.message === 'string' && error.message.includes('账户授权已过期')) {
            if (emailsList) {
                emailsList.innerHTML = '<div class="error">邮箱授权已过期，请返回账户列表重新验证</div>';
            }
            showNotification('邮箱授权已过期，请重新验证凭据', 'warning');
            setTimeout(() => backToAccounts(), 400);
        } else {
            if (emailsList) {
                emailsList.innerHTML = `<div class="error">❌ 加载失败: ${error.message}</div>`;
            }
            showNotification(`加载邮件失败: ${error.message}`, 'error');
        }
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<span>🔄</span> 刷新';
        }
    }
}

function updateEmailStats(emails) {
    const total = emails.length;
    const unread = emails.filter((email) => !email.is_read).length;
    const todayCount = emails.filter((email) => {
        const emailDate = new Date(email.date);
        const today = new Date();
        return emailDate.toDateString() === today.toDateString();
    }).length;
    const withAttachments = emails.filter((email) => email.has_attachments).length;

    const totalEl = document.getElementById('totalEmailCount');
    const unreadEl = document.getElementById('unreadEmailCount');
    const todayEl = document.getElementById('todayEmailCount');
    const attachmentEl = document.getElementById('attachmentEmailCount');

    if (totalEl) totalEl.textContent = total;
    if (unreadEl) unreadEl.textContent = unread;
    if (todayEl) todayEl.textContent = todayCount;
    if (attachmentEl) attachmentEl.textContent = withAttachments;
}

function searchEmails() {
    clearTimeout(window.emailSearchTimeout);
    window.emailSearchTimeout = setTimeout(() => applyFilters(), 300);
}

function applyFilters() {
    const searchInput = document.getElementById('emailSearchInput');
    const folderFilter = document.getElementById('folderFilter');
    const statusFilter = document.getElementById('statusFilter');
    const timeFilter = document.getElementById('timeFilter');
    const attachmentFilter = document.getElementById('attachmentFilter');

    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const folderValue = folderFilter ? folderFilter.value : 'all';
    const statusValue = statusFilter ? statusFilter.value : 'all';
    const timeValue = timeFilter ? timeFilter.value : 'all';
    const attachmentValue = attachmentFilter ? attachmentFilter.value : 'all';

    window.filteredEmails = window.allEmails.filter((email) => {
        if (searchTerm) {
            const searchableText = `${email.subject || ''} ${email.from_email || ''}`.toLowerCase();
            if (!searchableText.includes(searchTerm)) {
                return false;
            }
        }

        if (folderValue !== 'all' && email.folder.toLowerCase() !== folderValue) {
            return false;
        }

        if (statusValue === 'read' && !email.is_read) return false;
        if (statusValue === 'unread' && email.is_read) return false;

        if (timeValue !== 'all') {
            const emailDate = new Date(email.date);
            const now = new Date();
            if (timeValue === 'today' && emailDate.toDateString() !== now.toDateString()) return false;
            if (timeValue === 'week') {
                const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                if (emailDate < weekAgo) return false;
            }
            if (timeValue === 'month') {
                const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
                if (emailDate < monthAgo) return false;
            }
        }

        if (attachmentValue === 'with' && !email.has_attachments) return false;
        if (attachmentValue === 'without' && email.has_attachments) return false;

        return true;
    });

    renderFilteredEmails();
}

function renderFilteredEmails() {
    const emailsList = document.getElementById('emailsList');
    if (!emailsList) return;

    if (window.filteredEmails.length === 0) {
        emailsList.innerHTML = '<div class="text-center" style="padding: 40px; color: #64748b;">没有找到匹配的邮件</div>';
        return;
    }

    emailsList.innerHTML = window.filteredEmails.map(createEmailItem).join('');
}

function clearFilters() {
    const searchInput = document.getElementById('emailSearchInput');
    const folderFilter = document.getElementById('folderFilter');
    const statusFilter = document.getElementById('statusFilter');
    const timeFilter = document.getElementById('timeFilter');
    const attachmentFilter = document.getElementById('attachmentFilter');

    if (searchInput) searchInput.value = '';
    if (folderFilter) folderFilter.value = 'all';
    if (statusFilter) statusFilter.value = 'all';
    if (timeFilter) timeFilter.value = 'all';
    if (attachmentFilter) attachmentFilter.value = 'all';

    window.filteredEmails = [...window.allEmails];
    renderFilteredEmails();
}

function createEmailItem(email) {
    const unreadClass = email.is_read ? '' : 'unread';
    const attachmentIcon = email.has_attachments ? '<span style="color: #8b5cf6;">📎</span>' : '';
    const readIcon = email.is_read ? '📖' : '📧';

    return `
        <div class="email-item ${unreadClass}" onclick="showEmailDetail('${email.message_id}')">
            <div class="email-avatar">${email.sender_initial}</div>
            <div class="email-content">
                <div class="email-header">
                    <div class="email-subject">${email.subject || '(无主题)'}</div>
                    <div class="email-date">${formatEmailDate(email.date)}</div>
                </div>
                <div class="email-from">${readIcon} ${email.from_email} ${attachmentIcon}</div>
                <div class="email-preview">文件夹: ${email.folder} | 点击查看详情</div>
            </div>
        </div>
    `;
}

async function showEmailDetail(messageId) {
    const modal = document.getElementById('emailModal');
    const title = document.getElementById('emailModalTitle');
    const content = document.getElementById('emailModalContent');

    if (!modal || !title || !content) return;

    modal.classList.remove('hidden');
    title.textContent = '邮件详情';
    content.innerHTML = '<div class="loading">正在加载邮件详情...</div>';

    try {
        const data = await apiRequest(`/emails/${window.currentAccount}/${messageId}`);

        if (data && data.from_cache) {
            showNotification('上游网络错误', 'warning');
        }

        title.textContent = data.subject || '(无主题)';
        content.innerHTML = `
            <div class="email-detail-meta">
                <p><strong>发件人:</strong> ${data.from_email}</p>
                <p><strong>收件人:</strong> ${data.to_email}</p>
                <p><strong>日期:</strong> ${formatEmailDate(data.date)} (${new Date(data.date).toLocaleString()})</p>
                <p><strong>邮件ID:</strong> ${data.message_id}</p>
            </div>
            ${renderEmailContent(data)}
        `;
    } catch (error) {
        content.innerHTML = `<div class="error">加载失败: ${error.message}</div>`;
    }
}

function renderEmailContent(email) {
    const hasHtml = email.body_html && email.body_html.trim();
    const hasPlain = email.body_plain && email.body_plain.trim();

    if (!hasHtml && !hasPlain) {
        return '<p style="color: #9ca3af; font-style: italic;">此邮件无内容</p>';
    }

    if (hasHtml) {
        const sanitizedHtml = email.body_html.replace(/"/g, '&quot;');
        const rawHtml = email.body_html.replace(/</g, '&lt;').replace(/>/g, '&gt;');

        return `
            <div class="email-content-tabs">
                <button class="content-tab active" onclick="showEmailContentTab('html', this)">HTML视图</button>
                ${hasPlain ? '<button class="content-tab" onclick="showEmailContentTab(\'plain\', this)">纯文本</button>' : ''}
                <button class="content-tab" onclick="showEmailContentTab('raw', this)">源码</button>
            </div>
            <div class="email-content-body">
                <div id="htmlContent">
                    <iframe srcdoc="${sanitizedHtml}" style="width: 100%; min-height: 400px; border: none;" sandbox="allow-same-origin"></iframe>
                </div>
                ${hasPlain ? `<div id="plainContent" class="hidden"><pre>${email.body_plain}</pre></div>` : ''}
                <div id="rawContent" class="hidden"><pre style="background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 12px;">${rawHtml}</pre></div>
            </div>
        `;
    }

    return `<div class="email-content-body"><pre>${email.body_plain}</pre></div>`;
}

function showEmailContentTab(type, trigger) {
    document.querySelectorAll('.content-tab').forEach((tab) => tab.classList.remove('active'));
    if (trigger) trigger.classList.add('active');

    ['htmlContent', 'plainContent', 'rawContent'].forEach((id) => {
        const element = document.getElementById(id);
        if (!element) return;
        if (id === `${type}Content`) {
            element.classList.remove('hidden');
        } else {
            element.classList.add('hidden');
        }
    });
}

function closeEmailModal() {
    const modal = document.getElementById('emailModal');
    if (modal) modal.classList.add('hidden');
}

function refreshEmails() {
    loadEmails(true);
}

async function clearCache() {
    if (!window.currentAccount) return;
    try {
        await apiRequest(`/cache/${window.currentAccount}`, { method: 'DELETE' });
        showNotification('缓存已清除', 'success');
        loadEmails(true);
    } catch (error) {
        showNotification(`清除缓存失败: ${error.message}`, 'error');
    }
}

function exportEmails() {
    if (!window.filteredEmails || window.filteredEmails.length === 0) {
        showNotification('没有邮件可导出', 'warning');
        return;
    }

    const csvContent = generateEmailCSV(window.filteredEmails);
    const fileName = `emails_${window.currentAccount}_${new Date().toISOString().split('T')[0]}.csv`;
    downloadCSV(csvContent, fileName);
    showNotification(`已导出 ${window.filteredEmails.length} 封邮件`, 'success');
}

function generateEmailCSV(emails) {
    const headers = ['主题', '发件人', '日期', '文件夹', '是否已读', '是否有附件'];
    const rows = emails.map((email) => [
        `"${(email.subject || '').replace(/"/g, '""')}"`,
        `"${(email.from_email || '').replace(/"/g, '""')}"`,
        `"${email.date}"`,
        `"${email.folder}"`,
        email.is_read ? '已读' : '未读',
        email.has_attachments ? '有附件' : '无附件',
    ]);

    return [headers, ...rows].map((row) => row.join(',')).join('\n');
}

function downloadCSV(content, filename) {
    const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function updateEmailsPagination(totalEmails, pageSize) {
    const pagination = document.getElementById('emailsPagination');
    if (!pagination) return;

    const totalPages = Math.max(1, Math.ceil(totalEmails / pageSize));
    if (totalPages <= 1) {
        pagination.classList.add('hidden');
        pagination.innerHTML = '';
        return;
    }

    pagination.classList.remove('hidden');
    pagination.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="changeEmailPage(${window.currentEmailPage - 1})" ${window.currentEmailPage === 1 ? 'disabled' : ''}>‹ 上一页</button>
        <span style="padding: 0 16px; color: #64748b;">${window.currentEmailPage} / ${totalPages}</span>
        <button class="btn btn-secondary btn-sm" onclick="changeEmailPage(${window.currentEmailPage + 1})" ${window.currentEmailPage === totalPages ? 'disabled' : ''}>下一页 ›</button>
    `;
}

function changeEmailPage(page) {
    window.currentEmailPage = Math.max(1, page);
    loadEmails();
}

function showEmailsContextMenu(event) {
    if (!window.currentAccount) return;
    event.preventDefault();
    event.stopPropagation();
    const url = `${window.location.origin}/#/emails/${encodeURIComponent(window.currentAccount)}`;
    window.open(url, '_blank');
}

function copyEmailAddress(emailAddress) {
    const cleanEmail = (emailAddress || '').trim();
    if (!cleanEmail) {
        showNotification('邮箱地址为空', 'error');
        return;
    }

    navigator.clipboard.writeText(cleanEmail)
        .then(() => {
            showNotification(`邮箱地址已复制: ${cleanEmail}`, 'success');
            const emailElement = document.getElementById('currentAccountEmail');
            if (emailElement) {
                emailElement.classList.add('copy-success');
                setTimeout(() => emailElement.classList.remove('copy-success'), 300);
            }
        })
        .catch(() => {
            showNotification('复制失败，请手动复制邮箱地址', 'error');
        });
}

// 事件绑定
const emailModal = document.getElementById('emailModal');
if (emailModal) {
    emailModal.addEventListener('click', (event) => {
        if (event.target === emailModal) {
            closeEmailModal();
        }
    });
}

document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'r' && window.currentAccount) {
        event.preventDefault();
        refreshEmails();
    }

    if (event.key === 'Escape') {
        closeEmailModal();
    }

    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
        const searchInput = document.getElementById('emailSearchInput');
        if (searchInput) {
            event.preventDefault();
            searchInput.focus();
        }
    }
});

document.addEventListener('visibilitychange', () => {
    if (document.hidden || !window.currentAccount) return;

    const lastUpdateLabel = document.getElementById('lastUpdateTime');
    if (!lastUpdateLabel) return;

    const lastUpdateText = lastUpdateLabel.textContent;
    if (!lastUpdateText || lastUpdateText === '-') return;

    const lastUpdate = new Date(lastUpdateText);
    if (Number.isNaN(lastUpdate.getTime())) return;

    const now = new Date();
    const diffMinutes = (now - lastUpdate) / (1000 * 60);

    if (diffMinutes > 5) {
        showNotification('检测到数据可能过期，正在刷新...', 'info', '', 2000);
        setTimeout(() => refreshEmails(), 1000);
    }
});

window.viewAccountEmails = viewAccountEmails;
window.backToAccounts = backToAccounts;
window.loadEmails = loadEmails;
window.switchEmailTab = (folder, trigger) => {
    window.currentEmailFolder = folder;
    window.currentEmailPage = 1;

    document.querySelectorAll('#emailsPage .tab').forEach((tab) => tab.classList.remove('active'));
    if (trigger) {
        trigger.classList.add('active');
    }

    loadEmails();
};
window.searchEmails = searchEmails;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;
window.showEmailDetail = showEmailDetail;
window.showEmailContentTab = showEmailContentTab;
window.closeEmailModal = closeEmailModal;
window.refreshEmails = refreshEmails;
window.clearCache = clearCache;
window.exportEmails = exportEmails;
window.changeEmailPage = changeEmailPage;
window.showEmailsContextMenu = showEmailsContextMenu;
window.copyEmailAddress = copyEmailAddress;
