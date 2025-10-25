# 开发者指南

本指南专为开发者设计，提供多种运行方式，满足不同开发场景需求。

## 运行方式选择

根据您的开发环境和需求，选择最适合的运行方式：

| 运行方式 | 适用场景 | 优点 | 缺点 |
|---------|---------|------|------|
| **Docker方式** | 快速体验、生产部署、环境隔离 | 无需编译、环境一致、依赖管理简单 | 需要Docker环境、调试相对复杂 |
| **直接编译运行** | 本地开发、代码调试、功能扩展 | 调试方便、代码修改即时生效 | 需要配置Python环境、手动管理依赖 |

## Docker方式运行

Docker方式无需编译，适合快速体验和生产部署。

### 🐳 使用Docker Compose（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd OutlookManager

# 复制环境配置文件
cp docker.env.example .env

# 启动服务（自动构建镜像）
docker-compose up -d
```

### 🐳 使用预构建镜像

如果您有预构建的Docker镜像，可以直接使用：

```bash
# 拉取预构建镜像（如果有）
docker pull your-registry/outlook-manager:latest

# 运行容器
docker run -d \
  --name outlook-manager \
  -p 8000:8000 \
  -v $(pwd)/accounts.json:/app/accounts.json \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  your-registry/outlook-manager:latest
```

### 🐳 Docker方式优势

- ✅ **无需编译**：直接使用预构建镜像或自动构建
- ✅ **环境隔离**：避免本地Python环境冲突
- ✅ **依赖管理**：所有依赖已打包在镜像中
- ✅ **一致性**：开发、测试、生产环境完全一致

## 直接编译运行

直接编译运行适合本地开发和调试，需要配置Python环境。

### 📋 环境要求

- **Python**: 3.11 或更高版本
- **操作系统**: Windows 10/11, macOS 10.15+, Linux (Ubuntu 18.04+)
- **数据库**: PostgreSQL 12+ (可本地安装或使用云服务)
- **内存**: 至少 2GB RAM
- **存储**: 至少 1GB 可用空间

### 🔧 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd OutlookManager
   ```

2. **创建Python虚拟环境**
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   # 复制环境配置文件
   cp docker.env.example .env
   
   # 编辑.env文件，配置数据库连接等信息
   # Windows
   notepad .env
   
   # macOS/Linux
   nano .env
   ```

5. **初始化数据库**
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

6. **启动应用**
   ```bash
   # 开发模式启动
   python main.py
   
   # 或使用uvicorn直接启动（更多选项）
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### 🔍 直接编译运行优势

- ✅ **调试方便**：可直接使用IDE调试器
- ✅ **代码修改即时生效**：支持热重载
- ✅ **完全控制**：可自由修改和扩展代码
- ✅ **开发效率高**：适合频繁代码修改

## 开发者特定配置

### 🛠️ 开发环境配置

1. **启用调试模式**
   ```bash
   # 在.env文件中添加
   DEBUG=true
   LOG_LEVEL=debug
   ```

