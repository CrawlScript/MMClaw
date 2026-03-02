# ⚡ MMClaw

The Ultra-Lightweight, Pure Python Kernel for Multimodal AI Agents.

```bash
pip install mmclaw
```

<p align="center">
<img src="https://raw.githubusercontent.com/CrawlScript/MMClaw/main/MMCLAW_LOGO.jpg" width="400"/>
</p>

**Home:** [https://github.com/CrawlScript/MMClaw](https://github.com/CrawlScript/MMClaw)

**English** | [中文说明](https://github.com/CrawlScript/MMClaw/blob/main/README_zh.md)


[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)



> **Note:** This project was previously named [pipclaw](https://github.com/CrawlScript/pipclaw) (pre-v0.0.11).


MMClaw is a minimalist, 100% Pure Python autonomous agent kernel. While frameworks like OpenClaw offer great power, they often introduce heavy dependencies like Node.js, Docker, or complex C-extensions. 

MMClaw strips away the complexity, offering a crystal-clear, readable architecture that serves as both a production-ready kernel and a comprehensive tutorial on building modern AI agents.

---

## Use Cases

Control your AI agent from anywhere, through the apps you already use.

- **Chat & Automate** — Send messages via Telegram, WhatsApp, Feishu (飞书), or QQ Bot (QQ机器人) to ask questions, run commands, manage files, or delegate complex multi-step tasks to your agent.
- **Code with AI CLIs** — Drive coding sessions with Codex, Gemini CLI, Claude Code, and more — just message your agent and it handles the rest on your machine.
- **Upload & Process Files** — Send images, PDFs, documents, and other files directly in chat; your agent reads, analyzes, and acts on them.
- **Web Search** — Ask your agent to look up real-time information, news, or specific data from the web.
- **Custom Skills** — Extend your agent with your own skills; teach it new commands, workflows, and domain knowledge to do exactly what you need.
- **Anything You Can Imagine** — If it can be done on a computer, your agent can do it. The only limit is your imagination.


## 🌟 Key Features

* 100% Pure Python: No C-extensions, no Node.js, no Docker. If you have Python, you have MMClaw.
* Minimalist & Readable: A "Batteries-Included" architecture designed to be a living tutorial. Learn how to build an OpenClaw-style agent by reading code, not documentation.
* Highly Customizable Kernel: Designed as a core engine, not a rigid app. Easily plug in your own logic, state management, and custom tools.
* Universal Cross-Platform: Runs seamlessly on Windows, macOS, Linux, and minimalist environments like Raspberry Pi.
* Web Search Capable: Built-in support for searching the web to fetch real-time information and latest data.
* Multi-Channel Interaction: Built-in support for interacting with your agent via Telegram, WhatsApp, Feishu (飞书), QQ Bot (QQ机器人), and more—all handled through pure Python integrations.

## 🚀 Quick Start

No compiling, no heavy setup. Just pip and run.

```bash
pip install mmclaw
mmclaw run
```

If you plan to use **Feishu (飞书)** as your connector, install with the `[all]` option to include the required `lark-oapi` dependency:

```bash
pip install mmclaw[all]
```


## 🛠 The Philosophy

The trend in AI agents is moving towards massive complexity. MMClaw moves towards clarity. Most developers don't need a 400,000-line black box. They need a reliable, auditable kernel that handles the agent loop and tool-calling while remaining light enough to be modified in minutes. MMClaw is the "distilled essence" of an autonomous bot.

## 🔌 Connectors

MMClaw allows you to interact with your agent through multiple channels:

- **Terminal Mode**: Standard interactive CLI (default).
- **Telegram Mode**: No external dependencies. Just create a bot via [@BotFather](https://t.me/botfather) and provide your token during setup.
- **Feishu (飞书) Mode**: Dedicated support for Chinese users. Features the **most detailed step-by-step setup guide** in the industry, utilizing long-connections so you don't need a public IP or complex webhooks.
- **QQ Bot (QQ机器人) Mode**: Native support for QQ's official bot platform. Register at [q.qq.com](https://q.qq.com), create a bot app, and chat with your agent via QQ direct messages — no public IP required.
- **WhatsApp Mode**: Requires **Node.js** (v22.17.0 recommended) to run the lightweight bridge. The agent will show a QR code in your terminal for linking.

```bash
# To change your mode or LLM settings
mmclaw config
```

## 🧠 Providers

MMClaw supports a wide range of LLM providers:

- **OpenAI**: GPT-4o, o1, and more.
- **OpenAI Codex**: Premium support via **OAuth device code authentication** (no manual API key management needed).
- **Google Gemini**: Gemini 1.5 Pro/Flash, 2.0 Flash.
- **DeepSeek**: DeepSeek-V3, DeepSeek-R1.
- **Kimi (Moonshot AI)**: Native support for Kimi k2.5.
- **OpenAI-Compatible**: Customizable Base URL for local or third-party engines (Ollama, LocalAI, etc.).
- **Others**: OpenRouter and more.



---
*Developed with ❤️ for the Python community. Let's keep it simple.*