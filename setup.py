from setuptools import setup, find_packages

setup(
    name="mmclaw",
    version="0.0.15",

    author="Jun Hu",
    author_email="hujunxianligong@gmail.com",

    description="🐈 MMClaw: Ultra-Lightweight, Pure Python Multimodal Agent.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/CrawlScript/MMClaw",
    
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "mmclaw": ["skills/*.md", "bridge.js"],
    },
    
    entry_points={
        "console_scripts": [
            "mmclaw=mmclaw.main:main",
        ],
    },
    
    install_requires=[
        "requests",
        "openai",
        "pyTelegramBotAPI",
        "lark-oapi >= 1.5.3",
        "Pillow",
    ],
    
    python_requires=">=3.8",
)
