# 部署指南

本指南详细介绍如何在不同环境中部署Outlook邮件管理系统。

## 部署方式选择

| 部署场景 | 推荐方式 | 说明 |
|---------|---------|------|
| **生产环境** | Docker Compose | 包含完整服务栈，易于管理 |
| **容器化部署** | 单容器Docker | 适合已有外部数据库的场景 |
| **开发测试** | [开发者运行指南](development.md) | 支持代码修改和调试 |

## 🐳 Docker Compose部署（推荐）

### 准备工作

1. **安装Docker和Docker Compose**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install docker.io docker-compose-plugin
   
   # CentOS/RHEL
   sudo yum install docker docker-compose
   
   # 启动Docker服务
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

2. **克隆项目**
   ```bash
   git clone <repository-url>
   cd OutlookManager
   ```

### 部署步骤

1. **配置环境变量**
   ```bash
   # 复制环境配置文件
   cp docker.env.example .env
   
   # 编辑.env文件，配置生产环境参数
   nano .env
   ```

   生产环境配置示例：
   ```bash
   # 数据库配置
   ACCOUNTS_DB_HOST=postgres
   ACCOUNTS_DB_PORT=5432
   ACCOUNTS_DB_USER=outlook_user
   ACCOUNTS_DB_PASSWORD=your_secure_password
   ACCOUNTS_DB_NAME=outlook_db
   
   # 应用配置
   APP_USERNAME=admin
   APP_PASSWORD=your_secure_password
   DEBUG=false
   LOG_LEVEL=info
   
   # 安全配置
   SESSION_COOKIE_SECURE=true
   SESSION_COOKIE_SAMESITE=strict
   
   # 性能配置
   MAX_CONNECTIONS=20
   CACHE_EXPIRE_TIME=300
   ```

2. **配置Docker Compose**
   
   编辑`docker-compose.yml`文件，确保生产环境配置：
   ```yaml
   version: '3.8'
   
   services:
     postgres:
       image: postgres:14
       environment:
         POSTGRES_DB: outlook_db
         POSTGRES_USER: outlook_user
         POSTGRES_PASSWORD: your_secure_password
       volumes:
         - postgres_data:/var/lib/postgresql/data
       restart: unless-stopped
       networks:
         - outlook-network
   
     outlook-email-client:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DATABASE_URL=postgresql://outlook_user:your_secure_password@postgres:5432/outlook_db
       depends_on:
         - postgres
       restart: unless-stopped
       networks:
         - outlook-network
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:8000/api"]
         interval: 30s
         timeout: 10s
         retries: 3
   
   volumes:
     postgres_data:
   
   networks:
     outlook-network:
       driver: bridge
   ```

3. **启动服务**
   ```bash
   # 构建并启动所有服务
   docker-compose up -d
   
   # 查看服务状态
   docker-compose ps
   
   # 查看日志
   docker-compose logs -f
   ```

4. **验证部署**
   ```bash
   # 检查服务健康状态
   curl http://localhost:8000/api
   
   # 检查数据库连接
   docker-compose exec postgres psql -U outlook_user -d outlook_db -c "SELECT 1;"
   ```

## 🐳 单容器Docker部署

### 构建镜像

```bash
# 克隆项目
git clone <repository-url>
cd OutlookManager

# 构建镜像
docker build -t outlook-manager:latest .
```

### 运行容器

```bash
# 创建数据卷
docker volume create postgres-data

# 运行PostgreSQL容器（如果没有外部数据库）
docker run -d \
  --name postgres \
  -e POSTGRES_DB=outlook_db \
  -e POSTGRES_USER=outlook_user \
  -e POSTGRES_PASSWORD=your_secure_password \
  -v postgres-data:/var/lib/postgresql/data \
  postgres:14

# 运行应用容器
docker run -d \
  --name outlook-manager \
  -p 8000:8000 \
  -v $(pwd)/accounts.json:/app/accounts.json \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  -e DATABASE_URL=postgresql://outlook_user:your_secure_password@postgres:5432/outlook_db \
  --link postgres:postgres \
  outlook-manager:latest
```

### 使用外部数据库

如果您已有外部PostgreSQL数据库：