2. **配置热重载**
   ```bash
   # 使用uvicorn启动时添加--reload参数
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **开发数据库配置**
   ```bash
   # 建议使用本地开发数据库
   ACCOUNTS_DB_HOST=localhost
   ACCOUNTS_DB_PORT=5432
   ACCOUNTS_DB_DEV_USER=dev_user
   ACCOUNTS_DB_DEV_PASSWORD=dev_password
   ACCOUNTS_DB_DEV_NAME=outlook_dev_db
   ```

### 🐛 调试配置

1. **VS Code调试配置**
   ```json
   {
     "name": "Python: FastAPI",
     "type": "python",
     "request": "launch",
     "program": "${workspaceFolder}/main.py",
     "console": "integratedTerminal",
     "env": {
       "PYTHONPATH": "${workspaceFolder}"
     }
   }
   ```

2. **日志级别配置**
   ```bash
   # 在.env文件中设置
   LOG_LEVEL=debug  # debug, info, warning, error, critical
   ```

3. **性能监控**
   ```bash
   # 启用性能分析（可选）
   ENABLE_PROFILING=true
   ```

### 🧪 测试环境

1. **运行测试**
   ```bash
   # 安装测试依赖
   pip install pytest pytest-asyncio httpx
   
   # 运行测试
   pytest
   ```

2. **代码质量检查**
   ```bash
   # 安装代码检查工具
   pip install flake8 black isort
   
   # 代码格式化
   black .
   isort .
   
   # 代码检查
   flake8 .
   ```

## 项目结构

### 目录结构

```
OutlookManager/
├── app/                    # 应用核心代码
│   ├── accounts/          # 账户管理模块
│   ├── batch/             # 批量处理模块
│   ├── config/            # 配置模块
│   ├── core/              # 核心功能模块
│   ├── email/             # 邮件处理模块
│   ├── infrastructure/    # 基础设施模块
│   ├── interfaces/        # 接口模块
│   ├── models/            # 数据模型
│   ├── oauth/             # OAuth认证模块
│   ├── routes/            # 路由模块
│   ├── security/          # 安全模块
│   ├── shared/            # 共享模块
│   ├── sync/              # 同步模块
│   └── validation/        # 验证模块
├── docs/                  # 文档目录
├── scripts/               # 脚本目录
├── static/                # 静态资源
├── tests/                 # 测试目录
├── docker-compose.yml     # Docker Compose配置
├── Dockerfile            # Docker镜像配置
├── main.py               # 应用入口
├── requirements.txt      # Python依赖
└── .env                  # 环境变量配置
```

### 核心模块说明

#### app/accounts/
账户管理相关功能：
- `credentials.py` - 账户凭据管理
- `listing.py` - 账户列表功能
- `repository.py` - 账户数据仓库
- `service.py` - 账户服务
- `sync.py` - 账户同步功能
- `tagging.py` - 账户标签功能

#### app/batch/
批量处理相关功能：
- `config.py` - 批量处理配置
- `fetcher.py` - 数据获取器
- `imap_pool.py` - IMAP连接池
- `models.py` - 批量处理模型
- `oauth.py` - OAuth批量处理
- `runner.py` - 批量处理运行器
- `storage.py` - 批量处理存储

#### app/email/
邮件处理相关功能：
- `builders.py` - 邮件构建器
- `cache.py` - 邮件缓存
- `details.py` - 邮件详情
- `listing.py` - 邮件列表
- `service.py` - 邮件服务
- `utils.py` - 邮件工具

#### app/infrastructure/
基础设施相关功能：
- `imap.py` - IMAP基础设施
- `abstractions/` - 抽象层
- `connections/` - 连接管理
- `external/` - 外部服务
- `interfaces/` - 接口定义
- `messaging/` - 消息处理
- `monitoring/` - 监控功能
- `persistence/` - 持久化

## 开发工作流

### 1. 功能开发流程

1. **创建功能分支**
   ```bash
   git checkout -b feature/new-feature
   ```

2. **开发功能**
   - 在相应模块中添加代码
   - 编写单元测试
   - 更新文档

3. **测试功能**
   ```bash
   # 运行单元测试
   pytest tests/
   
   # 运行代码质量检查
   flake8 app/
   black app/
   isort app/
   ```

4. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   ```

5. **创建Pull Request**
   - 在GitHub上创建PR
   - 等待代码审查
   - 根据反馈修改代码

### 2. 调试技巧

#### 日志调试

```python
import logging

# 在代码中添加日志
logger = logging.getLogger(__name__)
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

#### 断点调试

```python
# 在代码中添加断点
import pdb; pdb.set_trace()

# 或使用更现代的调试器
import ipdb; ipdb.set_trace()
```

#### 性能分析

```python
# 使用cProfile进行性能分析
python -m cProfile -o profile.stats main.py

# 分析结果
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(20)
"
```

### 3. 代码规范

#### Python代码风格

- 遵循PEP 8规范
- 使用类型提示
- 编写文档字符串
- 保持函数简洁（不超过20行）

#### 示例代码

```python
from typing import List, Optional
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

class AccountService:
    """账户服务类"""
    
    def __init__(self, repository: AccountRepository):
        self.repository = repository
    
    async def get_account(self, account_id: str) -> Optional[Account]:
        """
        获取账户信息
        
        Args:
            account_id: 账户ID
            
        Returns:
            账户信息，如果不存在则返回None
            
        Raises:
            HTTPException: 当账户不存在时
        """
        try:
            account = await self.repository.get_by_id(account_id)
            if not account:
                raise HTTPException(status_code=404, detail="Account not found")
            return account
        except Exception as e:
            logger.error(f"Failed to get account {account_id}: {e}")
            raise
```

## API开发

### 1. 路由定义

```python
from fastapi import APIRouter, Depends, HTTPException
from typing import List

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

@router.get("/", response_model=List[AccountResponse])
async def get_accounts(
    skip: int = 0,
    limit: int = 100,
    service: AccountService = Depends(get_account_service)
):
    """获取账户列表"""
    return await service.get_accounts(skip=skip, limit=limit)

