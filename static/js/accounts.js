window.currentEditAccount = null;
window.currentEditTags = [];
window.currentNoteAccount = null;

const ACCOUNT_STATUS_META = {
    active: { label: '正常', badgeClass: 'status-badge status-active' },
    invalid: { label: '配置缺失', badgeClass: 'status-badge status-invalid' },
    expired: { label: '授权过期', badgeClass: 'status-badge status-expired' },
};

function clearAddAccountForm() {
    const emailInput = document.getElementById('email');
    const refreshInput = document.getElementById('refreshToken');
    const clientInput = document.getElementById('clientId');
    const tagInput = document.getElementById('accountTags');

    if (emailInput) emailInput.value = '';
    if (refreshInput) refreshInput.value = '';
    if (clientInput) clientInput.value = '';
    if (tagInput) tagInput.value = '';
}

function clearBatchForm() {
    const batchInput = document.getElementById('batchAccounts');
    if (batchInput) batchInput.value = '';
}

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function validateBatchFormat() {
    const batchInput = document.getElementById('batchAccounts');
    if (!batchInput) return;

    const batchText = batchInput.value.trim();
    if (!batchText) {
        showNotification('请先输入账户信息', 'warning');
        return;
    }

    const lines = batchText.split('\n').filter((line) => line.trim());
    let validCount = 0;
    const invalidLines = [];

    lines.forEach((line, index) => {
        const parts = line.split('----').map((p) => p.trim());
        if (parts.length === 4 && parts.every((part) => part.length > 0)) {
            validCount += 1;
        } else {
            invalidLines.push(index + 1);
        }
    });

    if (invalidLines.length === 0) {
        showNotification(`格式验证通过！共 ${validCount} 个有效账户`, 'success');
    } else {
        showNotification(`发现 ${invalidLines.length} 行格式错误：第 ${invalidLines.join(', ')} 行`, 'error');
    }
}

async function loadAccounts(page = 1, resetSearch = false) {
    if (resetSearch) {
        window.accountEmailSearchTerm = '';
        window.accountTagSearchTerm = '';
        const emailSearchInput = document.getElementById('accountEmailSearch');
        const tagSearchInput = document.getElementById('tagSearch');
        if (emailSearchInput) emailSearchInput.value = '';
        if (tagSearchInput) tagSearchInput.value = '';
        page = 1;
    }

    window.accountsCurrentPage = page;

    const accountsList = document.getElementById('accountsList');
    const statsBlock = document.getElementById('accountsStats');
    const pagination = document.getElementById('accountsPagination');

    if (accountsList) {
        accountsList.innerHTML = '<div class="loading"><div class="loading-spinner"></div>正在加载账户列表...</div>';
    }
    if (statsBlock) statsBlock.style.display = 'none';
    if (pagination) pagination.style.display = 'none';

    try {
        const params = new URLSearchParams({
            page: window.accountsCurrentPage,
            page_size: window.accountsPageSize,
            include_expired: 'true',
        });

        if (window.accountEmailSearchTerm) {
            params.append('email_search', window.accountEmailSearchTerm);
        }
        if (window.accountTagSearchTerm) {
            params.append('tag_search', window.accountTagSearchTerm);
        }

        const data = await apiRequest(`/accounts?${params.toString()}`);

        window.accounts = data.accounts || [];
        window.accountsTotalCount = data.total_accounts || 0;
        window.accountsTotalPages = data.total_pages || 0;

        updateAccountsStats();

        if (!accountsList) return;

        if (window.accounts.length === 0) {
            accountsList.innerHTML = '<div class="text-center" style="padding: 40px; color: #64748b;">暂无符合条件的账户</div>';
            return;
        }

        accountsList.innerHTML = window.accounts.map(createAccountItem).join('');
        updateAccountsPagination();
    } catch (error) {
        if (accountsList) {
            accountsList.innerHTML = `<div class="error">加载失败: ${error.message}</div>`;
        }
    }
}

