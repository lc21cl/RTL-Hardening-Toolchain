#!/usr/bin/env python3
"""
api_activation.py — OpenAIBackend API 激活配置模块

提供统一的 API 密钥管理和模型配置框架，简化真实 API 的激活流程。

核心功能：
  1. API 密钥管理 — 多来源密钥解析（环境变量、.env、命令行参数）
  2. 模型配置 — 支持 OpenAI、DeepSeek 等多种模型
  3. 环境检测 — 自动检测依赖和网络可用性
  4. 配置验证 — 验证 API 密钥和模型配置的有效性
  5. 一键激活 — 提供简单的激活接口

设计原则：
  - 安全 — 密钥不硬编码，不打印完整密钥
  - 灵活 — 支持多种配置来源
  - 透明 — 清晰的状态报告和诊断信息
  - 兼容 — 与现有的 OpenAIBackend/DeepSeekBackend 接口兼容

用法:
    from api_activation import APIActivator

    # 自动检测并激活
    activator = APIActivator()
    status = activator.detect()
    print(status)

    # 使用指定后端
    backend = activator.get_backend("deepseek")
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("api_activation")


# ============================================================================
# Model Configuration
# ============================================================================

MODEL_CONFIG = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "default_model": "gpt-4",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "api_key_file": ".env",
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-r1"],
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_file": ".env",
    },
    "mock": {
        "name": "Mock (Template-based)",
        "models": ["mock"],
        "default_model": "mock",
        "base_url": None,
        "api_key_env": None,
        "api_key_file": None,
    },
}

"""模型配置字典。"""


# ============================================================================
# APIActivator
# ============================================================================

class APIActivator:
    """API 激活器。

    提供统一的 API 密钥管理和模型配置框架。
    """

    def __init__(self):
        """初始化 API 激活器。"""
        self._status: Dict[str, Any] = {}
        self._detected = False

    def detect(self) -> Dict[str, Any]:
        """自动检测可用的 API 后端和配置。

        Returns:
            检测结果字典，包含各后端的状态信息。
        """
        logger.print(f"  [API_ACT] Detecting available backends...")

        self._status = {
            "backends": {},
            "recommendations": [],
            "timestamp": time.time(),
        }

        for backend_name, config in MODEL_CONFIG.items():
            status = self._check_backend(backend_name, config)
            self._status["backends"][backend_name] = status

            if status.get("available"):
                self._status["recommendations"].append(backend_name)

        if not self._status["recommendations"]:
            self._status["recommendations"] = ["mock"]

        self._detected = True
        return self._status

    def _check_backend(self, backend_name: str, config: Dict) -> Dict[str, Any]:
        """检查单个后端的可用性。"""
        status = {
            "name": config["name"],
            "available": False,
            "reason": "",
            "api_key_found": False,
            "api_key_source": None,
            "models": config["models"],
            "default_model": config["default_model"],
            "base_url": config["base_url"],
        }

        if backend_name == "mock":
            status["available"] = True
            status["reason"] = "Mock backend is always available"
            return status

        api_key = self._resolve_api_key(config["api_key_env"], config["api_key_file"])
        if api_key:
            status["api_key_found"] = True
            status["api_key_source"] = "environment" if os.environ.get(config["api_key_env"]) else ".env file"
        else:
            status["reason"] = "API key not found"
            return status

        try:
            import openai
            status["available"] = True
            status["reason"] = "API key found and openai package available"
        except ImportError:
            status["reason"] = "openai package not installed"

        return status

    def _resolve_api_key(self, env_var: Optional[str], env_file: Optional[str]) -> Optional[str]:
        """从多个来源解析 API 密钥。"""
        if env_var and os.environ.get(env_var):
            return os.environ[env_var]

        if env_file:
            for search_dir in [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]:
                env_path = os.path.join(search_dir, env_file)
                if os.path.isfile(env_path):
                    try:
                        with open(env_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith(f"{env_var}="):
                                    value = line[len(env_var) + 1:]
                                    if (value.startswith('"') and value.endswith('"')) or \
                                       (value.startswith("'") and value.endswith("'")):
                                        value = value[1:-1]
                                    return value
                    except OSError:
                        continue

        return None

    def get_backend(self, backend_name: str = None, api_key: str = None) -> Any:
        """获取指定后端实例。

        Args:
            backend_name: 后端名称 ('openai', 'deepseek', 'mock')
            api_key: 显式提供的 API 密钥（覆盖自动解析）

        Returns:
            后端实例（OpenAIBackend, DeepSeekBackend, 或 MockLLM）
        """
        if not self._detected:
            self.detect()

        target = backend_name or self._status["recommendations"][0]

        if target == "mock":
            logger.print(f"  [API_ACT] Using MockLLM backend")
            from rag_integration import MockLLM
            return MockLLM()

        if target == "deepseek":
            resolved_key = api_key or self._resolve_api_key(
                MODEL_CONFIG["deepseek"]["api_key_env"],
                MODEL_CONFIG["deepseek"]["api_key_file"],
            )
            if resolved_key:
                logger.print(f"  [API_ACT] Using DeepSeek backend")
                from rag_integration import DeepSeekBackend
                return DeepSeekBackend(api_key=resolved_key)
            else:
                logger.warning(f"  [API_ACT] DeepSeek API key not found, falling back to MockLLM")
                from rag_integration import MockLLM
                return MockLLM()

        if target == "openai":
            resolved_key = api_key or self._resolve_api_key(
                MODEL_CONFIG["openai"]["api_key_env"],
                MODEL_CONFIG["openai"]["api_key_file"],
            )
            logger.print(f"  [API_ACT] Using OpenAI backend")
            from rag_integration import OpenAIBackend
            return OpenAIBackend(api_key=resolved_key)

        logger.warning(f"  [API_ACT] Unknown backend '{target}', falling back to MockLLM")
        from rag_integration import MockLLM
        return MockLLM()

    def validate_key(self, backend_name: str, api_key: str) -> bool:
        """验证 API 密钥是否有效。

        Args:
            backend_name: 后端名称
            api_key: API 密钥

        Returns:
            True 密钥格式有效（不一定能访问 API），False 格式无效
        """
        if backend_name == "mock":
            return True

        key_patterns = {
            "openai": r'^sk-[a-zA-Z0-9-]+$',
            "deepseek": r'^sk-[a-zA-Z0-9-]+$',
        }

        pattern = key_patterns.get(backend_name)
        if pattern:
            return bool(re.match(pattern, api_key))

        return False

    def generate_env_file(self, output_path: str = ".env") -> bool:
        """生成示例 .env 文件。

        Args:
            output_path: 输出路径

        Returns:
            True 生成成功，False 失败
        """
        env_content = """\
