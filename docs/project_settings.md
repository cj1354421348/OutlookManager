# 项目配置规范

## 1. 核心哲学
- **Good Taste**: 追求简洁、直观的代码和架构。
- **实用主义**: 解决实际问题，不搞过度设计。
- **Never break userspace**: 在未经允许的情况下，保证现有功能的稳定性。

## 2. 时间与时区规范
- **统一时区**: 全项目强制使用 **东八区 (Asia/Shanghai)**。
- **实现方式**:
  - 所有时间获取通过 `app.core.time.now()` (需新建) 或标准库带时区的方式。
  - 禁止使用 `datetime.utcnow()` 或不带时区的 `datetime.now()`。
  - 数据库中 `TIMESTAMP` 字段建议存储为带时区的时间，或者明确文档约定为 Asia/Shanghai。

## 3. 账户数据结构与数据库 Schema

### 3.1 数据库表: `account_backups`

| 字段名 | 类型 | 说明 | 来源/备注 |
| :--- | :--- | :--- | :--- |
| **email** | VARCHAR(255) | 主键 | 账户邮箱 |
| **auth_data** | JSONB / TEXT | 认证数据 | 仅包含 `{"refresh_token": "...", "client_id": "..."}` |
| **status** | VARCHAR(50) | 账户状态 | 如 `active`, `expired`, `locked` |
| **status_updated_at** | TIMESTAMP | 状态更新时间 | 记录状态最后一次变更的时间 |
| **status_reason** | TEXT | 状态原因 | 如 `token_expired`, `login_failed` |
| **token_failures** | JSONB / TEXT | 令牌失败详情 | JSON 对象，包含 `count`, `first_failure_at` 等 |
| **tags** | TEXT | 标签 | 逗号分隔或 JSON 字符串 |
| **note** | TEXT | 备注 | 用户备注 |
| **last_modified_at** | TIMESTAMP | 最后修改时间 | **同步核心锚点**，用于解决冲突 |
| **is_deleted** | BOOLEAN | 软删除标记 | 默认为 FALSE |

### 3.2 本地文件: `accounts.json`

结构示例：
```json
{
  "user@outlook.com": {
    "refresh_token": "...",
    "client_id": "...",
    "status": "expired",
    "status_updated_at": "2025-11-10T14:00:03+08:00",
    "status_reason": "token_expired",
    "token_failures": {
      "count": 8,
      "last_error_message": "..."
    },
    "tags": ["work"],
    "note": "Main account",
    "last_modified_at": "2025-12-06T13:00:00+08:00"
  }
}
```

## 4. 同步策略 (Timestamp-based)

- **核心原则**: **Newer Wins (新覆盖旧)**
- **比较字段**: `last_modified_at`
- **逻辑**:
  1. **Pull**: 如果 `Remote.last_modified_at > Local.last_modified_at`，则 `Local = Remote`。
  2. **Push**: 如果 `Local.last_modified_at > Remote.last_modified_at`，则 `Remote = Local`。
  3. **Equal**: 跳过，不做操作。
- **初始化**: 若本地数据缺失 `last_modified_at`，默认视为当前时间或特定旧时间（取决于迁移策略），并补全该字段。

## 5. 术语表
- **DB**: 远程 PostgreSQL 数据库。
- **Local**: 本地 `accounts.json` 文件。
