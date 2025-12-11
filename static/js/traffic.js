// 全局状态：日志存储
window.trafficLogs = [];
window.trafficProtocolFilter = 'all'; // 'all', 'HTTP', 'IMAP'
const MAX_LOGS = 500;
let streamController = null;
let isStreamActive = false;

// 初始化：应用启动时调用
function startGlobalTrafficStream() {
    if (isStreamActive) return;
    isStreamActive = true;
    updateConnectionStatus('connecting');

    const url = '/api/traffic/stream';
    const headers = {};
    if (window.currentApiKey) {
        headers['Authorization'] = `Key ${window.currentApiKey}`;
    }

    fetch(url, { headers })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            streamController = reader;
            updateConnectionStatus('connected');

            function read() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        console.log('Traffic stream complete');
                        handleStreamDisconnect();
                        return;
                    }

                    const chunk = decoder.decode(value, { stream: true });
                    processStreamChunk(chunk);
                    read();
                }).catch(error => {
                    console.error('Traffic stream read error:', error);
                    handleStreamDisconnect();
                });
            }
            read();
        })
        .catch(error => {
            console.error('Traffic stream connection failed:', error);
            handleStreamDisconnect();
        });
}

function handleStreamDisconnect() {
    isStreamActive = false;
    streamController = null;
    updateConnectionStatus('disconnected');

    // 自动重连：5秒后重试
    setTimeout(() => {
        if (!isStreamActive) {
            console.log('Attempting to reconnect traffic stream...');
            startGlobalTrafficStream();
        }
    }, 5000);
}

function processStreamChunk(chunk) {
    // SSE format: "data: {...}\n\n"
    const lines = chunk.split('\n\n');
    lines.forEach(line => {
        if (line.startsWith('data: ')) {
            try {
                const jsonStr = line.substring(6);
                const entry = JSON.parse(jsonStr);
                addLogEntry(entry);
            } catch (e) {
                // Ignore parse errors (keepalives or empty lines)
            }
        }
    });
}

function addLogEntry(entry) {
    window.trafficLogs.unshift(entry);
    if (window.trafficLogs.length > MAX_LOGS) {
        window.trafficLogs.pop();
    }

    // 如果当前在日志页面，立即更新 UI
    const tbody = document.getElementById('trafficTableBody');
    if (tbody) {
        // 检查是否符合当前筛选条件
        if (window.trafficProtocolFilter === 'all' || entry.protocol === window.trafficProtocolFilter) {
            // 创建新行并插入到顶部
            const row = createTrafficRow(entry);
            tbody.insertAdjacentHTML('afterbegin', row);

            // 保持 DOM 数量限制（注意：这里限制的是显示的行数，不是总数据）
            if (tbody.children.length > MAX_LOGS) {
                tbody.lastElementChild.remove();
            }
        }
    }
}

// 页面加载时的渲染逻辑（切到 Tab 时调用）
function initTrafficPage() {
    renderTrafficLogs();

    // 如果没有连接，尝试触发连接（防御性编程）
    if (!isStreamActive) {
        startGlobalTrafficStream();
    }
}

function renderTrafficLogs() {
    const tbody = document.getElementById('trafficTableBody');
    if (!tbody) return;

    // 根据筛选条件过滤日志
    const filteredLogs = window.trafficProtocolFilter === 'all'
        ? window.trafficLogs
        : window.trafficLogs.filter(log => log.protocol === window.trafficProtocolFilter);

    if (filteredLogs.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="traffic-empty">
                    <div class="traffic-empty-text">${window.trafficLogs.length === 0 ? '暂无请求日志' : '筛选结果为空'}</div>
                    <div class="traffic-empty-hint">${window.trafficLogs.length === 0 ? '请尝试刷新邮箱列表或执行其他操作' : '请尝试其他筛选条件'}</div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filteredLogs.map(createTrafficRow).join('');

    // 同步当前连接状态UI
    updateConnectionStatus(isStreamActive ? 'connected' : 'disconnected');
}

function createTrafficRow(log) {
    const statusClass = log.status === 'OK' ? 'badge-ok' : 'badge-error';
    const protocolClass = log.protocol === 'HTTP' ? 'badge-http' : 'badge-imap';
    const date = new Date(log.timestamp);
    const timeStr = date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const accountShort = log.account.includes('@') ? log.account.split('@')[0] : log.account;

    return `
        <tr>
            <td class="td-time">${timeStr}</td>
            <td class="td-protocol">
                <span class="protocol-badge ${protocolClass}">${log.protocol}</span>
            </td>
            <td class="td-account" title="${log.account}">${accountShort}</td>
            <td class="td-action" title="${log.action}">${log.action}</td>
            <td class="td-status">
                <span class="status-badge ${statusClass}">${log.status}</span>
            </td>
            <td class="td-duration">${log.duration_ms.toFixed(0)} ms</td>
            <td class="td-details" title="${log.details || ''}" onclick="if('${log.details}'.trim()) alert('${(log.details || '').replace(/'/g, "\\'").replace(/"/g, '&quot;')}')">${log.details || '—'}</td>
        </tr>
    `;
}

function updateConnectionStatus(status) {
    const indicator = document.getElementById('trafficStatusIndicator');
    const text = document.getElementById('trafficStatusText');
    if (!indicator || !text) return;

    if (status === 'connected') {
        indicator.className = 'status-dot online';
        text.textContent = '实时连接正常';
    } else if (status === 'connecting') {
        indicator.className = 'status-dot offline';
        text.textContent = '正在连接...';
    } else {
        indicator.className = 'status-dot offline';
        text.textContent = '连接断开 (自动重连中)';
    }
}

// 协议筛选
function filterByProtocol(protocol) {
    window.trafficProtocolFilter = protocol;
    renderTrafficLogs();
}

// 暴露全局
window.startGlobalTrafficStream = startGlobalTrafficStream;
window.initTrafficPage = initTrafficPage;
window.renderTrafficLogs = renderTrafficLogs;
window.filterByProtocol = filterByProtocol;
