# Telegram 群管理机器人

一个面向 Telegram 群组的自动化管理机器人。它会根据链接、关键词、用户名、刷屏、重复消息和超长消息等规则删除垃圾消息，并按配置禁言或封禁发送者。管理员可在机器人私聊里使用中文按钮面板调整规则。

## 功能

- 自动删除命中规则的群消息
- 支持禁言、封禁、累计违规后封禁
- 支持链接、关键词、用户名、刷屏、重复消息、超长消息检测
- 支持从 `data/*.txt` 和自定义文件自动加载词库
- 支持私聊后台：规则开关、动作切换、禁言时长、刷屏阈值、词库重载
- 支持 `/addkeyword` 和 `/delkeyword` 动态维护自定义关键词
- 支持自学习：多个用户多次触发的可疑新词会加入自定义关键词
- 支持同步群管理员，避免误处理群管理员消息
- 支持可选日志群，记录已处理消息的原因和预览

## 快速部署

1. 在 BotFather 创建机器人并取得 `BOT_TOKEN`。
2. 把机器人拉进目标群。
3. 给机器人至少授予以下权限：
   - 删除消息
   - 封禁用户
   - 限制用户发送消息
4. 在 Debian 服务器执行：

```bash
git clone https://github.com/koajsj/tgadmin.git telegram-moderation-bot
cd telegram-moderation-bot
sudo bash setup_debian.sh
```

脚本会创建项目内 `.venv`、安装依赖、写入 `.env`、创建并启动 `tgadmin.service`。脚本只会要求输入一次 `BOT_TOKEN`。

依赖中包含 `python-telegram-bot[job-queue]`，用于定时同步群管理员列表。

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env` 填入 `BOT_TOKEN` 后运行：

```bash
.venv\Scripts\python main.py
```

Linux 或 Debian 上使用：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python main.py
```

## 管理面板

在群里让机器人看到至少一条消息后，私聊机器人发送：

```text
/admin
```

如果还没有设置机器人主人，第一位已同步的群管理员打开后台时会自动成为主人。后续主人拥有最高权限。

后台按钮支持：

- 开关链接检测、关键词过滤、用户名过滤、刷屏拦截、重复消息、超长消息、自学习
- 在禁言和封禁之间切换处理动作
- 快速设置刷屏阈值
- 快速设置禁言时长
- 重新载入词库
- 刷新当前状态

常用命令：

```text
/status
/reloadkeywords
/action mute
/action ban
/mute 3600
/mute 2h
/flood 6 10
/addkeyword 关键词
/delkeyword 关键词
/learn
```

## 词库

默认会自动加载：

- `data/keywords.txt`
- `data/` 目录下的所有 `.txt`
- 项目根目录下的所有 `.txt`，但会跳过 `requirements.txt`

每行一个关键词，空行和以 `#` 开头的行会被忽略。修改词库后，发送 `/reloadkeywords` 或重启服务生效。

内置词库文件包括：

- `data/博彩赌博.txt`
- `data/广告类型.txt`
- `data/成人内容.txt`
- `data/色情类型.txt`
- `data/色情词库.txt`
- `data/诈骗广告.txt`

自定义关键词通过 `/addkeyword` 添加，保存在 `data/state.json`。该文件是运行时状态，不建议提交到 Git。

## 配置

复制 `.env.example` 为 `.env` 后按需修改：

```env
BOT_TOKEN=your_telegram_bot_token
LOG_CHAT_ID=
ACTION=mute
MUTE_DURATION_SECONDS=86400
BAN_AFTER_STRIKES=0
STRIKE_WINDOW_SECONDS=86400
ADMIN_CACHE_TTL_SECONDS=300
KEYWORDS=free money,crypto,airdrop
KEYWORDS_FILE=data/keywords.txt
KEYWORDS_FILES=
AUTO_LOAD_TXT=true
LEARNING_ENABLED=true
LEARNING_MIN_HITS=3
LEARNING_MIN_UNIQUE_USERS=2
LEARNING_PROMOTE_HITS=6
LEARNING_PROMOTE_UNIQUE_USERS=3
LEARNING_RETIRE_SECONDS=2592000
LEARNING_WINDOW_SECONDS=86400
DELETE_SCORE_THRESHOLD=20
MUTE_SCORE_THRESHOLD=60
BAN_SCORE_THRESHOLD=100
LINK_SCORE=35
KEYWORD_SCORE=60
LEARNED_KEYWORD_SCORE=18
USERNAME_SCORE=20
LENGTH_SCORE=15
FLOOD_SCORE=35
REPEAT_SCORE=25
COMBO_LINK_KEYWORD_BONUS=15
COMBO_USERNAME_KEYWORD_BONUS=10
COMBO_FLOOD_REPEAT_BONUS=10
RULE_ENABLE_LINK=true
RULE_ENABLE_KEYWORDS=true
RULE_ENABLE_USERNAME=true
RULE_ENABLE_FLOOD=true
RULE_ENABLE_REPEAT=true
RULE_ENABLE_LENGTH=true
MAX_MESSAGE_LENGTH=600
FLOOD_MAX_MESSAGES=6
FLOOD_WINDOW_SECONDS=10
REPEAT_MAX_DUPES=2
REPEAT_WINDOW_SECONDS=60
```

关键配置说明：

- `ACTION`：违规后的动作，支持 `mute` 或 `ban`
- `MUTE_DURATION_SECONDS`：禁言秒数，设置为 `0` 时只删除消息
- `BAN_AFTER_STRIKES`：同一用户累计违规多少次后封禁，`0` 表示关闭
- `LOG_CHAT_ID`：可选日志群或日志频道 ID
- `KEYWORDS`：逗号分隔的内联关键词
- `KEYWORDS_FILE`：主词库文件
- `KEYWORDS_FILES`：逗号分隔的额外词库文件
- `AUTO_LOAD_TXT`：是否自动加载 `data/` 和项目根目录下的 `.txt`
- `LEARNING_MIN_HITS`：候选词出现次数阈值
- `LEARNING_MIN_UNIQUE_USERS`：候选词不同发送者数量阈值
- `LEARNING_PROMOTE_HITS`：候选词升级为高危词前的更高阈值
- `LEARNING_RETIRE_SECONDS`：学习词长期不再出现时自动退休的时间
- `DELETE_SCORE_THRESHOLD`：达到这个分数才删除消息
- `MUTE_SCORE_THRESHOLD`：达到这个分数才禁言
- `BAN_SCORE_THRESHOLD`：达到这个分数直接封禁

## 运维

查看服务状态：

```bash
sudo systemctl status tgadmin --no-pager
```

查看实时日志：

```bash
sudo journalctl -u tgadmin -f
```

重启服务：

```bash
sudo systemctl restart tgadmin
```

更新代码后重新安装依赖并重启：

```bash
git pull
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart tgadmin
```

## 测试

```bash
python -m unittest discover -s tests -v
```

当前测试覆盖规则判断和自学习关键词晋升，适合作为修改规则逻辑后的快速烟雾验证。
