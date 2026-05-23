# tgadmin（Telegram 群管理机器人）

本项目是在原有雏形上做的增量重构，不是推翻重写。

## 你最关心的结论

- 部署已简化为：**VPS 上执行 `sudo bash setup_debian.sh`，只输入一次 Bot Token 即可完成**。
- 不需要手动写 `.env`，脚本会自动生成并写入默认配置。
- 更新已简化为：`sudo bash update_debian.sh`。
- 已内置分级权限：普通群管理员仅可低风险操作，Owner 才可高风险/全局操作。

---

## 1. 当前功能（MVP）

- 基础命令：`/start /help /warn /mute /ban /unban /history /settings /setlog /reloadkeywords`
- 私聊面板：`/start` 或 `/panel` 打开多级 Inline 控制台
- 自动审核：关键词过滤、链接过滤、刷屏检测
- 新人管理：入群欢迎、新人观察期（禁链接/禁媒体）
- 阶梯处罚：删除 -> 警告 -> 短禁言 -> 长禁言 -> 封禁
- 观察模式：只记录命中并通知，不自动处罚
- 管理日志：日志群推送 + Inline 快捷操作按钮
- 持久化：PostgreSQL
- 短期状态：Redis（刷屏窗口）

---

## 1.1 命令与按钮说明（第二轮）

- 私聊命令：
  - `/start`：打开私聊控制台首页
  - `/panel`：进入群组选择与管理面板
  - `/status`：查看运行/配置状态
- 群内命令：
  - `/warn`：警告用户（管理员）
  - `/mute`：禁言用户（普通管理员仅短时禁言）
  - `/ban` `/unban`：封禁/解封（仅 Owner）
- Inline 按钮（日志群）：
  - `警告（记录违规）`
  - `禁言10分钟（短期）`
  - `禁言1小时（中期）`
  - `封禁（高风险）`
  - `忽略（不处罚）`
  - `白名单（后续放行）`
- 私聊面板按钮：已在按钮文案中加入中文短说明，例如“运行状态（健康检查）”“审计导出（CSV/JSON）”。

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

### 4.1 拉取代码

```bash
git clone https://github.com/koajsj/tgadmin.git
cd tgadmin
```

### 4.2 一键部署

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

### 4.3 查看运行状态

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
