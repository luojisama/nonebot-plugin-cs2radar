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
- `pwlogin <手机号> <验证码>`: 登录完美平台并保存本地会话
- `pw <昵称/SteamID>`: 查询完美平台战绩
- `bind <5e|pw> <玩家名>`: 绑定常用查询对象
- `match [5e|pw|mm] [@群友] [局数]`: 查询最近第 N 把详细对局并生成复盘

## 配置

环境变量统一使用 `cs2radar_*` 前缀；旧的 `cs_pro_*` 前缀当前仍兼容一版，但会打印弃用警告。

```env
cs2radar_llm_enabled=true
cs2radar_llm_api_type=openai
cs2radar_llm_api_url=https://api.openai.com/v1
cs2radar_llm_api_key=
cs2radar_llm_model=gpt-4o-mini

```

说明：

- LLM 配置为可选；未配置时仍可查询战绩，只是不生成 AI 复盘。
- `pw` / `match pw` / `match mm` 依赖完美平台登录态，请先执行 `pwlogin`。

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

这是正常行为。完美平台接口需要有效登录态，请先执行：

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

工作流优先使用仓库机密 `PYPI_API_TOKEN`；若未配置该机密，则回退为 PyPI Trusted Publishing。
