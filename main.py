import asyncio
import json
import logging
import email
import re
import socket
import threading
import time
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from queue import Queue, Empty

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from email.header import decode_header
from email.utils import parsedate_to_datetime
import imaplib
from fastapi.middleware.cors import CORSMiddleware
from itertools import groupby



# ============================================================================
# 配置常量
# ============================================================================

ACCOUNTS_FILE = "accounts.json"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
IMAP_SERVER = "outlook.live.com"
IMAP_PORT = 993

# IMAP连接池配置
MAX_CONNECTIONS = 5
CONNECTION_TIMEOUT = 30
SOCKET_TIMEOUT = 15

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型 (Pydantic)
# ============================================================================

class AccountCredentials(BaseModel):
    email: EmailStr
    refresh_token: str
    client_id: str

class EmailItem(BaseModel):
    message_id: str
    folder: str
    subject: str
    from_email: str
    date: str
    is_read: bool = False
    has_attachments: bool = False
    sender_initial: str = "?"

class EmailListResponse(BaseModel):
    email_id: str
    folder_view: str
    page: int
    page_size: int
    total_emails: int
    emails: List[EmailItem]

class DualViewEmailResponse(BaseModel):
    email_id: str
    inbox_emails: List[EmailItem]
    junk_emails: List[EmailItem]
    inbox_total: int
    junk_total: int

class EmailDetailsResponse(BaseModel):
    message_id: str
    subject: str
    from_email: str
    to_email: str
    date: str
    body_plain: Optional[str] = None
    body_html: Optional[str] = None

class AccountResponse(BaseModel):
    email_id: str
    message: str

class AccountInfo(BaseModel):
    email_id: str
    client_id: str
    status: str = "active"

class AccountListResponse(BaseModel):
    total_accounts: int
    accounts: List[AccountInfo]


# ============================================================================
# IMAP连接池管理
# ============================================================================

class IMAPConnectionPool:
    """IMAP连接池，提高连接复用和性能"""

    def __init__(self, max_connections=MAX_CONNECTIONS):
        self.max_connections = max_connections
        self.connections = {}  # {email: Queue of connections}
        self.connection_count = {}  # {email: count}
        self.lock = threading.Lock()

    def _create_connection(self, email: str, access_token: str):
        """创建新的IMAP连接"""
        try:
            # 设置socket超时
            socket.setdefaulttimeout(SOCKET_TIMEOUT)

            # 创建IMAP连接
            imap_client = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)

            # 设置更短的超时时间
            imap_client.sock.settimeout(CONNECTION_TIMEOUT)

            # XOAUTH2认证
            auth_string = f"user={email}\1auth=Bearer {access_token}\1\1".encode('utf-8')
            imap_client.authenticate('XOAUTH2', lambda x: auth_string)

            logger.info(f"Created new IMAP connection for {email}")
            return imap_client

        except Exception as e:
            logger.error(f"Failed to create IMAP connection for {email}: {e}")
            raise

    def get_connection(self, email: str, access_token: str):
        """获取IMAP连接"""
        with self.lock:
            if email not in self.connections:
                self.connections[email] = Queue(maxsize=self.max_connections)
                self.connection_count[email] = 0

            connection_queue = self.connections[email]

            # 尝试从池中获取连接
            try:
                connection = connection_queue.get_nowait()
                # 测试连接是否有效
                try:
                    connection.noop()
                    logger.debug(f"Reused IMAP connection for {email}")
                    return connection
                except:
                    # 连接无效，创建新连接
                    logger.debug(f"Connection invalid for {email}, creating new one")
                    pass
            except Empty:
                pass

            # 创建新连接
            if self.connection_count[email] < self.max_connections:
                connection = self._create_connection(email, access_token)
                self.connection_count[email] += 1
                return connection
            else:
                # 达到最大连接数，等待可用连接
                logger.warning(f"Max connections reached for {email}, waiting...")
                return connection_queue.get(timeout=30)

    def return_connection(self, email: str, connection):
        """归还连接到池中"""
        if email in self.connections:
            try:
                # 检查连接状态
                connection.noop()
                self.connections[email].put_nowait(connection)
                logger.debug(f"Returned IMAP connection for {email}")
            except:
                # 连接已断开，减少计数
                with self.lock:
                    self.connection_count[email] -= 1
                logger.debug(f"Discarded invalid connection for {email}")

    def close_all_connections(self, email: str = None):
        """关闭所有连接"""
        with self.lock:
            if email:
                if email in self.connections:
                    while not self.connections[email].empty():
                        try:
                            conn = self.connections[email].get_nowait()
                            conn.logout()
                        except:
                            pass
                    self.connection_count[email] = 0
            else:
                for email_key in list(self.connections.keys()):
                    self.close_all_connections(email_key)

