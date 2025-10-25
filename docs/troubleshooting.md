# 故障排除指南

本指南提供Outlook邮件管理系统常见问题的解决方案和故障排除方法。

## 🔍 问题诊断流程

### 1. 基础检查

在深入排查问题之前，先进行以下基础检查：

```bash
# 检查服务状态
docker-compose ps

# 检查系统资源
docker stats
free -h
df -h

# 检查网络连接
ping google.com
telnet outlook.live.com 993
```

### 2. 日志分析

```bash
# 查看应用日志
docker-compose logs -f outlook-email-client

# 查看数据库日志
docker-compose logs -f postgres

# 查看系统日志
journalctl -u docker
tail -f /var/log/syslog
```

### 3. 配置验证

```bash
# 验证环境变量
docker-compose exec outlook-email-client env | grep -E "(DATABASE|APP|IMAP)"

# 验证数据库连接
docker-compose exec postgres psql -U outlook_user -d outlook_db -c "SELECT 1;"

# 验证网络连接
docker-compose exec outlook-email-client nc -zv outlook.live.com 993
```

## 🚨 常见问题解答

### Q: 数据库连接失败怎么办？

**A**: 按以下步骤排查：

1. **验证数据库连接信息**：
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -p 5432
   ```

2. **检查.env文件配置**：
   - 确认`ACCOUNTS_DB_HOST`、`ACCOUNTS_DB_PORT`等配置正确
   - 确认数据库用户权限

3. **检查数据库服务状态**：
   ```bash
   # Docker环境
   docker-compose ps postgres
   
   # 本地环境
   sudo systemctl status postgresql
   
   # 检查数据库日志
   docker-compose logs postgres
   ```

4. **验证网络连接**：
   ```bash
   # 测试数据库端口连通性
   telnet localhost 5432
   
   # 检查防火墙设置
   sudo ufw status
   ```

5. **检查数据库表结构**：
   ```bash
   # 连接数据库
   psql -h localhost -U outlook_user -d outlook_db
   
   # 检查表是否存在
   \dt
   
   # 检查表结构
   \d account_backups
   ```

### Q: 忘记登录密码怎么办？

**A**: 可以通过以下方式重置：

1. **查看.env文件中的`APP_PASSWORD`**
   ```bash
   cat .env | grep APP_PASSWORD
   ```

2. **修改.env文件并重启服务**：
   ```bash
   # 修改密码
   sed -i 's/APP_PASSWORD=.*/APP_PASSWORD=new_password/' .env
   
   # 重启服务
   docker-compose restart outlook-email-client
   ```

3. **直接在数据库中重置**（如果上述方法无效）：
   ```bash
   # 连接数据库
   psql -h localhost -U outlook_user -d outlook_db
   
   # 查看用户表（如果存在）
   SELECT * FROM users WHERE username = 'admin';
   
   # 更新密码（根据实际表结构调整）
   UPDATE users SET password = 'new_password_hash' WHERE username = 'admin';
   ```

### Q: 如何获取OAuth2刷新令牌？

**A**: 按以下步骤操作：

1. **在Azure Portal注册应用程序**
   - 访问 [Azure Portal](https://portal.azure.com/)
   - 转到"Azure Active Directory" > "应用注册"
   - 点击"新注册"
   - 设置应用程序名称
   - 选择支持的账户类型
   - 设置重定向URI：`http://localhost:8000/auth/callback`

2. **配置API权限**
   - 在应用注册中，转到"API权限"
   - 添加"Microsoft Graph"权限
   - 添加"IMAP.AccessAsUser.All"和"offline_access"权限
   - 管理员同意授权（如果是租户应用）

3. **创建客户端密钥**
   - 转到"证书和密钥"
   - 创建新的客户端密钥
   - 复制密钥值（只显示一次）

4. **获取刷新令牌**
   ```python
   # 使用OAuth2授权流程获取刷新令牌
   import requests
   
   # 构建授权URL
   auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
   client_id = "your_client_id"
   redirect_uri = "http://localhost:8000/auth/callback"
   scope = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
   
   # 在浏览器中访问以下URL
   auth_params = {
       "client_id": client_id,
       "response_type": "code",
       "redirect_uri": redirect_uri,
       "scope": scope,
       "response_mode": "query"
   }
   
   # 获取授权码后，使用以下代码获取刷新令牌
   token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
   token_data = {
       "client_id": client_id,
       "client_secret": "your_client_secret",
       "code": "authorization_code_from_callback",
       "redirect_uri": redirect_uri,
       "grant_type": "authorization_code"
   }
   
   response = requests.post(token_url, data=token_data)
   token_info = response.json()
   refresh_token = token_info.get("refresh_token")
   ```

