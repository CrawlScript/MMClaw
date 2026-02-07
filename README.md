# 🐈 PipClaw

The Ultra-Lightweight, Pure Python Kernel for AI Agents.


[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)


PipClaw is a minimalist, 100% Pure Python autonomous agent kernel. While frameworks like OpenClaw offer great power, they often introduce heavy dependencies like Node.js, Docker, or complex C-extensions. 

PipClaw strips away the complexity, offering a crystal-clear, readable architecture that serves as both a production-ready kernel and a comprehensive tutorial on building modern AI agents.

---

## 🌟 Key Features

* 100% Pure Python: No C-extensions, no Node.js, no Docker. If you have Python, you have PipClaw.
* Minimalist & Readable: A "Batteries-Included" architecture designed to be a living tutorial. Learn how to build an OpenClaw-style agent by reading code, not documentation.
* Highly Customizable Kernel: Designed as a core engine, not a rigid app. Easily plug in your own logic, state management, and custom tools.
* Universal Cross-Platform: Runs seamlessly on Windows, macOS, Linux, and minimalist environments like Raspberry Pi.
* Multi-Channel Interaction: Built-in support for interacting with your agent via Telegram, WhatsApp, and more—all handled through pure Python integrations.

## 🚀 Quick Start

No compiling, no heavy setup. Just pip and run.

```bash
pip install pipclaw
pipclaw run
```

## 🛠 The Philosophy

The trend in AI agents is moving towards massive complexity. PipClaw moves towards clarity. Most developers don't need a 400,000-line black box. They need a reliable, auditable kernel that handles the agent loop and tool-calling while remaining light enough to be modified in minutes. PipClaw is the "distilled essence" of an autonomous bot.

## 🔌 Connectors

PipClaw allows you to interact with your agent through multiple channels:

- **Terminal Mode**: Standard interactive CLI (default).
- **Telegram Mode**: No external dependencies. Just create a bot via [@BotFather](https://t.me/botfather) and provide your token during setup.
- **WhatsApp Mode**: Requires **Node.js** (v22.17.0 recommended) to run the lightweight bridge. The agent will show a QR code in your terminal for linking.

```bash
# To change your mode or LLM settings
pipclaw config
```

## 📂 Project Structure

```text
pipclaw/
├── kernel/          # Core agent loop & state logic
├── connectors/      # Telegram, WhatsApp, and Web UI bridges
├── providers/       # LLM connectors (OpenAI, Anthropic, etc.)
└── tools/           # Extensible toolset (Search, Code Exec, etc.)
```

---
*Developed with ❤️ for the Python community. Let's keep it simple.*