# 全局连接池实例
imap_pool = IMAPConnectionPool()

# 简单的内存缓存
email_cache = {}
email_count_cache = {}  # 存储邮件总数，用于检测新邮件
CACHE_EXPIRE_TIME = 60  # 缩短到1分钟缓存，更快获取新邮件

def get_cache_key(email: str, folder: str, page: int, page_size: int) -> str:
    """生成缓存键"""
    return f"{email}:{folder}:{page}:{page_size}"

def get_cached_emails(cache_key: str, force_refresh: bool = False):
    """获取缓存的邮件列表"""
    if force_refresh:
        # 强制刷新，删除缓存
        if cache_key in email_cache:
            del email_cache[cache_key]
        return None

    if cache_key in email_cache:
        cached_data, timestamp = email_cache[cache_key]
        if time.time() - timestamp < CACHE_EXPIRE_TIME:
            logger.debug(f"Cache hit for {cache_key}")
            return cached_data
        else:
            # 缓存过期，删除
            del email_cache[cache_key]
    return None

def set_cached_emails(cache_key: str, data):
    """设置邮件列表缓存"""
    email_cache[cache_key] = (data, time.time())
    logger.debug(f"Cache set for {cache_key}")

def clear_email_cache(email: str = None):
    """清除邮件缓存"""
    if email:
        # 清除特定邮箱的缓存
        keys_to_delete = [key for key in email_cache.keys() if key.startswith(f"{email}:")]
        for key in keys_to_delete:
            del email_cache[key]
        logger.info(f"Cleared cache for {email}")
    else:
        # 清除所有缓存
        email_cache.clear()
        logger.info("Cleared all email cache")

# ============================================================================
# 辅助函数
# ============================================================================

def decode_header_value(header_value: str) -> str:
    """解码邮件头字段"""
    if not header_value:
        return ""
    
    try:
        decoded_parts = decode_header(str(header_value))
        decoded_string = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_string += part.decode(charset if charset else 'utf-8', 'replace')
                except (LookupError, UnicodeDecodeError):
                    decoded_string += part.decode('utf-8', 'replace')
            else:
                decoded_string += str(part)
        return decoded_string
    except Exception:
        return str(header_value) if header_value else ""


def extract_email_content(email_message: email.message.EmailMessage) -> tuple[str, str]:
    """提取邮件的纯文本和HTML内容"""
    body_plain = ""
    body_html = ""
    
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if 'attachment' not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        decoded_content = payload.decode(charset, errors='replace')
                        
                        if content_type == 'text/plain' and not body_plain:
                            body_plain = decoded_content
                        elif content_type == 'text/html' and not body_html:
                            body_html = decoded_content
                except Exception as e:
                    logger.warning(f"Failed to decode email part: {e}")
    else:
        try:
            charset = email_message.get_content_charset() or 'utf-8'
            payload = email_message.get_payload(decode=True)
            if payload:
                content = payload.decode(charset, errors='replace')
                content_type = email_message.get_content_type()
                
                if content_type == 'text/plain':
                    body_plain = content
                elif content_type == 'text/html':
                    body_html = content
                else:
                    body_plain = content  # 默认当作纯文本处理
        except Exception as e:
            logger.warning(f"Failed to decode email body: {e}")
    
    return body_plain, body_html


# ============================================================================
# 凭证管理模块
# ============================================================================

