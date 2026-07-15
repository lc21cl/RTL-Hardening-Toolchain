#!/usr/bin/env python3
"""
config.py — 统一配置管理

提供全局配置加载、验证和访问接口。
支持 YAML 配置文件 + 环境变量覆盖。

用法:
    from config import config

    # 访问配置
    data_dir = config.get('data.dir', 'data/')
    device = config.get('train.device', 'cpu')

    # 更新配置
    config.set('train.epochs', 200)

    # 保存配置
    config.save('config_override.yaml')
"""

import os
import sys
import json
from typing import Any, Dict, Optional

try:
    import yaml
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False


# ============================================================================
# Default Configuration
# ============================================================================

DEFAULT_CONFIG = {
    # ── Project Paths ──
    'paths': {
        'project_root': '',
        'scripts_dir': '',
        'docs_dir': '',
        'data_dir': 'data/',
        'models_dir': 'data/models/',
        'fpga_dir': 'data/fpga/',
        'blif_dir': 'data/blifs/',
        'aig_dir': 'data/aigs/',
        'onnx_dir': 'data/onnx/',
        'logs_dir': 'logs/',
    },

    # ── Training Configuration ──
    'train': {
        'model': 'SAGE3',
        'in_channels': 12,
        'hidden_channels': 128,
        'dropout': 0.3,
        'epochs': 200,
        'patience': 50,
        'batch_size': 32,
        'lr': 1e-3,
        'weight_decay': 5e-4,
        'device': 'cpu',
        'seed': 42,
        'loss': 'FocalLoss',
        'focal_alpha': 0.977,
        'focal_gamma': 2.0,
        'use_pi_weighting': True,
        'pi_weight': 10.0,
        'max_grad_norm': 5.0,
        'monitor_interval_min': 30,
    },

    # ── Inference Configuration ──
    'inference': {
        'model_path': '',
        'threshold': 0.05,
        'device': 'cpu',
        'batch_size': 32,
        'benchmark_runs': 10,
    },

    # ── Graph Pipeline Configuration ──
    'graph': {
        'target_features': 12,
        'generate_labels': True,
        'label_mode': 'prob_decay',
        'fault_prob': 0.1,
        'seed': 42,
    },

    # ── FPGA Deployment Configuration ──
    'fpga': {
        'clock_mhz': 100,
        'axi_data_width': 32,
        'target_device': 'xc7z020clg484-1',
        'hls_config': 'hls_config.tcl',
    },

    # ── Logging Configuration ──
    'logging': {
        'level': 'INFO',
        'format': 'structured',
        'file': 'pipeline.log',
        'max_size_mb': 10,
        'backup_count': 3,
        'console_output': True,
    },

    # ── CUDA / Hardware Configuration ──
    'hardware': {
        'gpu_memory_fraction': 0.8,
        'num_workers': 0,
        'pin_memory': False,
    },
}


# ============================================================================
# Config Manager
# ============================================================================

