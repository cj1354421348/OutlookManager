# 账户同步使用说明

本文档说明如何使用OutlookManager的账户同步功能，包括推送、拉取、冲突处理和故障排除。

## 📋 配置说明

**详细的数据库配置说明请参考：[配置指南](configuration.md)**

本文档专注于账户同步功能的使用说明，不包含配置说明。

## 🔄 功能概览

账户同步功能允许您在本地 `accounts.json` 文件和服务器数据库之间同步邮箱账户数据：

- **⬆️ 推送到服务器**：将本地的 `accounts.json` 内容备份到服务器数据库
- **⬇️ 拉取到本地**：将服务器数据库中的备份恢复到本地 `accounts.json`

## 📝 使用步骤

### 基本操作流程

1. **登录管理界面**，进入"邮箱账户"页面
2. **备份数据到服务器**：
   - 点击"⬆️ 推送到服务器"按钮
   - 等待系统提示"推送完成"
3. **从服务器恢复数据**：
   - 点击"⬇️ 拉取到本地"按钮
   - 根据提示确认"拉取完成"
4. **查看操作结果**：
   - 按钮旁会显示实时状态提示
   - 可在日志中查看详细操作记录

### 操作界面说明

- **推送按钮**：将本地账户数据上传到服务器
- **拉取按钮**：从服务器下载账户数据到本地
- **状态指示器**：显示当前操作状态和结果
- **操作日志**：记录所有同步操作的详细信息

## ⚖️ 冲突处理策略

### 默认策略

系统默认采用 **本地优先** 策略：
- 当本地和服务器数据不一致时，优先保留本地 `accounts.json` 的内容
- 适用于个人使用场景，确保本地配置不被意外覆盖

### 远程优先策略

如需采用 **服务器优先** 策略：

1. **修改配置**：
   ```bash
   # 在.env文件中设置
   ACCOUNTS_SYNC_CONFLICT=prefer_remote
   ```

2. **重启服务**：
   ```bash
   docker-compose restart
   ```

3. **验证配置**：
   - 检查服务日志确认配置生效
   - 进行测试同步验证策略是否正确

### 策略选择建议

| 使用场景 | 推荐策略 | 说明 |
|---------|---------|------|
| **个人使用** | `prefer_local` | 保护本地配置，避免意外覆盖 |
| **团队协作** | `prefer_remote` | 确保团队成员使用统一的配置 |
| **备份恢复** | `prefer_remote` | 从备份恢复时优先使用服务器数据 |

## 常见提示

### 错误信息及解决方案

- **"同步未配置"**：说明数据库连接信息还未就绪，请联系运维补齐环境变量后再操作。
  
  解决方案：
  1. 检查 `.env` 文件中的数据库配置
  2. 确认PostgreSQL服务正在运行
  3. 验证数据库用户权限
  4. 确保DATABASE_URL或ACCOUNTS_DB_*配置正确

- **"同步到服务器失败"或"从服务器同步失败"**：通常是数据库暂时不可用，稍后重试即可；如多次失败，请反馈给运维排查。
  
  解决方案：
  1. 检查数据库连接状态
  2. 验证表是否存在：`psql -h localhost -U outlook_user -d outlook_db -c "\dt"`
  3. 检查网络连接和防火墙设置

- **"数据库连接超时"**：可能是网络问题或数据库负载过高。
  
  解决方案：
  1. 检查数据库性能：`psql -h localhost -U outlook_user -d outlook_db -c "SELECT * FROM pg_stat_activity;"`
  2. 调整连接超时配置
  3. 检查数据库服务器资源使用情况

### 故障排除步骤

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

### 性能优化建议

1. **定期维护数据库**
   ```sql
   -- 更新表统计信息
   ANALYZE account_backups;
   
   -- 清理无用数据
   VACUUM account_backups;
   ```

2. **监控同步性能**
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


## 🔧 故障排除

### 常见错误信息及解决方案

#### 1. "同步未配置"

**错误描述**：系统提示同步功能未配置，无法进行同步操作。

**可能原因**：
- 数据库连接信息未正确配置
- PostgreSQL服务未启动
- 数据库用户权限不足

**解决方案**：
1. **检查配置文件**：
   ```bash
   # 检查.env文件中的数据库配置
   cat .env | grep ACCOUNTS_DB_
   ```

2. **验证数据库连接**：
   ```bash
   # 测试数据库连接
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"
   ```

3. **确认服务状态**：
   ```bash
   # 检查PostgreSQL服务状态
   docker-compose ps
   docker-compose logs postgres
   ```

4. **检查数据库用户权限**：
   ```bash
   # 验证用户权限
   psql -h localhost -U outlook_user -d outlook_db -c "\du"
   ```

#### 2. "同步到服务器失败"或"从服务器同步失败"

**错误描述**：同步操作执行失败，无法完成数据传输。

**可能原因**：
- 数据库暂时不可用
- 网络连接问题
- 数据库表不存在或损坏
- 磁盘空间不足

**解决方案**：
1. **检查数据库连接状态**：
   ```bash
   # 测试数据库连接
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"
   ```

