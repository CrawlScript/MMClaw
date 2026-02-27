
# ⚡ MMClaw

超轻量级、纯 Python 开发的 AI Agent 内核。

```bash
pip install mmclaw
```

<p align="center">
<img src="https://raw.githubusercontent.com/CrawlScript/MMClaw/main/MMClaw_LOGO.jpg" width="400"/>
</p>

**主页:** [https://github.com/CrawlScript/MMClaw](https://github.com/CrawlScript/MMClaw)

[English](README.md) | **中文说明**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)




> **说明：** 本项目在 v0.0.11 之前名为 [pipclaw](https://github.com/CrawlScript/pipclaw)。

MMClaw 是一个极简主义的、100% 纯 Python 编写的自主代理内核。虽然像 OpenClaw 这样的框架功能强大，但它们通常会引入沉重的依赖，如 Node.js、Docker 或复杂的 C 扩展。

MMClaw 剥离了复杂性，提供了一个清晰透明、易读的架构，既可以作为生产级的内核，也可以作为构建现代 AI Agent 的全面教程。

---

## 使用场景

随时随地，通过你最常用的 App 掌控你的 AI Agent。

- **聊天与自动化** — 通过 Telegram、WhatsApp 或飞书发送消息，让 Agent 回答问题、执行命令、管理文件，或完成复杂的多步骤任务。
- **AI CLI 辅助编程** — 借助 Codex、Gemini CLI、Claude Code 等工具驱动编程会话，只需发条消息，Agent 便在你的机器上处理一切。
- **上传并处理文件** — 直接在聊天中发送图片、PDF、文档等各类文件，Agent 会自动读取、分析并对其进行处理。
- **自定义技能** — 为 Agent 扩展专属技能，教会它新的指令、工作流和领域知识，让它完全按你的需求运作。
- **无限可能** — 凡是能在电脑上完成的事，Agent 都能做到。边界，只在你的想象力。

---

## 🌟 核心特性

* **100% 纯 Python**: 无 C 扩展，无 Node.js，无 Docker。只要有 Python，就能运行 MMClaw。
* **极简且易读**: “自带电池”的架构，旨在成为一个活生生的教程。通过阅读代码而非文档来学习如何构建 OpenClaw 风格的 Agent。
* **高度可定制的内核**: 设计为一个核心引擎，而非一个僵化的应用。可以轻松插入您自己的逻辑、状态管理和自定义工具。
* **通用的跨平台支持**: 在 Windows、macOS、Linux 以及像树莓派这样的极简环境中无缝运行。
* **多渠道交互**: 内置对 Telegram、飞书、WhatsApp 等渠道的支持——全部通过纯 Python 集成处理。

## 🚀 快速上手

无需编译，无需沉重的设置。只需 pip 安装并运行。

```bash
pip install mmclaw
mmclaw run
```

如需使用**飞书 (Feishu)** 连接器，请使用 `[all]` 选项安装，以包含所需的 `lark-oapi` 依赖：

```bash
pip install mmclaw[all]
```

## 🛠 开发理念

AI Agent 的趋势正朝着大规模复杂化发展。MMClaw 则趋向于清晰。大多数开发者不需要一个 40 万行代码的黑盒。他们需要一个可靠、可审计的内核来处理 Agent 循环和工具调用，同时保持足够轻量，以便在几分钟内完成修改。MMClaw 是自主机器人的“浓缩精华”。

## 🔌 连接器

MMClaw 允许您通过多个渠道与您的 Agent 交互：

- **终端模式 (Terminal Mode)**: 标准交互式 CLI（默认）。
- **Telegram 模式**: 无外部依赖。只需通过 [@BotFather](https://t.me/botfather) 创建机器人并在设置过程中提供 Token 即可。
- **飞书 (Feishu) 模式**: 专门为中国用户提供支持。拥有**业内最详尽的步骤式设置指南**，利用长连接技术，无需公网 IP 或复杂的 Webhook。
- **WhatsApp 模式**: 需要 **Node.js** (推荐 v22.17.0) 来运行轻量级桥接程序。Agent 将在终端显示二维码以便扫码绑定。

```bash
# 修改模式或 LLM 设置
mmclaw config
```

## 🧠 模型引擎 (Engines)

MMClaw 支持多种主流 LLM 引擎：

- **OpenAI**: 支持 GPT-4o, o1 等全系列模型。
- **OpenAI Codex**: 深度集成，通过 **OAuth 设备码认证** 登录（无需手动管理 API Key）。
- **Google Gemini**: 支持 Gemini 1.5 Pro/Flash, 2.0 Flash。
- **DeepSeek**: 支持 DeepSeek-V3, DeepSeek-R1。
- **Kimi (Moonshot AI)**: 原生支持 Kimi k2.5。
- **OpenAI-Compatible**: 支持自定义 Base URL，可连接本地或第三方引擎（如 Ollama, LocalAI 等）。
- **其他**: 支持 OpenRouter 等聚合平台。



---
*为 Python 社区倾情打造 ❤️。保持简单。*