function createAccountItem(account) {
    const safeEmail = account.email_id.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const tags = account.tags || [];
    const tagsHtml = tags.length
        ? `<div class="account-tags">${tags.map((tag) => `<span class="account-tag">${tag}</span>`).join('')}</div>`
        : '';
    const tagsPayload = JSON.stringify(tags).replace(/"/g, '&quot;');
    const notePayload = JSON.stringify(account.note ?? null).replace(/"/g, '&quot;');
    const statusInfo = ACCOUNT_STATUS_META[account.status] || ACCOUNT_STATUS_META.active;
    const isExpired = account.status === 'expired';
    const statusBadge = `<span class="${statusInfo.badgeClass}">${statusInfo.label}</span>`;
    const itemClasses = `account-item${isExpired ? ' account-item-expired' : ''}`;
    const viewButtonAction = isExpired
        ? `showExpiredAccountNotice('${safeEmail}')`
        : `viewAccountEmails('${safeEmail}')`;
    const viewButtonContent = isExpired ? '<span>⚠️</span> 授权过期' : '<span>📧</span> 查看邮件';
    const resetButtonHtml = isExpired
        ? `<button class="btn btn-warning btn-sm" onclick="resetAccountStatus('${safeEmail}')" title="重置状态为正常 (Reset Status)"><span>🔄</span> 重置状态</button>`
        : '';
    let notePreview = '';
    if (typeof account.note === 'string' && account.note.trim()) {
        const normalisedNote = account.note.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        const previewSource = normalisedNote.replace(/\s+/g, ' ').trim();
        const maxPreviewLength = 80;
        const truncated = previewSource.length > maxPreviewLength
            ? `${previewSource.slice(0, maxPreviewLength).trimEnd()}…`
            : previewSource;
        const titleAttr = escapeHtml(normalisedNote).replace(/\n/g, '&#10;');
        notePreview = `<p class="account-note" title="${titleAttr}">${escapeHtml(truncated)}</p>`;
    }

    return `
        <div class="${itemClasses}" onclick="${viewButtonAction}" oncontextmenu="showAccountContextMenu(event, '${safeEmail}')">
            <div class="account-info">
                <div class="account-avatar">${safeEmail.charAt(0).toUpperCase()}</div>
                <div class="account-details">
                    <h4>${safeEmail}</h4>
                    <p class="account-status">状态: ${statusBadge}</p>
                    ${tagsHtml}
                    ${notePreview}
                </div>
            </div>
            <div class="account-actions" onclick="event.stopPropagation()">
                <button class="btn btn-primary btn-sm" onclick="${viewButtonAction}">
                    ${viewButtonContent}
                </button>
                ${resetButtonHtml}
                <button class="btn btn-secondary btn-sm" onclick="editAccountTags('${safeEmail}', ${tagsPayload})">
                    <span>🏷️</span>
                    管理标签
                </button>
                <button class="btn btn-secondary btn-sm" onclick="editAccountNote('${safeEmail}', ${notePayload})">
                    <span>📝</span>
                    备注
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteAccount('${safeEmail}')">
                    <span>🗑️</span>
                    删除
                </button>
            </div>
        </div>
    `;
}

function updateAccountsStats() {
    const statsBlock = document.getElementById('accountsStats');
    const totalSpan = document.getElementById('totalAccounts');
    const pageSpan = document.getElementById('currentPage');
    const sizeSpan = document.getElementById('pageSize');

    if (totalSpan) totalSpan.textContent = window.accountsTotalCount;
    if (pageSpan) pageSpan.textContent = window.accountsCurrentPage;
    if (sizeSpan) sizeSpan.textContent = window.accountsPageSize;
    if (statsBlock) statsBlock.style.display = window.accountsTotalCount > 0 ? 'block' : 'none';
}

function updateAccountsPagination() {
    const pagination = document.getElementById('accountsPagination');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    const pageNumbers = document.getElementById('pageNumbers');

    if (!pagination || !prevBtn || !nextBtn || !pageNumbers) return;

    if (window.accountsTotalPages <= 1) {
        pagination.style.display = 'none';
        return;
    }

    pagination.style.display = 'flex';
    prevBtn.disabled = window.accountsCurrentPage <= 1;
    nextBtn.disabled = window.accountsCurrentPage >= window.accountsTotalPages;
    pageNumbers.innerHTML = generatePageNumbers();
}

function generatePageNumbers() {
    const maxVisiblePages = 5;
    let startPage = Math.max(1, window.accountsCurrentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(window.accountsTotalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    let html = '';

    if (startPage > 1) {
        html += `<span class="page-number" onclick="changePage(1)">1</span>`;
        if (startPage > 2) {
            html += '<span class="page-number disabled">...</span>';
        }
    }

    for (let i = startPage; i <= endPage; i += 1) {
        const activeClass = i === window.accountsCurrentPage ? 'active' : '';
        html += `<span class="page-number ${activeClass}" onclick="changePage(${i})">${i}</span>`;
    }

    if (endPage < window.accountsTotalPages) {
        if (endPage < window.accountsTotalPages - 1) {
            html += '<span class="page-number disabled">...</span>';
        }
        html += `<span class="page-number" onclick="changePage(${window.accountsTotalPages})">${window.accountsTotalPages}</span>`;
    }

    return html;
}

function changePage(direction) {
    let newPage = window.accountsCurrentPage;
    if (direction === 'prev') {
        newPage = Math.max(1, window.accountsCurrentPage - 1);
    } else if (direction === 'next') {
        newPage = Math.min(window.accountsTotalPages, window.accountsCurrentPage + 1);
    } else {
        newPage = Number(direction);
    }

    if (Number.isNaN(newPage) || newPage === window.accountsCurrentPage) {
        return;
    }

    if (newPage >= 1 && newPage <= window.accountsTotalPages) {
        loadAccounts(newPage);
    }
}

function searchAccounts() {
    const emailSearchInput = document.getElementById('accountEmailSearch');
    const tagSearchInput = document.getElementById('tagSearch');

    window.accountEmailSearchTerm = emailSearchInput ? emailSearchInput.value.trim() : '';
    window.accountTagSearchTerm = tagSearchInput ? tagSearchInput.value.trim() : '';

    loadAccounts(1);
}

function clearSearch() {
    const emailSearchInput = document.getElementById('accountEmailSearch');
    const tagSearchInput = document.getElementById('tagSearch');

    if (emailSearchInput) emailSearchInput.value = '';
    if (tagSearchInput) tagSearchInput.value = '';

    window.accountEmailSearchTerm = '';
    window.accountTagSearchTerm = '';
    loadAccounts(1);
}

function handleSearchKeyPress(event) {
    if (event.key === 'Enter') {
        searchAccounts();
    }
}

async function syncAccountsToServer(button) {
    const target = button || document.getElementById('syncToServerBtn');
    setButtonLoading(target, '推送中...');
    try {
        const result = await apiRequest('/accounts/sync/push', { method: 'POST' });
        showNotification(formatSyncMessage(result, '推送完成'), 'success');
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`同步到服务器失败: ${error.message}`, 'error');
    } finally {
        resetButtonLoading(target);
    }
}

async function syncAccountsFromServer(button) {
    const target = button || document.getElementById('syncFromServerBtn');
    setButtonLoading(target, '拉取中...');
    try {
        const result = await apiRequest('/accounts/sync/pull', { method: 'POST' });
        showNotification(formatSyncMessage(result, '拉取完成'), 'success');
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`从服务器同步失败: ${error.message}`, 'error');
    } finally {
        resetButtonLoading(target);
    }
}

async function addAccount() {
    const emailInput = document.getElementById('email');
    const refreshInput = document.getElementById('refreshToken');
    const clientInput = document.getElementById('clientId');
    const tagsInput = document.getElementById('accountTags');

    const email = emailInput ? emailInput.value.trim() : '';
    const refreshToken = refreshInput ? refreshInput.value.trim() : '';
    const clientId = clientInput ? clientInput.value.trim() : '';
    const tags = tagsInput && tagsInput.value.trim()
        ? tagsInput.value.split(',').map((tag) => tag.trim()).filter(Boolean)
        : [];

    if (!email || !refreshToken || !clientId) {
        showNotification('请填写所有必填字段', 'warning');
        return;
    }

    const addBtn = document.getElementById('addAccountBtn');
    if (addBtn) {
        addBtn.disabled = true;
        addBtn.innerHTML = '<span>⏳</span> 添加中...';
    }

    try {
        const response = await apiRequest('/accounts', {
            method: 'POST',
            body: JSON.stringify({
                email,
                refresh_token: refreshToken,
                client_id: clientId,
                tags,
            }),
        });

        showNotification(response?.message || '账户添加成功', 'success');
        clearAddAccountForm();
        showPage('accounts');
        loadAccounts(1, true);
    } catch (error) {
        showNotification(`添加账户失败: ${error.message}`, 'error');
    } finally {
        if (addBtn) {
            addBtn.disabled = false;
            addBtn.innerHTML = '<span>➕</span> 添加账户';
        }
    }
}

async function batchAddAccounts() {
    const batchInput = document.getElementById('batchAccounts');
    if (!batchInput) return;

    const batchText = batchInput.value.trim();
    if (!batchText) {
        showNotification('请输入账户信息', 'warning');
        return;
    }

    const lines = batchText.split('\n').filter((line) => line.trim());
    if (lines.length === 0) {
        showNotification('没有有效的账户信息', 'warning');
        return;
    }

    showBatchProgress();
    const batchBtn = document.getElementById('batchAddBtn');
    if (batchBtn) {
        batchBtn.disabled = true;
        batchBtn.innerHTML = '<span>⏳</span> 添加中...';
    }

    let successCount = 0;
    let failCount = 0;
    const results = [];

    for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i];
        const parts = line.split('----').map((p) => p.trim());

        updateBatchProgress(i + 1, lines.length, `处理第 ${i + 1} 个账户...`);

        if (parts.length !== 4) {
            failCount += 1;
            results.push({
                email: parts[0] || '格式错误',
                status: 'error',
                message: '格式错误：需包含4列 (邮箱----密码----[Token/ClientID]----[Token/ClientID])',
            });
            continue;
        }

        // Auto-detect format based on client_id length (UUID = 36 chars)
        const p3 = parts[2];
        const p4 = parts[3];
        let refreshToken, clientId;

        if (p3.length === 36 && p4.length > 36) {
            // Format: email----pass----client_id----refresh_token
            clientId = p3;
            refreshToken = p4;
        } else {
            // Format: email----pass----refresh_token----client_id (Default)
            refreshToken = p3;
            clientId = p4;
        }

        const email = parts[0];

        try {
            await apiRequest('/accounts', {
                method: 'POST',
                body: JSON.stringify({
                    email,
                    refresh_token: refreshToken,
                    client_id: clientId,
                }), // tags removed from body as it is not in the destructuring
            });
            successCount += 1;
            results.push({ email, status: 'success', message: '添加成功' });
        } catch (error) {
            failCount += 1;
            results.push({ email, status: 'error', message: error.message });
        }

        await new Promise((resolve) => setTimeout(resolve, 100));
    }

    updateBatchProgress(lines.length, lines.length, '批量添加完成！');
    showBatchResults(results);

    if (successCount > 0) {
        showNotification(`批量添加完成！成功 ${successCount} 个，失败 ${failCount} 个`, 'success');
        if (failCount === 0) {
            setTimeout(() => {
                clearBatchForm();
                showPage('accounts');
            }, 3000);
        }
        loadAccounts(1, true);
    } else {
        showNotification('所有账户添加失败，请检查账户信息', 'error');
    }

    if (batchBtn) {
        batchBtn.disabled = false;
        batchBtn.innerHTML = '<span>📦</span> 开始批量添加';
    }
}

