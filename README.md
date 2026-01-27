# Financial Dashboard Updater

Notion Financial Dashboard 自动化工具：用于更新资产价格和汇率，以及 AI 自动记账

## 核心功能

### 📊 资产价格更新
- **多市场支持**：支持美股、港股、A股、黄金、加密货币
- **多币种支持**：支持多种计价货币，支持自定义默认计价货币
- **并行更新**：利用多线程技术同步更新数据
- **定时更新**：每 60 分钟自动更新
- **手动触发**：通过访问本地指定的 Web 端口（默认 5001）即可立即刷新

### 🤖 AI 自动记账
- **智能识别**：使用 Gemini Vision API 自动识别支付截图中的交易信息
- **自动分类**：根据金额自动判断收入/支出，智能匹配分类
- **账户识别**：精准识别支付方式（支付宝、微信、银行卡等）
- **一键记账**：只需提供截图路径，自动创建 Notion 记账条目

## 快速开始

### 配置环境变量

在项目根目录下创建一个 `.env` 文件，内容参考 `env_example`

### 使用 Docker 部署（推荐）

```bash
# 构建并启动容器
docker compose up -d --build

# 查看日志
docker logs notion-updater

# 停止容器
docker stop notion-updater

# 重启容器
docker restart notion-updater
```

程序启动后会立即执行一次更新，随后每隔一小时更新一次

若需手动更新，可在浏览器访问：`http://localhost:5001` (或你自定义的端口)

### 本地部署

确保你的电脑已安装 Python 3.8+

```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动资产更新服务
python run.py

# 或使用 AI 自动记账
python auto_expense.py /path/to/screenshot.png
```

### 远程访问

如果需要在任何地方（使用手机信号）访问页面，可以使用 [Tailscale](https://tailscale.com/)

1. **安装**：在你的电脑和手机上下载并登录同一个 Tailscale 账号

2. **获取地址**：在电脑的 Tailscale 菜单中找到它的专属 IP（例如 `100.x.x.x`）

3. **远程触发**：只需在手机浏览器访问 `http://100.x.x.x:5001` 即可触发更新

## 项目结构

```text
.
├── .env                  # 环境配置文件
├── env_example           # 环境变量示例
├── Dockerfile            # Docker 镜像构建配置
├── docker-compose.yml    # Docker Compose 编排配置
├── requirements.txt      # Python 依赖
├── run.py                # 资产更新服务启动入口
├── auto_expense.py       # AI 自动记账脚本
├── updater.log           # 运行日志（自动生成）
├── backend/              # 后端代码
│   ├── app.py            # Flask 路由
│   ├── core/             # 核心引擎
│   └── services/         # 业务逻辑
└── frontend/             # 前端界面
    ├── templates/
    └── static/
```

## 许可证

MIT License
