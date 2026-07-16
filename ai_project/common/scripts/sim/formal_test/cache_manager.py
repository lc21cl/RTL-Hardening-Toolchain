#!/usr/bin/env python3
"""cache_manager.py — 缓存管理模块

实现中间结果缓存机制，避免重复计算。

用法:
    from cache_manager import CacheManager

    cache = CacheManager()
    cache.set("key", value, ttl=3600)
    result = cache.get("key")
    stats = cache.get_stats()
"""

import os
import json
import time
import hashlib
import threading
from typing import Dict, Any, Optional


class CacheManager:
    """缓存管理器。

    使用字典作为内存缓存，支持 TTL 过期机制和文件持久化。
    """

    def __init__(self, default_ttl: int = 3600):
        """初始化缓存管理器。

        Args:
            default_ttl: 默认过期时间（秒）
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }

    def _generate_key(self, content: str) -> str:
        """根据内容生成缓存键。

        Args:
            content: 内容字符串

        Returns:
            SHA256 哈希值作为键
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _clean_expired(self):
        """清理过期的缓存项。"""
        now = time.time()
        expired_keys = []
        with self._lock:
            for key, item in self._cache.items():
                if item.get("expire_time") and item["expire_time"] < now:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                self._stats["evictions"] += 1

    def get(self, key: str) -> Optional[Any]:
        """获取缓存项。

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        self._clean_expired()

        with self._lock:
            item = self._cache.get(key)
            if item:
                self._stats["hits"] += 1
                return item["value"]
            else:
                self._stats["misses"] += 1
                return None

    def get_by_content(self, content: str) -> Optional[Any]:
        """根据内容获取缓存项。

        Args:
            content: 内容字符串

        Returns:
            缓存值，如果不存在则返回 None
        """
        key = self._generate_key(content)
        return self.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ):
        """设置缓存项。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），默认为默认值
        """
        expire_time = None
        actual_ttl = ttl or self._default_ttl
        if actual_ttl > 0:
            expire_time = time.time() + actual_ttl

        with self._lock:
            self._cache[key] = {
                "value": value,
                "expire_time": expire_time,
                "set_time": time.time(),
            }
            self._stats["sets"] += 1

    def set_by_content(
        self,
        content: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> str:
        """根据内容设置缓存项。

        Args:
            content: 内容字符串
            value: 缓存值
            ttl: 过期时间（秒）

        Returns:
            生成的缓存键
        """
        key = self._generate_key(content)
        self.set(key, value, ttl)
        return key

    def delete(self, key: str) -> bool:
        """删除缓存项。

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["deletes"] += 1
                return True
            return False

    def exists(self, key: str) -> bool:
        """检查缓存项是否存在。

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        self._clean_expired()
        with self._lock:
            return key in self._cache

    def clear(self):
        """清空所有缓存。"""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息。

        Returns:
            统计信息字典
        """
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / max(total, 1) * 100

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": round(hit_rate, 2),
            "sets": self._stats["sets"],
            "deletes": self._stats["deletes"],
            "evictions": self._stats["evictions"],
            "cache_size": len(self._cache),
        }

    def save_cache(self, path: str):
        """保存缓存到文件。

        Args:
            path: 保存路径
        """
        with self._lock:
            data = {
                "cache": self._cache,
                "stats": self._stats,
                "saved_at": time.time(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def load_cache(self, path: str) -> bool:
        """从文件加载缓存。

        Args:
            path: 加载路径

        Returns:
            是否加载成功
        """
        if not os.path.isfile(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                self._cache = data.get("cache", {})
                self._stats = data.get("stats", self._stats)

            self._clean_expired()
            return True
        except Exception:
            return False


if __name__ == "__main__":
    cache = CacheManager(default_ttl=60)

    print("=== Cache Test ===")

    cache.set("test_key", "test_value")
    print(f"Set test_key: {cache.get('test_key')}")

    cache.set("ttl_key", "expires_soon", ttl=1)
    print(f"Set ttl_key: {cache.get('ttl_key')}")

    time.sleep(2)
    print(f"After 2s, ttl_key: {cache.get('ttl_key')}")

    content_key = cache.set_by_content("Hello World", "cached_result")
    print(f"Content key: {content_key}")
    print(f"Get by content: {cache.get_by_content('Hello World')}")

    stats = cache.get_stats()
    print(f"Stats: {stats}")

    cache.save_cache("test_cache.json")
    print("Cache saved to test_cache.json")

    new_cache = CacheManager()
    new_cache.load_cache("test_cache.json")
    print(f"Loaded cache size: {len(new_cache._cache)}")

    import os
    os.remove("test_cache.json")
