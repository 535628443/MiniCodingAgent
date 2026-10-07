import os
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

# 加载 .env 环境变量
load_dotenv(override=True)

if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"

# Anthropic Client 初始化 (通过 LiteLLM Proxy 转发时使用代理端点)
client = Anthropic(
    base_url=os.getenv("ANTHROPIC_BASE_URL"),
    api_key=os.getenv("ANTHROPIC_API_KEY", "sk-litellm-dummy-key"),
)
MODEL = os.environ.get("MODEL_ID", "gemini-2.5-flash-lite")