class Config:
    """全局配置管理器。

    支持:
      - 默认配置 (DEFAULT_CONFIG)
      - YAML 配置文件加载
      - 环境变量覆盖 (CONFIG__<SECTION>__<KEY>)
      - 点号路径访问 (config.get('train.epochs'))
    """

    def __init__(self):
        self._config = self._deep_copy(DEFAULT_CONFIG)
        self._loaded_files = []
        self._auto_detect_paths()

    def _auto_detect_paths(self):
        """Auto-detect project paths based on script location."""
        script_dir = os.path.dirname(os.path.abspath(__file__))

        if 'paths' not in self._config:
            self._config['paths'] = {}

        self._config['paths']['scripts_dir'] = script_dir
        self._config['paths']['project_root'] = os.path.dirname(script_dir)

        docs_dir = os.path.join(os.path.dirname(script_dir), 'docs')
        if os.path.isdir(docs_dir):
            self._config['paths']['docs_dir'] = docs_dir

        # Auto-detect model path
        default_model = os.path.join(
            script_dir, 'data', 'models', 'local_best_model.pt'
        )
        if os.path.exists(default_model):
            self._config['inference']['model_path'] = default_model

    def load(self, file_path: str) -> bool:
        """Load configuration from YAML or JSON file.

        Args:
            file_path: Path to .yaml, .yml, or .json config file

        Returns:
            True if loaded successfully
        """
        if not os.path.isfile(file_path):
            print(f"[WARN] Config file not found: {file_path}")
            return False

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext in ('.yaml', '.yml'):
                if not _HAVE_YAML:
                    raise ImportError("PyYAML required: pip install pyyaml")
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            elif ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                print(f"[WARN] Unsupported config format: {ext}")
                return False

            if data and isinstance(data, dict):
                self._merge(self._config, data)
                self._loaded_files.append(file_path)
                return True
        except Exception as e:
            print(f"[WARN] Failed to load config {file_path}: {e}")

        return False

    def save(self, file_path: str, format: str = 'yaml') -> str:
        """Save current configuration to file.

        Args:
            file_path: Output file path
            format: 'yaml' or 'json'

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.yaml', '.yml'):
            format = 'yaml'
        elif ext == '.json':
            format = 'json'

        if format == 'yaml':
            if not _HAVE_YAML:
                raise ImportError("PyYAML required: pip install pyyaml")
            with open(file_path, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False,
                          sort_keys=False)
        else:
            with open(file_path, 'w') as f:
                json.dump(self._config, f, indent=2)

        return file_path

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-separated key path.

        Args:
            key: Dot-separated path (e.g., 'train.epochs')
            default: Default value if key not found

        Returns:
            Config value or default
        """
        parts = key.split('.')
        cursor = self._config
        for part in parts:
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                return default
        return cursor

    def set(self, key: str, value: Any) -> None:
        """Set config value by dot-separated key path.

        Args:
            key: Dot-separated path (e.g., 'train.epochs')
            value: Value to set
        """
        parts = key.split('.')
        cursor = self._config
        for i, part in enumerate(parts[:-1]):
            if part not in cursor:
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = value

    def update(self, overrides: Dict) -> None:
        """Update config with a dictionary of overrides.

        Args:
            overrides: Dict with same structure as config
        """
        self._merge(self._config, overrides)

    def apply_env_overrides(self) -> None:
        """Apply environment variable overrides.

        Env format: CONFIG__<SECTION>__<KEY>
        Example: CONFIG__TRAIN__EPOCHS=200
        """
        prefix = 'CONFIG__'
        for env_key, env_val in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            parts = env_key[len(prefix):].lower().split('__')
            cursor = self._config
            for part in parts[:-1]:
                if part not in cursor:
                    cursor[part] = {}
                cursor = cursor[part]
            try:
                cursor[parts[-1]] = json.loads(env_val)
            except (json.JSONDecodeError, TypeError):
                cursor[parts[-1]] = env_val

    def to_dict(self) -> Dict:
        """Get a deep copy of the full configuration."""
        return self._deep_copy(self._config)

    def print(self) -> None:
        """Print current configuration in a readable format."""
        print("=" * 52)
        print("  Configuration")
        print("=" * 52)
        self._print_dict(self._config, indent=2)
        if self._loaded_files:
            print(f"\n  Loaded from: {', '.join(self._loaded_files)}")
        print("=" * 52)

    # ======================================================================
    # Internal Helpers
    # ======================================================================

    @staticmethod
    def _deep_copy(data: Dict) -> Dict:
        """Deep copy a dictionary."""
        import copy
        return copy.deepcopy(data)

    @staticmethod
    def _merge(base: Dict, overrides: Dict) -> None:
        """Recursively merge overrides into base dict."""
        for key, value in overrides.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Config._merge(base[key], value)
            else:
                base[key] = Config._deep_copy(value) if isinstance(value, dict) else value

    @staticmethod
    def _print_dict(data: Dict, indent: int = 0) -> None:
        """Recursively print a dictionary with formatting."""
        prefix = '  ' * (indent // 2)
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"{prefix}  {key}:")
                Config._print_dict(value, indent + 2)
            else:
                print(f"{prefix}  {key}: {value}")


# ============================================================================
# Singleton Instance
# ============================================================================

config = Config()

# Auto-load config.yaml if exists
_auto_paths = [
    os.path.join(os.path.dirname(__file__), 'config.yaml'),
    os.path.join(os.path.dirname(__file__), 'config.yml'),
    os.path.join(os.path.dirname(__file__), 'config.json'),
]
for _p in _auto_paths:
    if os.path.isfile(_p):
        config.load(_p)
        break

# Apply environment overrides
config.apply_env_overrides()


if __name__ == '__main__':
    config.print()
