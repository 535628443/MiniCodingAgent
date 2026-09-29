"""
MiniCodingAgent: Skill Loading 模块化重构版
两级按需知识注入架构 (Two-Level On-Demand Knowledge Injection)

运行方式:
  python -m MiniCodingAgent
或
  python MiniCodingAgent/main.py
"""
from .agent import agent_loop
from .main import main

__all__ = ["agent_loop", "main"]
