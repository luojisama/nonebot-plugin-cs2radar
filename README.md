# nonebot-plugin-cs2radar

NoneBot2 CS2 综合数据插件，支持职业选手查询、近期赛事与赛果、5E / 完美世界 / 官匹战绩查询、详细对局深度复盘及基于 HLTV 官方职业选手的智能战术画像与天梯瓶颈突破诊断。

---

## 功能特性

- **职业与赛事追踪**：支持查询 HLTV 职业选手资料卡、近期国际大赛赛程与赛果。
- **双平台天梯战绩**：支持 5E 对战平台（专属橙色主题）与完美世界电竞平台（科技蓝主题）综合生涯战绩查询，卡片视口统一为 960px 宽度并针对移动端进行排版优化。
- **智能战术画像与职业对标**：对接 HLTV 近 3 个月 Top 30 职业选手 7 维基准库（donk, b1t, ropz, sh1ro, m0NESY, apEX 等），将玩家数据结构化呈现为 4 维微卡片（【战力定位】【技术风格与职业对标】【偏科与武器地图】【天梯瓶颈突破】）。
- **零依赖智能兜底**：大模型未配置、网络超时或额度耗尽时，系统自动根据玩家真实 Rating、ADR、爆头率、首杀率及六维雷达指标进行智能模式匹配，100% 优雅生成结构化分析卡片。
- **单局详细复盘**：支持通过 `/match` 命令查询最近第 N 把比赛（5E、完美、官匹），呈现双方攻防半场走势、回合序列、击杀贡献与深度战局走势复盘。
- **元数据支持**：插件元数据内置完整的 `usage`、`extra["help"]` 与结构化 `extra["menu"]`，便于其他帮助插件或管理菜单反射查询。

---

## 安装

### 使用 nb-cli

```bash
nb plugin install nonebot-plugin-cs2radar
```

### 使用 pip

```bash
pip install nonebot-plugin-cs2radar
```

### 安装 Playwright 渲染依赖

本插件依赖 Playwright 渲染战绩图片，安装插件后需执行：

```bash
playwright install chromium
```

---

## 适配器支持

- `OneBot V11`

---

## 命令列表

| 命令 | 别名 | 参数说明 | 功能说明 |
| :--- | :--- | :--- | :--- |
| `cs查询` | `cs选手`, `csplayer` | `<选手名>` | 查询职业选手资料卡与能力评分 |
| `cs赛事` | `赛事`, `csgo赛事`, `cs2赛事` | 无 | 查询近期国际赛事与进行中赛程 |
| `赛果` | `cs赛果`, `赛事赛果` | 无 | 查询近几日完赛赛果与比分 |
| `5e` | `5e战绩`, `5e查询`, `cs战绩` | `[ID/昵称] [-r]` | 查询 5E 平台综合战绩与 4 维战术画像，无参数查绑定 |
| `pw` | `pw战绩`, `pw查询`, `完美战绩` | `[昵称/SteamID] [-r]` | 查询完美平台综合战绩与 4 维战术画像，无参数查绑定 |
| `pwlogin` | `完美登录` | `<手机号> <验证码>` | 登录完美世界电竞平台并保存本地会话 |
| `bind` | `绑定`, `添加`, `绑定用户` | `<5e\|pw> <玩家名>` | 绑定发送者 QQ 的常用查询玩家 |
| `match` | `战绩`, `查询战绩` | `[5e\|pw\|mm] [@群友] [局数] [-r]` | 查询指定平台最近第 N 把详细对局并生成四维战术复盘 |

> **提示**：查询命令后缀加上 `-r`（例如 `/pw 丰川NiKola -r` 或 `/5e -r`）可强制跳过本地缓存，刷新战绩与 AI 战术分析结果。

---

## 配置项说明

环境变量统一使用 `cs2radar_*` 前缀；旧版 `cs_pro_*` 前缀保持向后兼容。在 NoneBot2 项目根目录的 `.env` 或 `.env.prod` 中按需配置：

```env
# 基础配置
cs2radar_priority=5
cs2radar_http_timeout=15

# 主 LLM 配置
cs2radar_llm_enabled=true
cs2radar_llm_api_type=openai
cs2radar_llm_api_url=https://api.openai.com/v1
cs2radar_llm_api_key=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
cs2radar_llm_model=gpt-4o-mini
cs2radar_llm_timeout=30

# 备用 LLM 配置（可选容灾）
cs2radar_llm_backup_enabled=false
cs2radar_llm_backup_api_type=openai
cs2radar_llm_backup_api_url=https://api.openai.com/v1
cs2radar_llm_backup_api_key=
cs2radar_llm_backup_model=gpt-4o-mini
```