function showBatchProgress() {
    const progress = document.getElementById('batchProgress');
    const results = document.getElementById('batchResults');
    if (progress) progress.classList.remove('hidden');
    if (results) results.classList.add('hidden');
}

function hideBatchProgress() {
    const progress = document.getElementById('batchProgress');
    const results = document.getElementById('batchResults');
    if (progress) progress.classList.add('hidden');
    if (results) results.classList.add('hidden');
}

function updateBatchProgress(current, total, message) {
    const fill = document.getElementById('batchProgressFill');
    const text = document.getElementById('batchProgressText');
    const count = document.getElementById('batchProgressCount');

    const percentage = Math.min(100, (current / total) * 100);
    if (fill) fill.style.width = `${percentage}%`;
    if (text) text.textContent = message;
    if (count) count.textContent = `${current} / ${total}`;
}

function showBatchResults(results) {
    const resultsContainer = document.getElementById('batchResultsList');
    const resultsBlock = document.getElementById('batchResults');
    if (!resultsContainer || !resultsBlock) return;

    const successResults = results.filter((r) => r.status === 'success');
    const errorResults = results.filter((r) => r.status === 'error');

    let html = '';

    if (successResults.length > 0) {
        html += '<div style="margin-bottom: 16px;">'
            + '<h5 style="color: #16a34a; margin-bottom: 8px;">✅ 成功添加 (' + successResults.length + ')</h5>'
            + '<div style="background: #f0fdf4; padding: 12px; border-radius: 6px; border: 1px solid #bbf7d0;">'
            + successResults.map((result) => `<div style="font-size: 0.875rem; color: #15803d; margin-bottom: 4px;">• ${result.email}</div>`).join('')
            + '</div></div>';
    }

    if (errorResults.length > 0) {
        html += '<div>'
            + '<h5 style="color: #dc2626; margin-bottom: 8px;">❌ 添加失败 (' + errorResults.length + ')</h5>'
            + '<div style="background: #fef2f2; padding: 12px; border-radius: 6px; border: 1px solid #fecaca;">'
            + errorResults.map((result) => `
                <div style="font-size: 0.875rem; color: #dc2626; margin-bottom: 8px;">
                    <strong>• ${result.email}</strong><br>
                    <span style="color: #991b1b; font-size: 0.75rem;">&nbsp;&nbsp;${result.message}</span>
                </div>`).join('')
            + '</div></div>';
    }

    resultsContainer.innerHTML = html || '<div class="text-sm" style="color: #64748b;">暂无结果</div>';
    resultsBlock.classList.remove('hidden');
}

