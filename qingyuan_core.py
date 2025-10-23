#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from typing import Dict, Any
import importlib.util

# 导入新的分离式搜索脚本
current_dir = os.path.dirname(os.path.abspath(__file__))
web_search_path = os.path.join(current_dir, "web_search.py")
spec = importlib.util.spec_from_file_location("web_search", web_search_path)
web_search_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_search_module)

UnifiedSearch = web_search_module.UnifiedSearch


class QingYuan:
    def __init__(self):
        self.name = "清源"
        self.web_search = UnifiedSearch()  # 使用新的统一搜索接口
        self.config = self._load_config()
        self._config_mtime = None

    def _cleanup_whitespace(self, text: str) -> str:
        import re
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s+([，。！？；：])", r"\1", text)
        text = "\n".join(line.strip() for line in text.splitlines())
        return text.strip()

    def get_response(self, user_input: str) -> str:
        user_input = (user_input or "").strip()
        self._maybe_reload_config()
        return self._search_and_list(user_input)

    def _search_and_list(self, query: str) -> str:
        try:
            mode_cfg = self.config.get('mode', {}) if isinstance(self.config, dict) else {}
            sites = mode_cfg.get('sites')
            engines = mode_cfg.get('engines')
            limit = mode_cfg.get('limit')
            results = self.web_search.search_web(query, sites=sites, engines=engines, limit=limit)
        except Exception:
            results = []
        if not results:
            return self._cleanup_whitespace(f"查询：{query}\n无结果。")
        lines = []
        for it in results:
            title = (it.get('title') or '').strip()
            url = (it.get('url') or '').strip()
            if title or url:
                lines.append(f"- {title} {url}")
        return self._cleanup_whitespace(f"查询：{query}\n结果：\n" + "\n".join(lines))

    def _load_config(self) -> Dict[str, Any]:
        default_cfg: Dict[str, Any] = {
            "mode": {
                "pure_search": True,
                "sites": None,
                "engines": ["duckduckgo", "google", "bing", "baidu"],
                "limit": None
            }
        }
        try:
            mtime = os.path.getmtime('qingyuan_config.json')
            with open('qingyuan_config.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._config_mtime = mtime
            return data
        except FileNotFoundError:
            return default_cfg
        except Exception:
            return default_cfg

    def _maybe_reload_config(self):
        try:
            mtime = os.path.getmtime('qingyuan_config.json')
            if self._config_mtime is None or mtime != self._config_mtime:
                self.config = self._load_config()
        except Exception:
            pass
