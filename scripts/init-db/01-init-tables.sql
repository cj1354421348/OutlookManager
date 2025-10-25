-- PostgreSQL初始化脚本
-- 创建OutlookManager应用所需的表结构
-- 与app/accounts/sync.py中的表结构保持一致

-- 创建账户备份表
CREATE TABLE IF NOT EXISTS account_backups (
    "email" VARCHAR(255) NOT NULL PRIMARY KEY,
    "data" TEXT NOT NULL,
    "checksum" CHAR(64) NOT NULL,
    "tags" TEXT,
    "note" TEXT,
    "is_deleted" BOOLEAN NOT NULL DEFAULT FALSE,
    "source" VARCHAR(32) NOT NULL DEFAULT 'unknown',
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建标签表
CREATE TABLE IF NOT EXISTS account_backups_tags (
    "email" VARCHAR(255) NOT NULL,
    "tag" VARCHAR(255) NOT NULL,
    PRIMARY KEY ("email", "tag")
);

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS "idx_account_backups_tags_email" ON "account_backups_tags" ("email");

-- 创建触发器函数，自动更新updated_at字段
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为account_backups表创建触发器
CREATE TRIGGER update_account_backups_updated_at
    BEFORE UPDATE ON account_backups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建同步日志表（可选，用于跟踪同步操作）
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_sync_logs_account_id ON sync_logs(account_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_created_at ON sync_logs(created_at);

-- 输出初始化完成信息
DO $$
BEGIN
    RAISE NOTICE 'OutlookManager数据库初始化完成';
    RAISE NOTICE '已创建表: account_backups, account_backups_tags, sync_logs';
    RAISE NOTICE '已创建索引和触发器';
END $$;