function editAccountTags(emailId, tags) {
    window.contextMenuTarget = emailId;
    window.currentEditAccount = emailId;
    window.currentEditTags = Array.isArray(tags) ? [...tags] : [];

    const title = document.querySelector('#tagsModal .modal-header h3');
    if (title) {
        title.textContent = `管理 ${emailId} 的标签`;
    }

    renderCurrentTags();
    const modal = document.getElementById('tagsModal');
    if (modal) {
        modal.style.display = 'flex';
    }
}

function renderCurrentTags() {
    const tagsList = document.getElementById('currentTagsList');
    if (!tagsList) return;

    if (!window.currentEditTags || window.currentEditTags.length === 0) {
        tagsList.innerHTML = '<p class="text-sm" style="color: #64748b;">暂无标签</p>';
        return;
    }

    tagsList.innerHTML = window.currentEditTags
        .map((tag) => `
            <div class="tag-item">
                <span class="tag-name">${tag}</span>
                <button class="tag-delete" onclick="removeTag('${tag.replace(/'/g, '&#39;')}')">×</button>
            </div>
        `)
        .join('');
}

function addTag() {
    const newTagInput = document.getElementById('newTag');
    const newTag = newTagInput ? newTagInput.value.trim() : '';

    if (!newTag) {
        showNotification('标签名称不能为空', 'warning');
        return;
    }

    if (window.currentEditTags.includes(newTag)) {
        showNotification('标签已存在', 'warning');
        return;
    }

    window.currentEditTags.push(newTag);
    if (newTagInput) newTagInput.value = '';
    renderCurrentTags();
}