5. **配置账户信息**：
   - 在Web界面中添加账户，或直接编辑`accounts.json`文件

详细步骤请参考：[Microsoft OAuth2文档](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)

### Q: 邮箱账户添加失败怎么办？

**A**: 检查以下几点：

1. **确认邮箱地址格式正确**
   ```bash
   # 验证邮箱格式
   echo "user@outlook.com" | grep -E "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
   ```

2. **验证应用密码或刷新令牌有效**
   ```python
   # 测试OAuth令牌
   import requests
   
   token = "your_refresh_token"
   client_id = "your_client_id"
   
   # 尝试刷新令牌
   response = requests.post(
       "https://login.microsoftonline.com/common/oauth2/v2.0/token",
       data={
           "client_id": client_id,
           "refresh_token": token,
           "grant_type": "refresh_token"
       }
   )
   
   if response.status_code == 200:
       print("令牌有效")
   else:
       print(f"令牌无效: {response.text}")
   ```

3. **检查客户端ID配置**
   - 确认客户端ID与Azure Portal中的应用注册匹配
   - 确认重定向URI配置正确

4. **查看服务日志获取详细错误信息**：
   ```bash
   docker-compose logs outlook-email-client | grep -i error
   ```

5. **测试IMAP连接**：
   ```python
   import imaplib
   
   email = "user@outlook.com"
   password = "app_password"
   
   try:
       imap = imaplib.IMAP4_SSL("outlook.live.com", 993)
       imap.login(email, password)
       print("IMAP连接成功")
       imap.logout()
   except Exception as e:
       print(f"IMAP连接失败: {e}")
   ```

### Q: 如何备份配置数据？

**A**: 备份以下文件：

1. **配置文件**：
   ```bash
   cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. **账户数据**：
   ```bash
   cp accounts.json accounts.json.backup.$(date +%Y%m%d_%H%M%S)
   ```

3. **数据库数据**：
   ```bash
   # 本地数据库备份
   pg_dump -h localhost -U outlook_user outlook_db > database_backup_$(date +%Y%m%d_%H%M%S).sql
   
   # 云端数据库备份
   pg_dump "postgresql://username:password@host:port/dbname?sslmode=require" > database_backup_$(date +%Y%m%d_%H%M%S).sql
   
   # 压缩备份
   gzip database_backup_*.sql
   ```

4. **自动备份脚本**：
   ```bash
   #!/bin/bash
   BACKUP_DIR="/backups"
   DATE=$(date +%Y%m%d_%H%M%S)
   
   # 创建备份目录
   mkdir -p $BACKUP_DIR
   
   # 备份配置文件
   cp .env $BACKUP_DIR/.env.backup.$DATE
   cp accounts.json $BACKUP_DIR/accounts.json.backup.$DATE
   
   # 备份数据库
   docker-compose exec -T postgres pg_dump -U outlook_user outlook_db > $BACKUP_DIR/database_backup_$DATE.sql
   
   # 压缩备份
   gzip $BACKUP_DIR/database_backup_$DATE.sql
   
   # 删除7天前的备份
   find $BACKUP_DIR -name "*.backup.*" -mtime +7 -delete
   
   echo "备份完成: $DATE"
   ```

### Q: 服务启动后无法访问怎么办？

**A**: 按以下步骤排查：

1. **检查端口是否被占用**：
   ```bash
   # Windows
   netstat -ano | findstr :8000
   
   # macOS/Linux
   lsof -i :8000
   netstat -tulpn | grep :8000
   ```

2. **检查防火墙设置**：
   ```bash
   # Ubuntu/Debian
   sudo ufw status
   sudo ufw allow 8000/tcp
   
   # CentOS/RHEL
   sudo firewall-cmd --list-all
   sudo firewall-cmd --add-port=8000/tcp --permanent
   sudo firewall-cmd --reload
   
   # Windows
   # 检查Windows防火墙设置
   ```

3. **确认Docker容器正常运行**：
   ```bash
   docker-compose ps
   
   # 查看容器状态
   docker inspect outlook-manager_outlook-email-client_1
   ```

4. **查看容器日志**：
   ```bash
   docker-compose logs outlook-email-client
   
   # 查看最近的错误日志
   docker-compose logs --tail=50 outlook-email-client
   ```

5. **测试容器内部网络**：
   ```bash
   # 进入容器
   docker-compose exec outlook-email-client bash
   
   # 测试端口监听
   netstat -tulpn | grep :8000
   
   # 测试HTTP响应
   curl -I http://localhost:8000
   ```

6. **检查Docker网络**：
   ```bash
   # 列出Docker网络
   docker network ls
   
   # 检查网络详情
   docker network inspect outlook-manager_outlook-network
   ```

### Q: 账户同步功能出现错误怎么办？

**A**: 按以下步骤排查：

1. **检查服务状态**
   ```bash
   docker-compose ps
   docker-compose logs outlook-email-client
   ```

2. **验证数据库连接**
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"
   ```