async def get_account_credentials(email_id: str) -> AccountCredentials:
    """从accounts.json获取账户凭证"""
    try:
        if not Path(ACCOUNTS_FILE).exists():
            raise HTTPException(status_code=404, detail="Account not found")
        
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        if email_id not in accounts:
            raise HTTPException(status_code=404, detail="Account not found")
        
        account_data = accounts[email_id]
        return AccountCredentials(
            email=email_id,
            refresh_token=account_data['refresh_token'],
            client_id=account_data['client_id']
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to read accounts file")
    except Exception as e:
        logger.error(f"Error getting account credentials: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def save_account_credentials(email_id: str, credentials: AccountCredentials) -> None:
    """保存账户凭证到accounts.json"""
    try:
        accounts = {}
        if Path(ACCOUNTS_FILE).exists():
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                accounts = json.load(f)

        accounts[email_id] = {
            'refresh_token': credentials.refresh_token,
            'client_id': credentials.client_id
        }

        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)

        logger.info(f"Account credentials saved for {email_id}")
    except Exception as e:
        logger.error(f"Error saving account credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to save account")


async def get_all_accounts() -> AccountListResponse:
    """获取所有已加载的邮箱账户列表"""
    try:
        if not Path(ACCOUNTS_FILE).exists():
            return AccountListResponse(total_accounts=0, accounts=[])

        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            accounts_data = json.load(f)

        accounts = []
        for email_id, account_info in accounts_data.items():
            # 验证账户状态（可选：检查token是否有效）
            status = "active"
            try:
                # 简单验证：检查必要字段是否存在
                if not account_info.get('refresh_token') or not account_info.get('client_id'):
                    status = "invalid"
            except Exception:
                status = "error"

            accounts.append(AccountInfo(
                email_id=email_id,
                client_id=account_info.get('client_id', ''),
                status=status
            ))

        return AccountListResponse(
            total_accounts=len(accounts),
            accounts=accounts
        )

    except json.JSONDecodeError:
        logger.error("Failed to parse accounts.json")
        raise HTTPException(status_code=500, detail="Failed to read accounts file")
    except Exception as e:
        logger.error(f"Error getting accounts list: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# OAuth2令牌获取模块
# ============================================================================

async def get_access_token(credentials: AccountCredentials) -> str:
    """使用refresh_token获取access_token"""
    data = {
        'client_id': credentials.client_id,
        'grant_type': 'refresh_token',
        'refresh_token': credentials.refresh_token,
        'scope': 'https://outlook.office.com/IMAP.AccessAsUser.All offline_access'
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(TOKEN_URL, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data.get('access_token')
            
            if not access_token:
                raise HTTPException(status_code=401, detail="Failed to obtain access token")
            
            logger.info(f"Successfully obtained access token for {credentials.email}")
            return access_token
    
    except httpx.HTTPError as e:
        logger.error(f"HTTP error getting access token: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        logger.error(f"Error getting access token: {e}")
        raise HTTPException(status_code=500, detail="Token acquisition failed")


# ============================================================================
# IMAP核心服务 - 邮件列表
# ============================================================================

async def list_emails(credentials: AccountCredentials, folder: str, page: int, page_size: int, force_refresh: bool = False) -> EmailListResponse:
    """获取邮件列表 - 优化版本"""

    # 检查缓存
    cache_key = get_cache_key(credentials.email, folder, page, page_size)
    cached_result = get_cached_emails(cache_key, force_refresh)
    if cached_result:
        return cached_result

    access_token = await get_access_token(credentials)

    def _sync_list_emails():
        imap_client = None
        try:
            # 从连接池获取连接
            imap_client = imap_pool.get_connection(credentials.email, access_token)
            
            all_emails_data = []
            
            # 根据folder参数决定要获取的文件夹
            folders_to_check = []
            if folder == "inbox":
                folders_to_check = ["INBOX"]
            elif folder == "junk":
                folders_to_check = ["Junk"]
            else:  # folder == "all"
                folders_to_check = ["INBOX", "Junk"]
            
            for folder_name in folders_to_check:
                try:
                    # 选择文件夹
                    imap_client.select(f'"{folder_name}"', readonly=True)
                    
                    # 搜索所有邮件
                    status, messages = imap_client.search(None, "ALL")
                    if status != 'OK' or not messages or not messages[0]:
                        continue
                        
                    message_ids = messages[0].split()
                    
                    # 按日期排序所需的数据（邮件ID和日期）
                    # 为了避免获取所有邮件的日期，我们假设ID顺序与日期大致相关
                    message_ids.reverse() # 通常ID越大越新
                    
                    for msg_id in message_ids:
                        all_emails_data.append({
                            "message_id_raw": msg_id,
                            "folder": folder_name
                        })

                except Exception as e:
                    logger.warning(f"Failed to access folder {folder_name}: {e}")
                    continue
            
            # 对所有文件夹的邮件进行统一分页
            total_emails = len(all_emails_data)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_email_meta = all_emails_data[start_index:end_index]

            email_items = []
            # 按文件夹分组批量获取
            paginated_email_meta.sort(key=lambda x: x['folder'])
            
            for folder_name, group in groupby(paginated_email_meta, key=lambda x: x['folder']):
                try:
                    imap_client.select(f'"{folder_name}"', readonly=True)
                    
                    msg_ids_to_fetch = [item['message_id_raw'] for item in group]
                    if not msg_ids_to_fetch:
                        continue

                    # 批量获取邮件头 - 优化获取字段
                    msg_id_sequence = b','.join(msg_ids_to_fetch)
                    # 只获取必要的头部信息，减少数据传输
                    status, msg_data = imap_client.fetch(msg_id_sequence, '(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM MESSAGE-ID)])')

                    if status != 'OK':
                        continue
                    
                    # 解析批量获取的数据
                    for i in range(0, len(msg_data), 2):
                        header_data = msg_data[i][1]
                        
                        # 从返回的原始数据中解析出msg_id
                        # e.g., b'1 (BODY[HEADER.FIELDS (SUBJECT DATE FROM)] {..}'
                        match = re.match(rb'(\d+)\s+\(', msg_data[i][0])
                        if not match:
                            continue
                        fetched_msg_id = match.group(1)

                        msg = email.message_from_bytes(header_data)
                        
                        subject = decode_header_value(msg.get('Subject', '(No Subject)'))
                        from_email = decode_header_value(msg.get('From', '(Unknown Sender)'))
                        date_str = msg.get('Date', '')
                        
                        try:
                            date_obj = parsedate_to_datetime(date_str) if date_str else datetime.now()
                            formatted_date = date_obj.isoformat()
                        except:
                            date_obj = datetime.now()
                            formatted_date = date_obj.isoformat()
                        
                        message_id = f"{folder_name}-{fetched_msg_id.decode()}"
                        
                        # 提取发件人首字母
                        sender_initial = "?"
                        if from_email:
                            # 尝试提取邮箱用户名的首字母
                            email_match = re.search(r'([a-zA-Z])', from_email)
                            if email_match:
                                sender_initial = email_match.group(1).upper()
                        
                        email_item = EmailItem(
                            message_id=message_id,
                            folder=folder_name,
                            subject=subject,
                            from_email=from_email,
                            date=formatted_date,
                            is_read=False,  # 简化处理，实际可通过IMAP flags判断
                            has_attachments=False,  # 简化处理，实际需要检查邮件结构
                            sender_initial=sender_initial
                        )
                        email_items.append(email_item)

                except Exception as e:
                    logger.warning(f"Failed to fetch bulk emails from {folder_name}: {e}")
                    continue

            # 按日期重新排序最终结果
            email_items.sort(key=lambda x: x.date, reverse=True)

            # 归还连接到池中
            imap_pool.return_connection(credentials.email, imap_client)

            result = EmailListResponse(
                email_id=credentials.email,
                folder_view=folder,
                page=page,
                page_size=page_size,
                total_emails=total_emails,
                emails=email_items
            )

            # 设置缓存
            set_cached_emails(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            if imap_client:
                try:
                    # 如果出错，尝试归还连接或关闭
                    if hasattr(imap_client, 'state') and imap_client.state != 'LOGOUT':
                        imap_pool.return_connection(credentials.email, imap_client)
                    else:
                        # 连接已断开，从池中移除
                        pass
                except:
                    pass
            raise HTTPException(status_code=500, detail="Failed to retrieve emails")
    
    # 在线程池中运行同步代码
    return await asyncio.to_thread(_sync_list_emails)


# ============================================================================
# IMAP核心服务 - 邮件详情
# ============================================================================

async def get_email_details(credentials: AccountCredentials, message_id: str) -> EmailDetailsResponse:
    """获取邮件详细内容 - 优化版本"""
    # 解析复合message_id
    try:
        folder_name, msg_id = message_id.split('-', 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message_id format")

    access_token = await get_access_token(credentials)

    def _sync_get_email_details():
        imap_client = None
        try:
            # 从连接池获取连接
            imap_client = imap_pool.get_connection(credentials.email, access_token)
            
            # 选择正确的文件夹
            imap_client.select(folder_name)
            
            # 获取完整邮件内容
            status, msg_data = imap_client.fetch(msg_id, '(RFC822)')
            
            if status != 'OK' or not msg_data:
                raise HTTPException(status_code=404, detail="Email not found")
            
            # 解析邮件
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # 提取基本信息
            subject = decode_header_value(msg.get('Subject', '(No Subject)'))
            from_email = decode_header_value(msg.get('From', '(Unknown Sender)'))
            to_email = decode_header_value(msg.get('To', '(Unknown Recipient)'))
            date_str = msg.get('Date', '')
            
            # 格式化日期
            try:
                if date_str:
                    date_obj = parsedate_to_datetime(date_str)
                    formatted_date = date_obj.isoformat()
                else:
                    formatted_date = datetime.now().isoformat()
            except:
                formatted_date = datetime.now().isoformat()
            
            # 提取邮件内容
            body_plain, body_html = extract_email_content(msg)

            # 归还连接到池中
            imap_pool.return_connection(credentials.email, imap_client)

            return EmailDetailsResponse(
                message_id=message_id,
                subject=subject,
                from_email=from_email,
                to_email=to_email,
                date=formatted_date,
                body_plain=body_plain if body_plain else None,
                body_html=body_html if body_html else None
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting email details: {e}")
            if imap_client:
                try:
                    # 如果出错，尝试归还连接
                    if hasattr(imap_client, 'state') and imap_client.state != 'LOGOUT':
                        imap_pool.return_connection(credentials.email, imap_client)
                except:
                    pass
            raise HTTPException(status_code=500, detail="Failed to retrieve email details")
    
    # 在线程池中运行同步代码
    return await asyncio.to_thread(_sync_get_email_details)


# ============================================================================
# FastAPI应用和API端点
# ============================================================================

app = FastAPI(
    title="Outlook邮件API服务",
    description="基于FastAPI和aioimaplib的异步邮件管理服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 应用关闭时清理连接池
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理IMAP连接池"""
    logger.info("Shutting down IMAP connection pool...")
    imap_pool.close_all_connections()

# 挂载静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/accounts", response_model=AccountListResponse)
async def get_accounts():
    """获取所有已加载的邮箱账户列表"""
    return await get_all_accounts()


@app.post("/accounts", response_model=AccountResponse)
async def register_account(credentials: AccountCredentials):
    """注册或更新邮箱账户"""
    try:
        # 验证凭证有效性
        await get_access_token(credentials)

        # 保存凭证
        await save_account_credentials(credentials.email, credentials)

        return AccountResponse(
            email_id=credentials.email,
            message="Account verified and saved successfully."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering account: {e}")
        raise HTTPException(status_code=500, detail="Account registration failed")


@app.get("/emails/{email_id}", response_model=EmailListResponse)
async def get_emails(
    email_id: str,
    folder: str = Query("all", regex="^(inbox|junk|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    refresh: bool = Query(False, description="强制刷新缓存")
):
    """获取邮件列表"""
    credentials = await get_account_credentials(email_id)
    print('credentials:' + str(credentials))
    return await list_emails(credentials, folder, page, page_size, refresh)


@app.get("/emails/{email_id}/dual-view")
async def get_dual_view_emails(
    email_id: str,
    inbox_page: int = Query(1, ge=1),
    junk_page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """获取双栏视图邮件（收件箱和垃圾箱）"""
    credentials = await get_account_credentials(email_id)
    
    # 并行获取收件箱和垃圾箱邮件
    inbox_response = await list_emails(credentials, "inbox", inbox_page, page_size)
    junk_response = await list_emails(credentials, "junk", junk_page, page_size)
    
    return DualViewEmailResponse(
        email_id=email_id,
        inbox_emails=inbox_response.emails,
        junk_emails=junk_response.emails,
        inbox_total=inbox_response.total_emails,
        junk_total=junk_response.total_emails
    )


@app.get("/emails/{email_id}/{message_id}", response_model=EmailDetailsResponse)
async def get_email_detail(email_id: str, message_id: str):
    """获取邮件详细内容"""
    credentials = await get_account_credentials(email_id)
    return await get_email_details(credentials, message_id)


@app.get("/")
async def root():
    """根路径 - 返回前端页面"""
    return FileResponse("static/index.html")

@app.delete("/cache/{email_id}")
async def clear_cache(email_id: str):
    """清除指定邮箱的缓存"""
    clear_email_cache(email_id)
    return {"message": f"Cache cleared for {email_id}"}

@app.delete("/cache")
async def clear_all_cache():
    """清除所有缓存"""
    clear_email_cache()
    return {"message": "All cache cleared"}

@app.get("/api")
async def api_status():
    """API状态检查"""
    return {
        "message": "Outlook邮件API服务正在运行",
        "version": "1.0.0",
        "endpoints": {
            "get_accounts": "GET /accounts",
            "register_account": "POST /accounts",
            "get_emails": "GET /emails/{email_id}?refresh=true",
            "get_dual_view_emails": "GET /emails/{email_id}/dual-view",
            "get_email_detail": "GET /emails/{email_id}/{message_id}",
            "clear_cache": "DELETE /cache/{email_id}",
            "clear_all_cache": "DELETE /cache"
        }
    }


# ============================================================================
# 启动配置
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 