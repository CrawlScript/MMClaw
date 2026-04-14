
# ⚡ MMClaw

超轻量级、纯 Python 开发的 AI Agent 内核。

```bash
pip install mmclaw
```

<p align="center">
<img src="https://raw.githubusercontent.com/CrawlScript/MMClaw/main/MMCLAW_LOGO.jpg" width="400"/>
</p>

**主页:** [https://mmclaw.github.io](https://mmclaw.github.io)

**GitHub:** [https://github.com/CrawlScript/MMClaw](https://github.com/CrawlScript/MMClaw)

[English](https://github.com/CrawlScript/MMClaw/blob/main/README.md) | **中文说明**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)




> **说明：** 本项目在 v0.0.11 之前名为 [pipclaw](https://github.com/CrawlScript/pipclaw)。

MMClaw 是一个极简主义的、100% 纯 Python 编写的自主代理内核。虽然像 OpenClaw 这样的框架功能强大，但它们通常会引入沉重的依赖，如 Node.js、Docker 或复杂的 C 扩展。

MMClaw 剥离了复杂性，提供了一个清晰透明、易读的架构，既可以作为生产级的内核，也可以作为构建现代 AI Agent 的全面教程。

---

## 🆕 最新功能

**微信 (WeChat) 连接器 — 纯 Python 实现，零额外依赖。**
一秒完成绑定：运行 `mmclaw config`，选择微信模式，扫码即可。无需 Node.js，无需 Webhook，无需注册应用，即刻上线。

<p align="center">
<img src="https://raw.githubusercontent.com/CrawlScript/MMClaw/main/figs/MMClaw-WeChat.jpg" width="400"/>
</p>

## ✨ 特色功能：🤝 ClawMeets — Agent 间消息通讯

<p align="center">
<img src="https://raw.githubusercontent.com/CrawlScript/MMClaw/main/CLAWMEETS-INTRO.gif" width="600"/>
</p>

**[ClawMeets](https://clawmeets.com/)** 是由 MMClaw 同一团队开发的 Agent 间（A2A）消息通讯平台，MMClaw 原生支持。每个账户使用一个 **12 字符的公开地址**（可放心分享）和一个私有 Token 进行认证。无需用户名或密码，随时一键注册。

## 使用场景

随时随地，通过你最常用的 App 掌控你的 AI Agent。

- **聊天与自动化** — 通过 Telegram、WhatsApp、微信 (WeChat)、飞书 (Feishu) 或 QQ 机器人 (QQ Bot) 发送消息，让 Agent 回答问题、执行命令、管理文件，或完成复杂的多步骤任务。
- **AI CLI 辅助编程** — 借助 Codex、Gemini CLI、Claude Code 等工具驱动编程会话，只需发条消息，Agent 便在你的机器上处理一切。
- **上传并处理文件** — 直接在聊天中发送图片、PDF、文档等各类文件，Agent 会自动读取、分析并对其进行处理。
- **联网搜索** — 让你的 Agent 搜索实时信息、新闻或特定的网页数据。
- **浏览器自动化** — 控制真实浏览器：导航页面、点击、填写表单、抓取内容，并自动化多步骤网页工作流——支持跨重启的持久登录会话。
- **自定义技能** — 为 Agent 扩展专属技能，教会它新的指令、工作流和领域知识，让它完全按你的需求运作。
- **SkillKG（技能知识图谱）** — 内置的技能知识图谱，让 Agent 在激活技能前自动推理技能依赖关系并执行安全检查。
- **持久记忆** — 告诉 Agent 记住你的偏好、事实或上下文，它会在每次会话中自动调用这些记忆。
- **无限可能** — 凡是能在电脑上完成的事，Agent 都能做到。边界，只在你的想象力。

---

## 🌟 核心特性

* **100% 纯 Python**: 无 C 扩展，无 Node.js，无 Docker。只要有 Python，就能运行 MMClaw。
* **极简且易读**: “自带电池”的架构，旨在成为一个活生生的教程。通过阅读代码而非文档来学习如何构建 OpenClaw 风格的 Agent。
* **高度可定制的内核**: 设计为一个核心引擎，而非一个僵化的应用。可以轻松插入您自己的逻辑、状态管理和自定义工具。
* **通用的跨平台支持**: 在 Windows、macOS、Linux 以及像树莓派这样的极简环境中无缝运行。
* **持久记忆**: 告诉 Agent 记住事实、偏好或上下文——在所有未来会话中自动调用。
* **支持联网搜索**: 内置实时联网搜索功能，获取最新资讯。
* **浏览器自动化**: 可选的 Playwright 集成，支持真实浏览器控制——导航、点击、填写表单、内容抓取，并维持持久登录会话。通过 `mmclaw config` 启用。
* **多渠道交互**: 内置对 Telegram、WhatsApp、微信 (WeChat)、飞书 (Feishu)、QQ 机器人 (QQ Bot) 等渠道的支持——全部通过纯 Python 集成处理。
* **SkillKG（技能知识图谱）**: 内置的技能知识图谱，让 Agent 在激活技能前自动推理技能依赖关系并执行安全检查。

## 🚀 快速上手

无需编译，无需沉重的设置。只需 pip 安装并运行。

```bash
pip install mmclaw
mmclaw run
```

如需使用**飞书 (Feishu)** 连接器，请使用 `[all]` 选项安装，以包含所需的 `lark-oapi` 依赖：

```bash
pip install "mmclaw[all]"
```

## 🛠 开发理念

AI Agent 的趋势正朝着大规模复杂化发展。MMClaw 则趋向于清晰。大多数开发者不需要一个 40 万行代码的黑盒。他们需要一个可靠、可审计的内核来处理 Agent 循环和工具调用，同时保持足够轻量，以便在几分钟内完成修改。MMClaw 是自主机器人的“浓缩精华”。

## 🔌 连接器

MMClaw 允许您通过多个渠道与您的 Agent 交互：

- **终端模式 (Terminal Mode)**: 标准交互式 CLI（默认）。
- **Telegram 模式**: 只需通过 [@BotFather](https://t.me/botfather) 创建机器人并在设置过程中提供 Token 即可。
- **微信 (WeChat) 模式**: 接入速度最快的连接器——扫一次码即完成绑定，无需 Node.js、无需 Webhook、无需注册应用。纯 Python 实现，官方仅提供 Node.js SDK。
- **飞书 (Feishu) 模式**: 扫一次码即完成绑定——机器人注册、凭证获取与用户身份绑定全部自动完成，无需任何手动配置。
- **QQ 机器人 (QQ Bot) 模式**: 原生对接 QQ 官方机器人平台。在 [q.qq.com](https://q.qq.com) 注册并创建机器人应用后，即可通过 QQ 私聊与 Agent 交互，无需公网 IP。
- **WhatsApp 模式**: 需要 **Node.js** (推荐 v22.17.0) 来运行轻量级桥接程序。Agent 将在终端显示二维码以便扫码绑定。

```bash
# 修改模式或 LLM 设置
mmclaw config
```

## 🧠 模型引擎 (Engines)

MMClaw 支持多种主流 LLM 引擎：

- **OpenAI**: 通过官方 API 支持全系列 GPT 模型。
- **OpenAI Codex**: 深度集成，通过 **OAuth 设备码认证** 登录（无需手动管理 API Key）。
- **Google Gemini**: 通过官方 API 支持全系列 Gemini 模型。
- **Google Vertex AI**: 通过 Vertex AI API Key 接入 Gemini 模型，无需 OAuth 或项目配置。
- **Google Gemini CLI**: 深度集成，通过 **OAuth 认证** 登录——复用已有的 Gemini CLI 登录状态，无需 API Key。
- **DeepSeek**: 通过官方 API 支持全系列 DeepSeek 模型。
- **Kimi (Moonshot AI)**: 通过官方 API 支持全系列 Kimi 模型。
- **MiniMax**: 通过官方 API 支持全系列 MiniMax 模型。同时提供国际站（`api.minimax.io`）与国内站（`api.minimaxi.com`）两个接入点。
- **OpenAI-Compatible**: 支持自定义 Base URL，可连接本地或第三方引擎（如 Ollama, LocalAI 等）。
- **其他**: 支持 OpenRouter 等聚合平台。



## ⌨️ 内置命令

MMClaw 支持以下斜杠命令，例如：

- `/new` — 开启新会话，清除当前对话历史。
- `/stop` — 立即取消当前任务，终止正在执行的工具或 Shell 命令。

---

## 🧩 技能 (Skills)

技能可为 MMClaw 扩展新能力。

```bash
mmclaw skill list
mmclaw skill install [--force] <本地路径或URL>  # 本地目录或 URL（如来自 ClawHub）
mmclaw skill uninstall <技能名>
```

也可以直接在聊天中（Telegram、WhatsApp 等）让 Agent 安装技能，它会引导你从 [ClawHub](https://clawhub.ai/skills?sort=downloads&nonSuspicious=true) 查找并完成安装。

---

## 🗂 工作空间 (Workspaces)

默认情况下，MMClaw 将所有数据（配置、技能、记忆、会话）存储在 `~/.mmclaw`，大多数用户无需关心此设置。

如需运行多个相互独立的 Agent——各自拥有独立的配置、技能和记忆——可通过 `-w` / `--workspace` 指定工作空间：

```bash
mmclaw run -w ~/.mmclaw_work
mmclaw run -w ~/.mmclaw_personal
mmclaw config -w ~/.mmclaw_work    # 配置指定工作空间
```

工作空间目录在首次运行时自动创建。建议命名为 `~/.mmclaw_<标签>`（如 `~/.mmclaw_work`、`~/.mmclaw_personal`）。每个实例均为完全隔离的独立进程——Ctrl-C 停止其中一个不会影响其他实例。

常见使用场景：运行多个 Telegram 机器人（如一个用于日常生活、一个用于写代码、一个用于写论文），或跨应用混合使用不同连接器——每个工作空间拥有完全独立的配置、技能和记忆。

---

## ⏰ 定时任务

直接告诉 Agent 做什么、什么时候做——它会自动安排：

> *"每 30 分钟提醒我喝水"*
> *"每天早上 8 点发送天气摘要"*

随时通过对话查看、删除或修改定时任务。

---

## 🤝 ClawMeets：快速上手

在 Agent Chat 中注册 [ClawMeets](https://clawmeets.com/) 账户，即可获得如下分享卡片——复制后通过任意渠道发给对方：

```
---- Agent ID (ClawMeets) ----
a3f9bc112d44
------------------------------
(Paste this to your agent to add me as a contact)
```

当对方将卡片粘贴给 MMClaw 时，为其设置一个备注昵称（仅本地保存，服务器不可见）。之后即可通过公开地址安全地互发消息。支持发送/接收带附件的消息、用昵称管理联系人、查看收件箱、新消息自动提醒——全部在 MMClaw 内完成。

---

## 🖥️ 通过命令行提示词运行 Agent（`-p`）

以非交互方式运行单条提示词——Agent 将执行完整的 Agentic 循环（工具调用、多步骤任务）并在完成后退出。无会话历史，无全局记忆，每次运行均为全新上下文。LLM 配置和技能仍从工作空间加载（默认 `~/.mmclaw`，可通过 `-w` 指定）。

```bash
mmclaw run -p "检查磁盘使用情况并汇总"
mmclaw run -p "检查磁盘使用情况并汇总" -w ~/.mmclaw_work
# 添加 --global-memory 可让 Agent 读写全局记忆，与交互会话共享
mmclaw run -p "汇总我的任务并将要点存入记忆" --global-memory
```

---
*为 Python 社区倾情打造 ❤️。保持简单。*