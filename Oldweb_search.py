#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import random
import re
import time
import traceback
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, unquote, quote

import requests
import urllib3
from bs4 import BeautifulSoup

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class WebSearch:
    """网络搜索类，支持多种搜索引擎和网站搜索"""
    
    # 常量定义
    KNOWN_SITES_BLACKLIST = set()
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    RESOURCE_KEYWORDS = [
        "下载", "资源", "百度网盘", "网盘", "夸克网盘", "阿里云盘", "天翼云", "蓝奏云", "115网盘",
        "magnet:", "磁力", "torrent", "种子", "直链", "度盘", "提取码", "分享链接"
    ]
    
    BING_INTERNAL_PATHS = (
        "/search", "/images/", "/videos/", "/academic/", "/maps/", "/travel/", "/dict/"
    )
    
    # 无效链接模式
    INVALID_LINK_PATTERNS = [
        '#', 'javascript:void(0);', 'javascript:void(0)', 'javascript:',
        'mailto:', 'tel:', 'data:', 'about:', 'chrome:', 'file:'
    ]
    
    # 图片属性列表
    IMAGE_ATTRIBUTES = [
        'data-src', 'data-m', 'data-href', 'data-imgurl', 'data-bm', 
        'data-original', 'data-hires', 'data-full', 'data-large', 'data-hd', 'src',
        'data-msrc', 'data-big', 'data-super', 'data-zoom', 'data-thumb',
        'data-preview', 'data-image', 'data-img', 'data-pic', 'data-photo'
    ]
    
    def __init__(self, config_file: str = "sites_config.json"):
        """初始化WebSearch实例
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
        self.forbidden_domains = set()  # 403错误域名黑名单
        
        # 基础配置
        self.request_timeout = 10  # 超时时间10秒
        
        # 正则表达式
        self.file_ext_regex = re.compile(r"\.(pdf|docx?|pptx?|xlsx?)($|\?|#)", re.I)
        self.archive_ext_regex = re.compile(r"\.(zip|rar|7z|iso|apk|exe)($|\?|#)", re.I)

    def _load_config(self) -> Dict[str, Any]:
        """加载网站配置
        
        Returns:
            配置字典，如果加载失败则返回默认配置
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[DEBUG] 加载配置失败: {e}")
        
        # 返回默认配置
        return {
            "search_engines": {"bing": {"name": "Bing", "base_url": "https://www.bing.com", "enabled": True}},
            "web_sites": {},
            "resource_sites": {},
            "video_sites": {},
            "image_sites": {},
            "blacklist": {"domains": [], "enabled": True},
            "settings": {"engine_max_results": 35}
        }

    def _save_config(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG] 保存配置失败: {e}")

    def _session(self) -> requests.Session:
        """创建请求会话
        
        Returns:
            配置好的requests会话对象
        """
        s = requests.Session()
        s.headers.update({
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        })
        s.verify = False
        return s

    def _request(self, session: requests.Session, url: str, 
                 params: Optional[Dict[str, Any]] = None, 
                 headers: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        """发送HTTP请求
        
        Args:
            session: requests会话对象
            url: 请求URL
            params: 请求参数
            headers: 请求头
            
        Returns:
            响应对象或None
        """
        try:
            print(f"[DEBUG] 请求URL: {url}")
            
            # 对于百度等国内网站，使用更长的超时时间
            timeout = self.request_timeout
            if 'baidu.com' in url or 'sogou.com' in url or 'so.com' in url:
                timeout = 15  # 国内网站使用15秒超时
            
            resp = session.get(url, params=params, headers=headers, timeout=timeout)
            print(f"[DEBUG] 响应状态: {resp.status_code}, 内容长度: {len(resp.content)}")
            
            # 处理重定向
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get('Location')
                if loc:
                    resp = session.get(loc, timeout=timeout)
            
            if resp.status_code == 200:
                return resp
            else:
                print(f"[DEBUG] 请求失败，状态码: {resp.status_code}")
                return None
                
        except requests.exceptions.ConnectionError as e:
            print(f"[DEBUG] 连接错误: {e}")
            return None
                    
        except requests.exceptions.Timeout as e:
            print(f"[DEBUG] 请求超时: {e}")
            return None
                    
        except Exception as e:
            print(f"[DEBUG] 请求失败: {e}")
            return None

    def _normalize_url(self, href: Optional[str]) -> Optional[str]:
        """标准化URL"""
        if not href:
            return None
        
        # 过滤无效链接
        if self._is_invalid_link(href):
            return None
        
        # 处理Bing重定向
        try:
            pu = urlparse(href)
            if 'bing.com' in (pu.netloc or '') and ('/ck/a' in pu.path or 'redirect' in pu.path):
                qs = parse_qs(pu.query)
                u = qs.get('u') or qs.get('r') or []
                if u:
                    u0 = unquote(u[0])
                    if u0.startswith('http'):
                        href = u0
        except Exception:
            pass

        if href.startswith('//'):
            return 'https:' + href
        if href.startswith('/'):
            return 'https://www.bing.com' + href
        return href

    def _is_invalid_link(self, href: str) -> bool:
        """检查是否是无效链接
        
        Args:
            href: 链接地址
            
        Returns:
            是否为无效链接
        """
        if not href:
            return True
        
        href_lower = href.lower().strip()
        
        # 检查是否匹配无效模式
        for pattern in self.INVALID_LINK_PATTERNS:
            if href_lower.startswith(pattern):
                return True
        
        # 检查是否是纯锚点或空链接
        if href_lower in ['#', 'javascript:void(0);', 'javascript:void(0)']:
            return True
        
        # 检查是否是相对路径但指向无效位置
        if href.startswith('/') and len(href) == 1:
            return True
        
        return False

    def _extract_image_url(self, link_element, href: str) -> Optional[str]:
        """从链接元素中提取图片URL
        
        Args:
            link_element: 链接元素
            href: 链接地址
            
        Returns:
            图片URL或None
        """
        try:
            # 1. 检查所有可能的图片属性
            for attr in self.IMAGE_ATTRIBUTES:
                img_url = link_element.get(attr)
                if img_url and img_url.startswith('http'):
                    print(f"[DEBUG] 找到图片URL ({attr}): {img_url}")
                    return img_url
            
            # 2. 检查img标签中的所有属性
            img_tag = link_element.find('img')
            if img_tag:
                for attr in self.IMAGE_ATTRIBUTES:
                    img_src = img_tag.get(attr)
                    if img_src and img_src.startswith('http'):
                        print(f"[DEBUG] 找到img图片URL ({attr}): {img_src}")
                        return img_src
            
            # 3. 检查直接图片链接
            if href and any(href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                print(f"[DEBUG] 找到直接图片链接: {href}")
                return href
                
        except Exception as e:
            print(f"[DEBUG] 提取图片URL失败: {e}")
        
        return None

    def _extract_image_from_parent(self, link_element) -> Optional[str]:
        """从父元素中提取图片URL
        
        Args:
            link_element: 链接元素
            
        Returns:
            图片URL或None
        """
        try:
            # 向上查找父元素中的图片
            current = link_element.parent
            while current and current.name != 'body':
                # 查找当前元素中的img标签
                img_tag = current.find('img')
                if img_tag:
                    for attr in self.IMAGE_ATTRIBUTES:
                        img_src = img_tag.get(attr)
                        if img_src and img_src.startswith('http'):
                            print(f"[DEBUG] 从父元素找到图片URL ({attr}): {img_src}")
                            return img_src
                
                # 检查父元素的data属性
                for attr in self.IMAGE_ATTRIBUTES:
                    img_url = current.get(attr)
                    if img_url and img_url.startswith('http'):
                        print(f"[DEBUG] 从父元素属性找到图片URL ({attr}): {img_url}")
                        return img_url
                
                current = current.parent
        except Exception as e:
            print(f"[DEBUG] 从父元素提取图片失败: {e}")
        
        return None


    def _is_image_page_link(self, href: str) -> bool:
        """检查是否是图片页面链接而不是图片文件本身"""
        if not href:
            return False
        
        # 检查是否是图片文件扩展名
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']
        if any(href.lower().endswith(ext) for ext in image_extensions):
            return False
        
        # 检查是否是常见的图片页面链接模式
        page_patterns = [
            '/blogs/tag/',  # 堆糖标签页面
            '/tag/',        # 标签页面
            '/photo/',      # 照片页面
            '/image/',      # 图片页面
            '/gallery/',    # 画廊页面
            '/album/',      # 相册页面
            '/pics/',       # 图片页面
            '/images/',     # 图片页面
            '?name=',       # 带参数的页面
            '/detail/',     # 详情页面
            '/view/',       # 查看页面
        ]
        
        for pattern in page_patterns:
            if pattern in href.lower():
                return True
        
        return False

    def _is_bing_internal(self, href: str) -> bool:
        """检查是否是Bing内部链接
        
        Args:
            href: 链接地址
            
        Returns:
            是否为Bing内部链接
        """
        try:
            pu = urlparse(href)
            if 'bing.com' in (pu.netloc or ''):
                # 检查是否是Bing图片详情页面
                if 'images/search' in pu.path and 'view=detailV2' in pu.query:
                    return True
                # 检查其他Bing内部路径
                for path in self.BING_INTERNAL_PATHS:
                    if pu.path.startswith(path):
                        return True
        except Exception:
            pass
        return False

    def _is_blacklisted(self, url: str) -> bool:
        """检查URL是否在黑名单中"""
        if not self.config.get("blacklist", {}).get("enabled", True):
            return False
        
        try:
            pu = urlparse(url)
            host = (pu.netloc or '').lower()
            blacklist_domains = self.config.get("blacklist", {}).get("domains", [])
            for domain in blacklist_domains:
                if domain in host:
                        return True
        except Exception:
            pass
        return False

    def _clean_title(self, title: str, href: str, site: str) -> str:
        """清理和优化标题"""
        if not title:
            return ""
        
        title = title.strip()
        
        # 移除域名前缀
        if ' › ' in title:
            title = title.split(' › ')[-1].strip()
        
        # 移除URL拼接
        if 'http' in title:
            title = title.split('http')[0].strip()
        
        # 移除纯域名标题
        if title.endswith(('.com', '.cn', '.net', '.org')):
            title = self._filename_from_url(href)
        
        # 移除无用前缀
        prefixes_to_remove = [
            '首页', '主页', '网站首页', 'Home', 'Index',
            '搜索', 'Search', '结果', 'Results',
            '登录', 'Login', '注册', 'Register',
            '关于', 'About', '帮助', 'Help'
        ]
        
        for prefix in prefixes_to_remove:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
        
        # 限制标题长度
        if len(title) > 100:
            title = title[:100] + "..."
        
        return title

    def _normalize_text(self, text: str) -> str:
        """标准化文本，处理符号变体"""
        import re
        # 替换常见的符号变体
        text = re.sub(r'[＊*·•·]', '*', text)  # 统一星号变体
        text = re.sub(r'[：:]', ':', text)      # 统一冒号变体
        text = re.sub(r'[（）()]', '', text)    # 移除括号
        text = re.sub(r'[，,。.]', '', text)    # 移除标点
        return text.strip()
    
    def _super_loose_match(self, query: str, title: str) -> bool:
        """超宽松匹配：处理符号变体和部分匹配"""
        query_lower = query.lower()
        title_lower = title.lower()
        
        # 标准化文本
        normalized_query = self._normalize_text(query_lower)
        normalized_title = self._normalize_text(title_lower)
        
        # 检查标准化后的完整匹配
        if normalized_query in normalized_title:
            return True
        
        # 检查部分匹配（至少50%的查询词匹配）
        query_chars = set(normalized_query.replace(' ', ''))
        title_chars = set(normalized_title.replace(' ', ''))
        if len(query_chars) > 0:
            match_ratio = len(query_chars & title_chars) / len(query_chars)
            if match_ratio >= 0.5:  # 至少50%的字符匹配
                return True
        
        # 超宽松匹配：只要有一个字相同就不过滤（优先级低但不过滤）
        if len(query_chars) > 0:
            common_chars = query_chars & title_chars
            if len(common_chars) > 0:  # 至少有一个字符相同
                return True
        
        return False
    
    def _basic_keyword_match(self, query: str, title: str, url: str) -> bool:
        """基本关键词匹配"""
        query_lower = query.lower()
        title_lower = title.lower()
        url_lower = url.lower()
        
        query_words = query_lower.split()
        title_text = title_lower + ' ' + url_lower
        
        return (
            query_lower in title_text or  # 完整查询词在标题或URL中
            any(word in title_text for word in query_words)  # 查询词中的任何词在标题或URL中
        )

    def _is_relevant_content(self, title: str, url: str, query: str, stype: str) -> bool:
        """检查内容是否与搜索相关"""
        if not title or not query:
            return True
        
        title_lower = title.lower()
        query_lower = query.lower()
        
        # 网页搜索：不进行过滤，让用户自己判断
        if stype == 'web':
            return True
        
        # 资源搜索：使用超宽松匹配
        elif stype in ['files', 'resources']:
            # 过滤掉明显的无关内容
            irrelevant_keywords = [
                '登录', 'login', '注册', 'register', '首页', 'home', '关于', 'about',
                '联系我们', 'contact', '帮助', 'help', '隐私', 'privacy', '条款', 'terms',
                '广告', 'ad', '推广', 'promotion', '招聘', 'job', '招聘信息',
                '新闻', 'news', '公告', 'notice', '更新', 'update', '维护', 'maintenance'
            ]
            
            if any(keyword in title_lower for keyword in irrelevant_keywords):
                return False
            
            return self._super_loose_match(query, title)
        
        # 视频搜索：仅进行URL检查 + 超宽松匹配
        elif stype == 'videos':
            # 排除明显的非视频内容
            non_video_keywords = [
                '登录', 'login', '注册', 'register', '首页', 'home', '关于', 'about', 
                '隐私', '条款', '帮助', '客服', '联系我们', 'contact'
            ]
            
            if any(keyword in title_lower for keyword in non_video_keywords):
                return False
            
            # 仅检查URL中的视频特征（不检查视频网站）
            url_lower = url.lower()
            
            # 检查视频路径
            video_paths = ['/video/', '/v/', '/play/', '/player/', '/watch/', '/movie/', '/tv/', '/anime/', '/drama/']
            has_video_path = any(path in url_lower for path in video_paths)
            
            # 检查视频文件扩展名
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg']
            has_video_extension = any(ext in url_lower for ext in video_extensions)
            
            # 如果URL看起来像视频，使用超宽松匹配
            if has_video_path or has_video_extension:
                return self._super_loose_match(query, title)
            
            return False
        
        # 图片搜索：基本匹配 + 质量过滤
        elif stype == 'images':
            # 基本关键词匹配
            if not self._basic_keyword_match(query, title, url):
                return False
            
            # 排除明显不相关的内容
            irrelevant_keywords = [
                '登录', 'login', '注册', 'register', '首页', 'home', '关于', 'about',
                '联系我们', 'contact', '帮助', 'help', '隐私', 'privacy', '条款', 'terms',
                '广告', 'ad', '推广', 'promotion', '招聘', 'job', '招聘信息',
                '新闻', 'news', '公告', 'notice', '更新', 'update', '维护', 'maintenance',
                '图标', 'icon', 'logo', '标志', '按钮', 'button', '导航', 'nav',
                '缩略图', 'thumbnail', '预览', 'preview', '加载', 'loading',
                '背景', 'background', '装饰', 'decoration', '边框', 'border'
            ]
            
            if any(keyword in title_lower for keyword in irrelevant_keywords):
                return False
            
            # 检查图片质量相关指标
            low_quality_indicators = [
                '模糊', 'blur', '像素', 'pixel', '低清', 'low quality', '压缩', 'compress',
                '小图', 'small', '缩略', 'thumb', '预览', 'preview'
            ]
            
            if any(indicator in title_lower for indicator in low_quality_indicators):
                return False
            
            # 检查URL中的尺寸信息，过滤掉过小的图片
            if 'w=' in url and 'h=' in url:
                import re
                w_match = re.search(r'w=(\d+)', url)
                h_match = re.search(r'h=(\d+)', url)
                if w_match and h_match:
                    w = int(w_match.group(1))
                    h = int(h_match.group(1))
                    if w < 100 or h < 100:
                        return False
            
                return True
            
        # 默认：基本匹配
        return self._basic_keyword_match(query, title, url)

    def _filename_from_url(self, url: str) -> str:
        """从URL提取文件名"""
        try:
            m = re.search(r"/([^/?#]+)(?:\?|#|$)", url)
            if m:
                return m.group(1)
        except Exception:
            pass
        return url

    def _parse_search_results(self, soup: BeautifulSoup, query: str, engine: str = "bing", stype: str = "web") -> List[Dict[str, Any]]:
        """解析搜索结果页面"""
        results = []
        
        # 多种选择器尝试
        selectors = [
            'li.b_algo', 'li[class*="b_algo"]', '.b_algo', 
            'li[class*="algo"]', 'li[class*="result"]', 
            'div[class*="result"]', 'article', 'h2 a'
        ]
        
        found_results = False
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"[DEBUG] 使用选择器 {selector} 找到 {len(items)} 个结果")
                found_results = True
                
                for item in items:
                    link_elem = item.find('a', href=True)
                    if link_elem:
                        original_href = link_elem.get('href', '')
                        href = self._normalize_url(original_href)
                        if not href or self._is_bing_internal(href) or self._is_blacklisted(href):
                            if original_href in ['#', 'javascript:void(0);', 'javascript:void(0)']:
                                print(f"[DEBUG] 过滤无效链接: {original_href}")
                            elif self._is_blacklisted(href):
                                print(f"[DEBUG] 过滤黑名单链接: {href}")
                            continue
                        
                        title_elem = item.find('h2') or item.find('h3')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        else:
                            title = link_elem.get_text().strip()
                        
                        title = self._clean_title(title, href, "")
                        
                        if title:
                            # 图片搜索需要提取实际的图片URL并进行内容过滤
                            if stype == 'images':
                                # 先检查内容相关性
                                if not self._is_relevant_content(title, href, query, stype):
                                    print(f"[DEBUG] 过滤不相关图片: {title} - {href}")
                                    continue
                                
                                # 对于图片搜索，尝试从图源页面获取真正的原图URL
                                # 先尝试从链接元素提取图片URL
                                image_url = self._extract_image_url(link_elem, href)
                                if not image_url:
                                    # 如果没找到，尝试从父元素提取
                                    image_url = self._extract_image_from_parent(link_elem)
                                
                                # 使用Bing缩略图
                                if image_url and 'tse' in image_url and 'bing.net' in image_url:
                                    print(f"[DEBUG] 使用Bing缩略图: {image_url}")
                                
                                if image_url:
                                    # 有图片URL时，使用图片URL作为显示，原链接作为图源
                                    results.append({
                                        "title": title,
                                        "url": href,  # 图源链接（用于点击跳转）
                                        "snippet": image_url,  # 图片URL（用于显示）
                                        "page": href,  # 图源链接
                                        "engine": engine
                                    })
                                    print(f"[DEBUG] 找到{engine}图片结果: {title} - 图片:{image_url} 图源:{href}")
                                else:
                                    # 没有图片URL时，使用原链接作为图源
                                    results.append({
                                        "title": title,
                                        "url": href,
                                        "snippet": "",
                                        "page": href,  # 图源链接
                                        "engine": engine
                                    })
                                    print(f"[DEBUG] 找到{engine}链接结果: {title} - {href}")
                            else:
                                # 检查内容相关性
                                if self._is_relevant_content(title, href, query, stype):
                                    results.append({
                                        "title": title,
                                        "url": href,
                                        "snippet": "",
                                        "engine": engine
                                    })
                                    print(f"[DEBUG] 找到{engine}结果: {title} - {href}")
                                else:
                                    print(f"[DEBUG] 过滤不相关内容: {title} - {href}")
                break
        
        # 如果没找到结构化结果，尝试所有链接
        if not found_results:
            print(f"[DEBUG] 未找到结构化结果，尝试所有链接")
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                original_href = link.get('href', '')
                href = self._normalize_url(original_href)
                if not href or self._is_bing_internal(href) or self._is_blacklisted(href):
                    if original_href in ['#', 'javascript:void(0);', 'javascript:void(0)']:
                        print(f"[DEBUG] 过滤无效链接: {original_href}")
                    continue
                
                title = link.get_text().strip()
                title = self._clean_title(title, href, "")
                
                if title:
                    # 图片搜索需要提取实际的图片URL并进行内容过滤
                    if stype == 'images':
                        # 先检查内容相关性
                        if not self._is_relevant_content(title, href, query, stype):
                            print(f"[DEBUG] 过滤不相关图片: {title} - {href}")
                            continue
                        
                        # 对于图片搜索，尝试从图源页面获取真正的原图URL
                        # 先尝试从链接元素提取图片URL
                        image_url = self._extract_image_url(link, href)
                        if not image_url:
                            # 如果没找到，尝试从父元素提取
                            image_url = self._extract_image_from_parent(link)
                        
                        # 使用Bing缩略图
                        if image_url and 'tse' in image_url and 'bing.net' in image_url:
                            print(f"[DEBUG] 使用Bing缩略图: {image_url}")
                        
                        if image_url:
                            # 有图片URL时，使用图片URL作为显示，原链接作为图源
                            results.append({
                                "title": title,
                                "url": href,  # 图源链接（用于点击跳转）
                                "snippet": image_url,  # 图片URL（用于显示）
                                "page": href,  # 图源链接
                                "engine": engine
                            })
                            print(f"[DEBUG] 找到{engine}图片结果: {title} - 图片:{image_url} 图源:{href}")
                        else:
                            # 没有图片URL时，使用原链接作为图源
                            results.append({
                                "title": title,
                                "url": href,
                                "snippet": "",
                                "page": href,  # 图源链接
                                "engine": engine
                            })
                            print(f"[DEBUG] 找到{engine}链接结果: {title} - {href}")
                    else:
                        # 对于图片搜索，不进行相关性过滤
                        if stype == 'images':
                            results.append({
                                "title": title,
                                "url": href,
                                "snippet": "",
                                "engine": engine
                            })
                            print(f"[DEBUG] 找到{engine}图片结果: {title} - {href}")
                        else:
                            # 其他搜索类型进行相关性检查
                            if self._is_relevant_content(title, href, query, stype):
                                results.append({
                                    "title": title,
                                    "url": href,
                                    "snippet": "",
                                    "engine": engine
                                })
                                print(f"[DEBUG] 找到{engine}链接结果: {title} - {href}")
                            else:
                                print(f"[DEBUG] 过滤不相关内容: {title} - {href}")
        
        return results

    def _parse_bing_images_simple(self, soup: BeautifulSoup, query: str) -> List[Dict[str, Any]]:
        """简化的Bing图片解析，不过滤任何结果"""
        results = []
        
        # 查找真正的图源链接，过滤掉Bing内部链接
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            try:
                href = link.get('href', '')
                title = link.get_text().strip()
                
                # 过滤明显无效的链接
                if (not href or 
                    href.startswith('javascript:') or 
                    href.startswith('#') or
                    href.startswith('mailto:') or
                    len(title) < 2):
                    continue
                
                # 过滤Bing内部链接
                if (href.startswith('https://www.bing.com/') or 
                    href.startswith('https://cn.bing.com/') or
                    'bing.com' in href):
                    continue
                
                # 只处理外部链接（真正的图源）
                if not href.startswith('http'):
                    continue
                
                # 处理相对路径，转换为完整URL
                if href.startswith('/'):
                    href = f"https://www.bing.com{href}"
                elif not href.startswith('http'):
                    href = f"https://www.bing.com/{href}"
                
                # 尝试从链接元素提取图片URL
                image_url = self._extract_image_url(link, href)
                if not image_url:
                    # 如果没找到，尝试从父元素提取
                    image_url = self._extract_image_from_parent(link)
                
                # 使用找到的图片URL，如果没有则使用链接URL
                final_url = image_url or href
                
                # 直接添加所有有效链接，不进行任何相关性检查
                results.append({
                    "title": title or f"图片: {query}",
                    "url": href,  # 图源链接（用于点击跳转）
                    "snippet": image_url,  # 图片URL（用于显示）
                    "page": href,  # 图源链接
                    "engine": "bing"
                })
                print(f"[DEBUG] 找到Bing图片: {title} - 图片:{image_url} 图源:{href}")

                
            except Exception as e:
                print(f"[DEBUG] 解析Bing图片链接失败: {e}")
                continue
        
        print(f"[DEBUG] Bing图片解析完成: 找到 {len(results)} 条结果")
        return results

    def _search_bing(self, query: str, stype: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用Bing搜索，支持分页获取更多结果"""
        s = self._session()
        count = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
        first = max(0, int(page)) * count + 1
        
        if stype == 'images':
            url = f"https://www.bing.com/images/search?q={query}&setlang=zh-cn&count=60&first={first}"
        elif stype == 'videos':
            url = f"https://www.bing.com/videos/search?q={query}&setlang=zh-cn&count=50&first={first}"
        elif stype in ['files', 'resources']:
            # 为资源搜索使用更宽松的搜索条件，不限制文件类型
            url = f"https://www.bing.com/search?q={query} 下载 OR 资源 OR 游戏&setlang=zh-cn&count={count}&first={first}"
        else:
            url = f"https://www.bing.com/search?q={query}&setlang=zh-cn&count={count}&first={first}"
        
        r = self._request(s, url)
        if not r:
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # 对于图片搜索，使用简化的解析逻辑
        if stype == 'images':
            return self._parse_bing_images_simple(soup, query)
        else:
            return self._parse_search_results(soup, query, "bing", stype)
    
    def _search_bing_multiple_pages(self, query: str, stype: str, max_pages: int = 3) -> List[Dict[str, Any]]:
        """使用Bing搜索多页结果，参考百度爬虫的分页思路"""
        all_results = []
        
        for page in range(max_pages):
            try:
                print(f"[DEBUG] 正在获取Bing第{page+1}页结果...")
                page_results = self._search_bing(query, stype, page)
                
                if not page_results:
                    print(f"[DEBUG] 第{page+1}页无结果，停止获取")
                    break
                
                all_results.extend(page_results)
                print(f"[DEBUG] 第{page+1}页获取到 {len(page_results)} 条结果")
                
                # 添加延迟，避免请求过快（减少延迟时间）
                import time
                time.sleep(0.1)
                
            except Exception as e:
                print(f"[DEBUG] 获取第{page+1}页失败: {e}")
                break
        
        print(f"[DEBUG] Bing多页搜索完成，共获取 {len(all_results)} 条结果")
        return all_results

    def _search_baidu(self, query: str, stype: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用百度搜索"""
        try:
            s = self._session()
            count = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
            pn = max(0, int(page)) * count
            
            if stype == 'images':
                url = f"https://www.baidu.com/s?wd={query}&t=image&pn={pn}"
            elif stype == 'videos':
                url = f"https://www.baidu.com/s?wd={query}&t=video&pn={pn}"
            else:
                url = f"https://www.baidu.com/s?wd={query}&pn={pn}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
                "Referer": "https://www.baidu.com/"
            }
            
            print(f"[DEBUG] 百度搜索: {query} (第{page+1}页)")
            r = self._request(s, url, headers=headers)
            if not r:
                print(f"[DEBUG] 百度搜索失败: 无法获取响应")
                return []
            
            # 检查响应内容
            if len(r.content) < 1000:
                print(f"[DEBUG] 百度搜索响应内容过短: {len(r.content)} 字节")
                return []
            
            soup = BeautifulSoup(r.content, 'html.parser')
            results = self._parse_baidu_results(soup, query, stype)
            print(f"[DEBUG] 百度搜索成功: 获取到 {len(results)} 条结果")
            return results
            
        except Exception as e:
            print(f"[DEBUG] 百度搜索异常: {e}")
            return []

    def _search_sogou(self, query: str, stype: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用搜狗搜索"""
        try:
            s = self._session()
            
            # 搜狗搜索的分页参数，使用配置的最大结果数
            count = self.config.get("settings", {}).get("engine_max_results", 35)
            p = 40040100 + (page * count)
            
            if stype == 'images':
                url = f"https://pic.sogou.com/pics?query={query}&start={page * 20}"
            elif stype == 'videos':
                url = f"https://sogou.com/video?query={query}&p={p}"
            else:
                url = f"https://sogou.com/web?query={query}&_asf=www.sogou.com&_ast=&w=01019900&p={p}&ie=utf8&from=index-nologin&s_from=index&sourceid=9_01_03"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
                "Referer": "https://www.sogou.com/"
            }
            
            print(f"[DEBUG] 搜狗搜索: {query} (第{page+1}页)")
            r = self._request(s, url, headers=headers)
            if not r:
                print(f"[DEBUG] 搜狗搜索失败: 无法获取响应")
                return []
            
            # 检查响应内容
            if len(r.content) < 1000:
                print(f"[DEBUG] 搜狗搜索响应内容过短: {len(r.content)} 字节")
                return []
            
            soup = BeautifulSoup(r.content, 'html.parser')
            results = self._parse_sogou_results(soup, query, stype)
            print(f"[DEBUG] 搜狗搜索成功: 获取到 {len(results)} 条结果")
            return results
            
        except Exception as e:
            print(f"[DEBUG] 搜狗搜索异常: {e}")
            return []

    def _parse_baidu_results(self, soup: BeautifulSoup, query: str, stype: str) -> List[Dict[str, Any]]:
        """解析百度搜索结果"""
        results = []
        
        # 百度搜索结果的选择器 - 使用更精确的选择器
        selectors = [
            'div.result.c-container.xpath-log.new-pmd',  # 新的百度结果容器
            'div[class*="result c-container"]',          # 传统百度结果容器
            'div[class*="c-container"]',                 # 通用容器
            'div[class*="c-result"]',                    # 结果容器
            'h3 a',                                      # 标题链接
            '.t a'                                       # 标题链接
        ]
        
        found_results = False
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"[DEBUG] 百度使用选择器 {selector} 找到 {len(items)} 个结果")
                found_results = True
                
                for item in items:
                    try:
                        # 查找标题和链接
                        link_elem = item.find('a', href=True) if item.name != 'a' else item
                        if not link_elem:
                            continue
                            
                        href = link_elem.get('href', '')
                        title = link_elem.get_text().strip()
                        
                        if not href or not title or href.startswith('javascript:'):
                            continue
                        
                        # 处理百度重定向链接
                        real_url = self._get_baidu_real_url(href)
                        if not real_url:
                            continue
                        
                        # 获取来源网站
                        source_site = ""
                        source_elem = item.find('span', class_='c-color-gray')
                        if source_elem:
                            source_site = source_elem.get_text().strip()
                        
                        # 获取简介
                        description = ""
                        desc_div = item.find('div', class_='c-span9 c-span-last')
                        if desc_div:
                            desc_spans = desc_div.find_all('span')
                            if len(desc_spans) > 1:
                                description = desc_spans[1].get_text().strip()
                        else:
                            # 尝试其他描述选择器
                            desc_elem = item.find('span', class_='c-color-text')
                            if desc_elem:
                                description = desc_elem.get_text().strip()
                        
                        # 清理标题
                        title = self._clean_title(title, real_url, "baidu")
                        
                        if title and real_url:
                            results.append({
                                "title": title,
                                "url": real_url,
                                "snippet": description or f"百度搜索: {title}",
                                "engine": "baidu"
                            })
                            print(f"[DEBUG] 找到百度结果: {title} - {real_url}")
                            
                    except Exception as e:
                        print(f"[DEBUG] 解析百度结果项失败: {e}")
                        continue
                
                if results:
                    break
        
        # 如果没找到结构化结果，尝试所有链接
        if not found_results:
            print(f"[DEBUG] 百度未找到结构化结果，尝试所有链接")
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                try:
                    href = link.get('href', '')
                    title = link.get_text().strip()
                    
                    if not href or not title or href.startswith('javascript:'):
                        continue
                    
                    # 处理百度重定向链接
                    real_url = self._get_baidu_real_url(href)
                    if not real_url:
                        continue
                    
                    # 清理标题
                    title = self._clean_title(title, real_url, "baidu")
                    
                    if title and real_url:
                        results.append({
                            "title": title,
                            "url": real_url,
                            "snippet": f"百度搜索: {title}",
                            "engine": "baidu"
                        })
                        print(f"[DEBUG] 找到百度链接结果: {title} - {real_url}")
                        
                except Exception as e:
                    print(f"[DEBUG] 解析百度链接失败: {e}")
                    continue
        
        return results

    def _parse_baidu_images(self, soup: BeautifulSoup, query: str) -> List[Dict[str, Any]]:
        """解析百度图片搜索结果"""
        results = []
        
        # 百度图片搜索的选择器
        selectors = [
            'div.imgitem',           # 图片项目容器
            'div[class*="imgitem"]',  # 通用图片容器
            'div[class*="img"]',      # 图片相关容器
            'a[href*="img"]',        # 图片链接
            'img[src*="http"]'        # 图片元素
        ]
        
        found_results = False
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"[DEBUG] 百度图片使用选择器 {selector} 找到 {len(items)} 个结果")
                found_results = True
                
                for item in items:
                    try:
                        # 查找图片URL
                        img_url = ""
                        img_elem = item.find('img') if item.name != 'img' else item
                        if img_elem:
                            img_url = img_elem.get('src') or img_elem.get('data-src', '')
                        
                        # 查找链接
                        link_elem = item.find('a', href=True) if item.name != 'a' else item
                        href = link_elem.get('href', '') if link_elem else ''
                        
                        # 查找标题
                        title = ""
                        title_elem = item.find('span', class_='imgitem-title') or item.find('div', class_='imgitem-title')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        elif link_elem:
                            title = link_elem.get_text().strip()
                        
                        if not img_url and not href:
                            continue
                        
                        # 处理百度重定向链接
                        real_url = self._get_baidu_real_url(href) if href else img_url
                        if not real_url:
                            continue
                        
                        # 清理标题
                        title = self._clean_title(title, real_url, "baidu") if title else f"百度图片: {query}"
                        
                        results.append({
                            "title": title,
                            "url": real_url,
                            "snippet": f"百度图片搜索: {title}",
                            "engine": "baidu"
                        })
                        print(f"[DEBUG] 找到百度图片结果: {title} - {real_url}")
                        
                    except Exception as e:
                        print(f"[DEBUG] 解析百度图片结果项失败: {e}")
                        continue
                
                if results:
                    break
        
        # 如果没找到结构化结果，尝试所有图片链接
        if not found_results:
            print(f"[DEBUG] 百度图片未找到结构化结果，尝试所有图片链接")
            all_imgs = soup.find_all('img', src=True)
            for img in all_imgs:
                try:
                    img_url = img.get('src', '')
                    if not img_url or not img_url.startswith('http'):
                        continue
                    
                    # 查找父级链接
                    parent_link = img.find_parent('a', href=True)
                    href = parent_link.get('href', '') if parent_link else ''
                    
                    # 处理百度重定向链接
                    real_url = self._get_baidu_real_url(href) if href else img_url
                    if not real_url:
                        continue
                    
                    title = f"百度图片: {query}"
                    
                    results.append({
                        "title": title,
                        "url": real_url,
                        "snippet": f"百度图片搜索: {title}",
                        "engine": "baidu"
                    })
                    print(f"[DEBUG] 找到百度图片链接结果: {title} - {real_url}")
                    
                except Exception as e:
                    print(f"[DEBUG] 解析百度图片链接失败: {e}")
                    continue
        
        return results

    def _get_baidu_real_url(self, baidu_url: str) -> Optional[str]:
        """获取百度重定向链接的真实URL
        
        Args:
            baidu_url: 百度重定向链接
            
        Returns:
            真实URL或None
        """
        try:
            if not baidu_url or not baidu_url.startswith('/link?url='):
                return baidu_url
            
            # 创建临时会话
            s = self._session()
            
            # 构建完整的百度链接
            if baidu_url.startswith('/'):
                full_url = f"https://www.baidu.com{baidu_url}"
            else:
                full_url = baidu_url
            
            print(f"[DEBUG] 获取百度真实URL: {full_url}")
            
            # 发送请求，不允许重定向
            response = s.get(full_url, allow_redirects=False, timeout=10)
            
            if response.status_code == 302:
                # 从Location头获取真实URL
                real_url = response.headers.get('Location')
                if real_url:
                    print(f"[DEBUG] 从Location头获取真实URL: {real_url}")
                    return real_url
            
            # 尝试从响应内容中提取URL
            content = response.text
            url_patterns = [
                r"URL='([^']+)'",
                r'url="([^"]+)"',
                r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
                r'location\.href\s*=\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in url_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    real_url = matches[0]
                    if real_url.startswith('http'):
                        print(f"[DEBUG] 从内容提取真实URL: {real_url}")
                        return real_url
            
            print(f"[DEBUG] 无法获取百度真实URL")
            return None
            
        except Exception as e:
            print(f"[DEBUG] 获取百度真实URL失败: {e}")
            return None

    def _parse_sogou_results(self, soup: BeautifulSoup, query: str, stype: str) -> List[Dict[str, Any]]:
        """解析搜狗搜索结果"""
        results = []
        
        # 搜狗搜索结果的选择器
        selectors = [
            'div[class*="result"]', 'div[class*="vrwrap"]', 
            'h3 a', '.tit a', '.res-title a'
        ]
        
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"[DEBUG] 搜狗使用选择器 {selector} 找到 {len(items)} 个结果")
                
                for item in items:
                    link_elem = item.find('a', href=True) if item.name != 'a' else item
                    if link_elem:
                        href = link_elem.get('href', '')
                        title = link_elem.get_text().strip()
                        
                        if href and title and not href.startswith('javascript:'):
                            # 处理搜狗重定向链接
                            if href.startswith('/link?url='):
                                try:
                                    from urllib.parse import unquote
                                    href = unquote(href.split('url=')[1].split('&')[0])
                                except:
                                    continue
                            
                            results.append({
                                "title": title,
                                "url": href,
                                "snippet": f"搜狗搜索: {title}",
                                "engine": "sogou"
                            })
                            print(f"[DEBUG] 找到搜狗结果: {title} - {href}")
                
                if results:
                    break
        
        return results

    def _search_so(self, query: str, stype: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用360搜索"""
        try:
            s = self._session()
            count = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
            pn = max(0, int(page)) * count
            
            if stype == 'images':
                url = f"https://www.so.com/s?q={query}&src=image&pn={pn}"
            elif stype == 'videos':
                url = f"https://www.so.com/s?q={query}&src=video&pn={pn}"
            else:
                url = f"https://www.so.com/s?q={query}&pn={pn}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
                "Referer": "https://www.so.com/"
            }
            
            print(f"[DEBUG] 360搜索: {query} (第{page+1}页)")
            r = self._request(s, url, headers=headers)
            if not r:
                print(f"[DEBUG] 360搜索失败: 无法获取响应")
                return []
            
            # 检查响应内容
            if len(r.content) < 1000:
                print(f"[DEBUG] 360搜索响应内容过短: {len(r.content)} 字节")
                return []
            
            soup = BeautifulSoup(r.content, 'html.parser')
            results = self._parse_so_results(soup, query, stype)
            print(f"[DEBUG] 360搜索成功: 获取到 {len(results)} 条结果")
            return results
            
        except Exception as e:
            print(f"[DEBUG] 360搜索异常: {e}")
            return []

    def _parse_so_results(self, soup: BeautifulSoup, query: str, stype: str) -> List[Dict[str, Any]]:
        """解析360搜索结果"""
        results = []
        
        # 360搜索结果的选择器
        selectors = [
            'div[class*="result"]', 'div[class*="res-list"]', 
            'h3 a', '.res-title a', '.res-title'
        ]
        
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"[DEBUG] 360搜索使用选择器 {selector} 找到 {len(items)} 个结果")
                
                for item in items:
                    link_elem = item.find('a', href=True) if item.name != 'a' else item
                    if link_elem:
                        href = link_elem.get('href', '')
                        title = link_elem.get_text().strip()
                        
                        if href and title and not href.startswith('javascript:'):
                            # 处理360重定向链接
                            if href.startswith('/link?url='):
                                try:
                                    from urllib.parse import unquote
                                    href = unquote(href.split('url=')[1].split('&')[0])
                                except:
                                    continue
                            
                            results.append({
                                "title": title,
                                "url": href,
                                "snippet": f"360搜索: {title}",
                                "engine": "so"
                            })
                            print(f"[DEBUG] 找到360搜索结果: {title} - {href}")
                
                if results:
                    break
        
        return results

    def _search_direct_site(self, site: str, query: str, search_urls: List[str]) -> List[Dict[str, Any]]:
        """直接访问网站搜索"""
        results = []
        s = self._session()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        }
        
        # 如果没有配置搜索URL，使用默认搜索URL模板
        if not search_urls:
            print(f"[DEBUG] {site} 没有配置搜索URL，使用默认搜索URL模板")
            default_search_urls = [
                f"https://{site}/search?q={{query}}",           # 最常见的搜索参数
                f"https://{site}/search?query={{query}}",        # 第二常见的搜索参数
                f"https://{site}/search?keyword={{query}}",      # 关键词搜索
                f"https://{site}/search?word={{query}}",         # 单词搜索
                f"https://{site}/search?kw={{query}}",           # 缩写形式
                f"https://{site}/search?search={{query}}",       # 搜索参数
                f"https://{site}/search?q={{query}}&type=all",   # 全部类型搜索
                f"https://{site}/search?query={{query}}&type=all" # 全部类型搜索
            ]
            search_urls = default_search_urls
        
        for search_url in search_urls:
            try:
                formatted_url = search_url.format(query=quote(query))
                print(f"[DEBUG] 直接访问: {formatted_url}")
                response = self._request(s, formatted_url, headers=headers)
                
                if response and response.status_code == 200:
                    # 处理编码问题
                    try:
                        # 尝试从响应头获取编码
                        encoding = response.encoding
                        if not encoding or encoding.lower() in ['iso-8859-1', 'windows-1252']:
                            # 尝试从HTML内容中检测编码
                            content_str = response.content.decode('utf-8', errors='ignore')
                            if 'charset=' in content_str.lower():
                                import re
                                charset_match = re.search(r'charset=["\']?([^"\'>\s]+)', content_str, re.IGNORECASE)
                                if charset_match:
                                    encoding = charset_match.group(1)
                                else:
                                    encoding = 'utf-8'
                            else:
                                encoding = 'utf-8'
                        
                        # 使用正确的编码解码内容
                        content = response.content.decode(encoding, errors='ignore')
                        soup = BeautifulSoup(content, 'html.parser')
                        print(f"[DEBUG] {site} 页面长度: {len(content)}, 编码: {encoding}")
                    except Exception as e:
                        print(f"[DEBUG] {site} 编码处理失败: {e}, 使用默认编码")
                        soup = BeautifulSoup(response.content, 'html.parser')
                        print(f"[DEBUG] {site} 页面长度: {len(response.content)}")
                    
                    # 查找所有链接
                    all_links = soup.find_all('a', href=True)
                    print(f"[DEBUG] {site} 找到 {len(all_links)} 个链接")
                    
                    # 调试：检查页面内容
                    if len(all_links) == 0:
                        print(f"[DEBUG] {site} 页面内容预览: {content[:500]}...")
                        # 检查是否有搜索结果相关的元素
                        result_elements = soup.find_all(['div', 'li', 'h3'], class_=lambda x: x and ('result' in x.lower() or 'algo' in x.lower() or 'title' in x.lower()))
                        print(f"[DEBUG] {site} 找到 {len(result_elements)} 个可能的结果元素")
                        
                        # 检查是否可能是动态加载的内容
                        has_js_indicators = any(indicator in content.lower() for indicator in [
                            'loading', 'ajax', 'fetch', 'xhr', 'async', 'lazy', 
                            'infinite', 'scroll', 'pagination', 'more', 'load'
                        ])
                        
                        if has_js_indicators:
                            print(f"[DEBUG] {site} 检测到可能的动态加载内容，等待页面加载...")
                            import time
                            time.sleep(1)  # 等待1秒让JavaScript加载内容
                            
                            # 重新请求页面
                            try:
                                print(f"[DEBUG] {site} 重新请求页面...")
                                retry_response = self._request(s, formatted_url, headers=headers)
                                if retry_response and retry_response.status_code == 200:
                                    retry_content = retry_response.content.decode(encoding, errors='ignore')
                                    soup = BeautifulSoup(retry_content, 'html.parser')
                                    all_links = soup.find_all('a', href=True)
                                    print(f"[DEBUG] {site} 延迟加载后找到 {len(all_links)} 个链接")
                            except Exception as e:
                                print(f"[DEBUG] {site} 延迟加载失败: {e}")
                        
                        # 如果延迟加载后还是没有找到链接，使用专门解析
                        if len(all_links) == 0:
                            print(f"[DEBUG] 尝试 {site} 专门解析...")
                            # 查找网站特有的元素
                            special_links = []
                            
                            # 查找包含内容的div（视频、图片、文章等）
                            content_divs = soup.find_all('div', class_=lambda x: x and any(keyword in x.lower() for keyword in ['video', 'item', 'result', 'content', 'post', 'article', 'card', 'box', 'list', 'grid']))
                            print(f"[DEBUG] {site} 找到 {len(content_divs)} 个内容div")
                            
                            for div in content_divs:
                                # 在div内查找链接
                                div_links = div.find_all('a', href=True)
                                for link in div_links:
                                    href = link.get('href', '')
                                    title = link.get_text().strip()
                                    
                                    # 处理相对链接
                                    if href.startswith('/'):
                                        href = f"https://{site}{href}"
                                    elif not href.startswith('http') and not href.startswith('//'):
                                        # 检查是否已经包含域名，避免重复
                                        if site not in href:
                                            href = f"https://{site}/{href}"
                                        else:
                                            href = f"https://{href}"
                                    
                                    if href and title and len(title) > 3:
                                        special_links.append((href, title))
                                        print(f"[DEBUG] {site} 找到链接: {title} - {href}")
                            
                            # 如果没有找到，尝试查找所有可能的链接
                            if not special_links:
                                all_possible_links = soup.find_all('a', href=True)
                                for link in all_possible_links:
                                    href = link.get('href', '')
                                    title = link.get_text().strip()
                                    
                                    # 处理相对链接
                                    if href.startswith('/'):
                                        href = f"https://{site}{href}"
                                    elif not href.startswith('http') and not href.startswith('//'):
                                        # 检查是否已经包含域名，避免重复
                                        if site not in href:
                                            href = f"https://{site}/{href}"
                                        else:
                                            href = f"https://{href}"
                                    
                                    # 过滤掉明显不是内容的链接
                                    if (href and title and len(title) > 3 and 
                                        not href.startswith('javascript:') and
                                        not href.startswith('mailto:') and
                                        not href.startswith('tel:') and
                                        not 'login' in href.lower() and
                                        not 'register' in href.lower() and
                                        not 'help' in href.lower() and
                                        not 'about' in href.lower() and
                                        not 'contact' in href.lower() and
                                        not 'privacy' in href.lower() and
                                        not 'terms' in href.lower()):
                                        special_links.append((href, title))
                                        print(f"[DEBUG] {site} 找到可能链接: {title} - {href}")
                            
                            # 将找到的链接添加到all_links中
                            for href, title in special_links:
                                # 创建一个虚拟的link对象
                                fake_link = type('FakeLink', (), {
                                    'get': lambda self, attr: href if attr == 'href' else '',
                                    'get_text': lambda self: title
                                })()
                                all_links.append(fake_link)
                            
                            print(f"[DEBUG] {site} 专门解析找到 {len(special_links)} 个链接")
                    
                    for link in all_links:
                        href = link.get('href', '')
                        title = link.get_text().strip()
                        
                        # 处理相对链接
                        if href.startswith('/'):
                            href = f"https://{site}{href}"
                        elif not href.startswith('http') and not href.startswith('//'):
                            # 检查是否已经包含域名，避免重复
                            if site not in href:
                                href = f"https://{site}/{href}"
                            else:
                                href = f"https://{href}"
                        
                        # 清理标题
                        title = self._clean_title(title, href, site)
                        
                        # 基础过滤条件（所有搜索都适用）
                        basic_filter = (title and href and 
                            not self._is_bing_internal(href) and 
                            not href.startswith('https://so.com/s?q=') and
                            not href.startswith('javascript:') and
                            not href.startswith('mailto:') and
                            not href.startswith('tel:') and
                            len(title) > 3)
                        
                        # 资源类搜索使用宽松过滤（游戏、软件、电影等）
                        resource_keywords = ['游戏', '软件', '电影', '音乐', '小说', '漫画', '动画', '下载', '资源', '破解', '汉化', '补丁', '修改器', '存档', 'CG', '攻略']
                        is_resource_search = any(keyword in query.lower() for keyword in resource_keywords)
                        
                        if is_resource_search:
                            # 资源类搜索：只过滤最基本的无效内容
                            should_include = (basic_filter and
                                not title.startswith('京') and  # 过滤备案信息
                                not title.startswith('增值电信') and
                                not title.startswith('隐私') and
                                not title.startswith('条款'))
                        else:
                            # 普通搜索：使用严格过滤
                            should_include = (basic_filter and
                                not 'microsoft.com' in href and
                                not 'beian.gov.cn' in href and
                                not 'miit.gov.cn' in href and
                                not 'go.microsoft.com' in href and
                                not title.startswith('京') and  # 过滤备案信息
                                not title.startswith('增值电信') and
                                not title.startswith('隐私') and
                                not title.startswith('条款') and
                                not title.startswith('跳至内容') and
                                not title.startswith('网页') and
                                not title.startswith('地图') and
                                not title.startswith('工具') and
                                not title.startswith('时间不限') and
                                not title.startswith('更多') and
                                not title.startswith('此处'))
                        
                        if should_include:
                            # 获取实际网页内容
                            try:
                                print(f"[DEBUG] 正在获取网页内容: {href}")
                                page_response = self._request(s, href, headers=headers)
                                if page_response and page_response.status_code == 200:
                                    # 解析网页内容
                                    page_soup = BeautifulSoup(page_response.content, 'html.parser')
                                    
                                    # 提取页面标题
                                    page_title = ""
                                    title_tag = page_soup.find('title')
                                    if title_tag and title_tag.get_text().strip():
                                        page_title = title_tag.get_text().strip()
                                        # 清理标题，移除网站名后缀
                                        if ' - ' in page_title:
                                            page_title = page_title.split(' - ')[0]
                                        if ' | ' in page_title:
                                            page_title = page_title.split(' | ')[0]
                                        if ' _ ' in page_title:
                                            page_title = page_title.split(' _ ')[0]
                                    
                                    # 如果没有页面标题，使用原始标题
                                    if not page_title:
                                        page_title = title
                                    
                                    # 提取页面描述或摘要
                                    description = ""
                                    meta_desc = page_soup.find('meta', attrs={'name': 'description'})
                                    if meta_desc and meta_desc.get('content'):
                                        description = meta_desc.get('content').strip()
                                    else:
                                        # 如果没有meta描述，尝试从页面内容中提取
                                        paragraphs = page_soup.find_all('p')
                                        for p in paragraphs[:3]:  # 只取前3段
                                            text = p.get_text().strip()
                                            if len(text) > 20:  # 只取有意义的段落
                                                description += text + " "
                                                if len(description) > 200:  # 限制长度
                                                    break
                                    
                                    # 如果还是没有描述，使用页面标题作为描述
                                    if not description:
                                        description = page_title
                                    
                                    results.append({
                                        "title": page_title,
                                        "url": href,
                                        "snippet": description[:300] + "..." if len(description) > 300 else description,
                                        "engine": "direct"
                                    })
                                    print(f"[DEBUG] 获取到网页内容: {page_title} - {href}")
                                    
                                    # 添加延迟，避免请求过快（减少延迟时间）
                                    import time
                                    time.sleep(random.uniform(0.1, 0.3))
                                else:
                                    # 如果无法获取内容，至少提供链接
                                    results.append({
                                        "title": title,
                                        "url": href,
                                        "snippet": f"直接访问: {site}",
                                        "engine": "direct"
                                    })
                                    print(f"[DEBUG] 无法获取内容，仅提供链接: {title} - {href}")
                            except Exception as e:
                                print(f"[DEBUG] 获取网页内容失败 {href}: {e}")
                                # 如果获取内容失败，至少提供链接
                                results.append({
                                    "title": title,
                                    "url": href,
                                    "snippet": f"直接访问: {site}",
                                    "engine": "direct"
                                })
                                print(f"[DEBUG] 获取内容失败，仅提供链接: {title} - {href}")
                    
                    max_results = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
                    if len(results) >= max_results:  # 限制每个搜索引擎的最大结果数
                        break  # 找到足够结果就停止尝试其他URL
                        
            except Exception as e:
                print(f"[DEBUG] 直接访问失败 {site}: {e}")
                continue
        
        return results

    def _get_sites_by_type(self, stype: str) -> List[Dict[str, Any]]:
        """根据搜索类型获取相关网站"""
        sites = []
        
        if stype in ['files', 'resources']:
            # 资源搜索
            for category, config in self.config.get("resource_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的资源网站: {domain}")
                            continue
                        
                        search_urls = config.get("search_urls", {}).get(domain, [])
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": search_urls
                        })
                        print(f"[DEBUG] 添加资源网站: {domain}, 搜索URL: {len(search_urls)} 个")
                        if len(search_urls) == 0:
                            print(f"[DEBUG] 警告: {domain} 没有配置搜索URL，将跳过搜索")
        
        elif stype == 'videos':
            # 视频搜索
            for category, config in self.config.get("video_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的视频网站: {domain}")
                            continue
                        
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": config.get("search_urls", {}).get(domain, [])
                        })
        
        elif stype == 'images':
            # 图片搜索
            for category, config in self.config.get("image_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的图片网站: {domain}")
                            continue
                        
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": config.get("search_urls", {}).get(domain, [])
                        })
        
        else:
            # 网页搜索
            for category, config in self.config.get("web_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的网页网站: {domain}")
                            continue
                        
                        search_urls = config.get("search_urls", {}).get(domain, [])
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": search_urls
                        })
                        print(f"[DEBUG] 添加网页网站: {domain}, 搜索URL: {len(search_urls)} 个")
        
        return sites

    def search_web(self, query: str, stype: str = 'web', page: int = 0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """主搜索函数
        
        Args:
            query: 搜索关键词
            stype: 搜索类型 ('web', 'images', 'videos', 'files', 'resources')
            page: 页码，从0开始
            limit: 结果数量限制
            
        Returns:
            搜索结果列表
        """
        if not query or len(query.strip()) < 1:
            return []
        
        results = []
        stype = stype.lower()
        
        try:
            # 对于图片搜索，使用配置的图片网站
            if stype == 'images':
                # 1. 直接访问配置的图片网站
                sites = self._get_sites_by_type('images')
                timeout = 8  # 固定超时时间
                start_time = time.time()
                max_results = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
                
                for site_info in sites:
                    if time.time() - start_time > timeout:
                        print(f"[DEBUG] 图片搜索超时，已搜索 {len(sites)} 个网站")
                        break
                    
                    # 如果已经有足够的结果，停止搜索
                    if len(results) >= max_results:
                        print(f"[DEBUG] 已获取足够图片结果({len(results)}条)，停止搜索")
                        break
                    
                    domain = site_info["domain"]
                    search_urls = site_info.get("search_urls", [])
                    
                    print(f"[DEBUG] 开始搜索图片网站: {domain}")
                    
                    if search_urls:
                        # 有直接搜索URL的图片网站
                        print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                        direct_results = self._search_direct_site(domain, query, search_urls)
                        # 图片搜索不进行过滤，直接保留所有结果
                        results.extend(direct_results)
                        print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条，无过滤")
                    else:
                        # 没有搜索URL的图片网站，使用默认的搜索URL模板
                        print(f"[DEBUG] {domain} 没有配置搜索URL，使用默认搜索URL模板")
                        # 为图片网站生成默认搜索URL模板
                        default_search_urls = [
                            f"https://{domain}/search?q={{query}}",           # 最常见的搜索参数
                            f"https://{domain}/search?query={{query}}",        # 第二常见的搜索参数
                            f"https://{domain}/search?keyword={{query}}",      # 关键词搜索
                            f"https://{domain}/search?word={{query}}",         # 单词搜索
                            f"https://{domain}/search?kw={{query}}",           # 缩写形式
                            f"https://{domain}/search?search={{query}}",       # 搜索参数
                            f"https://{domain}/search?q={{query}}&type=image", # 图片类型搜索
                            f"https://{domain}/search?query={{query}}&type=image" # 图片类型搜索
                        ]
                        
                        # 尝试使用默认搜索URL
                        direct_results = self._search_direct_site(domain, query, default_search_urls)
                        
                        # 图片搜索不进行过滤，直接保留所有结果
                        results.extend(direct_results)
                        print(f"[DEBUG] {domain} 默认搜索返回: {len(direct_results)} 条，无过滤")
                
                # 2. 如果图片网站结果不够，只使用Bing图片搜索补充
                if len(results) < max_results:  # 如果图片网站结果不足，补充Bing图片搜索
                    print(f"[DEBUG] 图片网站结果不足({len(results)}条)，补充Bing图片搜索")
                    try:
                        # 只使用Bing图片搜索
                        print(f"[DEBUG] 使用Bing图片搜索补充结果")
                        bing_results = self._search_bing(query, stype, page=0)
                        if bing_results:
                            # 图片搜索不进行名称过滤，直接保留所有结果
                            results.extend(bing_results)
                            print(f"[DEBUG] Bing图片搜索补充: {len(bing_results)} 条，无过滤")
                        
                    except Exception as e:
                        print(f"[DEBUG] Bing图片搜索失败: {e}")
            
            # 对于资源搜索，结合直接访问和Bing搜索
            elif stype in ['files', 'resources']:
                # 1. 直接访问配置的网站
                sites = self._get_sites_by_type(stype)
                timeout = 8  # 固定超时时间
                start_time = time.time()
                max_results = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
                
                for site_info in sites:
                    if time.time() - start_time > timeout:
                        print(f"[DEBUG] 搜索超时，已搜索 {len(sites)} 个网站")
                        break
                    
                    # 如果已经有足够的结果，停止搜索
                    if len(results) >= max_results:
                        print(f"[DEBUG] 已获取足够资源结果({len(results)}条)，停止搜索")
                        break
                    
                    domain = site_info["domain"]
                    search_urls = site_info.get("search_urls", [])
                    
                    print(f"[DEBUG] 开始搜索网站: {domain}")
                    
                    if search_urls:
                        # 有直接搜索URL的网站
                        print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                        direct_results = self._search_direct_site(domain, query, search_urls)
                        # 对直接访问结果进行相关性过滤
                        filtered_results = []
                        for result in direct_results:
                            if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query, stype):
                                filtered_results.append(result)
                            else:
                                print(f"[DEBUG] 过滤{domain}不相关内容: {result.get('title', '')} - {result.get('url', '')}")
                        
                        results.extend(filtered_results)
                        print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条，过滤后: {len(filtered_results)} 条")
                    else:
                        # 没有搜索URL的网站，使用默认的搜索URL模板
                        print(f"[DEBUG] {domain} 没有配置搜索URL，使用默认搜索URL模板")
                        # 默认搜索URL模板，按常见程度排序
                        default_search_urls = [
                            f"https://{domain}/search?q={{query}}",           # 最常见的搜索参数
                            f"https://{domain}/search?query={{query}}",        # 第二常见的搜索参数
                            f"https://{domain}/search?keyword={{query}}",      # 关键词搜索
                            f"https://{domain}/search?word={{query}}",         # 单词搜索
                            f"https://{domain}/search?kw={{query}}",           # 缩写形式
                            f"https://{domain}/search?search={{query}}",       # 搜索参数
                            f"https://{domain}/search?q={{query}}&type=all",   # 带类型的搜索
                            f"https://{domain}/search?query={{query}}&type=all" # 带类型的搜索
                        ]
                        
                        # 尝试使用默认搜索URL
                        direct_results = self._search_direct_site(domain, query, default_search_urls)
                        
                        # 对直接访问结果进行相关性过滤
                        filtered_results = []
                        for result in direct_results:
                            if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query, stype):
                                filtered_results.append(result)
                            else:
                                print(f"[DEBUG] 过滤{domain}不相关内容: {result.get('title', '')} - {result.get('url', '')}")
                        
                        results.extend(filtered_results)
                        print(f"[DEBUG] {domain} 默认搜索返回: {len(direct_results)} 条，过滤后: {len(filtered_results)} 条")
                
            elif stype == 'videos':
                # 视频搜索使用配置的视频网站
                sites = self._get_sites_by_type('videos')
                timeout = 8  # 固定超时时间
                start_time = time.time()
                max_results = self.config.get("settings", {}).get("engine_max_results", 35)  # 从配置获取引擎最大结果数
                
                for site_info in sites:
                    if time.time() - start_time > timeout:
                        print(f"[DEBUG] 视频搜索超时，已搜索 {len(sites)} 个网站")
                        break
                    
                    # 如果已经有足够的结果，停止搜索
                    if len(results) >= max_results:
                        print(f"[DEBUG] 已获取足够视频结果({len(results)}条)，停止搜索")
                        break
                    
                    domain = site_info["domain"]
                    search_urls = site_info.get("search_urls", [])
                    
                    print(f"[DEBUG] 开始搜索视频网站: {domain}")
                    
                    if search_urls:
                        # 有直接搜索URL的视频网站
                        print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                        direct_results = self._search_direct_site(domain, query, search_urls)
                        # 视频搜索不进行过滤，直接保留所有结果
                        results.extend(direct_results)
                        print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条，无过滤")
                    else:
                        # 没有搜索URL的视频网站，使用默认的搜索URL模板
                        print(f"[DEBUG] {domain} 没有配置搜索URL，使用默认搜索URL模板")
                        # 为视频网站生成默认搜索URL模板
                        default_search_urls = [
                            f"https://{domain}/search?q={{query}}",           # 最常见的搜索参数
                            f"https://{domain}/search?query={{query}}",        # 第二常见的搜索参数
                            f"https://{domain}/search?keyword={{query}}",      # 关键词搜索
                            f"https://{domain}/search?word={{query}}",         # 单词搜索
                            f"https://{domain}/search?kw={{query}}",           # 缩写形式
                            f"https://{domain}/search?search={{query}}",       # 搜索参数
                            f"https://{domain}/search?q={{query}}&type=video", # 视频类型搜索
                            f"https://{domain}/search?query={{query}}&type=video" # 视频类型搜索
                        ]
                        
                        # 尝试使用默认搜索URL
                        direct_results = self._search_direct_site(domain, query, default_search_urls)
                        
                        # 视频搜索不进行过滤，直接保留所有结果
                        results.extend(direct_results)
                        print(f"[DEBUG] {domain} 默认搜索返回: {len(direct_results)} 条，无过滤")
                
                # 2. 如果视频网站结果不够，使用Bing视频搜索补充
                if len(results) < max_results:  # 如果视频网站结果不足，补充Bing视频搜索
                    print(f"[DEBUG] 视频网站结果不足({len(results)}条)，补充Bing视频搜索")
                    try:
                        # 只使用Bing视频搜索
                        print(f"[DEBUG] 使用Bing视频搜索补充结果")
                        bing_results = self._search_bing(query, stype, page=0)
                        if bing_results:
                            # 视频搜索不进行名称过滤，直接保留所有结果
                            results.extend(bing_results)
                            print(f"[DEBUG] Bing视频搜索补充: {len(bing_results)} 条，无过滤")
                        
                    except Exception as e:
                        print(f"[DEBUG] Bing视频搜索失败: {e}")
            
            else:
                # 其他搜索类型使用国内搜索引擎，一次性加载更多结果
                # 1. 直接访问配置的搜索引擎网站
                sites = self._get_sites_by_type('web')
                timeout = 8  # 固定超时时间
                start_time = time.time()
                
                for site_info in sites:
                    if time.time() - start_time > timeout:
                        print(f"[DEBUG] 搜索超时，已搜索 {len(sites)} 个网站")
                        break
                    
                    # 如果已经有足够的结果，停止搜索
                    if len(results) >= 140:  # 最多140条结果（4个搜索引擎 × 35条）
                        print(f"[DEBUG] 已获取足够结果({len(results)}条)，停止搜索")
                        break
                    
                    domain = site_info["domain"]
                    search_urls = site_info.get("search_urls", [])
                    
                    print(f"[DEBUG] 开始搜索搜索引擎: {domain}")
                    
                    if search_urls:
                        # 有直接搜索URL的搜索引擎
                        print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                        
                        # 为搜索引擎使用专门的解析方法
                        if domain in ['bing.com', 'www.bing.com']:
                            direct_results = self._search_bing(query, stype, page=0)
                        elif domain in ['baidu.com', 'www.baidu.com']:
                            direct_results = self._search_baidu(query, stype, page=0)
                        elif domain in ['sogou.com', 'www.sogou.com']:
                            direct_results = self._search_sogou(query, stype, page=0)
                        elif domain in ['so.com', 'www.so.com']:
                            direct_results = self._search_so(query, stype, page=0)
                        else:
                            direct_results = self._search_direct_site(domain, query, search_urls)
                        # 对直接访问结果进行相关性过滤
                        filtered_results = []
                        for result in direct_results:
                            if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query, stype):
                                filtered_results.append(result)
                            else:
                                print(f"[DEBUG] 过滤{domain}不相关内容: {result.get('title', '')} - {result.get('url', '')}")
                        
                        results.extend(filtered_results)
                        print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条，过滤后: {len(filtered_results)} 条")
                    else:
                        print(f"[DEBUG] {domain} 没有配置搜索URL，跳过")
                
                # 2. 如果国内搜索引擎没有结果，使用Bing作为备用
                if not results:
                    print(f"[DEBUG] 国内搜索引擎无结果，使用Bing作为备用")
                    bing_results = self._search_bing(query, stype, page=0)
                    
                    # 对Bing结果进行相关性过滤（包括图片搜索）
                    filtered_bing_results = []
                    for result in bing_results:
                        if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query, stype):
                            filtered_bing_results.append(result)
                        else:
                            print(f"[DEBUG] 过滤Bing不相关内容: {result.get('title', '')} - {result.get('url', '')}")
                    
                    results.extend(filtered_bing_results)
                    print(f"[DEBUG] Bing备用搜索: {len(bing_results)} 条，过滤后: {len(filtered_bing_results)} 条")
                
                # 3. 网页搜索一次性加载更多结果，避免触底重复搜索
                if stype == 'web' and results:
                    print(f"[DEBUG] 网页搜索一次性加载更多结果，当前: {len(results)} 条")
                    # 尝试从其他搜索引擎获取更多结果
                    additional_results = []
                    
                    # 如果结果较少，尝试从其他搜索引擎获取更多
                    if len(results) < 50:
                        print(f"[DEBUG] 结果较少，尝试从其他搜索引擎获取更多结果")
                        # 这里可以添加更多搜索引擎的搜索逻辑
                        # 暂时使用Bing多页搜索作为补充
                        try:
                            bing_more_results = self._search_bing_multiple_pages(query, stype, max_pages=2)
                            if bing_more_results:
                                # 过滤Bing结果
                                filtered_bing_more = []
                                for result in bing_more_results:
                                    if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query, stype):
                                        filtered_bing_more.append(result)
                                
                                additional_results.extend(filtered_bing_more)
                                print(f"[DEBUG] Bing多页搜索补充: {len(bing_more_results)} 条，过滤后: {len(filtered_bing_more)} 条")
                        except Exception as e:
                            print(f"[DEBUG] Bing多页搜索失败: {e}")
                    
                    # 合并所有结果
                    results.extend(additional_results)
                    print(f"[DEBUG] 网页搜索总计: {len(results)} 条结果")
            
            # 3. 去重和排序（智能去重，处理重定向链接）
            seen = set()
            dedup = []
            duplicate_count = 0
            
            def get_dedup_key(item):
                """获取去重键，处理重定向链接"""
                if stype == 'images':
                    # 图片搜索使用缩略图链接作为去重键
                    snippet = item.get("snippet", "")
                    if not snippet or snippet.startswith('javascript:') or snippet.startswith('#'):
                        return None
                    return snippet
                
                url = item.get("url", "")
                title = item.get("title", "")
                    
                # 过滤掉明显无用的URL
                if url and any(skip in url for skip in [
                    'javascript:', '###more', 'e.so.com/adx/clk',
                    'e.so.com/search/eclk', 'e.so.com/search/mid',
                    'info.so.com/feedback.html'
                ]):
                    return None
                
                # 处理重定向链接的去重
                if 'so.com/link?m=' in url:
                    # 360搜索重定向链接，使用标题作为去重依据
                    return f"redirect:{title}"
                elif 'baidu.com/link?url=' in url:
                    # 百度重定向链接，使用标题作为去重依据
                    return f"redirect:{title}"
                elif 'sogou.com/link?url=' in url:
                    # 搜狗重定向链接，使用标题作为去重依据
                    return f"redirect:{title}"
                else:
                    # 直接链接，使用URL作为去重依据
                    return url
            
            for item in results:
                dedup_key = get_dedup_key(item)
                
                if dedup_key is None:
                        duplicate_count += 1
                        continue
                
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    dedup.append(item)
                else:
                    duplicate_count += 1
                    if stype == 'images':
                        print(f"[DEBUG] 跳过重复图片 ({duplicate_count}): {item.get('snippet', '')}")
                    else:
                        print(f"[DEBUG] 跳过重复URL ({duplicate_count}): {item.get('url', '')} (标题: {item.get('title', '')})")
            
            print(f"[DEBUG] 去重后: {len(dedup)} 条结果，跳过了 {duplicate_count} 个重复项")
            print(f"[DEBUG] 原始结果: {len(results)} 条，去重后: {len(dedup)} 条，重复: {duplicate_count} 条")
            
            # 按相关性排序，概念性、官网类优先级更高
            def get_priority_score(item):
                title = item.get('title', '').lower()
                url = item.get('url', '').lower()
                query_lower = query.lower()
                
                score = 0
                
                # 基础匹配分数
                score += title.count(query_lower) * 10
                
                # 资源类搜索的匹配度评分

                
                    # 计算字符匹配度
                def normalize_text(text):
                    import re
                    text = re.sub(r'[＊*·•·]', '*', text)
                    text = re.sub(r'[：:]', ':', text)
                    text = re.sub(r'[（）()]', '', text)
                    text = re.sub(r'[，,。.]', '', text)
                    return text.strip()
                
                normalized_query = normalize_text(query_lower)
                normalized_title = normalize_text(title)
                
                # 完整匹配最高分
                if normalized_query in normalized_title:
                    score += 1000
                else:
                    # 部分匹配按匹配度给分
                    query_chars = set(normalized_query.replace(' ', ''))
                    title_chars = set(normalized_title.replace(' ', ''))
                    if len(query_chars) > 0:
                        match_ratio = len(query_chars & title_chars) / len(query_chars)
                        score += int(match_ratio * 500)  # 匹配度越高分数越高
                
                # 概念性内容优先级
                concept_keywords = ['概念', '定义', '原理', '介绍', '说明', '解释', '是什么', '什么是', '概念解释', '基本概念']
                for keyword in concept_keywords:
                    if keyword in title:
                        score += 50
                        break
                
                # 官网优先级
                official_domains = ['.gov.cn', '.edu.cn', '.org.cn', 'wikipedia.org', 'baike.baidu.com', 'zh.wikipedia.org']
                for domain in official_domains:
                    if domain in url:
                        score += 100
                        break
                
                # 百科类优先级
                wiki_keywords = ['百科', 'wiki', 'baike', '词典', '字典', '术语']
                for keyword in wiki_keywords:
                    if keyword in title or keyword in url:
                        score += 80
                        break
                
                # 学术类优先级
                academic_keywords = ['论文', '研究', '学术', '期刊', '学报', '理论', '分析', '报告']
                for keyword in academic_keywords:
                    if keyword in title:
                        score += 60
                        break
                
                # 标题长度权重（较短的标题通常更重要）
                score += (100 - len(title)) * 0.1
                
                return score
            
            dedup.sort(key=get_priority_score, reverse=True)
            
            # 不限制结果数量，返回所有结果
            
            return dedup
            
        except Exception as e:
            print(f"[DEBUG] 搜索异常: {e}")
            traceback.print_exc()
            return []

    # 网站管理功能
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置
        
        Returns:
            完整的配置字典
        """
        return self.config

    def _normalize_domain(self, domain: str) -> str:
        """规范化域名，智能处理各种域名变体
        
        Args:
            domain: 原始域名
            
        Returns:
            str: 规范化后的域名
        """
        domain = domain.lower().strip()
        
        # 移除端口号
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # 移除路径
        if '/' in domain:
            domain = domain.split('/')[0]
        
        # 移除www前缀
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # 智能处理国家/地区域名
        # 如果域名包含国家代码前缀（如cn.、us.、uk.等），尝试提取主域名
        parts = domain.split('.')
        if len(parts) >= 3:
            # 检查是否是常见的国家代码
            country_codes = ['cn', 'us', 'uk', 'jp', 'kr', 'de', 'fr', 'it', 'es', 'ru', 'ca', 'au', 'br', 'in', 'mx']
            if parts[0] in country_codes:
                # 移除国家代码，保留主域名
                main_domain = '.'.join(parts[1:])
                # 只对知名网站进行规范化，避免误判
                known_domains = [
                    'bing.com', 'google.com', 'yahoo.com', 'baidu.com', 'sogou.com', 'so.com',
                    'github.com', 'stackoverflow.com', 'wikipedia.org', 'youtube.com',
                    'amazon.com', 'microsoft.com', 'apple.com', 'facebook.com', 'twitter.com',
                    'instagram.com', 'linkedin.com', 'reddit.com', 'quora.com', 'medium.com'
                ]
                if main_domain in known_domains:
                    domain = main_domain
        
        return domain

    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None) -> dict:
        """添加网站
        
        Args:
            domain: 网站域名
            site_type: 网站类型
            search_urls: 搜索URL列表
            
        Returns:
            dict: 包含操作结果的字典
        """
        # 规范化域名
        normalized_domain = self._normalize_domain(domain)
        
        if site_type not in self.config:
            self.config[site_type] = {}
        
        # 使用统一的custom分类
        category = "custom"
        if category not in self.config[site_type]:
            self.config[site_type][category] = {
                "domains": [],
                "enabled": True,
                "search_urls": {}
            }
        
        # 检查规范化后的域名是否已存在
        if normalized_domain in self.config[site_type][category]["domains"]:
            # 域名已存在，检查URL是否不同
            # 查找现有的URL配置（可能使用不同的键名）
            existing_urls = []
            for key, urls in self.config[site_type][category]["search_urls"].items():
                if self._normalize_domain(key) == normalized_domain:
                    existing_urls = urls
                    break
        
            if search_urls:
                # 比较URL列表
                if set(existing_urls) == set(search_urls):
                    return {
                        'success': False,
                        'message': f'域名 {normalized_domain} 已存在，且URL完全相同',
                        'action': 'duplicate'
                    }
                else:
                    # URL不同，更新URL（使用找到的原始键）
                    if "search_urls" not in self.config[site_type][category]:
                        self.config[site_type][category]["search_urls"] = {}
                    # 找到原始键并更新
                    for key, urls in self.config[site_type][category]["search_urls"].items():
                        if self._normalize_domain(key) == normalized_domain:
                            self.config[site_type][category]["search_urls"][key] = search_urls
                            break
                    self._save_config()
                    return {
                        'success': True,
                        'message': f'域名 {normalized_domain} 已存在，已更新URL',
                        'action': 'updated'
                    }
            else:
                return {
                    'success': False,
                    'message': f'域名 {normalized_domain} 已存在，且没有提供新的URL',
                    'action': 'duplicate'
                }
        else:
            # 域名不存在，直接添加
            if search_urls:
                if "search_urls" not in self.config[site_type][category]:
                    self.config[site_type][category]["search_urls"] = {}
                self.config[site_type][category]["search_urls"][normalized_domain] = search_urls
            
            self.config[site_type][category]["domains"].append(normalized_domain)
        
        self._save_config()
        return {
            'success': True,
            'message': f'域名 {normalized_domain} 添加成功',
                'action': 'added'
            }

    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站
        
        Args:
            domain: 网站域名
            site_type: 网站类型
        """
        category = "custom"
        if site_type in self.config and category in self.config[site_type]:
            if domain in self.config[site_type][category]["domains"]:
                self.config[site_type][category]["domains"].remove(domain)
                # 同时删除domain_status中的状态记录
                if "domain_status" in self.config[site_type][category] and domain in self.config[site_type][category]["domain_status"]:
                    del self.config[site_type][category]["domain_status"][domain]
                # 同时删除search_urls中的搜索URL配置
                if "search_urls" in self.config[site_type][category] and domain in self.config[site_type][category]["search_urls"]:
                    del self.config[site_type][category]["search_urls"][domain]
                self._save_config()

    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单
        
        Args:
            domain: 要添加的域名
        """
        if "blacklist" not in self.config:
            self.config["blacklist"] = {"domains": [], "enabled": True}
        
        if domain not in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].append(domain)
            self._save_config()

    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除
        
        Args:
            domain: 要移除的域名
        """
        if "blacklist" in self.config and domain in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].remove(domain)
            self._save_config()

    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态
        
        Args:
            domain: 网站域名
            site_type: 网站类型
            enabled: 是否启用
        """
        category = "custom"
        if site_type in self.config and category in self.config[site_type]:
            # 初始化域名状态字典
            if "domain_status" not in self.config[site_type][category]:
                self.config[site_type][category]["domain_status"] = {}
            
            # 设置特定域名的状态
            self.config[site_type][category]["domain_status"][domain] = enabled
            self._save_config()


    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        try:
            print(f"[DEBUG] 获取网站搜索URL: site_type={site_type}, domain={domain}")
            site_config = self.config.get(f"{site_type}_sites", {}).get("custom", {})
            search_urls = site_config.get("search_urls", {})
            urls = search_urls.get(domain, [])
            print(f"[DEBUG] 找到的URL: {urls}")
            return urls
        except Exception as e:
            print(f"[ERROR] 获取网站搜索URL失败: {e}")
            return []

    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        try:
            # 确保配置结构存在
            if f"{site_type}_sites" not in self.config:
                self.config[f"{site_type}_sites"] = {}
            if "custom" not in self.config[f"{site_type}_sites"]:
                self.config[f"{site_type}_sites"]["custom"] = {}
            if "search_urls" not in self.config[f"{site_type}_sites"]["custom"]:
                self.config[f"{site_type}_sites"]["custom"]["search_urls"] = {}
            
            # 更新搜索URL
            self.config[f"{site_type}_sites"]["custom"]["search_urls"][domain] = search_urls
            
            # 保存配置
            self._save_config()
            print(f"[INFO] 已更新 {domain} 的搜索URL配置")
        except Exception as e:
            print(f"[ERROR] 更新网站搜索URL失败: {e}")
            raise e