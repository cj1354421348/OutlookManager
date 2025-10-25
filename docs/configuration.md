# 配置指南

本指南详细介绍Outlook邮件管理系统的各项配置选项。

## 快速配置

对于大多数用户，系统已经预配置了默认设置，可以直接使用：

1. **确保PostgreSQL数据库可用**
2. **使用默认配置启动**：
   ```bash
   docker-compose up -d
   ```
3. **使用默认认证信息登录**：
   - 用户名：`admin`
   - 密码：`admin`

## 环境配置文件

### 创建配置文件

编辑项目根目录的`.env`文件（如果需要重置配置，可以复制`docker.env.example`为`.env`）：

```bash
# 复制示例配置文件
cp docker.env.example .env
```

### 配置方式选择

**方式1：使用完整连接字符串（推荐云端数据库）**
```bash
DATABASE_URL=postgresql://username:password@host:port/dbname?sslmode=require
```

**方式2：使用单独参数（推荐本地数据库）**
```bash
# 数据库连接配置
ACCOUNTS_DB_HOST=localhost          # 数据库服务器地址
ACCOUNTS_DB_PORT=5432               # 数据库端口
ACCOUNTS_DB_USER=outlook_user       # 数据库用户名
ACCOUNTS_DB_PASSWORD=secure_password # 数据库密码
ACCOUNTS_DB_NAME=outlook_db         # 数据库名称
ACCOUNTS_DB_TABLE=account_backups   # 数据表名称
```

**注意**：如果设置了`DATABASE_URL`，它会覆盖所有`ACCOUNTS_DB_*`配置。

## 数据库配置

### PostgreSQL配置示例

**Docker Compose环境**
```bash
# 在.env文件中配置
ACCOUNTS_DB_HOST=postgres
ACCOUNTS_DB_PORT=5432
ACCOUNTS_DB_USER=outlook_user
ACCOUNTS_DB_PASSWORD=your_secure_password
ACCOUNTS_DB_NAME=outlook_db
```

**本地PostgreSQL环境**
```bash
# 在.env文件中配置
ACCOUNTS_DB_HOST=localhost
ACCOUNTS_DB_PORT=5432
ACCOUNTS_DB_USER=outlook_user
ACCOUNTS_DB_PASSWORD=your_secure_password
ACCOUNTS_DB_NAME=outlook_db
```

**云端PostgreSQL环境（如Neon.tech）**
```bash
# 在.env文件中配置
DATABASE_URL=postgresql://username:password@host:port/dbname?sslmode=require
```

### 数据库初始化

系统首次启动时会自动创建必要的表结构。如果需要手动初始化：

```bash
# 使用本地PostgreSQL
psql -h localhost -U outlook_user -d outlook_db -f scripts/init-db/01-init-tables.sql

# 使用云端数据库
psql "postgresql://username:password@host:port/dbname?sslmode=require" -f scripts/init-db/01-init-tables.sql
```

### 验证数据库连接

```bash
# 测试数据库连接
psql -h localhost -U outlook_user -d outlook_db -p 5432

# 如果连接成功，应该看到数据库提示符
outlook_db=#
```

## 应用认证配置

### 默认认证信息

系统默认使用以下认证信息：
- 用户名：`admin`
- 密码：`admin`

### 修改认证信息

如需修改默认认证信息，编辑`.env`文件：

```bash
# 应用认证配置
APP_USERNAME=your_username    # 修改用户名
APP_PASSWORD=your_password    # 修改密码
```

修改后重启服务：
```bash
docker-compose restart
```

### 会话配置

```bash
# 会话配置
SESSION_COOKIE_SECURE=false   # 生产环境建议设置为true
SESSION_COOKIE_SAMESITE=lax   # CSRF保护级别
```

## 邮箱账户配置

### accounts.json文件说明

系统使用`accounts.json`文件存储邮箱账户信息。该文件会在首次启动时自动创建。

文件格式示例：
```json
{
  "accounts": [
    {
      "email": "user1@outlook.com",
      "password": "app_password",
      "refresh_token": "oauth_refresh_token",
      "client_id": "oauth_client_id"
    }
  ]
}
```

### OAuth2/刷新令牌获取方法

