# Financial Dashboard Updater

本项目对 Notion Financial Dashboard 提供行情更新和自动记账功能

项目包含两个独立入口：

- `tracker`：Flask Web 服务，通过图片识别交易并写入 Notion
- `updater`：更新资产价格和汇率，并将账户快照写入 Notion

本地可直接运行上述入口；云端使用 Cloud Run Service 托管 Tracker，使用 Cloud Run Job 运行 Updater，并由 Cloud Scheduler 定时触发

## 核心功能

### 📊 行情与汇率更新
- 支持美股、ETF、港股、A 股、黄金、加密货币
- 支持多币种计价，支持自定义默认计价币种
- 并行更新 Notion 中的资产价格和汇率
- 生成可供 AI 读取的 Dashboard JSON Snapshot

### 🤖 AI 自动记账
- 使用兼容 OpenAI 接口的视觉模型识别交易截图
- 提取商品名称、日期、金额、类型、交易账户
- 网页端可修改识别结果后再写入 Notion
- 支持 iOS Shortcut 自动截图记账

## 运行要求

- Python 3.11+
- 已完成相关数据库授权的 Notion Integration
- 兼容 OpenAI 接口的视觉模型

## 环境变量

在项目根目录创建 `.env` 并填写实际配置：

```bash
cp .env.example .env
```

其中 `MODEL_BASE_URL` 和 `MODEL_NAME` 可选择兼容 OpenAI 接口的任意平台及其视觉多模态模型（支持 `image_url` 消息类型）

本地运行无需配置 `TRACKER_API_TOKEN`

## 本地部署

安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-tracker.txt
pip install -r requirements-updater.txt
```

启动自动记账：默认地址为 `http://localhost:5001`

```bash
python -m tracker.main
```

更新行情数据：

```bash
python -m updater.main
```

## Cloud Run 部署（推荐）

部署前需安装 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)，并完成登录：

```bash
gcloud auth login
```

### 准备 Secret

选择 Google Cloud 项目，启用 Secret Manager：

```bash
PROJECT_ID=your-google-cloud-project
gcloud config set project "$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com
```

创建以下 Secret：

```bash
gcloud secrets create INTERNAL_INTEGRATION_TOKEN --replication-policy=automatic
gcloud secrets create MODEL_API_KEY --replication-policy=automatic
gcloud secrets create TRACKER_API_TOKEN --replication-policy=automatic
```

执行以下每条命令，粘贴实际 Token 值，按 `Ctrl-D` 完成输入：

```bash
gcloud secrets versions add INTERNAL_INTEGRATION_TOKEN --data-file=-
gcloud secrets versions add MODEL_API_KEY --data-file=-
gcloud secrets versions add TRACKER_API_TOKEN --data-file=-
```

部署脚本会把每个 Secret 只授权给实际需要它的专用 Runtime Service Account

### 配置部署参数

执行以下命令，编辑 `deploy/cloud-run.env`，填写各配置参数：

```bash
cp deploy/cloud-run.env.example deploy/cloud-run.env
```

### 执行部署

运行部署脚本，默认读取 `deploy/cloud-run.env` ：

```bash
./deploy/cloud-run.sh
```

如需传入其他配置文件：

```bash
./deploy/cloud-run.sh deploy/production.env
```

部署完成后，脚本会输出 Tracker URL、Updater Job 和 Scheduler 信息

### 验证服务

验证 Tracker 服务：

```bash
TRACKER_URL=$(gcloud run services describe notion-tracker \
  --region asia-east2 \
  --format='value(status.url)')
curl "$TRACKER_URL/health"
```

手动执行 Updater 任务：

```bash
REGION=asia-east2
gcloud run jobs execute notion-updater \
  --region "$REGION" \
  --wait
```

任务结束后，可直接看到执行成功或失败

## iOS 快捷指令

**[👉 安装 "Notion Tracker" 快捷指令](https://www.icloud.com/shortcuts/f074b9921832486a9e167a918b026dab)**

打开 "Notion Tracker" 快捷指令，找到 "Get contents of URL"

将地址修改为：

```text
https://<TRACKER_URL>/api/transaction/shortcut
```

将 Header 修改为：

```text
Authorization: Bearer <TRACKER_API_TOKEN>
```

打开 “设置 → 辅助功能 → 触控 → 轻点背面 → 轻点两下”，然后选择 "Notion Tracker" 快捷指令

完成上述设置后，就可以通过“双击手机背面”来调取快捷指令，自动完成记账

## 项目结构

```text
.
├── tracker/                 # AI 自动记账服务
│   ├── main.py              # 本地 Flask 启动入口
│   ├── app.py               # HTTP 路由和 API 鉴权
│   ├── config.py            # Tracker 环境配置
│   ├── service.py           # Notion 与模型客户端
│   ├── transactions.py      # 图片处理、模型调用和 Notion 写入
│   ├── templates/           # 网页模板
│   └── static/              # CSS 和 JavaScript
├── updater/                 # Cloud Run Job 更新任务
│   ├── main.py              # 更新任务入口
│   ├── assets.py            # 资产价格更新
│   ├── currencies.py        # 汇率更新
│   ├── market_data.py       # 外部行情数据
│   ├── notion.py            # Notion 客户端
│   └── snapshot.py          # Snapshot 生成与写入
├── shared/                  # 共用工具
├── .env.example             # 本地环境变量示例
├── deploy/                  # Cloud Run 部署配置与脚本
├── requirements-tracker.txt # Tracker 镜像依赖
├── requirements-updater.txt # Updater 镜像依赖
├── Dockerfile               # Tracker 镜像
└── Dockerfile.updater       # Updater 镜像
```