function removeTag(tag) {
    window.currentEditTags = window.currentEditTags.filter((t) => t !== tag);
    renderCurrentTags();
}

function closeTagsModal() {
    const modal = document.getElementById('tagsModal');
    if (modal) modal.style.display = 'none';
    window.currentEditAccount = null;
    window.currentEditTags = [];
}

function editAccountNote(emailId, note) {
    window.currentNoteAccount = emailId;
    const modal = document.getElementById('noteModal');
    const textarea = document.getElementById('noteTextarea');
    const title = document.querySelector('#noteModal .modal-header h3');

    if (title) {
        title.textContent = `编辑 ${emailId} 的备注`;
    }

    if (textarea) {
        textarea.value = typeof note === 'string' ? note : '';
    }

    if (modal) {
        modal.style.display = 'flex';
    }
}

function closeNoteModal() {
    const modal = document.getElementById('noteModal');
    if (modal) modal.style.display = 'none';
    const textarea = document.getElementById('noteTextarea');
    if (textarea) textarea.value = '';
    window.currentNoteAccount = null;
}

async function saveAccountNote() {
    if (!window.currentNoteAccount) {
        closeNoteModal();
        return;
    }

    const textarea = document.getElementById('noteTextarea');
    const rawValue = textarea ? textarea.value.replace(/\r\n/g, '\n') : '';
    const payload = {
        note: rawValue.trim() ? rawValue : null,
    };

    try {
        const response = await apiRequest(`/accounts/${window.currentNoteAccount}/note`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
        showNotification(response?.message || '备注更新成功', 'success');
        closeNoteModal();
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`备注更新失败: ${error.message}`, 'error');
    }
}

async function saveAccountTags() {
    if (!window.currentEditAccount) {
        closeTagsModal();
        return;
    }

    try {
        const response = await apiRequest(`/accounts/${window.currentEditAccount}/tags`, {
            method: 'PUT',
            body: JSON.stringify({ tags: window.currentEditTags }),
        });

        showNotification(response?.message || '标签更新成功', 'success');
        closeTagsModal();
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`标签更新失败: ${error.message}`, 'error');
    }
}

