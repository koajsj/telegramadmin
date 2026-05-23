# 项目结构分析与整理说明

## 1. 现状分析

当前仓库职责已经具备基础分层：

- `bot/handlers`：命令与事件入口。
- `bot/services`：业务逻辑与外部交互。
- `bot/database`：模型、会话、仓储。
- `bot/schemas`：类型定义。
- `bot/keyboards`：私聊面板与日志按钮。
- `bot/utils`：权限与通用工具。
- `migrations`：数据库迁移。
- `scripts`：部署与更新脚本。
- `tests`：测试。

## 2. 发现的问题

- 任务型代码与服务逻辑混放：`admin_sync` 更接近后台任务，不是纯服务函数。
- 私聊 Owner 鉴权逻辑散落在 handler 内，缺少独立守卫层。
- 私聊面板统计与导出权限语义不够明确（已收敛为 Owner-only）。
- 缺少学习候选数据模型，历史建议难以审核与追踪。

## 3. 已做整理

- 新增 `bot/tasks/`，并将管理员同步任务落到 `bot/tasks/admin_sync_task.py`。
- 保留 `bot/services/admin_sync.py` 兼容导出，避免破坏旧引用。
- 新增 `bot/middlewares/owner_guard.py`，统一私聊 Owner 守卫逻辑。
- 新增 `learning_candidates` 数据表与迁移，承载候选词/规则审核状态。
- 将学习建议扫描、候选审核、观察启用、正式启用流程独立到：
  - `bot/services/learning_intelligence.py`
  - `bot/services/learning_review.py`

## 4. 冗余/临时文件检查结论

- 未发现已跟踪的 `__pycache__`、临时文件、日志文件进入仓库。
- 根目录 `setup_debian.sh` 与 `update_debian.sh` 为脚本入口转发器，保留。
- `scripts/` 中为实际部署逻辑，保留。

## 5. 后续建议

- 若继续扩展，可把 `services` 按子域拆分为 `moderation/lexicon/audit/learning` 子包。
- 增加面向生产的定时任务调度器（如 APScheduler 或独立 worker）统一执行 `tasks`。
