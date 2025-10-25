# ================================
# 构建阶段 - 安装编译依赖和构建应用
# ================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-alpine3.21 AS builder

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    postgresql-dev

# 复制requirements文件并安装Python依赖到构建环境
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ================================
# 运行阶段 - 只包含运行时依赖
# ================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-alpine3.21 AS runtime

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

# 只安装运行时必需的系统依赖
RUN apk add --no-cache \
    libffi \
    openssl \
    libpq \
    && rm -rf /var/cache/apk/*

# 从构建阶段复制Python包
COPY --from=builder /root/.local /root/.local

# 复制应用代码（确保不复制__pycache__）
COPY app/ ./app/
COPY main.py .
COPY static/ ./static/
COPY docker-entrypoint.sh .

# 设置启动脚本权限
RUN chmod +x docker-entrypoint.sh

# 创建数据目录用于持久化存储
RUN mkdir -p /app/data && chown 777 /app/data

# 创建非root用户
RUN addgroup -g 1000 -S appgroup && \
    adduser -u 1000 -S appuser -G appgroup
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api')" || exit 1

# 启动命令
CMD ["./docker-entrypoint.sh"]