@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    service: AccountService = Depends(get_account_service)
):
    """创建新账户"""
    return await service.create_account(account)
```

### 2. 数据模型

```python
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class AccountBase(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None

class AccountCreate(AccountBase):
    password: str
    refresh_token: str
    client_id: str

class AccountResponse(AccountBase):
    id: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True
```

### 3. 依赖注入

```python
from fastapi import Depends
from app.accounts.service import AccountService
from app.accounts.repository import AccountRepository

async def get_account_repository() -> AccountRepository:
    return AccountRepository()

async def get_account_service(
    repository: AccountRepository = Depends(get_account_repository)
) -> AccountService:
    return AccountService(repository)
```

## 测试策略

### 1. 单元测试

```python
import pytest
from unittest.mock import Mock, AsyncMock
from app.accounts.service import AccountService
from app.accounts.repository import AccountRepository

@pytest.fixture
def mock_repository():
    repository = Mock(spec=AccountRepository)
    return repository

@pytest.fixture
def service(mock_repository):
    return AccountService(mock_repository)

@pytest.mark.asyncio
async def test_get_account_found(service, mock_repository):
    # Arrange
    account_id = "test-id"
    expected_account = Account(id=account_id, email="test@example.com")
    mock_repository.get_by_id.return_value = expected_account
    
    # Act
    result = await service.get_account(account_id)
    
    # Assert
    assert result == expected_account
    mock_repository.get_by_id.assert_called_once_with(account_id)
```

### 2. 集成测试

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_get_accounts_api():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/accounts")
        assert response.status_code == 200
        assert "accounts" in response.json()
```

### 3. 端到端测试

```python
import pytest
from playwright.async_api import async_playwright

@pytest.mark.asyncio
async def test_account_management_e2e():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # 访问应用
        await page.goto("http://localhost:8000")
        
        # 登录
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        await page.click("#login-button")
        
        # 添加账户
        await page.click("#add-account-button")
        await page.fill("#email", "test@example.com")
        await page.fill("#password", "test-password")
        await page.click("#save-button")
        
        # 验证账户已添加
        await page.wait_for_selector(".account-item")
        
        await browser.close()
```

## 性能优化

### 1. 数据库优化

```python
# 使用连接池
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=300
)

# 批量操作
async def bulk_create_accounts(accounts: List[AccountCreate]):
    async with AsyncSession(engine) as session:
        session.add_all([Account(**account.dict()) for account in accounts])
        await session.commit()
```

### 2. 缓存策略

```python
from functools import lru_cache
import redis

# 内存缓存
@lru_cache(maxsize=128)
def get_account_config(account_id: str):
    # 获取账户配置
    pass

# Redis缓存
redis_client = redis.Redis(host='localhost', port=6379, db=0)

async def get_cached_account(account_id: str):
    cached = redis_client.get(f"account:{account_id}")
    if cached:
        return json.loads(cached)
    
    account = await get_account_from_db(account_id)
    redis_client.setex(f"account:{account_id}", 300, json.dumps(account))
    return account
```

### 3. 异步处理

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=10)

async def process_emails_async(emails: List[Email]):
    loop = asyncio.get_event_loop()
    tasks = []
    
    for email in emails:
        task = loop.run_in_executor(executor, process_single_email, email)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    return results
```

## 部署准备

### 1. 环境变量管理

```bash
# 开发环境
cp .env.example .env.dev

# 测试环境
cp .env.example .env.test

# 生产环境
cp .env.example .env.prod
```

### 2. Docker构建

```dockerfile
# 多阶段构建
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. 健康检查

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 检查数据库连接
        # 检查外部服务
        return {"status": "healthy", "timestamp": datetime.utcnow()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## 贡献指南

### 1. 代码提交规范

使用[Conventional Commits](https://www.conventionalcommits.org/)规范：

```
feat: 添加新功能
fix: 修复bug
docs: 更新文档
style: 代码格式调整
refactor: 代码重构
test: 添加测试
chore: 构建过程或辅助工具的变动
```

### 2. Pull Request流程

1. Fork项目
2. 创建功能分支
3. 开发并测试
4. 提交PR
5. 代码审查
6. 合并代码

### 3. 代码审查要点

- 代码风格是否符合规范
- 是否有适当的测试
- 是否有文档更新
- 是否有性能影响
- 是否有安全考虑

更多开发问题请参考[故障排除指南](troubleshooting.md)。