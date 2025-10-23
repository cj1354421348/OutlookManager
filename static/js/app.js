const PAGE_TITLES = {
    accounts: '邮箱账户管理',
    addAccount: '添加邮箱账户',
    batchAdd: '批量添加账户',
    apiDocs: 'API接口文档',
    emails: '邮件列表',
    settings: '安全设置',
};

function showPage(pageName, targetElement = null) {
    const protectedPages = ['accounts', 'addAccount', 'batchAdd', 'emails'];
    if (protectedPages.includes(pageName) && !window.currentApiKey) {
        showNotification('请先在安全设置中生成 API Key', 'warning');
        if (pageName !== 'settings') {
            showPage('settings');
        }
        return;
    }

    document.querySelectorAll('.page').forEach((page) => page.classList.add('hidden'));
    const targetPage = document.getElementById(`${pageName}Page`);
    if (targetPage) {
        targetPage.classList.remove('hidden');
    }

    document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
    if (targetElement) {
        targetElement.classList.add('active');
    } else {
        document.querySelectorAll('.nav-item').forEach((button) => {
            if (button.getAttribute('onclick')?.includes(`'${pageName}'`)) {
                button.classList.add('active');
            }
        });
    }

    const title = document.getElementById('pageTitle');
    if (title) {
        title.textContent = PAGE_TITLES[pageName] || '';
    }

    switch (pageName) {
        case 'accounts':
            loadAccounts();
            break;
        case 'addAccount':
            clearAddAccountForm();
            break;
        case 'batchAdd':
            clearBatchForm();
            hideBatchProgress();
            break;
        case 'apiDocs':
            initApiDocs();
            break;
        case 'emails':
            loadEmails();
            break;
        case 'settings':
            refreshSecurityInfo().catch(() => {});
            break;
        default:
            break;
    }
}

function initApiDocs() {
    const baseUrlEl = document.getElementById('baseUrlExample');
    if (baseUrlEl) {
        baseUrlEl.textContent = window.location.origin;
    }
}

function copyApiBaseUrl() {
    const baseUrl = window.location.origin;
    navigator.clipboard.writeText(baseUrl)
        .then(() => showNotification('Base URL已复制到剪贴板', 'success'))
        .catch(() => showNotification('复制失败，请手动复制', 'error'));
}

function downloadApiDocs() {
    const markdown = generateApiDocsMarkdown();
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', 'outlook-email-api-docs.md');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showNotification('API文档已下载', 'success');
}

function generateApiDocsMarkdown() {
    const baseUrl = window.location.origin;
    return `# Outlook邮件管理系统 API文档

## 基础信息

- **Base URL**: ${baseUrl}
- **认证方式**: 登录后使用会话 Cookie + Authorization: Key <API_KEY>
- **响应格式**: JSON

## 接口列表

### 1. 获取邮箱列表

**请求**
\`\`\`
GET /accounts
\`\`\`

**响应示例**
\`\`\`json
{
  "accounts": [
    {
      "email_id": "example@outlook.com",
      "status": "active",
      "tags": []
    }
  ],
  "total_count": 1
}
\`\`\`

### 2. 获取邮件列表

**请求**
\`\`\`
GET /emails/{email_id}?folder=inbox&page=1&page_size=20&refresh=false
\`\`\`

**响应示例**
\`\`\`json
{
  "email_id": "example@outlook.com",
  "folder_view": "inbox",
  "page": 1,
  "page_size": 20,
  "total_emails": 150,
  "emails": [...]
}
\`\`\`

### 3. 获取邮件详情

**请求**
\`\`\`
GET /emails/{email_id}/{message_id}
\`\`\`

**响应示例**
\`\`\`json
{
  "message_id": "INBOX-1",
  "subject": "邮件主题",
  "from_email": "sender@example.com",
  "to_email": "example@outlook.com",
  "date": "2024-01-01T12:00:00Z",
  "body_plain": "纯文本内容",
  "body_html": "HTML内容"
}
\`\`\`

---
生成时间: ${new Date().toLocaleString()}
`;
}

