# nonebot-plugin-cs2radar

NoneBot2 的 CS2 插件，提供职业选手查询、近期赛事/赛果、5E 战绩、完美平台战绩、官匹战绩、账号绑定与单局详细复盘。

## 安装

### 使用 nb-cli

```bash
nb plugin install nonebot-plugin-cs2radar
```

### 使用 pip

```bash
pip install nonebot-plugin-cs2radar
```

### 安装 Playwright 浏览器

本插件依赖 `playwright` 渲染图片，请额外执行：

```bash
playwright install chromium
```

## 适配器

- `OneBot V11`

## 命令

- `cs查询 <选手名>`: 查询职业选手资料卡
- `cs赛事`: 查询近期赛事与比赛
- `赛果`: 查询近几日赛果
- `5e <ID/昵称>`: 查询 5E 战绩
- `pwlogin <手机号> <验证码>`: 可选的应急登录命令，仅限超级用户私聊且默认关闭
- `pw <昵称/SteamID>`: 查询完美平台战绩
- `bind <5e|pw> <玩家名>`: 绑定常用查询对象
- `match [5e|pw|mm] [@群友] [局数]`: 查询最近第 N 把详细对局并生成复盘

## 配置

环境变量统一使用 `cs2radar_*` 前缀。旧的 `cs_pro_*` 配置默认忽略；仅迁移期间显式设置
`cs2radar_allow_legacy_config=true` 时才会临时读取，并会打印弃用警告。

```env
cs2radar_llm_enabled=false
cs2radar_llm_api_type=openai
cs2radar_llm_api_url=https://api.openai.com/v1
cs2radar_llm_api_key=
cs2radar_llm_model=gpt-4o-mini

# 推荐：通过服务器环境变量提供完美平台 Session，不经过 QQ 消息
cs2radar_pw_token=
cs2radar_pw_steam_id=

# 默认不把 token 写入磁盘
cs2radar_pw_session_persist=false

# QQ 登录默认关闭；确需使用时仍只允许 SUPERUSER 私聊
cs2radar_pw_login_enabled=false

cs2radar_max_concurrency=2
cs2radar_cooldown_seconds=10
cs2radar_allow_query_others=false
cs2radar_allow_legacy_config=false

```

说明：

- LLM 默认关闭；启用后仅使用本插件自己的 `cs2radar_llm_*` 配置，不会复用其他插件的 Key。
- LLM API URL 必须使用 HTTPS，且不得在 URL 中嵌入用户名或密码。
- `pw` / `match pw` / `match mm` 依赖完美平台登录态，请优先通过服务器环境变量配置。
- 推荐在服务器环境变量中设置 `cs2radar_pw_token` 与 `cs2radar_pw_steam_id`。不要在群聊发送手机号和验证码。
- `cs2radar_allow_query_others` 默认关闭，避免群成员查询他人的绑定战绩。
- Linux 下敏感文件会收紧为仅当前用户可读写；Windows 部署应额外通过目录 ACL 或容器隔离保护数据目录。

## 数据存储与迁移

插件默认把数据存储到 `nonebot-plugin-localstore` 的插件数据目录下，并会尝试自动迁移旧版本的以下文件：

- `data/cs_pro/user_bindings.db`
- `data/cs_pro/user_data.db`
- `data/cs_pro/user_data.json`
- `data/cs_pro/pw_session.json`

## 常见问题

### 1. 提示找不到浏览器或渲染失败

请确认已经执行过：

```bash
playwright install chromium
```

### 2. `pw` 查询提示先登录

这是正常行为。推荐在服务器环境变量中配置 token 与 Steam ID。

如确需临时通过 QQ 登录，必须同时满足：

- 发送者在 NoneBot `SUPERUSERS` 中；
- 使用机器人私聊；
- 管理员显式设置 `cs2radar_pw_login_enabled=true`；
- 已确认 NapCat、NoneBot 和容器日志不会记录敏感消息。

之后在私聊执行：

```bash
pwlogin <手机号> <验证码>
```

### 3. AI 复盘没有返回

未配置 LLM Key、模型返回非 JSON、接口超时都会触发降级。此时插件仍会返回战绩图片，只是不附带 AI 结论。

## License

MIT

## 发布

推送语义化标签后会自动触发 GitHub Actions 发布到 PyPI，例如：

```bash
git tag v0.1.0
git push origin v0.1.0
```

工作流使用 PyPI Trusted Publishing，并将第三方 Actions 固定到具体提交。
