# 安装指南

本指南将帮助您安装和配置Outlook邮件管理系统。

## 系统要求

### 硬件要求
- **内存**: 至少 2GB RAM
- **存储**: 至少 1GB 可用空间
- **网络**: 稳定的互联网连接（用于访问Outlook IMAP服务器）

### 软件要求
- **操作系统**: Windows 10/11, macOS 10.15+, Linux (Ubuntu 18.04+)
- **Docker**: 20.10+ (推荐)
- **Docker Compose**: 2.0+ (推荐)
- **数据库**: PostgreSQL 12+ (可本地安装或使用云服务)
- **浏览器**: 现代浏览器（Chrome、Firefox、Safari、Edge）

## 安装方式

### 方式一：Docker安装（推荐）

Docker方式无需编译，适合快速体验和生产部署。

#### 1. 安装Docker和Docker Compose

**Windows:**
1. 下载并安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. 启动Docker Desktop

**macOS:**
1. 下载并安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)
2. 启动Docker Desktop

**Linux (Ubuntu/Debian):**
```bash
# 更新包索引
sudo apt-get update

# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装Docker Compose
sudo apt-get install docker-compose-plugin

# 将当前用户添加到docker组
sudo usermod -aG docker $USER
```

#### 2. 下载项目

```bash
# 克隆项目
git clone <repository-url>
cd OutlookManager
```

#### 3. 配置环境变量

```bash
# 复制环境配置文件
cp docker.env.example .env

# 编辑.env文件，配置数据库连接等信息
# Windows
notepad .env

# macOS/Linux
nano .env
```

#### 4. 启动服务

```bash
# 启动应用服务（连接到PostgreSQL数据库）
docker-compose up -d
```

#### 5. 验证安装

启动成功后，在浏览器中访问：
- **Web界面**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **API状态**: http://localhost:8000/api

**默认登录信息**：
- 用户名：`admin`
- 密码：`admin`

### 方式二：直接安装

直接安装适合本地开发和调试，需要配置Python环境。

#### 1. 安装Python

**Windows:**
1. 访问 [Python官网](https://www.python.org/downloads/)
2. 下载Python 3.11或更高版本
3. 安装时勾选"Add Python to PATH"

**macOS:**
```bash
# 使用Homebrew安装
brew install python@3.11

# 或从官网下载安装包
```

**Linux (Ubuntu/Debian):**
```bash
# 更新包索引
sudo apt-get update

# 安装Python和pip
sudo apt-get install python3.11 python3.11-pip python3.11-venv
```

#### 2. 安装PostgreSQL

**Windows:**
1. 下载并安装 [PostgreSQL for Windows](https://www.postgresql.org/download/windows/)
2. 记住安装时设置的密码

**macOS:**
```bash
# 使用Homebrew安装
brew install postgresql@14

# 启动PostgreSQL服务
brew services start postgresql@14

# 创建用户和数据库
createuser -s postgres
createdb -O postgres outlook_db
```

**Linux (Ubuntu/Debian):**
```bash
# 安装PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# 启动PostgreSQL服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 创建用户和数据库
sudo -u postgres createuser -s outlook_user
sudo -u postgres createdb -O outlook_user outlook_db
```

#### 3. 下载并配置项目

```bash
# 克隆项目
git clone <repository-url>
cd OutlookManager

# 创建Python虚拟环境
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp docker.env.example .env
# 编辑.env文件，配置数据库连接等信息
```

#### 4. 初始化数据库

```bash
# 确保PostgreSQL服务运行，并创建数据库
# 然后运行数据库初始化脚本
python -c "
import psycopg2
from app.config import ACCOUNTS_DB_HOST, ACCOUNTS_DB_PORT, ACCOUNTS_DB_USER, ACCOUNTS_DB_PASSWORD, ACCOUNTS_DB_NAME

try:
    conn = psycopg2.connect(
        host=ACCOUNTS_DB_HOST,
        port=ACCOUNTS_DB_PORT,
        user=ACCOUNTS_DB_USER,
        password=ACCOUNTS_DB_PASSWORD,
        database=ACCOUNTS_DB_NAME
    )
    print('数据库连接成功')
    conn.close()
except Exception as e:
    print(f'数据库连接失败: {e}')
"
```

#### 5. 启动应用

```bash
# 开发模式启动
python main.py

# 或使用uvicorn直接启动（更多选项）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 验证安装

### 1. 检查服务状态

**Docker方式:**
```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f outlook-email-client
```

**直接安装方式:**
```bash
# 检查进程
ps aux | grep python

# 查看日志
tail -f logs/app.log
```

### 2. 验证数据库连接

```bash
# 测试数据库连接
psql -h localhost -U outlook_user -d outlook_db -c "SELECT 1;"

# 如果连接成功，应该看到数据库提示符
outlook_db=#
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

## 下一步

安装完成后，您可以：

1. 阅读[配置指南](configuration.md)了解详细配置选项
2. 查看[使用指南](../README.md#-使用指南)学习如何使用系统
3. 参考[开发者指南](development.md)进行二次开发

## 常见问题

### Q: Docker安装失败怎么办？

A: 按以下步骤排查：

1. **确认Docker版本**：
   ```bash
   docker --version
   docker-compose --version
   ```

2. **检查Docker服务状态**：
   ```bash
   # Windows/macOS
   # 确保Docker Desktop正在运行
   
   # Linux
   sudo systemctl status docker
   ```

3. **查看详细错误日志**：
   ```bash
   docker-compose logs
   ```

### Q: Python依赖安装失败怎么办？

A: 尝试以下解决方案：

1. **升级pip**：
   ```bash
   python -m pip install --upgrade pip
   ```

2. **使用国内镜像源**：
   ```bash
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
   ```

3. **检查Python版本**：
   ```bash
   python --version
   # 确保是3.11或更高版本
   ```

### Q: 数据库连接失败怎么办？

A: 按以下步骤排查：

1. **验证数据库连接信息**：
   ```bash
   psql -h localhost -U outlook_user -d outlook_db -p 5432
   ```

2. **检查.env文件配置**：
   - 确认`ACCOUNTS_DB_HOST`、`ACCOUNTS_DB_PORT`等配置正确
   - 确认数据库用户权限

3. **确认数据库服务运行**：
   ```bash
   # Linux
   sudo systemctl status postgresql
   
   # macOS
   brew services list | grep postgresql
   
   # Windows
   # 检查服务中的PostgreSQL服务
   ```

更多问题请参考[故障排除指南](troubleshooting.md)。