async function tryApi(apiType) {
    let path = '';
    let responseElementId = '';
    let data = null;

    try {
        if (apiType === 'accounts') {
            path = '/accounts';
            responseElementId = 'accountsResponse';
            data = await apiRequest(path);
        } else if (apiType === 'emails') {
            const accountsData = await apiRequest('/accounts');
            if (!accountsData.accounts || accountsData.accounts.length === 0) {
                showNotification('没有可用的邮箱账户，请先添加账户', 'warning');
                return;
            }
            const emailId = encodeURIComponent(accountsData.accounts[0].email_id);
            path = `/emails/${emailId}?folder=inbox&page=1&page_size=5`;
            responseElementId = 'emailsResponse';
            data = await apiRequest(path);
        } else if (apiType === 'emailDetail') {
            const accountsData = await apiRequest('/accounts');
            if (!accountsData.accounts || accountsData.accounts.length === 0) {
                showNotification('没有可用的邮箱账户，请先添加账户', 'warning');
                return;
            }
            const emailId = encodeURIComponent(accountsData.accounts[0].email_id);
            const emailsData = await apiRequest(`/emails/${emailId}?folder=all&page=1&page_size=1`);
            if (!emailsData.emails || emailsData.emails.length === 0) {
                showNotification('该邮箱没有邮件', 'warning');
                return;
            }
            const messageId = emailsData.emails[0].message_id;
            path = `/emails/${emailId}/${messageId}`;
            responseElementId = 'emailDetailResponse';
            data = await apiRequest(path);
        } else {
            return;
        }

        const responseElement = document.getElementById(responseElementId);
        const responseDataElement = document.getElementById(responseElementId.replace('Response', 'ResponseData'));

        if (responseDataElement) {
            responseDataElement.textContent = JSON.stringify(data, null, 2);
        }
        if (responseElement) {
            responseElement.classList.add('show');
        }

        showNotification(`API 调用成功：${window.location.origin + path}`, 'success');
    } catch (error) {
        showNotification(`API调用失败: ${error.message}`, 'error');
    }
}

function handleUrlRouting() {
    if (!window.currentApiKey) {
        return;
    }

    const { hash } = window.location;
    if (hash.startsWith('#/emails/')) {
        const emailId = decodeURIComponent(hash.replace('#/emails/', ''));
        if (emailId) {
            window.currentAccount = emailId;
            const emailLabel = document.getElementById('currentAccountEmail');
            const emailsNav = document.getElementById('emailsNav');
            if (emailLabel) emailLabel.textContent = emailId;
            if (emailsNav) emailsNav.style.display = 'block';
            showPage('emails');
        }
    }
}

async function initializeApp() {
    try {
        await checkSession();
        await refreshSecurityInfo();

        const hasHash = window.location.hash && window.location.hash !== '#';
        if (window.currentApiKey) {
            if (hasHash) {
                handleUrlRouting();
            } else {
                showPage('accounts');
            }
        } else {
            showPage('settings');
            showNotification('请先在安全设置中生成 API Key', 'warning');
        }

        setTimeout(() => {
            showNotification('欢迎使用邮件管理系统！', 'info', '欢迎', 3000);
        }, 500);
    } catch (error) {
        window.location.href = '/login';
    }
}

window.addEventListener('load', initializeApp);
window.addEventListener('popstate', () => {
    if (!window.currentApiKey) {
        showPage('settings');
        return;
    }
    handleUrlRouting();
});

window.showPage = showPage;
window.initApiDocs = initApiDocs;
window.copyApiBaseUrl = copyApiBaseUrl;
window.downloadApiDocs = downloadApiDocs;
window.generateApiDocsMarkdown = generateApiDocsMarkdown;
window.tryApi = tryApi;
window.handleUrlRouting = handleUrlRouting;