# ── API Key Configuration ──
# Uncomment and fill in your API keys below

# OpenAI API Key (for OpenAIBackend)
# OPENAI_API_KEY=sk-your-openai-api-key

# DeepSeek API Key (for DeepSeekBackend)
# DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# ── Model Configuration ──
# DEFAULT_BACKEND=deepseek
# DEFAULT_MODEL=deepseek-chat
"""

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(env_content)
            logger.print(f"  [API_ACT] Generated sample .env file: {output_path}")
            return True
        except OSError as e:
            logger.error(f"  [API_ACT] Failed to generate .env file: {e}")
            return False

    def get_status_summary(self) -> str:
        """获取状态摘要字符串。

        Returns:
            格式化的状态摘要。
        """
        if not self._detected:
            self.detect()

        lines = ["API Activation Status:"]

        for backend_name, status in self._status["backends"].items():
            avail = "✓" if status["available"] else "✗"
            key = "✓" if status["api_key_found"] else "✗"
            lines.append(f"  {avail} {status['name']}: API key={key}, models={', '.join(status['models'])}")

        lines.append(f"\nRecommended backend: {self._status['recommendations'][0]}")
        return "\n".join(lines)


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="API Activation Configuration")
    parser.add_argument("--detect", action="store_true", help="Detect available backends")
    parser.add_argument("--generate-env", action="store_true", help="Generate sample .env file")
    parser.add_argument("--activate", type=str, help="Activate specific backend (openai/deepseek/mock)")
    parser.add_argument("--check-key", type=str, help="Validate API key format")
    parser.add_argument("--backend", type=str, help="Backend for key validation")
    args = parser.parse_args()

    activator = APIActivator()

    if args.detect:
        status = activator.detect()
        print(activator.get_status_summary())
        print(json.dumps(status, indent=2))

    elif args.generate_env:
        activator.generate_env_file()

    elif args.activate:
        backend = activator.get_backend(args.activate)
        print(f"Activated backend: {type(backend).__name__}")

    elif args.check_key:
        if not args.backend:
            parser.error("--backend is required with --check-key")
        valid = activator.validate_key(args.backend, args.check_key)
        print(f"API key format validation: {'✓ Valid' if valid else '✗ Invalid'}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