async function deleteAccount(emailId) {
    if (!confirm(`确定要删除账户 ${emailId} 吗？`)) {
        return;
    }

    try {
        const response = await apiRequest(`/accounts/${emailId}`, { method: 'DELETE' });
        showNotification(response?.message || '账户已删除', 'success');
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`删除账户失败: ${error.message}`, 'error');
    }
}

async function resetAccountStatus(emailId) {
    if (!confirm(`确定要重置账户 ${emailId} 的状态为正常吗？\n(这将清除失败计数并尝试重新恢复使用)`)) {
        return;
    }

    try {
        const response = await apiRequest(`/accounts/${emailId}/reset-status`, { method: 'POST' });
        showNotification(response?.message || '账户状态已重置', 'success');
        loadAccounts(window.accountsCurrentPage);
    } catch (error) {
        showNotification(`重置状态失败: ${error.message}`, 'error');
    }
}

function showAccountContextMenu(event, emailId) {
    event.preventDefault();
    event.stopPropagation();

    window.contextMenuTarget = emailId;
    const contextMenu = document.getElementById('contextMenu');
    if (!contextMenu) return;

    contextMenu.style.left = `${event.pageX}px`;
    contextMenu.style.top = `${event.pageY}px`;
    contextMenu.style.display = 'block';

    setTimeout(() => {
        document.addEventListener('click', hideContextMenu, { once: true });
    }, 10);
}

function hideContextMenu() {
    const contextMenu = document.getElementById('contextMenu');
    if (contextMenu) contextMenu.style.display = 'none';
    window.contextMenuTarget = null;
}

function openInNewTab() {
    if (!window.contextMenuTarget) return;
    const url = `${window.location.origin}/#/emails/${encodeURIComponent(window.contextMenuTarget)}`;
    window.open(url, '_blank');
    hideContextMenu();
}

function showExpiredAccountNotice(emailId) {
    const label = emailId || '该账户';
    showNotification(`邮箱 ${label} 授权已过期，请重新验证凭据`, 'warning');
}

function copyAccountLink() {
    if (!window.contextMenuTarget) return;
    const url = `${window.location.origin}/#/emails/${encodeURIComponent(window.contextMenuTarget)}`;

    if (navigator.clipboard) {
        navigator.clipboard.writeText(url)
            .then(() => showNotification('链接已复制到剪贴板', 'success'))
            .catch(() => fallbackCopyText(url));
    } else {
        fallbackCopyText(url);
    }

    hideContextMenu();
}

function contextEditTags() {
    if (!window.contextMenuTarget) return;
    const account = window.accounts.find((acc) => acc.email_id === window.contextMenuTarget);
    if (account) {
        editAccountTags(window.contextMenuTarget, account.tags || []);
    }
    hideContextMenu();
}

function contextDeleteAccount() {
    if (window.contextMenuTarget) {
        deleteAccount(window.contextMenuTarget);
    }
    hideContextMenu();
}

window.clearAddAccountForm = clearAddAccountForm;
window.clearBatchForm = clearBatchForm;
window.validateBatchFormat = validateBatchFormat;
window.loadAccounts = loadAccounts;
window.searchAccounts = searchAccounts;
window.clearSearch = clearSearch;
window.handleSearchKeyPress = handleSearchKeyPress;
window.syncAccountsToServer = syncAccountsToServer;
window.syncAccountsFromServer = syncAccountsFromServer;
window.addAccount = addAccount;
window.batchAddAccounts = batchAddAccounts;
window.hideBatchProgress = hideBatchProgress;
window.editAccountTags = editAccountTags;
window.addTag = addTag;
window.removeTag = removeTag;
window.closeTagsModal = closeTagsModal;
window.saveAccountTags = saveAccountTags;
window.deleteAccount = deleteAccount;
window.showAccountContextMenu = showAccountContextMenu;
window.openInNewTab = openInNewTab;
window.copyAccountLink = copyAccountLink;
window.contextEditTags = contextEditTags;
window.contextDeleteAccount = contextDeleteAccount;
window.changePage = changePage;
window.editAccountNote = editAccountNote;
window.closeNoteModal = closeNoteModal;
window.saveAccountNote = saveAccountNote;
window.showExpiredAccountNotice = showExpiredAccountNotice;
window.resetAccountStatus = resetAccountStatus;