### 完整配置项清单

| 配置项 | 类型 | 默认值 | 旧版兼容名称 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `cs2radar_priority` | int | `5` | `cs_pro_priority` | 插件事件响应优先级（1-20） |
| `cs2radar_bind_db_path` | str | `None` | `cs_pro_bind_db_path` | 账号绑定 SQLite 数据库路径，留空时默认存放在 localstore 数据目录 |
| `cs2radar_http_timeout` | int | `15` | `cs_pro_http_timeout` | 战绩与接口数据抓取超时时间（秒，5-60） |
| `cs2radar_llm_enabled` | bool | `true` | `cs_pro_llm_enabled` | 是否启用 LLM 战术分析与智能对标画像 |
| `cs2radar_llm_api_type` | str | `"openai"` | `cs_pro_llm_api_type` | 主大模型接口协议类型，支持 `openai`、`gemini`、`anthropic` |
| `cs2radar_llm_api_url` | str | `"https://api.openai.com/v1"` | `cs_pro_llm_api_url` | 主大模型接口 Base URL（支持各大中转/代理格式） |
| `cs2radar_llm_api_key` | str | `""` | `cs_pro_llm_api_key` | 主大模型 API Key（未配置时自动降级走智能动态兜底算法） |
| `cs2radar_llm_model` | str | `"gpt-4o-mini"` | `cs_pro_llm_model` | 主大模型调用模型名称 |
| `cs2radar_llm_timeout` | int | `30` | `cs_pro_llm_timeout` | 大模型请求超时时间（秒，5-120） |
| `cs2radar_llm_system_prompt` | str | `None` | `cs_pro_llm_system_prompt` | 自定义单局复盘 System Prompt（为空时使用内置电竞分析师预设） |
| `cs2radar_llm_backup_enabled` | bool | `false` | `cs_pro_llm_backup_enabled` | 是否启用备用大模型容灾链路 |
| `cs2radar_llm_backup_api_type` | str | `"openai"` | `cs_pro_llm_backup_api_type` | 备用大模型接口协议类型 |
| `cs2radar_llm_backup_api_url` | str | `"https://api.openai.com/v1"` | `cs_pro_llm_backup_api_url` | 备用大模型接口 Base URL |
| `cs2radar_llm_backup_api_key` | str | `""` | `cs_pro_llm_backup_api_key` | 备用大模型 API Key |
| `cs2radar_llm_backup_model` | str | `"gpt-4o-mini"` | `cs_pro_llm_backup_model` | 备用大模型调用模型名称 |

---

## 元数据与插件联动

为便于第三方插件（如帮助菜单、权限管理或机器人总控后台）自动获取命令信息，本插件在 `__plugin_meta__` 中暴露了标准化的元数据结构：

```python
from nonebot import get_plugin

plugin = get_plugin("nonebot_plugin_cs2radar")
if plugin and plugin.metadata:
    # 纯文本帮助内容
    help_text = plugin.metadata.usage
    # 或者通过 extra 读取扩展字典
    menu_list = plugin.metadata.extra.get("menu", [])
    config_dict = plugin.metadata.extra.get("configs", {})
```

---

## 数据存储与旧版本迁移

插件严格遵循 NoneBot2 `nonebot-plugin-localstore` 标准规范，自动管理数据与持久化存储。启动时会自动检测并平滑迁移旧版本（如 `data/cs_pro/`）中的以下历史文件：

- `user_bindings.db`（用户平台绑定数据）
- `user_data.db` / `user_data.json`（历史战绩缓存）
- `pw_session.json`（完美平台登录态）

---

## 常见问题

### 1. 提示找不到浏览器或渲染失败
Playwright 核心依赖未安装，请在运行环境中执行：
```bash
playwright install chromium
```

### 2. 完美战绩查询提示请先登录
完美世界官方接口需要已绑定的移动端登录态。初次使用时请执行一次：
```text
/pwlogin <手机号> <验证码>
```
会话态将加密保存在本地并自动保持心跳。

### 3. 未配置大模型或 API 欠费时能否正常使用？
可以。插件内置了全量智能动态兜底算法。当未配置 API Key 或上游接口不可用时，系统会自动基于玩家的实际数据（Rating、ADR、爆头率、首杀率及雷达指标）对标职业选手并输出 4 维微报告，不会中断查询流程。

---

## 构建与发布

本仓库已配置 GitHub Actions 自动构建与发布工作流。推送语义化版本 Tag 即可自动构建并发布 Wheel 至 PyPI：

```bash
git tag v0.2.1
git push origin v0.2.1
```

---

## License

[MIT](LICENSE)