3. **检查表结构**
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -c "\d account_backups"
   ```

4. **查看同步日志**
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT * FROM sync_logs ORDER BY created_at DESC LIMIT 10;"
   ```

5. **手动触发同步测试**：
   ```python
   # 测试同步功能
   import asyncio
   from app.accounts.sync import AccountSyncService
   
   async def test_sync():
       service = AccountSyncService()
       result = await service.sync_account("account_id")
       print(f"同步结果: {result}")
   
   asyncio.run(test_sync())
   ```

6. **检查IMAP连接**：
   ```python
   import imaplib
   import ssl
   
   def test_imap_connection(email, password):
       try:
           # 创建SSL上下文
           context = ssl.create_default_context()
           
           # 连接IMAP服务器
           imap = imaplib.IMAP4_SSL("outlook.live.com", 993, ssl_context=context)
           
           # 登录
           imap.login(email, password)
           
           # 选择收件箱
           imap.select("INBOX")
           
           # 搜索邮件
           status, messages = imap.search(None, "ALL")
           
           print(f"IMAP连接成功，找到 {len(messages[0].split())} 封邮件")
           
           # 登出
           imap.logout()
           return True
       except Exception as e:
           print(f"IMAP连接失败: {e}")
           return False
   ```

### Q: 数据库连接超时怎么办？

**A**: 可能是网络问题或数据库负载过高。

1. **检查数据库性能**：
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT * FROM pg_stat_activity;"
   ```

2. **调整连接超时配置**：
   ```bash
   # 在.env文件中增加超时时间
   CONNECTION_TIMEOUT=60
   SOCKET_TIMEOUT=30
   ```

3. **检查数据库服务器资源使用情况**：
   ```bash
   # 检查CPU和内存使用
   top
   htop
   
   # 检查磁盘I/O
   iostat -x 1
   
   # 检查数据库连接数
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT count(*) FROM pg_stat_activity;"
   ```

4. **优化数据库配置**：
   ```sql
   -- 调整PostgreSQL配置
   -- 在postgresql.conf中设置
   max_connections = 100
   shared_buffers = 256MB
   effective_cache_size = 1GB
   work_mem = 4MB
   maintenance_work_mem = 64MB
   ```

5. **重启数据库服务**：
   ```bash
   # Docker环境
   docker-compose restart postgres
   
   # 本地环境
   sudo systemctl restart postgresql
   ```

### Q: 如何优化数据库性能？

**A**: 定期维护数据库：

1. **更新表统计信息**：
   ```sql
   ANALYZE account_backups;
   ANALYZE sync_logs;
   ```

2. **清理无用数据**：
   ```sql
   VACUUM account_backups;
   VACUUM sync_logs;
   
   -- 完整清理（会锁定表）
   VACUUM FULL account_backups;
   ```

3. **重建索引**：
   ```sql
   REINDEX TABLE account_backups;
   REINDEX TABLE sync_logs;
   ```

4. **监控同步性能**：
   ```sql
   -- 查看同步统计
   SELECT
       operation,
       status,
       COUNT(*) as count,
       MAX(created_at) as last_operation
   FROM sync_logs
   GROUP BY operation, status
   ORDER BY last_operation DESC;
   ```

5. **检查慢查询**：
   ```sql
   -- 启用慢查询日志
   -- 在postgresql.conf中设置
   log_min_duration_statement = 1000  # 记录超过1秒的查询
   log_statement = 'all'              # 记录所有SQL语句
   
   -- 查看慢查询
   SELECT query, mean_time, calls, total_time
   FROM pg_stat_statements
   ORDER BY mean_time DESC
   LIMIT 10;
   ```

6. **优化查询**：
   ```sql
   -- 创建适当的索引
   CREATE INDEX IF NOT EXISTS idx_account_backups_email ON account_backups(email);
   CREATE INDEX IF NOT EXISTS idx_sync_logs_created_at ON sync_logs(created_at);
   CREATE INDEX IF NOT EXISTS idx_sync_logs_status ON sync_logs(status);
   ```

## 🔧 高级故障排除

### 1. 内存问题诊断

```bash
# 检查内存使用
free -h
docker stats --no-stream

