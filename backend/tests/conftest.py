"""pytest 全局 fixture。

测试启动前注入 .env 默认值,避免本地未配 API key 时测试无法跑。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保 backend/ 在 sys.path 中,让 `from app.xxx import ...` 工作
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 测试环境注入 LLM 凭据 fallback,避免本地未配 .env 时 import 失败
# 真实 LLM 调用会被 mock,key 内容不重要
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-key")
os.environ.setdefault("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-chat")
