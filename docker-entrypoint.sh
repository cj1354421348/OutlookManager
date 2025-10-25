#!/bin/sh

# 设置默认值
HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-8000}
WORKERS=${WORKERS:-1}

# 数据目录（可挂载卷），保持兼容
DATA_DIR="/app/data"
ACCOUNTS_TARGET="/app/accounts.json"
SECURITY_TARGET="/app/security.json"
ACCOUNTS_DATA_PATH="$DATA_DIR/accounts.json"
SECURITY_DATA_PATH="$DATA_DIR/security.json"

mkdir -p "$DATA_DIR"

link_data_file() {
    data_path="$1"
    target_path="$2"
    default_payload="$3"

    if [ -L "$target_path" ]; then
        rm -f "$target_path"
    elif [ -f "$target_path" ]; then
        mkdir -p "$(dirname "$data_path")"
        cp "$target_path" "$data_path"
        rm -f "$target_path"
    fi

    if [ ! -f "$data_path" ]; then
        if [ -n "$default_payload" ]; then
            printf '%s' "$default_payload" > "$data_path"
        else
            touch "$data_path"
        fi
    fi

    ln -sf "$data_path" "$target_path"
}

link_data_file "$ACCOUNTS_DATA_PATH" "$ACCOUNTS_TARGET" "{}"
link_data_file "$SECURITY_DATA_PATH" "$SECURITY_TARGET" "{}"

# 确保目录和文件权限正确
# 首先确保数据目录及其内容的权限
chown -R appuser:appuser "$DATA_DIR" 2>/dev/null || true
chmod -R 755 "$DATA_DIR" 2>/dev/null || true

# 确保符号链接目标文件的权限
chown appuser:appuser "$ACCOUNTS_DATA_PATH" 2>/dev/null || true
chown appuser:appuser "$SECURITY_DATA_PATH" 2>/dev/null || true
chmod 644 "$ACCOUNTS_DATA_PATH" 2>/dev/null || true
chmod 644 "$SECURITY_DATA_PATH" 2>/dev/null || true

# 确保符号链接本身的权限
chown -h appuser:appuser "$ACCOUNTS_TARGET" 2>/dev/null || true
chown -h appuser:appuser "$SECURITY_TARGET" 2>/dev/null || true

echo "🚀 启动Outlook邮件API服务..."
echo "📋 配置信息:"
echo "   - 主机地址: $HOST"
echo "   - 端口: $PORT"
echo "   - 工作进程: $WORKERS"
echo "   - 数据目录: /app/data"

# 启动应用
echo "🚀 启动应用..."
exec python main.py