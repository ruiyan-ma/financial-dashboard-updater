# Financial Dashboard Updater

Notion Financial Dashboard 自动化工具：用于更新资产价格和汇率，以及 AI 自动记账

## 核心功能

### 📊 资产价格更新
- **多市场支持**：支持美股、港股、A股、黄金、加密货币
- **多币种支持**：支持多种计价货币，支持自定义默认计价货币
- **并行更新**：利用多线程技术同步更新数据
- **定时更新**：通过 Cloud Run 每小时自动更新
- **手动触发**：通过 Web 页面立即刷新
- **自动快照**：价格和汇率更新成功后，将 Dashboard Snapshot 写入 Notion

### 🤖 AI 自动记账
- **智能识别**：使用大模型自动识别支付截图中的交易信息
- **自动分类**：根据金额自动判断收入/支出，智能匹配分类
- **账户识别**：精准识别支付方式（支付宝、微信、银行卡等）
- **iOS 快捷指令**：双击手机背面自动截图记账

## 快速开始

### 配置环境变量

在项目根目录下创建一个 `.env` 文件，内容参考 `env_example`

AI 自动记账功能使用 OpenAI 兼容格式的 API，你可以选择提供视觉模型的任意平台

⚠️ 所选模型必须为**视觉多模态模型**（支持 `image_url` 类型的消息内容）

默认使用 [SiliconFlow](https://cloud.siliconflow.cn) + Qwen3.6-35B-A3B 模型，如需更换平台或模型，修改 `MODEL_BASE_URL` 和 `MODEL_NAME` 即可

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

访问 `http://localhost:5001`（或你自定义的端口）即可使用自动记账和手动更新功能

### 本地部署

确保你的电脑已安装 Python 3.8+

```bash
# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
python3 run.py
```

### iOS 快捷指令

**[👉 点击安装 “Notion Updater” 快捷指令](https://www.icloud.com/shortcuts/aba1bdb6b07f4890b188f514b4be4149)**

安装完成后，请对快捷指令进行编辑，将 “Get contents of URL” 中的链接替换为你的主机地址

```
http://<your-machine-ip>:5001/api/transaction/shortcut
```

如果部署在 Cloud Run，还需要在 “Get contents of URL” 中添加请求头：

```text
Authorization: Bearer <SHORTCUT_API_TOKEN>
```

URL 改为 Cloud Run 提供的 HTTPS 地址，路径仍为 `/api/transaction/shortcut`。

打开 “设置” -> “辅助功能” -> “触控” -> “轻点背面” -> “轻点两下”，然后选择 “Notion Updater” 快捷指令

完成上述设置后，就可以通过“双击手机背面”来调取快捷指令，自动完成记账

### 远程访问

如果需要在任何地方（使用手机信号）访问页面，可以使用 [Tailscale](https://tailscale.com/)

1. **安装**：在你的电脑和手机上下载并登录同一个 Tailscale 账号

2. **获取地址**：在电脑的 Tailscale 菜单中找到它的专属 IP（例如 `100.x.x.x`）

3. **远程触发**：只需在手机浏览器访问 `http://100.x.x.x:5001` 即可触发更新

## 让 AI 读取 Dashboard 内容

在 Codex 或 Claude Code 上安装 Notion 插件后，由于 AI 无法读取 Formula 属性的计算结果，我们需要为其生成 JSON Snapshot

```bash
python3 refresh_dashboard.py
```

脚本先更新 Asset 价格和 Currency 汇率；全部更新成功后，再读取 Asset、Platform、Net Value 和 Growth Log 数据库，并将 JSON 写入 `AI Snapshot` 页面

为减少无效数据，美元市值为零的 Asset、总价值为零的 Platform，以及持仓数量为零的 Holding 不会出现在 Snapshot 中

## Cloud Run

Cloud Run 托管自动记账网页和 API；`dashboard-refresh` Job 更新价格并生成 Snapshot，由 Cloud Scheduler 在每小时的第 30 分钟触发。

网页首次访问时需要输入 `SHORTCUT_API_TOKEN`。Notion Integration 还需要拥有相关数据库及其 Formula、Rollup 所依赖数据库的访问权限。

## 项目结构

```text
.
├── .env                  # 环境配置文件
├── env_example           # 环境变量示例
├── Dockerfile            # Docker 镜像构建配置
├── docker-compose.yml    # Docker Compose 编排配置
├── requirements.txt      # Python 依赖
├── run.py                # 服务启动入口
├── refresh_dashboard.py  # 更新价格并生成 Snapshot
├── gen_snapshot.py       # 生成 JSON Snapshot
├── backend/              # 后端代码
│   ├── app.py            # Flask 路由
│   ├── core/             # 核心引擎
│   └── services/         # 业务逻辑
└── frontend/             # 前端界面
    ├── templates/        # HTML 模板
    └── static/           # CSS/JS 资源
```

## 许可证

MIT License
