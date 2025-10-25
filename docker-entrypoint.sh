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

# 确保文件权限正确
chown appuser:appuser "$DATA_DIR" 2>/dev/null || true
chown appuser:appuser "$ACCOUNTS_TARGET" 2>/dev/null || true
chown appuser:appuser "$SECURITY_TARGET" 2>/dev/null || true

# 处理 accounts.json.lock 文件权限
ACCOUNTS_LOCK_TARGET="/app/accounts.json.lock"
ACCOUNTS_LOCK_DATA_PATH="$DATA_DIR/accounts.json.lock"

# 确保锁文件目录存在
mkdir -p "$(dirname "$ACCOUNTS_LOCK_DATA_PATH")" 2>/dev/null || true

# 如果锁文件已存在但不是符号链接，则移动到数据目录
if [ -f "$ACCOUNTS_LOCK_TARGET" ] && [ ! -L "$ACCOUNTS_LOCK_TARGET" ]; then
    cp "$ACCOUNTS_LOCK_TARGET" "$ACCOUNTS_LOCK_DATA_PATH" 2>/dev/null || true
    rm -f "$ACCOUNTS_LOCK_TARGET" 2>/dev/null || true
fi

# 创建符号链接或确保锁文件存在
if [ ! -f "$ACCOUNTS_LOCK_DATA_PATH" ]; then
    touch "$ACCOUNTS_LOCK_DATA_PATH" 2>/dev/null || true
fi

ln -sf "$ACCOUNTS_LOCK_DATA_PATH" "$ACCOUNTS_LOCK_TARGET" 2>/dev/null || true

# 设置锁文件权限
chown appuser:appuser "$ACCOUNTS_LOCK_DATA_PATH" 2>/dev/null || true
chown appuser:appuser "$ACCOUNTS_LOCK_TARGET" 2>/dev/null || true
chmod 644 "$ACCOUNTS_LOCK_DATA_PATH" 2>/dev/null || true

echo "🚀 启动Outlook邮件API服务..."
echo "📋 配置信息:"
echo "   - 主机地址: $HOST"
echo "   - 端口: $PORT"
echo "   - 工作进程: $WORKERS"
echo "   - 数据目录: /app/data"

# 快速验证关键模块
echo "🔍 验证环境..."
python -c "import sys; print('Python路径:', ':'.join(sys.path[:3]))" 2>/dev/null || echo "Python路径检查失败"
python -c "import fastapi, uvicorn; print('✅ 核心模块已加载')" 2>/dev/null || echo "❌ 核心模块加载失败"

# 启动应用
echo "🚀 启动应用..."
exec python main.py