```bash
# 运行应用容器（连接外部数据库）
docker run -d \
  --name outlook-manager \
  -p 8000:8000 \
  -v $(pwd)/accounts.json:/app/accounts.json \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  -e DATABASE_URL=postgresql://username:password@external-db-host:5432/dbname \
  outlook-manager:latest
```

## 🔧 生产环境配置建议

### 1. 安全配置

```bash
# 在.env文件中设置
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=strict
APP_PASSWORD=your_secure_password

# 使用HTTPS
SSL_CERT_PATH=/path/to/cert.pem
SSL_KEY_PATH=/path/to/key.pem
```

### 2. 性能优化

```bash
# 调整连接池大小
MAX_CONNECTIONS=20

# 设置适当的缓存时间
CACHE_EXPIRE_TIME=300

# 启用Gzip压缩
ENABLE_GZIP=true

# 配置工作进程数
WORKERS=4
```

### 3. 监控配置

```bash
# 启用健康检查
HEALTHCHECK_INTERVAL=30s
HEALTHCHECK_TIMEOUT=10s
HEALTHCHECK_RETRIES=3

# 配置日志
LOG_LEVEL=info
LOG_FILE=/app/logs/app.log
LOG_MAX_SIZE=100MB
LOG_BACKUP_COUNT=5
```

### 4. 资源限制

在`docker-compose.yml`中添加资源限制：

```yaml
services:
  outlook-email-client:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## 🌐 反向代理配置

### Nginx配置

1. **安装Nginx**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install nginx
   
   # CentOS/RHEL
   sudo yum install nginx
   ```

2. **配置Nginx**
   
   创建`/etc/nginx/sites-available/outlook-manager`文件：
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       # 重定向到HTTPS
       return 301 https://$server_name$request_uri;
   }
   
   server {
       listen 443 ssl http2;
       server_name your-domain.com;
       
       # SSL配置
       ssl_certificate /path/to/your/cert.pem;
       ssl_certificate_key /path/to/your/key.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
       ssl_prefer_server_ciphers off;
       
       # 安全头
       add_header X-Frame-Options DENY;
       add_header X-Content-Type-Options nosniff;
       add_header X-XSS-Protection "1; mode=block";
       add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
       
       # 静态文件
       location /static/ {
           alias /path/to/OutlookManager/static/;
           expires 1y;
           add_header Cache-Control "public, immutable";
       }
       
       # API和Web界面
       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           
           # WebSocket支持
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           
           # 超时设置
           proxy_connect_timeout 60s;
           proxy_send_timeout 60s;
           proxy_read_timeout 60s;
       }
   }
   ```

3. **启用配置**
   ```bash
   # 创建软链接
   sudo ln -s /etc/nginx/sites-available/outlook-manager /etc/nginx/sites-enabled/
   
   # 测试配置
   sudo nginx -t
   
   # 重启Nginx
   sudo systemctl restart nginx
   ```

### Apache配置

1. **安装Apache和模块**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install apache2
   sudo a2enmod proxy proxy_http proxy_wstunnel ssl rewrite headers
   
   # CentOS/RHEL
   sudo yum install httpd mod_proxy mod_proxy_http mod_proxy_wstunnel mod_ssl
   ```

2. **配置Apache**
   
   创建`/etc/apache2/sites-available/outlook-manager.conf`文件：
   ```apache
   <VirtualHost *:80>
       ServerName your-domain.com
       Redirect permanent / https://your-domain.com/
   </VirtualHost>
   
   <VirtualHost *:443>
       ServerName your-domain.com
       
       # SSL配置
       SSLEngine on
       SSLCertificateFile /path/to/your/cert.pem
       SSLCertificateKeyFile /path/to/your/key.pem
       SSLProtocol all -SSLv2 -SSLv3 -TLSv1 -TLSv1.1
       
       # 安全头
       Header always set X-Frame-Options DENY
       Header always set X-Content-Type-Options nosniff
       Header always set X-XSS-Protection "1; mode=block"
       Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
       
       # 静态文件
       Alias /static /path/to/OutlookManager/static
       <Directory /path/to/OutlookManager/static>
           Options -Indexes
           ExpiresActive On
           ExpiresDefault "access plus 1 year"
           Header append Cache-Control "public, immutable"
       </Directory>
       
       # 代理配置
       ProxyPreserveHost On
       ProxyRequests Off
       ProxyPass /static !
       ProxyPass / ws://localhost:8000/
       ProxyPassReverse / ws://localhost:8000/
       ProxyPass / http://localhost:8000/
       ProxyPassReverse / http://localhost:8000/
       
       # WebSocket支持
       RewriteEngine On
       RewriteCond %{HTTP:Upgrade} =websocket [NC]
       RewriteRule /(.*) ws://localhost:8000/$1 [P,L]
       RewriteCond %{HTTP:Upgrade} !=websocket [NC]
       RewriteRule /(.*) http://localhost:8000/$1 [P,L]
   </VirtualHost>
   ```

