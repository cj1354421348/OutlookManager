window.tokenHealthEnabled = true;
window.tokenHealthInterval = 1440;
window.tokenHealthStatus = {
    running: false,
    last_started_at: null,
    last_completed_at: null,
    last_result: null,
};

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
    await Promise.all([loadApiKey(), loadSecurityStats(), loadTokenHealthSettings()]);
    await loadTokenHealthStatus();
}

async function loadTokenHealthSettings() {
    try {
        const data = await apiRequest('/auth/token-health', { skipApiKey: true, useSession: true });
        window.tokenHealthEnabled = !!(data && data.enabled);
        window.tokenHealthInterval = (data && data.interval_minutes) || 1440;
        updateTokenHealthToggle();
        updateTokenHealthInterval();
    } catch (error) {
        showNotification(`获取巡检配置失败: ${error.message}`, 'error');
    }
}

function updateTokenHealthToggle() {
    const toggleButton = document.getElementById('tokenHealthToggle');
    const statusLabel = document.getElementById('tokenHealthStatus');
    if (!toggleButton || !statusLabel) {
        return;
    }

    toggleButton.classList.remove('btn-primary', 'btn-secondary');
    if (window.tokenHealthEnabled) {
        toggleButton.classList.add('btn-primary');
        toggleButton.innerHTML = '<span>🟢</span> 自动巡检已开启';
        statusLabel.textContent = '系统会按设定间隔自动校验所有账户令牌。';
    } else {
        toggleButton.classList.add('btn-secondary');
        toggleButton.innerHTML = '<span>⚪</span> 自动巡检已关闭';
        statusLabel.textContent = '后台巡检已暂停，令牌仅在手动请求时校验。';
    }
}

async function toggleTokenHealth() {
    const nextEnabled = !window.tokenHealthEnabled;
    try {
        const data = await apiRequest('/auth/token-health', {
            method: 'POST',
            body: JSON.stringify({ enabled: nextEnabled, interval_minutes: window.tokenHealthInterval }),
            skipApiKey: true,
            useSession: true,
        });
        window.tokenHealthEnabled = !!(data && data.enabled);
        window.tokenHealthInterval = (data && data.interval_minutes) || window.tokenHealthInterval;
        updateTokenHealthToggle();
        updateTokenHealthInterval();
        showNotification(window.tokenHealthEnabled ? '已开启自动巡检' : '已关闭自动巡检', 'success');
    } catch (error) {
        showNotification(`更新巡检设置失败: ${error.message}`, 'error');
    }
}

function updateTokenHealthInterval() {
    const intervalInput = document.getElementById('tokenHealthInterval');
    if (intervalInput) {
        intervalInput.value = window.tokenHealthInterval;
    }
}

async function saveTokenHealthInterval() {
    const intervalInput = document.getElementById('tokenHealthInterval');
    if (!intervalInput) return;
    const value = parseInt(intervalInput.value, 10);
    if (Number.isNaN(value) || value < 60 || value > 10080) {
        showNotification('间隔需在 60-10080 分钟之间', 'warning');
        intervalInput.value = window.tokenHealthInterval;
        return;
    }
    try {
        const data = await apiRequest('/auth/token-health', {
            method: 'POST',
            body: JSON.stringify({ enabled: window.tokenHealthEnabled, interval_minutes: value }),
            skipApiKey: true,
            useSession: true,
        });
        window.tokenHealthEnabled = !!(data && data.enabled);
        window.tokenHealthInterval = data.interval_minutes || value;
        updateTokenHealthToggle();
        updateTokenHealthInterval();
        showNotification('巡检间隔已更新', 'success');
    } catch (error) {
        showNotification(`更新巡检间隔失败: ${error.message}`, 'error');
        intervalInput.value = window.tokenHealthInterval;
    }
}

async function loadTokenHealthStatus() {
    try {
        const data = await apiRequest('/auth/token-health/status', { skipApiKey: true, useSession: true });
        window.tokenHealthStatus = data || window.tokenHealthStatus;
        updateTokenHealthStatus();
    } catch (error) {
        showNotification(`获取巡检状态失败: ${error.message}`, 'error');
    }
}

function updateTokenHealthStatus() {
    const statusBadge = document.getElementById('tokenHealthRunStatus');
    const lastRunLabel = document.getElementById('tokenHealthLastRun');
    const resultLabel = document.getElementById('tokenHealthLastResult');
    if (!statusBadge || !lastRunLabel || !resultLabel) {
        return;
    }

    const fmt = (ts) => (ts ? TimeUtils.format(ts * 1000) : '无记录');
    statusBadge.textContent = window.tokenHealthStatus.running ? '运行中' : '空闲';
    statusBadge.className = window.tokenHealthStatus.running ? 'status-badge active' : 'status-badge idle';
    lastRunLabel.textContent = fmt(window.tokenHealthStatus.last_completed_at);

    const result = window.tokenHealthStatus.last_result;
    if (result) {
        resultLabel.textContent = `总计 ${result.total}，成功 ${result.success}，失败 ${result.failures}，新拉黑 ${result.newly_expired}`;
    } else {
        resultLabel.textContent = '暂无执行记录';
    }
}

async function triggerTokenHealthRun() {
    try {
        await apiRequest('/auth/token-health/run-now', {
            method: 'POST',
            skipApiKey: true,
            useSession: true,
        });
        showNotification('已触发巡检任务', 'success');
        await loadTokenHealthStatus();
    } catch (error) {
        showNotification(`触发巡检失败: ${error.message}`, 'error');
    }
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
window.loadTokenHealthSettings = loadTokenHealthSettings;
window.updateTokenHealthToggle = updateTokenHealthToggle;
window.toggleTokenHealth = toggleTokenHealth;
window.updateTokenHealthInterval = updateTokenHealthInterval;
window.saveTokenHealthInterval = saveTokenHealthInterval;
window.loadTokenHealthStatus = loadTokenHealthStatus;
window.updateTokenHealthStatus = updateTokenHealthStatus;
window.triggerTokenHealthRun = triggerTokenHealthRun;