2. **验证表结构**：
   ```bash
   # 检查表是否存在
   psql -h localhost -U outlook_user -d outlook_db -c "\dt"
   
   # 检查表结构
   psql -h localhost -U outlook_user -d outlook_db -c "\d account_backups"
   ```

3. **检查网络连接**：
   ```bash
   # 测试网络连通性
   ping postgres_host
   telnet postgres_host 5432
   ```

4. **查看系统日志**：
   ```bash
   # 查看应用日志
   docker-compose logs outlook-email-client
   
   # 查看数据库日志
   docker-compose logs postgres
   ```

#### 3. "数据库连接超时"

**错误描述**：数据库连接操作超时，无法在指定时间内建立连接。

**可能原因**：
- 网络延迟过高
- 数据库负载过重
- 连接池配置不当
- 防火墙阻拦

**解决方案**：
1. **检查数据库性能**：
   ```sql
   -- 查看活跃连接数
   SELECT count(*) FROM pg_stat_activity;
   
   -- 查看慢查询
   SELECT query, mean_time, calls 
   FROM pg_stat_statements 
   ORDER BY mean_time DESC 
   LIMIT 10;
   ```

2. **调整超时配置**：
   ```bash
   # 在.env文件中增加超时时间
   CONNECTION_TIMEOUT=60
   SOCKET_TIMEOUT=30
   ```

3. **优化数据库性能**：
   ```sql
   -- 更新表统计信息
   ANALYZE account_backups;
   
   -- 清理无用数据
   VACUUM account_backups;
   ```

4. **检查防火墙设置**：
   ```bash
   # 检查端口是否开放
   telnet postgres_host 5432
   
   # 检查防火墙规则
   # Ubuntu/Debian
   sudo ufw status
   
   # CentOS/RHEL
   sudo firewall-cmd --list-all
   ```

### 诊断步骤

#### 完整故障排除流程

1. **检查服务状态**
   ```bash
   # 检查所有服务状态
   docker-compose ps
   
   # 查看应用日志
   docker-compose logs outlook-email-client
   
   # 查看数据库日志
   docker-compose logs postgres
   ```

2. **验证数据库连接**
   ```bash
   # 基本连接测试
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"
   
   # 检查数据库大小
   psql -h localhost -U outlook_user -d outlook_db -c "SELECT pg_size_pretty(pg_database_size('outlook_db'));"
   ```

3. **检查表结构**
   ```bash
   # 列出所有表
   psql -h localhost -U outlook_user -d outlook_db -c "\dt"
   
   # 检查同步表结构
   psql -h localhost -U outlook_user -d outlook_db -c "\d account_backups"
   
   # 检查同步日志表
   psql -h localhost -U outlook_user -d outlook_db -c "\d sync_logs"
   ```

4. **查看同步日志**
   ```bash
   # 查看最近的同步操作
   psql -h localhost -U outlook_user -d outlook_db -c "
   SELECT * FROM sync_logs 
   ORDER BY created_at DESC 
   LIMIT 10;
   "
   
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

5. **测试手动同步**
   ```bash
   # 手动测试数据库写入
   psql -h localhost -U outlook_user -d outlook_db -c "
   INSERT INTO account_backups (account_data, created_at) 
   VALUES ('{\"test\": \"data\"}', NOW());
   "
   
   # 验证数据写入
   psql -h localhost -U outlook_user -d outlook_db -c "
   SELECT * FROM account_backups 
   ORDER BY created_at DESC 
   LIMIT 1;
   "
   ```

### 性能优化建议

#### 数据库维护

1. **定期维护数据库**
   ```sql
   -- 更新表统计信息
   ANALYZE account_backups;
   
   -- 清理无用数据
   VACUUM account_backups;
   
   -- 重建索引
   REINDEX TABLE account_backups;
   ```

2. **监控同步性能**
   ```sql
   -- 查看同步统计
   SELECT
       operation,
       status,
       COUNT(*) as count,
       MAX(created_at) as last_operation,
       AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration
   FROM sync_logs
   GROUP BY operation, status
   ORDER BY last_operation DESC;
   ```

3. **清理历史日志**
   ```sql
   -- 清理30天前的同步日志
   DELETE FROM sync_logs 
   WHERE created_at < NOW() - INTERVAL '30 days';
   ```

#### 系统优化

1. **调整连接池大小**
   ```bash
   # 在.env文件中配置
   MAX_CONNECTIONS=10
   ```

2. **优化缓存设置**
   ```bash
   # 增加缓存时间
   CACHE_EXPIRE_TIME=300
   ```

3. **启用健康检查**
   ```bash
   # 在docker-compose.yml中添加
   healthcheck:
     test: ["CMD", "pg_isready", "-U", "outlook_user"]
     interval: 30s
     timeout: 10s
     retries: 3
   ```

## 📞 获取帮助

如果以上解决方案无法解决您的问题，请：

1. **收集诊断信息**：
   - 系统日志
   - 错误截图
   - 配置文件（隐藏敏感信息）

2. **联系技术支持**：
   - 提交GitHub Issue
   - 联系开发团队
   - 查看社区论坛

3. **参考相关文档**：
   - [PostgreSQL数据库管理指南](postgresql-setup.md)
   - [配置指南](configuration.md)
   - [README.md - 常见问题解答](../README.md#常见问题解答)
