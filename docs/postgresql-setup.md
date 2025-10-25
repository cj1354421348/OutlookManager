# PostgreSQL数据库管理指南

本文档说明如何管理OutlookManager的PostgreSQL数据库，包括安装、维护、备份和恢复操作。

## 📋 配置说明

**详细的数据库配置说明请参考：[配置指南](configuration.md)**

本文档专注于数据库的管理操作，不包含配置说明。

## 数据库管理

### 连接数据库
```bash
# 本地Docker
docker exec -it outlook-postgres psql -U outlook_user -d outlook_db

# 云端数据库
psql "postgresql://username:password@host:port/dbname?sslmode=require"
```

### 备份数据库
```bash
# 本地Docker
docker exec outlook-postgres pg_dump -U outlook_user outlook_db > backup.sql

# 云端数据库
pg_dump "postgresql://username:password@host:port/dbname?sslmode=require" > backup.sql
```

### 恢复数据库
```bash
# 本地Docker
docker exec -i outlook-postgres psql -U outlook_user outlook_db < backup.sql

# 云端数据库
psql "postgresql://username:password@host:port/dbname?sslmode=require" < backup.sql

#### 本地PostgreSQL环境
```bash
# 连接本地PostgreSQL
psql -h localhost -U outlook_user -d outlook_db
```

### 数据库备份

#### 完整备份
```bash
# 本地Docker环境
docker exec outlook-postgres pg_dump -U outlook_user outlook_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 云端数据库
pg_dump "postgresql://username:password@host:port/dbname?sslmode=require" > backup_$(date +%Y%m%d_%H%M%S).sql

# 本地PostgreSQL环境
pg_dump -h localhost -U outlook_user outlook_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### 压缩备份
```bash
# 压缩备份文件
pg_dump -h localhost -U outlook_user outlook_db | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

#### 仅备份数据（不包含结构）
```bash
pg_dump -h localhost -U outlook_user --data-only outlook_db > data_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 数据库恢复

#### 从备份文件恢复
```bash
# 本地Docker环境
docker exec -i outlook-postgres psql -U outlook_user outlook_db < backup.sql

# 云端数据库
psql "postgresql://username:password@host:port/dbname?sslmode=require" < backup.sql

# 本地PostgreSQL环境
psql -h localhost -U outlook_user outlook_db < backup.sql
```

#### 从压缩备份恢复
```bash
# 从压缩文件恢复
gunzip -c backup.sql.gz | psql -h localhost -U outlook_user outlook_db
```

### 数据库维护

#### 查看数据库状态
```bash
# 查看数据库大小
psql -h localhost -U outlook_user -d outlook_db -c "SELECT pg_size_pretty(pg_database_size('outlook_db'));"

# 查看表大小
psql -h localhost -U outlook_user -d outlook_db -c "SELECT schemaname,tablename,pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname = 'public';"

# 查看连接数
psql -h localhost -U outlook_user -d outlook_db -c "SELECT count(*) FROM pg_stat_activity;"
```

#### 性能优化
```sql
-- 更新表统计信息
ANALYZE account_backups;

-- 清理无用数据
VACUUM account_backups;

-- 完整清理（包括索引优化）
VACUUM FULL account_backups;

-- 重建索引
REINDEX TABLE account_backups;
```

#### 监控查询
```sql
-- 查看活跃连接
SELECT * FROM pg_stat_activity WHERE state = 'active';

-- 查看慢查询
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

-- 查看表锁
SELECT t.relname AS table_name, l.locktype, l.mode 
FROM pg_locks l 
JOIN pg_class t ON l.relation = t.oid 
WHERE NOT l.granted;
```

### 数据库安全管理

#### 用户管理
```sql
-- 创建只读用户
CREATE USER readonly_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE outlook_db TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- 创建备份用户
CREATE USER backup_user WITH PASSWORD 'backup_password';
GRANT CONNECT ON DATABASE outlook_db TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
```

#### 权限管理
```sql
-- 查看用户权限
\du

-- 查看表权限
SELECT grantee, privilege_type 
FROM information_schema.role_table_grants 
WHERE table_name = 'account_backups';
```

## 🔧 故障排除

### 常见问题解决

#### 1. 连接超时
```bash
# 检查网络连接
ping postgres_host

# 检查端口是否开放
telnet postgres_host 5432

# 查看PostgreSQL服务状态
docker exec outlook-postgres pg_isready
```

#### 2. 权限问题
```bash
# 检查用户权限
psql -h localhost -U outlook_user -d outlook_db -c "\du"

# 重新授权
psql -h localhost -U postgres -d outlook_db -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO outlook_user;"
```

#### 3. 磁盘空间不足
```bash
# 检查磁盘使用情况
df -h

# 清理日志文件
docker exec outlook-postgres psql -U postgres -c "SELECT pg_size_pretty(pg_database_size('outlook_db'));"
```

## 📊 监控和日志

### 启用日志记录
```bash
# 在postgresql.conf中配置
log_statement = 'all'
log_duration = on
log_min_duration_statement = 1000
```

### 监控同步性能
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

-- 查看最近的同步日志
SELECT * FROM sync_logs 
ORDER BY created_at DESC 
LIMIT 20;
```