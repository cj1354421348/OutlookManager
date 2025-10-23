async function loadApiKey() {
    try {
        const data = await apiRequest('/auth/api-key', { skipApiKey: true, useSession: true });
        window.currentApiKey = data && data.api_key ? data.api_key : null;
        updateApiKeyDisplay();
    } catch (error) {
        window.currentApiKey = null;
        updateApiKeyDisplay();
        showNotification(error.message || '获取 API Key 失败', 'error');
    }
}

function updateApiKeyDisplay() {
    const displayInput = document.getElementById('apiKeyDisplay');
    const copyButton = document.getElementById('copyApiKeyBtn');
    if (!displayInput || !copyButton) return;

    if (window.currentApiKey) {
        displayInput.value = window.currentApiKey;
        copyButton.disabled = false;
    } else {
        displayInput.value = '未设置';
        copyButton.disabled = true;
    }
}

async function generateApiKey() {
    try {
        const data = await apiRequest('/auth/api-key', {
            method: 'POST',
            body: JSON.stringify({}),
            skipApiKey: true,
            useSession: true,
        });
        window.currentApiKey = data.api_key;
        updateApiKeyDisplay();
        await loadSecurityStats();
        showNotification('已生成新的 API Key', 'success');
    } catch (error) {
        showNotification(`生成 API Key 失败: ${error.message}`, 'error');
    }
}

async function saveCustomApiKey() {
    const input = document.getElementById('customApiKeyInput');
    const value = input ? input.value.trim() : '';

    if (!value) {
        showNotification('请输入自定义 Key', 'warning');
        return;
    }

    try {
        const data = await apiRequest('/auth/api-key', {
            method: 'POST',
            body: JSON.stringify({ api_key: value }),
            skipApiKey: true,
            useSession: true,
        });
        window.currentApiKey = data.api_key;
        updateApiKeyDisplay();
        await loadSecurityStats();
        showNotification('自定义 API Key 已保存', 'success');
    } catch (error) {
        showNotification(`保存 API Key 失败: ${error.message}`, 'error');
    }
}

async function deleteApiKey() {
    if (!confirm('确定要删除当前 API Key 吗？删除后必须重新设置才可调用接口。')) {
        return;
    }

    try {
        await apiRequest('/auth/api-key', {
            method: 'DELETE',
            skipApiKey: true,
            useSession: true,
        });
        window.currentApiKey = null;
        updateApiKeyDisplay();
        await loadSecurityStats();
        showNotification('API Key 已删除', 'success');
        showPage('settings');
    } catch (error) {
        showNotification(`删除 API Key 失败: ${error.message}`, 'error');
    }
}

function copyApiKey() {
    if (!window.currentApiKey) {
        showNotification('尚未设置 API Key', 'warning');
        return;
    }

    navigator.clipboard.writeText(window.currentApiKey)
        .then(() => showNotification('API Key 已复制到剪贴板', 'success'))
        .catch(() => showNotification('复制失败，请手动复制', 'error'));
}

async function loadSecurityStats() {
    try {
        const data = await apiRequest('/auth/security-stats', { skipApiKey: true, useSession: true });
        window.securityStats = data || window.securityStats;
        updateSecurityStatsDisplay();
    } catch (error) {
        showNotification(`获取安全统计失败: ${error.message}`, 'error');
    }
}

function updateSecurityStatsDisplay() {
    const passwordFail = document.getElementById('passwordFailCount');
    const apiKeyFail = document.getElementById('apiKeyFailCount');
    const loginLocked = document.getElementById('loginLockedIps');
    const keyLocked = document.getElementById('keyLockedIps');

    if (passwordFail) {
        passwordFail.textContent = window.securityStats.failed_password_attempts || 0;
    }
    if (apiKeyFail) {
        apiKeyFail.textContent = window.securityStats.failed_api_key_attempts || 0;
    }
    if (loginLocked) {
        const list = window.securityStats.locked_login_ips || [];
        loginLocked.textContent = list.length ? list.join(', ') : '无';
    }
    if (keyLocked) {
        const list = window.securityStats.locked_api_key_ips || [];
        keyLocked.textContent = list.length ? list.join(', ') : '无';
    }
}

async function refreshSecurityInfo() {
    await Promise.all([loadApiKey(), loadSecurityStats()]);
}

window.loadApiKey = loadApiKey;
window.updateApiKeyDisplay = updateApiKeyDisplay;
window.generateApiKey = generateApiKey;
window.saveCustomApiKey = saveCustomApiKey;
window.deleteApiKey = deleteApiKey;
window.copyApiKey = copyApiKey;
window.loadSecurityStats = loadSecurityStats;
window.updateSecurityStatsDisplay = updateSecurityStatsDisplay;
window.refreshSecurityInfo = refreshSecurityInfo;
