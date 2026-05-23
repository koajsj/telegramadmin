# tgadmin（Telegram 群管理机器人）

本项目是在原有雏形上做的增量重构，不是推翻重写。

## 你最关心的结论

- 部署已简化为：**VPS 上执行 `sudo bash setup_debian.sh`，只输入一次 Bot Token 即可完成**。
- 不需要手动写 `.env`，脚本会自动生成并写入默认配置。
- 更新已简化为：`sudo bash update_debian.sh`。
- 已内置分级权限：普通群管理员仅可低风险操作，Owner 才可高风险/全局操作。

---

## 1. 当前功能（MVP）

- 基础命令：已实现 `/start /help /warn /mute /ban /unban /history /settings /setlog /reloadkeywords`。
- 私聊面板：支持通过 `/start` 或 `/panel` 打开多级 Inline 管理面板，可在私聊中完成常用管理操作。
- 自动审核能力：已实现关键词过滤、链接过滤、刷屏检测，支持规则命中后自动处置。
- 新人管理：支持入群欢迎、新人观察期、观察期内禁链接/禁媒体。
- 阶梯处罚：支持删除 -> 警告 -> 短禁言 -> 长禁言 -> 封禁的升级策略。
- 观察模式：支持只记录/通知不执行处罚，便于上线前调参与误封控制。
- 管理日志：支持日志群推送、快捷处置按钮、审计日志留存。
- 权限体系：支持 Owner 与群管理员分级权限，危险操作默认仅 Owner 可执行。
- 数据与状态：PostgreSQL 存储长期数据，Redis 处理刷屏窗口与短期状态。
- 部署能力：支持 Debian VPS 一键部署与一键更新（Docker Compose）。

---

## 1.1 命令与按钮说明（第二轮）

- 私聊命令：
  - `/start`：打开私聊控制台首页。
  - `/panel`：进入群组选择与管理面板。
  - `/help`：查看命令说明与权限说明。
  - `/status`：查看运行状态与当前配置摘要。
- 群内命令：
  - `/warn <user_id>`：警告目标用户并记录处罚历史（管理员可用）。
  - `/mute <user_id> <10m|1h|1d>`：禁言目标用户（普通管理员受最大禁言时长限制）。
  - `/ban <user_id>`：封禁用户（仅 Owner）。
  - `/unban <user_id>`：解封用户（仅 Owner）。
  - `/history <user_id>`：查看目标用户处罚历史（管理员可用）。
  - `/settings`：查看当前群规则与开关配置（管理员可用）。
  - `/setlog <log_chat_id>`：设置日志群（仅 Owner）。
  - `/reloadkeywords`：刷新关键词词库（仅 Owner）。
- Inline 按钮（日志群快捷处置）：
  - `警告（记录违规）`：写入处罚记录，不禁言。
  - `禁言10分钟（短期）`：快速短时禁言。
  - `禁言1小时（中期）`：快速中时禁言。
  - `封禁（高风险）`：直接封禁，受权限控制。
  - `忽略（不处罚）`：不执行处罚，仅结束当前处置。
  - `白名单（后续放行）`：加入白名单，降低误杀。
- 私聊面板按钮：
  - 已加入中文短说明文案，例如“运行状态（健康检查）”“审计导出（CSV/JSON）”。
  - 所有按钮回调会二次鉴权，不信任 callback_data。

---

## 2. 目录说明（已整理）

```text
bot/                  # 新架构主代码
  handlers/           # 命令、消息、回调、入群请求
  services/           # 规则、处罚、新人、日志
  database/           # SQLAlchemy 模型、会话、仓储
  schemas/            # 类型定义
  main.py             # Bot 入口

scripts/              # 运维脚本
  setup_debian.sh     # 一键部署（只需 Token）
  update_debian.sh    # 一键更新

docs/                 # 文档
  DEPLOY_DEBIAN.md    # Debian 详细部署与排障

docker-compose.yml
Dockerfile
main.py               # 根入口（转发到 bot.main）
setup_debian.sh       # 根快捷入口（调用 scripts/setup_debian.sh）
update_debian.sh      # 根快捷入口（调用 scripts/update_debian.sh）
```

---

## 3. 从本地推送到 GitHub

在你的本地仓库执行：

```bash
git add .
git commit -m "refactor: simplify debian deployment and improve bot architecture"
git push origin main
```

如果你的默认分支不是 `main`，替换成实际分支名。

---

## 4. VPS 首次部署（只输 Token）

> 适用于 Debian VPS。

### 4.1 前置准备（未安装 Git 时先执行）

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git ca-certificates curl
```

可选：设置时区（避免日志时间不一致）

```bash
sudo timedatectl set-timezone Asia/Shanghai
timedatectl
```

### 4.2 拉取代码

```bash
git clone https://github.com/koajsj/tgadmin.git
cd tgadmin
```

### 4.3 一键部署

```bash
sudo bash setup_debian.sh
```

脚本会自动完成：

1. 安装 Docker / Docker Compose（若未安装）
2. 自动生成 `.env`（若不存在）
3. 写入你输入的 `BOT_TOKEN`
4. 启动 `postgres` / `redis` / `bot`
5. 自动执行 `alembic upgrade head`
6. 默认不对公网暴露 PostgreSQL/Redis 端口（仅容器内访问）

### 4.4 查看运行状态

```bash
docker compose ps
docker compose logs -f bot
```

---

## 5. VPS 更新流程（以后就这几步）

进入项目目录后执行：

```bash
sudo bash update_debian.sh
```

更新脚本会自动：

1. `git fetch --all --prune`
2. `git pull --ff-only`
3. `docker compose up -d --build`
4. `alembic upgrade head`

---

## 6. 常用运维命令

```bash
# 实时看机器人日志
docker compose logs -f bot

# 重启机器人
docker compose restart bot

# 停止全部服务
docker compose down

# 启动全部服务
docker compose up -d

# 数据库备份
docker compose exec -T postgres pg_dump -U postgres tgadmin > backup.sql

# 数据库恢复
cat backup.sql | docker compose exec -T postgres psql -U postgres -d tgadmin
```

---

## 7. 环境变量说明（自动生成，可后续再改）

首次部署时脚本会自动写入：

- `BOT_TOKEN`
- `POSTGRES_PASSWORD`
- `BOT_OWNER_IDS`（Owner Telegram ID，逗号分隔）
- `DATABASE_URL`
- `REDIS_URL`
- `LOG_LEVEL`
- `ENVIRONMENT`
- `WEBHOOK_SECRET`

你不需要手工创建配置文件。

权限规则：
- 群管理员：`warn`、短时 `mute`（不超过 `GROUP_ADMIN_MAX_MUTE_SECONDS`）、查看配置和历史。
- Owner：`ban/unban`、黑白名单、日志群修改、词库刷新、全局敏感操作。
- 回调按钮：每次点击都会重新鉴权，不能靠伪造 callback_data 越权。

---

## 8. 开发与测试

```bash
python -m unittest discover -s tests -v
```

当前测试覆盖：
- MVP 服务层（阶梯处罚、新人限制、规则命中）

---

## 9. 生产部署建议

当前推荐：
- `Long Polling + Docker Compose`（简单稳定）

后续如果要高并发再升级：
- `Webhook + Nginx + HTTPS`

详细排障与进阶部署见：
- `docs/DEPLOY_DEBIAN.md`