1. **注册Azure应用程序**：
   - 访问 [Azure Portal](https://portal.azure.com/)
   - 创建新的应用程序注册
   - 获取客户端ID和客户端密钥

2. **获取刷新令牌**：
   - 使用OAuth2授权流程获取刷新令牌
   - 确保请求以下权限：`https://outlook.office.com/IMAP.AccessAsUser.All offline_access`

3. **配置账户信息**：
   - 在Web界面中添加账户，或直接编辑`accounts.json`文件

### 批量账户配置

批量添加账户时，使用以下格式：
```
邮箱地址----应用密码----刷新令牌----客户端ID
```

示例：
```
user1@outlook.com----password1----token1----client1
user2@outlook.com----password2----token2----client2
```

## 高级配置选项

### IMAP连接配置

```bash
# IMAP服务器配置
IMAP_SERVER=outlook.live.com    # IMAP服务器地址
IMAP_PORT=993                   # IMAP端口
MAX_CONNECTIONS=5               # 最大连接数
CONNECTION_TIMEOUT=30          # 连接超时时间（秒）
SOCKET_TIMEOUT=15              # Socket超时时间（秒）
```

### 缓存配置

```bash
# 缓存配置
CACHE_EXPIRE_TIME=60           # 缓存过期时间（秒）
```

### 同步配置

```bash
# 同步冲突策略
ACCOUNTS_SYNC_CONFLICT=prefer_local  # prefer_local 或 prefer_remote
```

### 开发环境配置

```bash
# 调试模式
DEBUG=true
LOG_LEVEL=debug  # debug, info, warning, error, critical

# 性能分析（可选）
ENABLE_PROFILING=true
```

### 生产环境配置

```bash
# 安全配置
SESSION_COOKIE_SECURE=true
APP_PASSWORD=your_secure_password

# 性能优化
MAX_CONNECTIONS=10
CACHE_EXPIRE_TIME=300

# 健康检查
HEALTHCHECK_INTERVAL=30s
HEALTHCHECK_TIMEOUT=10s
```

## 配置验证

### 1. 验证服务启动

```bash
# 检查服务状态
docker-compose ps

# 查看启动日志
docker-compose logs outlook-email-client
```

### 2. 验证数据库连接

**方式1：使用psql命令行**
```bash
# 本地数据库
psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"

# 云端数据库
psql "postgresql://username:password@host:port/dbname?sslmode=require" -c "SELECT 1;"
```

**方式2：在容器内测试**
```bash
# 在容器内测试数据库连接
docker exec outlook-email-client python -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        user='outlook_user',
        password='secure_password',
        database='outlook_db'
    )
    print('数据库连接成功')
    conn.close()
except Exception as e:
    print(f'数据库连接失败: {e}')
"
```

**方式3：检查表结构**
```bash
# 检查表是否存在
psql -h localhost -U outlook_user -d outlook_db -c "\dt"

# 检查表结构
psql -h localhost -U outlook_user -d outlook_db -c "\d account_backups"
```

### 3. 验证Web界面

1. 访问 http://localhost:8000
2. 使用默认认证信息登录（admin/admin）
3. 确认能够看到管理界面

### 4. 验证API接口

```bash
# 测试API状态
curl http://localhost:8000/api

# 应该返回类似以下内容：
{"status": "ok", "message": "Outlook Email Manager API is running"}
```

### 5. 验证账户同步功能

```bash
# 检查同步日志
psql -h localhost -U outlook_user -d outlook_db -c "SELECT * FROM sync_logs ORDER BY created_at DESC LIMIT 10;"

# 查看同步统计
psql -h localhost -U outlook_user -d outlook_db -c "
SELECT
    operation,
    status,
    COUNT(*) as count,
    MAX(created_at) as last_operation
FROM sync_logs
GROUP BY operation, status
ORDER BY last_operation DESC;
"
```

## 配置最佳实践

### 1. 安全配置

- **生产环境**：始终设置强密码
- **HTTPS**：在生产环境中启用HTTPS
- **会话安全**：设置`SESSION_COOKIE_SECURE=true`
- **数据库安全**：使用强密码和适当的权限

### 2. 性能优化

- **连接池**：根据负载调整`MAX_CONNECTIONS`
- **缓存**：适当设置`CACHE_EXPIRE_TIME`
- **数据库**：定期执行`VACUUM`和`ANALYZE`

### 3. 监控配置

- **日志级别**：生产环境使用`info`或`warning`
- **健康检查**：配置适当的检查间隔
- **性能监控**：考虑启用`ENABLE_PROFILING`

### 4. 备份策略

- **配置文件**：定期备份`.env`和`accounts.json`
- **数据库**：设置定期数据库备份
- **版本控制**：将配置文件模板纳入版本控制

## 环境特定配置

### 开发环境

```bash
# 开发环境配置示例
DEBUG=true
LOG_LEVEL=debug
ACCOUNTS_DB_HOST=localhost
ACCOUNTS_DB_DEV_NAME=outlook_dev_db
SESSION_COOKIE_SECURE=false
```

### 测试环境

```bash
# 测试环境配置示例
DEBUG=false
LOG_LEVEL=info
ACCOUNTS_DB_HOST=test-db-server
ACCOUNTS_DB_NAME=outlook_test_db
SESSION_COOKIE_SECURE=false
```

### 生产环境

```bash
# 生产环境配置示例
DEBUG=false
LOG_LEVEL=warning
ACCOUNTS_DB_HOST=prod-db-server
ACCOUNTS_DB_NAME=outlook_prod_db
SESSION_COOKIE_SECURE=true
APP_PASSWORD=very_secure_password
MAX_CONNECTIONS=20
CACHE_EXPIRE_TIME=600
```

## 配置模板

### 基础配置模板

```bash
# 基础配置模板
# 数据库配置
ACCOUNTS_DB_HOST=localhost
ACCOUNTS_DB_PORT=5432
ACCOUNTS_DB_USER=outlook_user
ACCOUNTS_DB_PASSWORD=your_password
ACCOUNTS_DB_NAME=outlook_db

# 应用配置
APP_USERNAME=admin
APP_PASSWORD=admin
DEBUG=false
LOG_LEVEL=info

# IMAP配置
IMAP_SERVER=outlook.live.com
IMAP_PORT=993
MAX_CONNECTIONS=5
CONNECTION_TIMEOUT=30
SOCKET_TIMEOUT=15

# 缓存配置
CACHE_EXPIRE_TIME=60

# 同步配置
ACCOUNTS_SYNC_CONFLICT=prefer_local

# 会话配置
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
```

更多配置问题请参考[故障排除指南](troubleshooting.md)。