3. **启用配置**
   ```bash
   # 启用站点
   sudo a2ensite outlook-manager.conf
   
   # 测试配置
   sudo apache2ctl configtest
   
   # 重启Apache
   sudo systemctl restart apache2
   ```

## 🚀 云平台部署

### AWS部署

1. **使用ECS**
   
   创建`ecs-task-definition.json`：
   ```json
   {
     "family": "outlook-manager",
     "networkMode": "awsvpc",
     "requiresCompatibilities": ["FARGATE"],
     "cpu": "512",
     "memory": "1024",
     "executionRoleArn": "arn:aws:iam::account:role/ecsTaskExecutionRole",
     "containerDefinitions": [
       {
         "name": "outlook-manager",
         "image": "your-registry/outlook-manager:latest",
         "portMappings": [
           {
             "containerPort": 8000,
             "protocol": "tcp"
           }
         ],
         "environment": [
           {
             "name": "DATABASE_URL",
             "value": "postgresql://username:password@rds-endpoint:5432/dbname"
           }
         ],
         "logConfiguration": {
           "logDriver": "awslogs",
           "options": {
             "awslogs-group": "/ecs/outlook-manager",
             "awslogs-region": "us-west-2",
             "awslogs-stream-prefix": "ecs"
           }
         }
       }
     ]
   }
   ```

2. **使用Elastic Beanstalk**
   
   创建`Dockerrun.aws.json`：
   ```json
   {
     "AWSEBDockerrunVersion": "2",
     "containerDefinitions": [
       {
         "name": "outlook-manager",
         "image": "your-registry/outlook-manager:latest",
         "essential": true,
         "memory": 1024,
         "portMappings": [
           {
             "hostPort": 80,
             "containerPort": 8000
           }
         ],
         "environment": [
           {
             "name": "DATABASE_URL",
             "value": "postgresql://username:password@rds-endpoint:5432/dbname"
           }
         ]
       }
     ]
   }
   ```

### Google Cloud Platform部署

1. **使用Cloud Run**
   ```bash
   # 构建并推送镜像
   gcloud builds submit --tag gcr.io/PROJECT_ID/outlook-manager
   
   # 部署到Cloud Run
   gcloud run deploy outlook-manager \
     --image gcr.io/PROJECT_ID/outlook-manager \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars DATABASE_URL=postgresql://username:password@cloud-sql-proxy:5432/dbname
   ```

2. **使用GKE**
   
   创建`k8s-deployment.yaml`：
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: outlook-manager
   spec:
     replicas: 3
     selector:
       matchLabels:
         app: outlook-manager
     template:
       metadata:
         labels:
           app: outlook-manager
       spec:
         containers:
         - name: outlook-manager
           image: gcr.io/PROJECT_ID/outlook-manager:latest
           ports:
           - containerPort: 8000
           env:
           - name: DATABASE_URL
             value: "postgresql://username:password@cloud-sql-proxy:5432/dbname"
           resources:
             requests:
               memory: "512Mi"
               cpu: "500m"
             limits:
               memory: "1Gi"
               cpu: "1000m"
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: outlook-manager-service
   spec:
     selector:
       app: outlook-manager
     ports:
     - protocol: TCP
       port: 80
       targetPort: 8000
     type: LoadBalancer
   ```

### Azure部署

1. **使用Container Instances**
   ```bash
   # 创建资源组
   az group create --name outlook-manager-rg --location eastus
   
   # 部署容器
   az container create \
     --resource-group outlook-manager-rg \
     --name outlook-manager \
     --image your-registry/outlook-manager:latest \
     --dns-name-label outlook-manager-unique \
     --ports 8000 \
     --environment-variables DATABASE_URL=postgresql://username:password@db-server:5432/dbname
   ```

2. **使用AKS**
   
   创建`azure-deployment.yaml`：
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: outlook-manager
   spec:
     replicas: 3
     selector:
       matchLabels:
         app: outlook-manager
     template:
       metadata:
         labels:
           app: outlook-manager
       spec:
         containers:
         - name: outlook-manager
           image: your-registry/outlook-manager:latest
           ports:
           - containerPort: 8000
           env:
           - name: DATABASE_URL
             valueFrom:
               secretKeyRef:
                 name: outlook-secrets
                 key: database-url
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: outlook-manager-service
   spec:
     selector:
       app: outlook-manager
     ports:
     - protocol: TCP
       port: 80
       targetPort: 8000
     type: LoadBalancer
   ```