# 检查内存泄漏
docker-compose exec outlook-email-client python -c "
import psutil
import gc
print(f'内存使用: {psutil.virtual_memory().percent}%')
print(f'对象数量: {len(gc.get_objects())}')
"
```

### 2. CPU问题诊断

```bash
# 检查CPU使用
top
htop
docker stats --no-stream

# 检查CPU密集型进程
docker-compose exec outlook-email-client python -c "
import psutil
for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
    if proc.info['cpu_percent'] > 10:
        print(proc.info)
"
```

### 3. 磁盘空间问题

```bash
# 检查磁盘使用
df -h
du -sh /var/lib/docker/

# 清理Docker
docker system prune -a
docker volume prune
```

### 4. 网络问题诊断

```bash
# 检查网络连接
netstat -tulpn
ss -tulpn

# 测试DNS解析
nslookup outlook.live.com
dig outlook.live.com

# 测试网络延迟
ping outlook.live.com
traceroute outlook.live.com
```

## 📊 性能监控

### 1. 应用性能监控

```python
# 添加性能监控中间件
import time
import logging
from fastapi import Request, Response

logger = logging.getLogger(__name__)

async def performance_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    if process_time > 1.0:  # 记录超过1秒的请求
        logger.warning(f"Slow request: {request.url} took {process_time:.2f}s")
    
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

### 2. 数据库性能监控

```sql
-- 创建性能监控视图
CREATE OR REPLACE VIEW performance_stats AS
SELECT 
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation
FROM pg_stats 
WHERE schemaname = 'public';

-- 监控表大小
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public';
```

### 3. 系统资源监控

```bash
# 创建监控脚本
#!/bin/bash
LOG_FILE="/var/log/outlook-manager-monitor.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# 记录系统状态
echo "[$DATE] System Status:" >> $LOG_FILE
echo "Memory: $(free -h | grep Mem)" >> $LOG_FILE
echo "Disk: $(df -h /)" >> $LOG_FILE
echo "Load: $(uptime)" >> $LOG_FILE

# 记录Docker状态
echo "Docker Status:" >> $LOG_FILE
docker stats --no-stream >> $LOG_FILE

echo "---" >> $LOG_FILE
```

## 🚨 紧急恢复程序

### 1. 服务完全宕机

```bash
# 快速恢复脚本
#!/bin/bash

echo "开始紧急恢复..."

# 1. 检查Docker服务
sudo systemctl status docker
if [ $? -ne 0 ]; then
    echo "启动Docker服务..."
    sudo systemctl start docker
fi

# 2. 启动数据库
docker-compose up -d postgres

# 等待数据库启动
sleep 10

# 3. 检查数据库连接
docker-compose exec postgres pg_isready -U outlook_user

# 4. 启动应用
docker-compose up -d outlook-email-client

# 5. 检查服务状态
docker-compose ps

echo "恢复完成"
```

### 2. 数据库损坏

```bash
# 数据库恢复脚本
#!/bin/bash

BACKUP_FILE=$1
DB_NAME="outlook_db"
DB_USER="outlook_user"

if [ -z "$BACKUP_FILE" ]; then
    echo "用法: $0 <备份文件>"
    exit 1
fi

echo "开始恢复数据库..."

# 1. 停止应用
docker-compose stop outlook-email-client

# 2. 删除现有数据库
docker-compose exec postgres psql -U $DB_USER -c "DROP DATABASE IF EXISTS $DB_NAME;"
docker-compose exec postgres psql -U $DB_USER -c "CREATE DATABASE $DB_NAME;"

# 3. 恢复数据
if [[ $BACKUP_FILE == *.gz ]]; then
    gunzip -c $BACKUP_FILE | docker-compose exec -T postgres psql -U $DB_USER $DB_NAME
else
    docker-compose exec -T postgres psql -U $DB_USER $DB_NAME < $BACKUP_FILE
fi

# 4. 重启应用
docker-compose start outlook-email-client

echo "数据库恢复完成"
```

## 📞 获取帮助

如果以上解决方案无法解决您的问题，请：

1. **收集诊断信息**：
   ```bash
   # 收集系统信息
   docker-compose version
   docker version
   uname -a
   
   # 收集日志
   docker-compose logs > outlook-manager-logs.txt
   
   # 收集配置
   cat .env > config.txt
   cat docker-compose.yml >> config.txt
   ```

2. **提交问题报告**：
   - 在GitHub Issues中提交问题
   - 附上收集的诊断信息
   - 详细描述问题现象和重现步骤

3. **联系技术支持**：
   - 查看项目文档获取联系方式
   - 发送邮件至技术支持团队

---

**💡 提示**：定期检查系统状态，保持系统和依赖更新，可以有效预防许多常见问题。