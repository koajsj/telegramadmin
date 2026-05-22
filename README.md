# Telegram 群管理机器人

基于规则的 Telegram 群管理机器人。可自动删除垃圾信息，并禁言或封禁发送者。

## 最简部署

1) 把机器人拉进群，并授予 “删除消息” 和 “封禁用户” 权限。

2) 在 Debian VPS 上执行：

```bash
git clone https://github.com/koajsj/tgadmin.git telegram-moderation-bot
cd telegram-moderation-bot
sudo bash setup_debian.sh
```

脚本会自动安装依赖、写入配置并创建服务。你只需要输入一次 `BOT_TOKEN`。

## 词库导入

把违禁词 `.txt` 放在当前目录，默认会自动加载 `data/` 目录下的所有 `.txt`（不会加载 `requirements.txt`）。

每行一个词，支持中文/英文。修改后发送 `/reloadkeywords` 或重启生效。

机器人还会根据已删除的垃圾消息自动学习新词，但只有在多次出现、且来自不同用户时才会加入，尽量减少误判。

当前已经内置了更有针对性的词库分类，例如：

- `成人内容.txt`
- `诈骗广告.txt`
- `博彩赌博.txt`

## 私聊后台管理

私聊机器人发送 `/admin` 打开面板（管理员ID会自动从群管理员列表同步，每天更新）。

如果提示未授权，请在群里发一条消息让机器人同步管理员列表。

如果还没有设置“机器人主人”，第一位通过私聊打开面板的群管理员会自动成为主人。

按钮支持：规则开关、用户名过滤、切换禁言/封禁、切换自学习、预设禁言时长、重新载入词库。

按钮文字已经改成中文说明，点起来更直观。

常用指令：

```
/mute 3600
/mute 2h
/action mute
/action ban
/flood 6 10
/reloadkeywords
/addkeyword 关键词
/delkeyword 关键词
/learn
/status
```

部署完成后，机器人在线并加入群后，就可以直接在私聊里发送 `/admin` 进行管理。

## 主要配置说明

```
AUTO_LOAD_TXT=true  # 自动加载当前目录下的 .txt 词库
KEYWORDS_FILES=文件1.txt,文件2.txt  # 可选，指定额外词库
LEARNING_ENABLED=true  # 自动学习新词
RULE_ENABLE_USERNAME=true  # 检测用户名是否包含违禁词
FLOOD_MAX_MESSAGES=6  # 刷屏阈值
FLOOD_WINDOW_SECONDS=10  # 刷屏时间窗
```
