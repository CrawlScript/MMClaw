from setuptools import setup, find_packages

setup(
    name="pipclaw",
    version="0.0.9",

    author="Jun Hu",
    author_email="hujunxianligong@gmail.com",

    description="🐈 PipClaw: Ultra-Lightweight, Pure Python Agent.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/CrawlScript/pipclaw",
    
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "pipclaw": ["skills/*.md", "bridge.js"],
    },
    
    entry_points={
        "console_scripts": [
            "pipclaw=pipclaw.main:main",
        ],
    },
    
    install_requires=[
        "requests",
        "openai",
        "pyTelegramBotAPI",
        "lark-oapi",
    ],
    
    python_requires=">=3.8",
)