## 📊 监控和日志

### 1. 应用监控

```bash
# 启用Prometheus指标
ENABLE_METRICS=true
METRICS_PORT=9090

# 配置健康检查端点
HEALTHCHECK_ENDPOINT=/health
```

### 2. 日志管理

```bash
# 配置日志级别
LOG_LEVEL=info

# 配置日志输出
LOG_FORMAT=json
LOG_OUTPUT=file
LOG_FILE=/app/logs/app.log
```

### 3. 性能监控

```bash
# 启用性能分析
ENABLE_PROFILING=true

# 配置APM（如New Relic、DataDog）
NEW_RELIC_LICENSE_KEY=your_license_key
NEW_RELIC_APP_NAME=outlook-manager
```

## 🔒 安全最佳实践

### 1. 网络安全

```bash
# 使用防火墙限制访问
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 配置VPN访问（可选）
```

### 2. 数据库安全

```bash
# 使用SSL连接数据库
DATABASE_URL=postgresql://username:password@host:5432/dbname?sslmode=require

# 限制数据库访问权限
# 只授予必要的权限给应用用户
```

### 3. 应用安全

```bash
# 定期更新依赖
pip install --upgrade -r requirements.txt

# 使用安全扫描工具
pip install safety bandit
safety check
bandit -r app/
```

## 🔄 备份和恢复

### 1. 数据库备份

```bash
# 创建备份脚本
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="outlook_db"

# 创建备份
pg_dump -h localhost -U outlook_user $DB_NAME > $BACKUP_DIR/outlook_db_$DATE.sql

# 压缩备份
gzip $BACKUP_DIR/outlook_db_$DATE.sql

# 删除7天前的备份
find $BACKUP_DIR -name "outlook_db_*.sql.gz" -mtime +7 -delete
```

### 2. 应用数据备份

```bash
# 备份配置文件
cp .env .env.backup.$(date +%Y%m%d)
cp accounts.json accounts.json.backup.$(date +%Y%m%d)

# 备份到云存储
aws s3 cp .env.backup.$(date +%Y%m%d) s3://your-backup-bucket/
aws s3 cp accounts.json.backup.$(date +%Y%m%d) s3://your-backup-bucket/
```

### 3. 恢复流程

```bash
# 恢复数据库
gunzip -c outlook_db_20231201_120000.sql.gz | psql -h localhost -U outlook_user outlook_db

# 恢复配置文件
cp .env.backup.20231201 .env
cp accounts.json.backup.20231201 accounts.json

# 重启服务
docker-compose restart
```

## 🚨 故障排除

### 1. 常见问题

**容器启动失败**
```bash
# 查看容器日志
docker-compose logs outlook-email-client

# 检查容器状态
docker-compose ps
```

**数据库连接失败**
```bash
# 测试数据库连接
docker-compose exec postgres psql -U outlook_user -d outlook_db -c "SELECT 1;"

# 检查网络连接
docker network ls
docker network inspect outlook-manager_outlook-network
```

**性能问题**
```bash
# 检查资源使用
docker stats

# 查看应用日志
docker-compose logs -f outlook-email-client
```

### 2. 监控告警

设置监控告警，及时发现和解决问题：

```bash
# 使用Prometheus和Grafana
# 配置告警规则
# 设置通知渠道
```

更多部署问题请参考[故障排除指南](troubleshooting.md)。