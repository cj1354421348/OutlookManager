# 📚 OutlookManager 文档中心

欢迎来到OutlookManager邮件管理系统的文档中心。这里包含了系统的完整使用指南、配置说明和技术文档。

## 🗺️ 文档导航

### 🚀 快速开始
- [📦 安装指南](installation.md) - 详细的系统安装步骤和环境配置
- [⚙️ 配置指南](configuration.md) - 完整的配置选项说明和最佳实践
- [🏠 主项目README](../README.md) - 项目概述、功能特性和快速开始

### 📖 功能使用
- [📧 账户同步使用说明](account_sync_usage.md) - 账户数据同步功能的使用指南
- [🗄️ PostgreSQL设置](postgresql-setup.md) - 数据库配置和优化指南

### 👨‍💻 开发与部署
- [🛠️ 开发者指南](development.md) - 开发环境搭建、代码贡献和API开发
- [🚀 部署指南](deployment.md) - 生产环境部署方案和云平台配置
- [🔧 故障排除指南](troubleshooting.md) - 常见问题解决方案和诊断方法

### 🖼️ 图片资源
- [images/](images/) - 文档中使用的图片和截图资源

## 🎯 按角色查看文档

### 👤 普通用户
如果您是系统的普通用户，建议按以下顺序阅读：
1. [主项目README](../README.md) - 了解系统功能和安装方法
2. [安装指南](installation.md) - 按步骤安装系统
3. [配置指南](configuration.md) - 基本配置说明
4. [账户同步使用说明](account_sync_usage.md) - 学习如何使用数据同步功能

### 🔧 系统管理员
如果您负责系统的部署和维护，建议阅读：
1. [安装指南](installation.md) - 系统安装和环境配置
2. [配置指南](configuration.md) - 详细配置选项和最佳实践
3. [部署指南](deployment.md) - 生产环境部署方案
4. [PostgreSQL设置](postgresql-setup.md) - 数据库配置和优化
5. [故障排除指南](troubleshooting.md) - 问题诊断和解决方案

### 🛠️ 开发人员
如果您是开发人员，建议阅读所有文档以全面了解系统：
1. [开发者指南](development.md) - 开发环境搭建和代码贡献
2. [安装指南](installation.md) - 开发环境安装
3. [配置指南](configuration.md) - 开发环境配置
4. [部署指南](deployment.md) - 部署流程和CI/CD
5. [故障排除指南](troubleshooting.md) - 调试和问题解决

## 🗂️ 文档结构

```
docs/
├── README.md                           # 文档中心首页（本文件）
├── installation.md                     # 系统安装指南
├── configuration.md                    # 配置选项说明
├── development.md                      # 开发者指南
├── deployment.md                       # 部署指南
├── troubleshooting.md                  # 故障排除指南
├── account_sync_usage.md              # 账户同步使用说明
├── postgresql-setup.md                # PostgreSQL配置指南
└── images/                            # 文档图片资源
    ├── account-add.png                # 账户添加界面截图
    ├── account-management.png         # 账户管理界面截图
    ├── api-docs.png                   # API文档界面截图
    └── email-list.png                 # 邮件列表界面截图
```

## 🔍 快速导航

### 常见问题快速解答

**Q: 如何快速部署系统？**
A: 参考 [安装指南](installation.md) 中的Docker Compose部署方式。

**Q: 如何配置PostgreSQL数据库？**
A: 参考 [PostgreSQL设置](postgresql-setup.md) 中的详细配置步骤。

**Q: 如何使用账户同步功能？**
A: 参考 [账户同步使用说明](account_sync_usage.md) 中的使用指南。

**Q: 如何进行生产环境部署？**
A: 参考 [部署指南](deployment.md) 中的详细部署方案。

**Q: 遇到问题如何排查？**
A: 参考 [故障排除指南](troubleshooting.md) 中的问题诊断流程。

**Q: 如何参与开发？**
A: 参考 [开发者指南](development.md) 中的开发环境搭建和代码贡献流程。

## 📋 文档使用指南

### 📖 阅读顺序
1. **新用户**：从 [主项目README](../README.md) 开始，然后阅读 [安装指南](installation.md)
2. **系统管理员**：重点阅读 [安装指南](installation.md)、[配置指南](configuration.md) 和 [部署指南](deployment.md)
3. **开发人员**：从 [开发者指南](development.md) 开始，然后根据需要阅读其他文档

### 🔍 搜索技巧
- 使用浏览器的页面搜索功能（Ctrl+F）快速查找内容
- 查看每个文档的目录结构，快速定位所需信息
- 参考文档中的交叉引用链接，获取相关内容

### 📝 文档约定
- **代码块**：表示命令行操作或代码示例
- **⚠️ 警告**：表示需要特别注意的重要信息
- **💡 提示**：表示有用的建议和最佳实践
- **🔗 链接**：表示相关文档或外部资源

## 📊 文档统计

| 文档类型 | 文档数量 | 主要内容 |
|---------|---------|----------|
| 安装配置 | 2 | 系统安装、环境配置、参数设置 |
| 开发部署 | 2 | 开发指南、部署方案、云平台配置 |
| 使用支持 | 3 | 功能使用、故障排除、数据库配置 |
| 总计 | 7 | 覆盖系统完整生命周期 |

## 📝 文档贡献

如果您发现文档中的错误或有改进建议，欢迎：
1. 在GitHub上提交Issue
2. 提交Pull Request
3. 联系开发团队

### 贡献指南
- 确保内容准确性和完整性
- 保持文档风格一致
- 添加适当的示例和截图
- 更新相关交叉引用

## 🔗 相关链接

### 项目资源
- [项目GitHub仓库](https://github.com/your-repo/OutlookManager)
- [API接口文档](http://localhost:8000/docs) （需要先启动系统）
- [项目主页](../README.md)

### 技术文档
- [FastAPI官方文档](https://fastapi.tiangolo.com/)
- [PostgreSQL官方文档](https://www.postgresql.org/docs/)
- [Docker官方文档](https://docs.docker.com/)
- [Azure OAuth2文档](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)

### 社区支持
- [GitHub Issues](https://github.com/your-repo/OutlookManager/issues)
- [GitHub Discussions](https://github.com/your-repo/OutlookManager/discussions)

## 📋 文档更新记录

| 版本 | 日期 | 更新内容 | 作者 |
|------|------|----------|------|
| 2.0 | 2024-12-25 | 重新组织文档结构，添加详细指南 | 开发团队 |
| 1.2 | 2024-02-01 | 完善迁移指南和使用说明 | 开发团队 |
| 1.1 | 2024-01-15 | 添加PostgreSQL配置指南 | 开发团队 |
| 1.0 | 2024-01-01 | 初始文档创建 | 开发团队 |

---

**💡 提示**：如果您是第一次使用OutlookManager系统，建议从 [主项目README](../README.md) 开始阅读，然后根据您的角色选择相应的文档进行深入学习。

**🔍 需要帮助？** 如果您在使用过程中遇到问题，请首先查看 [故障排除指南](troubleshooting.md)，或在GitHub上提交Issue获取支持。