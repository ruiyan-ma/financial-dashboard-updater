# Financial Dashboard Updater

本项目用于为 Notion Financial Dashboard 提供自动更新行情数据和自动记账的功能

## 核心功能

### 📊 行情与汇率更新
- **多市场支持**：支持美股、港股、A股、黄金、加密货币
- **多币种支持**：支持多种计价货币，支持自定义默认计价货币
- **并行更新**：多线程同步更新数据
- **账户快照**：生成可供 ChatGPT 读取的账户快照

### 🤖 AI 自动记账
- **智能识别**：使用视觉模型识别交易截图中的信息
- **自动分类**：智能匹配收入和支出分类
- **账户识别**：自动识别交易账户（支付宝、微信、银行卡等）
- **修改与确认**：网页端允许修改识别结果并确认
- **iOS 快捷指令**：双击手机背面完成自动记账

## 运行要求

- Python 3.11+
- 已完成相关数据库授权的 Notion Integration
- 兼容 OpenAI 接口的视觉模型

## 配置环境变量

在项目根目录创建 `.env` 并填写实际配置：

```bash
cp env_example .env
```

其中 `MODEL_BASE_URL` 和 `MODEL_NAME` 可选择兼容 OpenAI 接口的任意平台及其视觉多模态模型（支持 `image_url` 消息类型）

## 本地部署

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. 启动自动记账服务

```bash
python3 -m tracker.main
```

启动服务后访问 `http://localhost:5001` （或你自定义的端口）即可上传图片并完成自动记账

### 3. 更新行情数据

```bash
python -m updater.main
```

程序将依次执行以下任务：

1. 更新 Asset 数据库中的资产价格
2. 更新 Currency 数据库中的换算汇率
3. 等待 5 秒，让 Notion 重新计算 Formula 和 Rollup 属性
4. 读取 Asset、Platform、Net Value 和 Growth Log 数据库
5. 将 JSON Snapshot 写入 AI Snapshot 页面中的代码块

如果 Asset 或 Currency 数据库更新失败，则不会生成 Snapshot，并在终端中显示具体失败条目

## Docker 本地运行

构建并启动容器：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker logs notion-updater
```

当前 Docker 容器只启动自动记账服务，如需在容器内更新行情：

```bash
docker exec notion-updater python -m updater.main
```

停止服务：

```bash
docker compose down
```

## iOS 快捷指令

**[👉 点击安装 “Notion Updater” 快捷指令](https://www.icloud.com/shortcuts/aba1bdb6b07f4890b188f514b4be4149)**

安装完成后，将快捷指令中 “Get contents of URL” 的地址修改为：

```text
http://<本机局域网 IP>:5001/api/transaction/shortcut
```

打开 “设置” -> “辅助功能” -> “触控” -> “轻点背面” -> “轻点两下”，然后选择 “Notion Updater” 快捷指令

完成上述设置后，就可以通过“双击手机背面”来调取快捷指令，自动完成记账

若手机与运行服务的电脑不在相同局域网内，需要自行配置远程访问方案

## 项目结构

```text
.
├── tracker/                 # AI 自动记账服务
│   ├── main.py              # Flask 服务入口
│   ├── app.py               # HTTP 路由
│   ├── config.py            # 环境配置
│   ├── service.py           # Notion 与模型客户端
│   ├── transactions.py      # 图片处理与模型响应
│   ├── templates/           # 网页模板
│   └── static/              # 前端 CSS 和 JavaScript
│
├── updater/                 # 行情更新服务
│   ├── main.py              # 更新任务入口
│   ├── assets.py            # 资产价格更新
│   ├── currencies.py        # 汇率更新
│   ├── market_data.py       # 获取外部行情数据
│   ├── notion.py            # Notion 客户端
│   └── snapshot.py          # Snapshot 生成及写入
│
├── shared/                  # 共用工具函数
├── env_example              # 环境变量示例
├── requirements.txt         # Python 依赖
├── Dockerfile               # 本地容器镜像
└── docker-compose.yml       # 本地容器配置
```

## 许可证

MIT License
