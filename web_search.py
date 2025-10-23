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
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from bs4 import BeautifulSoup


# 尝试导入Selenium相关模块
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[DEBUG] Selenium未安装，将使用requests进行搜索")

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BaseSearch:
    """搜索基类，包含通用功能"""
    
    # 常量定义
    KNOWN_SITES_BLACKLIST = set()
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ]
    
    # 代理服务器列表
    PROXY_LIST = [

    ]
    
    # 无效链接模式
    INVALID_LINK_PATTERNS = [
        '#', 'javascript:void(0);', 'javascript:void(0)', 'javascript:',
        'mailto:', 'tel:', 'data:', 'about:', 'chrome:', 'file:'
    ]
    
    def __init__(self, config_file: str = "sites_config.json"):
        """初始化搜索实例
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
        self.current_proxy_index = 0  # 当前代理索引
        
        # 基础配置
        self.request_timeout = self.config.get("settings", {}).get("site_timeout", 10)  # 从配置文件读取超时时间
        
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
        
        # 返回默认配置 - 使用main.py中的DEFAULT_CONFIG
        try:
            from main import DEFAULT_CONFIG
            return DEFAULT_CONFIG.copy()
        except ImportError:
            # 如果无法导入，返回最小配置
            return {
                "search_engines": {},
                "web_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "resource_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "video_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "image_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "blacklist": {"domains": [], "enabled": True},
                "settings": {"engine_max_results": 35, "site_timeout": 10}
            }

    def _save_config(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG] 保存配置失败: {e}")
            raise e  # 重新抛出异常，让调用方知道保存失败

    def _load_proxy_config(self) -> Dict[str, Any]:
        """加载代理配置
        
        Returns:
            代理配置字典
        """
        try:
            if os.path.exists('proxy_config.json'):
                with open('proxy_config.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[DEBUG] 加载代理配置失败: {e}")
        
        return {
            "proxy_settings": {
                "enabled": False,
                "proxies": [],
                "rotation_strategy": "round_robin",
                "test_url": "http://httpbin.org/ip"
            }
        }

    def _get_next_proxy(self) -> Optional[str]:
        """获取下一个代理服务器
        
        Returns:
            代理URL或None
        """
        proxy_config = self._load_proxy_config()
        if not proxy_config.get("proxy_settings", {}).get("enabled", False):
            return None
        
        proxies = proxy_config.get("proxy_settings", {}).get("proxies", [])
        if not proxies:
            return None
        
        # 过滤启用的代理
        enabled_proxies = [p for p in proxies if p.get("enabled", False)]
        if not enabled_proxies:
            return None
        
        proxy = enabled_proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(enabled_proxies)
        
        # 构建代理URL
        proxy_url = proxy.get("url", "")
        if proxy.get("username") and proxy.get("password"):
            # 如果有认证信息，添加到URL中
            if "://" in proxy_url:
                protocol, rest = proxy_url.split("://", 1)
                proxy_url = f"{protocol}://{proxy.get('username')}:{proxy.get('password')}@{rest}"
        
        return proxy_url

    def _test_proxy(self, proxy_url: str) -> bool:
        """测试代理是否可用
        
        Args:
            proxy_url: 代理URL
            
        Returns:
            是否可用
        """
        try:
            proxy_config = self._load_proxy_config()
            test_url = proxy_config.get("proxy_settings", {}).get("test_url", "http://httpbin.org/ip")
            
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            response = requests.get(test_url, proxies=proxies, timeout=10)
            if response.status_code == 200:
                print(f"[DEBUG] 代理测试成功: {proxy_url}")
                return True
            else:
                print(f"[DEBUG] 代理测试失败: {proxy_url}, 状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"[DEBUG] 代理测试异常: {proxy_url}, 错误: {e}")
            return False

    def _session(self) -> requests.Session:
        """创建请求会话
        
        Returns:
            配置好的requests会话对象
        """
        s = requests.Session()
        
        # 随机选择User-Agent
        user_agent = random.choice(self.USER_AGENTS)
        s.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        
        # 设置代理（如果有的话）
        proxy = self._get_next_proxy()
        if proxy:
            # 测试代理可用性
            if self._test_proxy(proxy):
                s.proxies = {
                    'http': proxy,
                    'https': proxy
                }
                print(f"[DEBUG] 使用代理: {proxy}")
            else:
                print(f"[DEBUG] 代理不可用，跳过: {proxy}")
        
        s.verify = False
        return s

    def _create_selenium_driver(self) -> Optional[webdriver.Chrome]:
        """创建Selenium WebDriver
        
        Returns:
            Chrome WebDriver实例或None
        """
        if not SELENIUM_AVAILABLE:
            return None
            
        try:
            options = Options()
            # 基础配置
            options.add_argument('--headless')  # 无头模式
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            
            # 反检测配置
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # 随机User-Agent
            user_agent = random.choice(self.USER_AGENTS)
            options.add_argument(f'--user-agent={user_agent}')
            
            # 禁用图片和CSS加载以提高速度
            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.managed_default_content_settings.stylesheets": 2,
                "profile.managed_default_content_settings.plugins": 2,
                "profile.managed_default_content_settings.popups": 2,
                "profile.managed_default_content_settings.geolocation": 2,
                "profile.managed_default_content_settings.media_stream": 2,
            }
            options.add_experimental_option("prefs", prefs)
            
            # 禁用各种功能以减少检测
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')
            options.add_argument('--disable-javascript')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=VizDisplayCompositor')
            
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)
            
            # 执行反检测脚本
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent,
                "acceptLanguage": "zh-CN,zh;q=0.9,en;q=0.8",
                "platform": "Win32"
            })
            
            return driver
        except Exception as e:
            print(f"[DEBUG] 创建Selenium WebDriver失败: {e}")
            return None

    def _request_with_selenium(self, url: str) -> Optional[str]:
        """使用Selenium请求页面
        
        Args:
            url: 请求URL
            
        Returns:
            页面HTML内容或None
        """
        driver = self._create_selenium_driver()
        if not driver:
            return None
            
        try:
            print(f"[DEBUG] Selenium请求URL: {url}")
            driver.get(url)
            
            # 等待页面加载完成
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            time.sleep(random.uniform(0.5, 1))
            
            # 获取页面源码
            html = driver.page_source
            print(f"[DEBUG] Selenium响应: 内容长度 {len(html)}")
            return html
            
        except TimeoutException:
            print(f"[DEBUG] Selenium请求超时: {url}")
            return None
        except Exception as e:
            print(f"[DEBUG] Selenium请求失败: {e}")
            return None
        finally:
            try:
                driver.quit()
            except:
                pass

    def _request(self, session: requests.Session, url: str, 
                 params: Optional[Dict[str, Any]] = None, 
                 headers: Optional[Dict[str, str]] = None,
                 use_selenium: bool = False) -> Optional[requests.Response]:
        """发送HTTP请求
        
        Args:
            session: requests会话对象
            url: 请求URL
            params: 请求参数
            headers: 请求头
            use_selenium: 是否使用Selenium
            
        Returns:
            响应对象或None
        """
        # 如果使用Selenium，先尝试Selenium
        if use_selenium and SELENIUM_AVAILABLE:
            html = self._request_with_selenium(url)
            if html:
                # 创建一个模拟的Response对象
                class MockResponse:
                    def __init__(self, content):
                        self.content = content.encode('utf-8')
                        self.status_code = 200
                        self.headers = {}
                
                return MockResponse(html)
        
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

    def _unwrap_bing_url(self, bing_url: str) -> str:
        """从Bing跳转链接中提取真实URL（参考Go代码实现）
        
        Args:
            bing_url: Bing跳转链接
            
        Returns:
            真实URL或原URL
        """
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            import base64
            
            u = urlparse(bing_url)
            if 'bing.com' not in (u.netloc or ''):
                return bing_url
            
            # 获取u参数
            enc = u.query and parse_qs(u.query).get('u', [None])[0]
            if not enc:
                return bing_url
            
            # 去掉前缀（如果存在）
            if enc.startswith('a1'):
                enc = enc[2:]
            
            # base64解码
            try:
                decoded = base64.urlsafe_b64decode(enc + '==')  # 添加padding
                real_url = decoded.decode('utf-8')
                if real_url.startswith('http'):
                    print(f"[DEBUG] Bing URL解包: {bing_url} -> {real_url}")
                    return real_url
            except Exception as e:
                print(f"[DEBUG] Bing URL解码失败: {e}")
                pass
                
        except Exception as e:
            print(f"[DEBUG] Bing URL解包异常: {e}")
            
        return bing_url

    def _normalize_url(self, href: Optional[str]) -> Optional[str]:
        """标准化URL"""
        if not href:
            return None
        
        # 过滤无效链接
        if self._is_invalid_link(href):
            return None
        
        # 处理Bing重定向 - 使用新的解包方法
        if 'bing.com' in href:
            href = self._unwrap_bing_url(href)
        
        # 处理其他搜索引擎的重定向
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

    def _smart_deduplication(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """智能去重机制（基于URL和标题相似度）
        
        Args:
            results: 搜索结果列表
            
        Returns:
            去重后的结果列表
        """
        if not results:
            return []
        
        dedup = []
        seen_urls = set()
        seen_titles = set()
        
        for item in results:
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
            
            if not url:
                continue
            
            # 1. URL完全匹配去重
            if url in seen_urls:
                print(f"[DEBUG] 过滤重复URL: {url}")
                continue
            
            # 2. 标题相似度去重
            title_normalized = self._normalize_text(title.lower())
            if title_normalized in seen_titles:
                print(f"[DEBUG] 过滤重复标题: {title}")
                continue
            
            # 3. 检查URL相似度（处理参数差异）
            url_similar = False
            for seen_url in seen_urls:
                if self._are_urls_similar(url, seen_url):
                    print(f"[DEBUG] 过滤相似URL: {url} (相似于: {seen_url})")
                    url_similar = True
                    break
            
            if url_similar:
                continue
            
            # 4. 检查标题相似度（处理符号变体）
            title_similar = False
            for seen_title in seen_titles:
                if self._are_titles_similar(title_normalized, seen_title):
                    print(f"[DEBUG] 过滤相似标题: {title} (相似于: {seen_title})")
                    title_similar = True
                    break
            
            if title_similar:
                continue
            
            # 通过所有检查，添加到结果中
            seen_urls.add(url)
            seen_titles.add(title_normalized)
            dedup.append(item)
        
        print(f"[DEBUG] 智能去重: {len(results)} -> {len(dedup)} 条结果")
        return dedup

    def _are_urls_similar(self, url1: str, url2: str) -> bool:
        """检查两个URL是否相似
        
        Args:
            url1: 第一个URL
            url2: 第二个URL
            
        Returns:
            是否相似
        """
        try:
            from urllib.parse import urlparse, parse_qs
            
            # 解析URL
            p1 = urlparse(url1)
            p2 = urlparse(url2)
            
            # 比较域名和路径
            if p1.netloc != p2.netloc or p1.path != p2.path:
                return False
            
            # 比较查询参数（忽略某些参数）
            q1 = parse_qs(p1.query)
            q2 = parse_qs(p2.query)
            
            # 忽略的参数
            ignore_params = {'utm_source', 'utm_medium', 'utm_campaign', 'ref', 'source', 'from'}
            
            # 移除忽略的参数
            for param in ignore_params:
                q1.pop(param, None)
                q2.pop(param, None)
            
            # 比较剩余参数
            return q1 == q2
            
        except Exception:
            return False

    def _are_titles_similar(self, title1: str, title2: str) -> bool:
        """检查两个标题是否相似
        
        Args:
            title1: 第一个标题
            title2: 第二个标题
            
        Returns:
            是否相似
        """
        if not title1 or not title2:
            return False
        
        # 计算字符相似度
        def similarity(s1: str, s2: str) -> float:
            if not s1 or not s2:
                return 0.0
            
            # 使用集合计算Jaccard相似度
            set1 = set(s1)
            set2 = set(s2)
            
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            
            return intersection / union if union > 0 else 0.0
        
        sim = similarity(title1, title2)
        return sim > 0.8  # 相似度阈值

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

    def _filename_from_url(self, url: str) -> str:
        """从URL提取文件名"""
        try:
            m = re.search(r"/([^/?#]+)(?:\?|#|$)", url)
            if m:
                return m.group(1)
        except Exception:
            pass
        return url

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


class WebSearch(BaseSearch):
    """网页搜索类"""
    
    BING_INTERNAL_PATHS = (
        "/search", "/images/", "/videos/", "/academic/", "/maps/", "/travel/", "/dict/"
    )
    
    def __init__(self, config_file: str = "sites_config.json"):
        super().__init__(config_file)
        self.search_type = "web"
    
    def _is_bing_internal(self, href: str) -> bool:
        """检查是否是Bing内部链接"""
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

    def _is_relevant_content(self, title: str, url: str, query: str) -> bool:
        """检查内容是否与网页搜索相关 - 使用分数计算"""
        if not title or not query:
            return False
        
        # 使用分数计算来判断相关性
        score = self._calculate_relevance_score(title, url, query)
        return score > 0

    def _calculate_relevance_score(self, title: str, url: str, query: str) -> int:
        """计算相关性分数（不过滤任何结果）"""
        if not title or not query:
            return 1  # 给基础分数，不过滤
        
        title_lower = title.lower()
        query_lower = query.lower()
        
        # 标准化文本
        normalized_query = self._normalize_text(query_lower)
        normalized_title = self._normalize_text(title_lower)
        
        # 检查匹配数量
        query_chars = set(normalized_query.replace(' ', ''))
        title_chars = set(normalized_title.replace(' ', ''))
        match_count = len(query_chars & title_chars)
        
        # 基础分数，确保所有结果都有分数
        score = 1
        
        # 如果有匹配字符，给额外分数
        if match_count > 0:
            score += match_count * 50  # 每个匹配字符给50分
        
        # 完整匹配给高分
        if normalized_query in normalized_title:
            score += 1000
        
        # 概念性、官网类内容加分
        official_keywords = [
            '官网', '官方网站', 'official', 'homepage', 'home page',
            '概念', '介绍', 'introduction', 'about', '什么是', 'what is',
            '定义', 'definition', '百科', 'wiki', '萌娘百科', '萌娘百科'
        ]

        for keyword in official_keywords:
            if keyword in title_lower or keyword in url.lower():
                score += 20  # 概念性、官网类内容额外加分
                break
        
        return score

    def _parse_search_results(self, soup: BeautifulSoup, query: str, engine: str = "bing") -> List[Dict[str, Any]]:
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
                            # 计算相关性分数
                            score = self._calculate_relevance_score(title, href, query)
                            results.append({
                                "title": title,
                                "url": href,
                                "snippet": "",
                                "engine": engine,
                                "score": score
                            })
                            print(f"[DEBUG] 找到{engine}结果: {title} - {href} (分数: {score})")
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
                    # 计算相关性分数
                    score = self._calculate_relevance_score(title, href, query)
                    results.append({
                        "title": title,
                        "url": href,
                        "snippet": "",
                        "engine": engine,
                        "score": score
                    })
                    print(f"[DEBUG] 找到{engine}链接结果: {title} - {href} (分数: {score})")
        
        return results

    def _search_bing(self, query: str, page: int = 0, use_selenium: bool = False) -> List[Dict[str, Any]]:
        """使用Bing搜索"""
        s = self._session()
        count = self.config.get("settings", {}).get("engine_max_results", 35)
        first = max(0, int(page)) * count + 1
        
        url = f"https://www.bing.com/search?q={query}&setlang=zh-cn&count={count}&first={first}"
        
        r = self._request(s, url, use_selenium=use_selenium)
        if not r:
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_search_results(soup, query, "bing")

    def _get_sites_by_type(self, stype: str) -> List[Dict[str, Any]]:
        """获取指定类型的网站列表"""
        sites = []
        
        if stype == 'web':
            # 网页搜索
            for category, config in self.config.get("web_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的网页网站: {domain}")
                            continue
                        
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": config.get("search_urls", {}).get(domain, [])
                        })
        
        return sites

    def _search_web_site(self, domain: str, query: str, search_urls: List[str], timeout: int = 8) -> List[Dict[str, Any]]:
        """直接访问网页网站搜索"""
        results = []
        s = self._session()
        start_time = time.time()
        
        for search_url in search_urls:
            # 检查单个网站的超时
            if time.time() - start_time > timeout:
                print(f"[DEBUG] {domain} 搜索超时({timeout}秒)，已搜索 {len(results)} 条结果")
                break
                
            try:
                # 替换查询参数
                url = search_url.replace('{query}', query)
                print(f"[DEBUG] 直接访问网页网站: {url}")
                
                r = self._request(s, url)
                if not r:
                    continue
                
                soup = BeautifulSoup(r.content, 'html.parser')
                site_results = self._parse_web_site_results(soup, query, domain)
                results.extend(site_results)
                print(f"[DEBUG] {domain} 直接访问返回: {len(site_results)} 条结果")
                
            except Exception as e:
                print(f"[DEBUG] {domain} 直接访问失败: {e}")
                continue
        
        return results

    def _parse_web_site_results(self, soup: BeautifulSoup, query: str, domain: str) -> List[Dict[str, Any]]:
        """解析网页网站搜索结果页面"""
        results = []
        
        # 通用解析策略：查找所有链接
        items = soup.select('a[href]')
        for item in items:
            href = item.get('href', '')
            title = item.get_text(strip=True)
            
            if not href or not title:
                continue
            
            # 处理相对URL
            if href.startswith('/'):
                href = f"https://{domain}{href}"
            elif not href.startswith('http'):
                continue
            
            # 过滤掉无效链接
            if self._is_invalid_link(href):
                continue
            
            # 过滤掉与查询无关的链接
            if not self._is_relevant_content(title, href, query):
                continue
            
            results.append({
                "title": title,
                "url": href,
                "snippet": title,
                "source": domain
            })
        
        return results

    def _search_baidu(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用百度搜索"""
        s = self._session()
        pn = max(0, int(page)) * 10
        
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
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_search_results(soup, query, "baidu")

    def _search_sogou(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用搜狗搜索"""
        s = self._session()
        p = max(0, int(page)) + 1
        
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
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_search_results(soup, query, "sogou")


    def _search_multiple_pages(self, query: str, max_pages: int = 3, use_selenium: bool = False) -> List[Dict[str, Any]]:
        """多页搜索功能（参考Go代码的分页逻辑）
        
        Args:
            query: 搜索关键词
            max_pages: 最大搜索页数
            use_selenium: 是否使用Selenium
            
        Returns:
            搜索结果列表
        """
        all_results = []
        seen = set()  # 用于去重
        
        for page in range(max_pages):
            print(f"[DEBUG] 搜索第 {page + 1} 页")
            
            # 使用Bing进行多页搜索
            page_results = self._search_bing(query, page, use_selenium)
            
            if not page_results:
                print(f"[DEBUG] 第 {page + 1} 页无结果，停止搜索")
                break
            
            new_count = 0
            for result in page_results:
                url = result.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    all_results.append(result)
                    new_count += 1
                    print(f"[DEBUG] 新增结果: {result.get('title', '')} - {url}")
            
            print(f"[DEBUG] 第 {page + 1} 页新增 {new_count} 条结果")
            
            # 如果没有新结果，停止搜索
            if new_count == 0:
                print(f"[DEBUG] 第 {page + 1} 页无新结果，停止搜索")
                break
        
        print(f"[DEBUG] 多页搜索完成，共获得 {len(all_results)} 条结果")
        return all_results

    def _search_site_concurrent(self, site_info: Dict[str, Any], query: str, page: int = 0, timeout: int = None) -> List[Dict[str, Any]]:
        """并发搜索单个网站
        
        Args:
            site_info: 网站信息
            query: 搜索关键词
            page: 页码
            
        Returns:
            搜索结果列表
        """
        domain = site_info["domain"]
        search_urls = site_info.get("search_urls", [])
        
        print(f"[DEBUG] 并发搜索网站: {domain}")
        
        if not search_urls:
            print(f"[DEBUG] {domain} 没有配置搜索URL，跳过")
            return []
        
        # 为搜索引擎使用专门的解析方法
        if domain in ['bing.com', 'www.bing.com']:
            # 对于Bing，使用多页搜索
            direct_results = self._search_multiple_pages(query, max_pages=3, use_selenium=False)
        elif domain in ['baidu.com', 'www.baidu.com']:
            direct_results = self._search_baidu(query, page)
        elif domain in ['sogou.com', 'www.sogou.com']:
            direct_results = self._search_sogou(query, page)
        else:
            # 其他网站使用配置的搜索URL
            timeout_value = timeout if timeout is not None else self.request_timeout
            direct_results = self._search_web_site(domain, query, search_urls, timeout=timeout_value)
        
        # 对直接访问结果进行分数计算（不过滤任何结果）
        scored_results = []
        for result in direct_results:
            title = result.get("title", "")
            url = result.get("url", "")
            score = self._calculate_relevance_score(title, url, query)
            result["score"] = score
            scored_results.append(result)
            print(f"[DEBUG] {domain}结果: {title} - {url} (分数: {score})")
        
        print(f"[DEBUG] {domain} 并发搜索返回: {len(direct_results)} 条，全部保留: {len(scored_results)} 条")
        return scored_results

    def search(self, query: str, page: int = 0, limit: Optional[int] = None, filter_mode: str = 'loose') -> List[Dict[str, Any]]:
        """网页搜索主函数"""
        if not query or len(query.strip()) < 1:
            return []
        
        results = []
        
        try:
            # 1. 并发搜索配置的搜索引擎网站
            sites = self._get_sites_by_type('web')
            timeout_per_site = self.config.get("settings", {}).get("site_timeout", 8)  # 每个网站的超时时间
            
            print(f"[DEBUG] 开始并发搜索 {len(sites)} 个网站")
            
            # 使用线程池进行并发搜索
            with ThreadPoolExecutor(max_workers=min(len(sites), 4)) as executor:
                # 提交所有搜索任务
                future_to_site = {
                    executor.submit(self._search_site_concurrent, site_info, query, page, timeout_per_site): site_info 
                    for site_info in sites
                }
                
                # 收集结果
                for future in as_completed(future_to_site):
                    site_info = future_to_site[future]
                    try:
                        site_results = future.result(timeout=timeout_per_site)
                        results.extend(site_results)
                        print(f"[DEBUG] {site_info['domain']} 并发搜索完成: {len(site_results)} 条结果")
                    except Exception as e:
                        print(f"[DEBUG] {site_info['domain']} 并发搜索失败: {e}")
                        continue
            
            # 2. 如果国内搜索引擎没有结果，使用Bing作为备用
            if not results:
                print(f"[DEBUG] 国内搜索引擎无结果，使用Bing作为备用")
                bing_results = self._search_multiple_pages(query, max_pages=3, use_selenium=False)
                
                # 对Bing结果进行分数计算（不过滤任何结果）
                scored_bing_results = []
                for result in bing_results:
                    title = result.get("title", "")
                    url = result.get("url", "")
                    score = self._calculate_relevance_score(title, url, query)
                    result["score"] = score
                    scored_bing_results.append(result)
                    print(f"[DEBUG] Bing结果: {title} - {url} (分数: {score})")
                
                results.extend(scored_bing_results)
                print(f"[DEBUG] Bing备用搜索: {len(bing_results)} 条，全部保留: {len(scored_bing_results)} 条")
            
            print(f"[DEBUG] 网页搜索完成，共搜索了 {len(sites)} 个网站（每个网站超时{timeout_per_site}秒），获得 {len(results)} 条原始结果")
            
            # 智能去重
            dedup = self._smart_deduplication(results)
            
            # 按分数排序（分数高的在前）
            dedup.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            print(f"[DEBUG] 网页搜索总计: {len(results)} 条结果，去重后: {len(dedup)} 条")
            return dedup
            
        except Exception as e:
            print(f"[DEBUG] 网页搜索异常: {e}")
            traceback.print_exc()
            return []
    
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.config
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None) -> dict:
        """添加网站"""
        try:
            # 获取网页网站配置
            web_sites = self.config.get("web_sites", {})
            custom_config = web_sites.get("custom", {})
            
            # 获取域名列表
            domains = custom_config.get("domains", [])
            
            # 检查域名是否已存在
            if domain in domains:
                # 更新搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                    web_sites["custom"] = custom_config
                    self.config["web_sites"] = web_sites
                    self._save_config()
                return {'success': True, 'action': 'updated', 'message': f'网页搜索网站 {domain} 已更新'}
            else:
                # 添加新域名
                domains.append(domain)
                custom_config["domains"] = domains
                
                # 添加搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                
                # 设置域名状态为启用
                domain_status = custom_config.get("domain_status", {})
                domain_status[domain] = True
                custom_config["domain_status"] = domain_status
                
                web_sites["custom"] = custom_config
                self.config["web_sites"] = web_sites
                self._save_config()
                
                return {'success': True, 'action': 'added', 'message': f'网页搜索网站 {domain} 添加成功'}
                
        except Exception as e:
            print(f"[DEBUG] 添加网页搜索网站失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 从所有分类中删除指定域名
            for category, config in sites_config.items():
                # 从域名列表中删除
                domains = config.get("domains", [])
                if domain in domains:
                    domains.remove(domain)
                    config["domains"] = domains
                    print(f"[DEBUG] 从分类 {category} 中删除域名: {domain}")
                
                # 从搜索URL中删除
                search_urls = config.get("search_urls", {})
                if domain in search_urls:
                    del search_urls[domain]
                    config["search_urls"] = search_urls
                
                # 从域名状态中删除
                domain_status = config.get("domain_status", {})
                if domain in domain_status:
                    del domain_status[domain]
                    config["domain_status"] = domain_status
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 删除网站: {domain} ({site_type})")
        except Exception as e:
            print(f"[DEBUG] 删除网站失败: {e}")
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        if "blacklist" not in self.config:
            self.config["blacklist"] = {"domains": [], "enabled": True}
        
        if domain not in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].append(domain)
            self._save_config()
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        if "blacklist" in self.config and domain in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].remove(domain)
            self._save_config()
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新域名状态
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "domain_status" not in config:
                        config["domain_status"] = {}
                    config["domain_status"][domain] = enabled
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 切换网站状态: {domain} -> {'启用' if enabled else '禁用'}")
        except Exception as e:
            print(f"[DEBUG] 切换网站状态失败: {e}")
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return []
            
            # 查找指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    search_urls = config.get("search_urls", {})
                    if domain in search_urls:
                        return search_urls[domain]
            
            return []
        except Exception as e:
            print(f"[DEBUG] 获取搜索URL失败: {e}")
            return []
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "search_urls" not in config:
                        config["search_urls"] = {}
                    config["search_urls"][domain] = search_urls
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 更新 {domain} 的搜索URL: {search_urls}")
        except Exception as e:
            print(f"[DEBUG] 更新搜索URL失败: {e}")


class ImageSearch(BaseSearch):
    """图片搜索类"""
    
    # 图片属性列表
    IMAGE_ATTRIBUTES = [
        'data-src', 'data-m', 'data-href', 'data-imgurl', 'data-bm', 
        'data-original', 'data-hires', 'data-full', 'data-large', 'data-hd', 'src',
        'data-msrc', 'data-big', 'data-super', 'data-zoom', 'data-thumb',
        'data-preview', 'data-image', 'data-img', 'data-pic', 'data-photo'
    ]
    
    def __init__(self, config_file: str = "sites_config.json"):
        super().__init__(config_file)
        self.search_type = "images"
    
    def _is_image_content(self, url: str, title: str) -> bool:
        """检查是否是图片内容 - 基于标题语言判断
        
        Args:
            url: 链接地址
            title: 标题
            
        Returns:
            是否为图片内容
        """
        if not url or not title:
            return False
        
        # 检查标题是否包含中文字符
        def has_chinese(text):
            for char in text:
                if '\u4e00' <= char <= '\u9fff':
                    return True
            return False
        
        # 如果标题包含中文，很可能是无效的图片链接
        if has_chinese(title):
            print(f"[DEBUG] 过滤中文标题: {title}")
            return False
        
        url_lower = url.lower()
        
        # 检查是否是图片文件扩展名
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico']
        for ext in image_extensions:
            if ext in url_lower:
                print(f"[DEBUG] 找到图片文件扩展名: {ext} in {url}")
                return True
        
        return False
    
    def _is_valid_image(self, image_url: str) -> bool:
        """检查图片是否有效（不是太小的图片）
        
        Args:
            image_url: 图片URL
            
        Returns:
            是否为有效图片
        """
        if not image_url:
            return False
        
        # 检查URL中是否包含尺寸参数，过滤太小的图片
        import re
        
        # 检查常见的尺寸参数模式
        size_patterns = [
            r'w=(\d+)',  # width参数
            r'width=(\d+)',  # width参数
            r'h=(\d+)',  # height参数
            r'height=(\d+)',  # height参数
            r'size=(\d+)',  # size参数
            r'dim=(\d+)',  # dimension参数
        ]
        
        for pattern in size_patterns:
            matches = re.findall(pattern, image_url)
            for match in matches:
                size = int(match)
                if size < 50:  # 过滤小于50像素的图片
                    print(f"[DEBUG] 过滤小图片: {size}px in {image_url}")
                    return False
        
        # 检查URL中是否包含小图片的标识
        small_image_indicators = [
            'w=12', 'h=12', 'w=16', 'h=16', 'w=24', 'h=24', 'w=32', 'h=32',
            'size=12', 'size=16', 'size=24', 'size=32', 'size=48',
            'thumb', 'thumbnail', 'icon', 'favicon', 'logo'
        ]
        
        for indicator in small_image_indicators:
            if indicator in image_url.lower():
                print(f"[DEBUG] 过滤小图片标识: {indicator} in {image_url}")
                return False
        
        return True
    
    def _extract_image_url(self, link_element, href: str) -> Optional[str]:
        """从链接元素中提取图片URL"""
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
        """从父元素中提取图片URL"""
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

    def _parse_bing_images_simple(self, soup: BeautifulSoup, query: str) -> List[Dict[str, Any]]:
        """简化的Bing图片解析"""
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
                
                # 过滤太小的图片和无效图片URL
                if image_url and self._is_valid_image(image_url):
                    results.append({
                        "title": title or f"图片: {query}",
                        "url": href,  # 图源链接（用于点击跳转）
                        "snippet": image_url,  # 图片URL（用于显示）
                        "page": href,  # 图源链接
                        "engine": "bing"
                    })
                    print(f"[DEBUG] 找到Bing图片: {title} - 图片:{image_url} 图源:{href}")
                else:
                    if not image_url:
                        print(f"[DEBUG] 过滤无图片URL: {title} - {href}")
                    else:
                        print(f"[DEBUG] 过滤无效图片: {title} - {image_url}")

                
            except Exception as e:
                print(f"[DEBUG] 解析Bing图片链接失败: {e}")
                continue
        
        print(f"[DEBUG] Bing图片解析完成: 找到 {len(results)} 条结果")
        return results

    def _search_bing(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用Bing图片搜索"""
        s = self._session()
        count = self.config.get("settings", {}).get("engine_max_results", 35)
        first = max(0, int(page)) * count + 1
        
        url = f"https://www.bing.com/images/search?q={query}&setlang=zh-cn&count={count}&first={first}"
        
        r = self._request(s, url)
        if not r:
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_bing_images_simple(soup, query)

    def search(self, query: str, page: int = 0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """图片搜索主函数"""
        if not query or len(query.strip()) < 1:
            return []
        
        results = []
        
        try:
            # 1. 搜索配置的图片网站
            sites = self._get_sites_by_type('images')
            print(f"[DEBUG] 找到 {len(sites)} 个图片网站: {[site['domain'] for site in sites]}")
            timeout_per_site = self.config.get("settings", {}).get("site_timeout", 8)
            
            for i, site_info in enumerate(sites, 1):
                domain = site_info["domain"]
                search_urls = site_info.get("search_urls", [])
                
                print(f"[DEBUG] 开始搜索图片网站 ({i}/{len(sites)}): {domain}")
                
                if search_urls:
                    # 有直接搜索URL的图片网站
                    print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                    direct_results = self._search_direct_site(domain, query, search_urls, timeout_per_site)
                    results.extend(direct_results)
                    print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条结果")
                else:
                    # 没有搜索URL，尝试直接访问首页
                    print(f"[DEBUG] {domain} 没有搜索URL，尝试直接访问")
                    direct_results = self._search_direct_site(domain, query, [f"https://{domain}/"], timeout_per_site)
                    results.extend(direct_results)
                    print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条结果")
            
            # 2. 如果配置的网站没有结果，使用Bing作为备用
            if not results:
                print(f"[DEBUG] 配置的图片网站无结果，使用Bing搜索")
                bing_results = self._search_bing(query, page)
                results.extend(bing_results)
                print(f"[DEBUG] Bing图片搜索返回: {len(bing_results)} 条结果")
            
            # 去重（基于图片URL）
            seen = set()
            dedup = []
            
            for item in results:
                snippet = item.get("snippet", "")
                if snippet and snippet not in seen:
                    seen.add(snippet)
                    dedup.append(item)
            
            print(f"[DEBUG] 图片搜索完成，共 {len(dedup)} 条结果")
            return dedup
            
        except Exception as e:
            print(f"[DEBUG] 图片搜索异常: {e}")
            traceback.print_exc()
            return []
    
    def _get_sites_by_type(self, stype: str) -> List[Dict[str, Any]]:
        """获取指定类型的网站列表"""
        sites = []
        
        if stype == 'images':
            # 图片搜索
            for category, config in self.config.get("image_sites", {}).items():
                if config.get("enabled", True):
                    for domain in config.get("domains", []):
                        # 检查单个域名的禁用状态
                        domain_status = config.get("domain_status", {})
                        if domain in domain_status and not domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的图片网站: {domain}")
                            continue
                        
                        search_urls = config.get("search_urls", {}).get(domain, [])
                        sites.append({
                            "domain": domain,
                            "category": category,
                            "search_urls": search_urls
                        })
                        print(f"[DEBUG] 添加图片网站: {domain}, 搜索URL: {len(search_urls)} 个")
        
        return sites

    def _search_direct_site(self, domain: str, query: str, search_urls: List[str], timeout: int = 8) -> List[Dict[str, Any]]:
        """直接访问网站搜索图片"""
        results = []
        
        for search_url in search_urls:
            try:
                # 替换查询参数
                url = search_url.replace('{query}', quote(query))
                print(f"[DEBUG] 直接访问: {url}")
                
                # 创建会话
                session = requests.Session()
                session.headers.update({
                    'User-Agent': random.choice(self.USER_AGENTS),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                })
                
                # 发送请求
                response = session.get(url, timeout=timeout, verify=False)
                print(f"[DEBUG] 请求URL: {url}")
                print(f"[DEBUG] 响应状态: {response.status_code}, 内容长度: {len(response.content)}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    site_results = self._parse_site_images(soup, query, domain)
                    results.extend(site_results)
                    print(f"[DEBUG] {domain} 直接访问返回: {len(site_results)} 条结果")
                else:
                    print(f"[DEBUG] 请求失败，状态码: {response.status_code}")
                    
            except Exception as e:
                print(f"[DEBUG] {domain} 直接访问失败: {e}")
                continue
        
        return results

    def _parse_site_images(self, soup: BeautifulSoup, query: str, domain: str) -> List[Dict[str, Any]]:
        """解析网站图片结果"""
        results = []
        
        # 查找所有图片元素
        img_elements = soup.find_all(['img', 'a'])
        
        for element in img_elements:
            try:
                # 获取图片URL
                img_url = None
                if element.name == 'img':
                    img_url = element.get('src') or element.get('data-src') or element.get('data-original')
                elif element.name == 'a':
                    href = element.get('href', '')
                    if any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        img_url = href
                
                if not img_url:
                    continue
                
                # 处理相对URL
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = f"https://{domain}{img_url}"
                elif not img_url.startswith('http'):
                    img_url = f"https://{domain}/{img_url}"
                
                # 获取标题
                title = element.get('alt', '') or element.get('title', '') or query
                
                # 检查是否是有效的图片内容
                if self._is_image_content(img_url, title):
                    results.append({
                        'title': title,
                        'url': img_url,
                        'snippet': img_url,
                        'source': domain
                    })
                    
            except Exception as e:
                print(f"[DEBUG] 解析图片元素失败: {e}")
                continue
        
        return results

    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.config
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None) -> dict:
        """添加网站"""
        try:
            # 获取图片网站配置
            image_sites = self.config.get("image_sites", {})
            custom_config = image_sites.get("custom", {})
            
            # 获取域名列表
            domains = custom_config.get("domains", [])
            
            # 检查域名是否已存在
            if domain in domains:
                # 更新搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                    image_sites["custom"] = custom_config
                    self.config["image_sites"] = image_sites
                    self._save_config()
                return {'success': True, 'action': 'updated', 'message': f'图片搜索网站 {domain} 已更新'}
            else:
                # 添加新域名
                domains.append(domain)
                custom_config["domains"] = domains
                
                # 添加搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                
                # 设置域名状态为启用
                domain_status = custom_config.get("domain_status", {})
                domain_status[domain] = True
                custom_config["domain_status"] = domain_status
                
                image_sites["custom"] = custom_config
                self.config["image_sites"] = image_sites
                self._save_config()
                
                return {'success': True, 'action': 'added', 'message': f'图片搜索网站 {domain} 添加成功'}
                
        except Exception as e:
            print(f"[DEBUG] 添加图片搜索网站失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 从所有分类中删除指定域名
            for category, config in sites_config.items():
                # 从域名列表中删除
                domains = config.get("domains", [])
                if domain in domains:
                    domains.remove(domain)
                    config["domains"] = domains
                    print(f"[DEBUG] 从分类 {category} 中删除域名: {domain}")
                
                # 从搜索URL中删除
                search_urls = config.get("search_urls", {})
                if domain in search_urls:
                    del search_urls[domain]
                    config["search_urls"] = search_urls
                
                # 从域名状态中删除
                domain_status = config.get("domain_status", {})
                if domain in domain_status:
                    del domain_status[domain]
                    config["domain_status"] = domain_status
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 删除图片网站: {domain} ({site_type})")
        except Exception as e:
            print(f"[DEBUG] 删除图片网站失败: {e}")
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        if "blacklist" not in self.config:
            self.config["blacklist"] = {"domains": [], "enabled": True}
        
        if domain not in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].append(domain)
            self._save_config()
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        if "blacklist" in self.config and domain in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].remove(domain)
            self._save_config()
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新域名状态
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "domain_status" not in config:
                        config["domain_status"] = {}
                    config["domain_status"][domain] = enabled
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 切换图片网站状态: {domain} -> {'启用' if enabled else '禁用'}")
        except Exception as e:
            print(f"[DEBUG] 切换图片网站状态失败: {e}")
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return []
            
            # 查找指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    search_urls = config.get("search_urls", {})
                    if domain in search_urls:
                        return search_urls[domain]
            
            return []
        except Exception as e:
            print(f"[DEBUG] 获取图片搜索URL失败: {e}")
            return []
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "search_urls" not in config:
                        config["search_urls"] = {}
                    config["search_urls"][domain] = search_urls
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 更新图片网站 {domain} 的搜索URL: {search_urls}")
        except Exception as e:
            print(f"[DEBUG] 更新图片搜索URL失败: {e}")


class VideoSearch(BaseSearch):
    """视频搜索类"""
    
    # 视频文件扩展名
    VIDEO_EXTENSIONS = [
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', 
        '.3gp', '.mpg', '.mpeg', '.m2v', '.ogv', '.vob', '.asf', '.rm', 
        '.rmvb', '.ts', '.mts', '.m2ts', '.divx', '.xvid'
    ]
    
    def __init__(self, config_file: str = "sites_config.json"):
        super().__init__(config_file)
        self.search_type = "videos"
    
    def _is_video_content(self, url: str, title: str) -> bool:
        """检查是否是视频内容 - 检查视频路径，过滤带参数的URL
        
        Args:
            url: 链接地址
            title: 标题（不使用）
            
        Returns:
            是否为视频内容
        """
        if not url:
            return False
        
        # 1. 如果是Bing的搜索页面URL，过滤掉
        if 'bing.com' in url and ('search' in url or 'videos/search' in url):
            print(f"[DEBUG] 过滤Bing搜索页面URL: {url}")
            return False
        
        # 2. 先检查是否包含视频路径关键词
        video_paths = ['/videos', '/video', '/v/', '/play/', '/player/', '/watch/', '/movie/', '/tv/', '/anime/', '/drama/', '/clip/', '/stream/', '/live/', '/x/', '/cover/', '/page/']
        has_video_path = any(path in url for path in video_paths)
        
        if has_video_path:
            # 3. 如果包含视频路径，检查是否不含?
            question_pos = url.find('?')
            if question_pos == -1:
                # 不含?，直接保留
                print(f"[DEBUG] 找到视频路径且无参数，保留URL: {url}")
                return True
            else:
                # 4. 含?，检查是否在最后一个/后面
                url_before_param = url[:question_pos]
                last_slash_pos = url_before_param.rfind('/')
                
                if question_pos > last_slash_pos:
                    # 5. ?在最后一个/后面，检查是否在域名后面/的后面
                    domain_part = url_before_param[:last_slash_pos]
                    if '.' in domain_part:
                        # 6. 在域名后面/的后面，检查紧贴?前面的几个字母是否是search或视频路径关键词
                        # 获取紧贴?前面的几个字母
                        chars_before_param = url_before_param[-10:] if len(url_before_param) >= 10 else url_before_param  # 取最后10个字符
                        has_search = chars_before_param.lower().endswith('search')
                        has_video_path_before_param = any(chars_before_param.lower().endswith(path[1:]) for path in video_paths)
                        
                        if has_search or has_video_path_before_param:
                            # 有search或视频路径关键词，过滤
                            if has_search:
                                print(f"[DEBUG] 过滤视频路径但有search的URL: {url}")
                            else:
                                print(f"[DEBUG] 过滤视频路径但?前有视频路径关键词的URL: {url}")
                            return False
                        else:
                            # 没有search且没有视频路径关键词，保留
                            print(f"[DEBUG] 找到视频路径且无search无视频路径关键词，保留URL: {url}")
                            return True
                    else:
                        # 不在域名后面/的后面，保留
                        print(f"[DEBUG] 找到视频路径且不在域名后，保留URL: {url}")
                        return True
                else:
                    # ?不在最后一个/后面，保留
                    print(f"[DEBUG] 找到视频路径且?不在最后/后，保留URL: {url}")
                    return True
        
        # 7. 其他情况全部过滤
        print(f"[DEBUG] 过滤非视频内容: {url}")
        return False
    
    def _search_bing(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用Bing视频搜索"""
        s = self._session()
        count = self.config.get("settings", {}).get("engine_max_results", 35)
        first = max(0, int(page)) * count + 1
        
        url = f"https://www.bing.com/videos/search?q={query}&setlang=zh-cn&count={count}&first={first}"
        
        r = self._request(s, url)
        if not r:
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_search_results(soup, query, "bing")

    def _parse_search_results(self, soup: BeautifulSoup, query: str, engine: str = "bing") -> List[Dict[str, Any]]:
        """解析视频搜索结果页面"""
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
                        if not href or self._is_blacklisted(href):
                            continue
                        
                        title_elem = item.find('h2') or item.find('h3')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        else:
                            title = link_elem.get_text().strip()
                        
                        title = self._clean_title(title, href, "")
                        
                        if title:
                            # 使用视频内容筛选
                            if self._is_video_content(href, title):
                                results.append({
                                    "title": title,
                                    "url": href,
                                    "snippet": "",
                                    "engine": engine
                                })
                                print(f"[DEBUG] 找到{engine}视频结果: {title} - {href}")
                            else:
                                print(f"[DEBUG] 过滤非视频内容: {title} - {href}")
                break
        
        # 如果没找到结构化结果，尝试所有链接
        if not found_results:
            print(f"[DEBUG] 未找到结构化结果，尝试所有链接")
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                original_href = link.get('href', '')
                href = self._normalize_url(original_href)
                if not href or self._is_blacklisted(href):
                    continue
                
                title = link.get_text().strip()
                title = self._clean_title(title, href, "")
                
                if title:
                    # 使用视频内容筛选
                    if self._is_video_content(href, title):
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": "",
                            "engine": engine
                        })
                        print(f"[DEBUG] 找到{engine}视频链接结果: {title} - {href}")
                    else:
                        print(f"[DEBUG] 过滤非视频内容: {title} - {href}")
        
        return results

    def search(self, query: str, page: int = 0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """视频搜索主函数"""
        if not query or len(query.strip()) < 1:
            return []
        
        results = []
        
        try:
            # 使用Bing视频搜索
            bing_results = self._search_bing(query, page)
            results.extend(bing_results)
            
            # 去重
            seen = set()
            dedup = []
            
            for item in results:
                url = item.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    dedup.append(item)
            
            return dedup
            
        except Exception as e:
            print(f"[DEBUG] 视频搜索异常: {e}")
            traceback.print_exc()
            return []
    
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.config
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None) -> dict:
        """添加网站"""
        try:
            # 获取视频网站配置
            video_sites = self.config.get("video_sites", {})
            custom_config = video_sites.get("custom", {})
            
            # 获取域名列表
            domains = custom_config.get("domains", [])
            
            # 检查域名是否已存在
            if domain in domains:
                # 更新搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                    video_sites["custom"] = custom_config
                    self.config["video_sites"] = video_sites
                    self._save_config()
                return {'success': True, 'action': 'updated', 'message': f'视频搜索网站 {domain} 已更新'}
            else:
                # 添加新域名
                domains.append(domain)
                custom_config["domains"] = domains
                
                # 添加搜索URL
                if search_urls:
                    search_urls_dict = custom_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    custom_config["search_urls"] = search_urls_dict
                
                # 设置域名状态为启用
                domain_status = custom_config.get("domain_status", {})
                domain_status[domain] = True
                custom_config["domain_status"] = domain_status
                
                video_sites["custom"] = custom_config
                self.config["video_sites"] = video_sites
                self._save_config()
                
                return {'success': True, 'action': 'added', 'message': f'视频搜索网站 {domain} 添加成功'}
                
        except Exception as e:
            print(f"[DEBUG] 添加视频搜索网站失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 从配置中删除指定域名
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    # 从域名列表中删除
                    domains = config.get("domains", [])
                    if domain in domains:
                        domains.remove(domain)
                        config["domains"] = domains
                    
                    # 从搜索URL中删除
                    search_urls = config.get("search_urls", {})
                    if domain in search_urls:
                        del search_urls[domain]
                        config["search_urls"] = search_urls
                    
                    # 从域名状态中删除
                    domain_status = config.get("domain_status", {})
                    if domain in domain_status:
                        del domain_status[domain]
                        config["domain_status"] = domain_status
                    
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 删除视频网站: {domain} ({site_type})")
        except Exception as e:
            print(f"[DEBUG] 删除视频网站失败: {e}")
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        if "blacklist" not in self.config:
            self.config["blacklist"] = {"domains": [], "enabled": True}
        
        if domain not in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].append(domain)
            self._save_config()
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        if "blacklist" in self.config and domain in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].remove(domain)
            self._save_config()
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新域名状态
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "domain_status" not in config:
                        config["domain_status"] = {}
                    config["domain_status"][domain] = enabled
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 切换视频网站状态: {domain} -> {'启用' if enabled else '禁用'}")
        except Exception as e:
            print(f"[DEBUG] 切换视频网站状态失败: {e}")
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return []
            
            # 查找指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    search_urls = config.get("search_urls", {})
                    if domain in search_urls:
                        return search_urls[domain]
            
            return []
        except Exception as e:
            print(f"[DEBUG] 获取视频搜索URL失败: {e}")
            return []
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "search_urls" not in config:
                        config["search_urls"] = {}
                    config["search_urls"][domain] = search_urls
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 更新视频网站 {domain} 的搜索URL: {search_urls}")
        except Exception as e:
            print(f"[DEBUG] 更新视频搜索URL失败: {e}")


class ResourceSearch(BaseSearch):
    """资源搜索类"""
    
    RESOURCE_KEYWORDS = [
        "下载", "资源", "百度网盘", "网盘", "夸克网盘", "阿里云盘", "天翼云", "蓝奏云", "115网盘",
        "magnet:", "磁力", "torrent", "种子", "直链", "度盘", "提取码", "分享链接"
    ]
    
    def __init__(self, config_file: str = "sites_config.json"):
        super().__init__(config_file)
        self.search_type = "resources"
    
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
    
    def _is_relevant_content(self, title: str, url: str, query: str) -> bool:
        """检查内容是否与资源搜索相关"""
        if not title or not query:
            return True
        
        title_lower = title.lower()
        query_lower = query.lower()
        
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
    
    def _search_bing(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """使用Bing资源搜索"""
        s = self._session()
        count = self.config.get("settings", {}).get("engine_max_results", 35)
        first = max(0, int(page)) * count + 1
        
        # 为资源搜索使用更宽松的搜索条件，不限制文件类型
        url = f"https://www.bing.com/search?q={query} 下载 OR 资源 OR 游戏&setlang=zh-cn&count={count}&first={first}"
        
        r = self._request(s, url)
        if not r:
            return []
        
        soup = BeautifulSoup(r.content, 'html.parser')
        return self._parse_search_results(soup, query, "bing")
    
    def _parse_search_results(self, soup: BeautifulSoup, query: str, engine: str = "bing") -> List[Dict[str, Any]]:
        """解析资源搜索结果页面"""
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
                        if not href or self._is_blacklisted(href):
                            continue
                        
                        title_elem = item.find('h2') or item.find('h3')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        else:
                            title = link_elem.get_text().strip()
                        
                        title = self._clean_title(title, href, "")
                        
                        if title:
                            # 检查内容相关性
                            if self._is_relevant_content(title, href, query):
                                results.append({
                                    "title": title,
                                    "url": href,
                                    "snippet": "",
                                    "engine": engine
                                })
                                print(f"[DEBUG] 找到{engine}资源结果: {title} - {href}")
                            else:
                                print(f"[DEBUG] 过滤不相关资源: {title} - {href}")
                break
        
        # 如果没找到结构化结果，尝试所有链接
        if not found_results:
            print(f"[DEBUG] 未找到结构化结果，尝试所有链接")
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                original_href = link.get('href', '')
                href = self._normalize_url(original_href)
                if not href or self._is_blacklisted(href):
                    continue
                
                title = link.get_text().strip()
                title = self._clean_title(title, href, "")
                
                if title:
                    # 进行相关性检查
                    if self._is_relevant_content(title, href, query):
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": "",
                            "engine": engine
                        })
                        print(f"[DEBUG] 找到{engine}资源链接结果: {title} - {href}")
                    else:
                        print(f"[DEBUG] 过滤不相关资源: {title} - {href}")
        
        return results

    def _parse_resource_site_results(self, soup: BeautifulSoup, query: str, domain: str) -> List[Dict[str, Any]]:
        """解析资源网站搜索结果页面 - 通用解析策略"""
        results = []
        
        # 通用解析策略：查找所有链接
        items = soup.select('a[href]')
        for item in items:
            href = item.get('href', '')
            
            # 处理相对URL
            if href.startswith('/'):
                href = f"https://{domain}{href}"
            elif href.startswith('http'):
                # 只保留来自当前域名的链接
                if domain not in href:
                    continue
            else:
                # 跳过无效链接
                continue
            
            # 获取标题
            title = item.get_text().strip()
            
            # 过滤条件
            if (title and href and 
                len(title) > 3 and  # 标题长度
                not href.startswith('javascript:') and  # 跳过JS链接
                not href.startswith('mailto:') and  # 跳过邮箱链接
                not href.startswith('#') and  # 跳过锚点链接
                not title.lower() in ['更多', 'more', '下一页', 'next', '上一页', 'prev']):  # 跳过导航链接
                
                results.append({
                    "title": title,
                    "url": href,
                    "snippet": f"来自 {domain} 的资源",
                    "engine": domain
                })
                print(f"[DEBUG] 找到{domain}资源链接结果: {title} - {href}")
        
        return results

    def _get_sites_by_type(self, stype: str, category: str = '') -> List[Dict[str, Any]]:
        """获取指定类型的网站列表"""
        sites = []
        
        if stype in ['files', 'resources']:
            # 资源搜索
            resource_sites = self.config.get("resource_sites", {})
            print(f"[DEBUG] 配置中的资源站点类别: {list(resource_sites.keys())}")
            
            # 如果指定了分类，只搜索该分类的网站
            if category and category != 'all':
                if category in resource_sites:
                    categories_to_search = [category]
                    print(f"[DEBUG] 按分类过滤: {category}")
                else:
                    print(f"[DEBUG] 分类 {category} 不存在，返回空结果")
                    return []
            else:
                # 搜索所有分类（包括category为空或'all'的情况）
                categories_to_search = list(resource_sites.keys())
                print(f"[DEBUG] 搜索所有分类: {categories_to_search}")
            
            # 获取custom分类的URL和状态信息（主配置）
            custom_config = resource_sites.get("custom", {})
            custom_search_urls = custom_config.get("search_urls", {})
            custom_domain_status = custom_config.get("domain_status", {})
            
            # 使用集合来避免重复搜索同一个网站
            processed_domains = set()
            
            for category_name in categories_to_search:
                config = resource_sites[category_name]
                print(f"[DEBUG] 处理资源类别: {category_name}, 启用状态: {config.get('enabled', True)}")
                if config.get("enabled", True):
                    domains = config.get("domains", [])
                    print(f"[DEBUG] {category_name} 类别下的域名: {domains}")
                    for domain in domains:
                        # 避免重复搜索同一个网站
                        if domain in processed_domains:
                            print(f"[DEBUG] 跳过已处理的网站: {domain}")
                            continue
                        
                        # 从custom分类中获取域名的禁用状态
                        if domain in custom_domain_status and not custom_domain_status[domain]:
                            print(f"[DEBUG] 跳过禁用的资源网站: {domain}")
                            continue
                        
                        # 从custom分类中获取搜索URL
                        search_urls = custom_search_urls.get(domain, [])
                        print(f"[DEBUG] 添加资源网站: {domain}, 搜索URL数量: {len(search_urls)}")
                        sites.append({
                            "domain": domain,
                            "category": category_name,
                            "search_urls": search_urls
                        })
                        processed_domains.add(domain)
        
        return sites

    def _search_direct_site(self, domain: str, query: str, search_urls: List[str], timeout: int = 8) -> List[Dict[str, Any]]:
        """直接访问网站搜索"""
        results = []
        s = self._session()
        start_time = time.time()
        
        for search_url in search_urls:
            # 检查单个网站的超时
            if time.time() - start_time > timeout:
                print(f"[DEBUG] {domain} 搜索超时({timeout}秒)，已搜索 {len(results)} 条结果")
                break
                
            try:
                # 替换查询参数
                url = search_url.replace('{query}', query)
                print(f"[DEBUG] 直接访问: {url}")
                
                r = self._request(s, url)
                if not r:
                    continue
                
                soup = BeautifulSoup(r.content, 'html.parser')
                site_results = self._parse_resource_site_results(soup, query, domain)
                results.extend(site_results)
                print(f"[DEBUG] {domain} 直接访问返回: {len(site_results)} 条结果")
                
            except Exception as e:
                print(f"[DEBUG] {domain} 直接访问失败: {e}")
                continue
        
        return results

    def search(self, query: str, page: int = 0, limit: Optional[int] = None, category: str = '') -> List[Dict[str, Any]]:
        """资源搜索主函数"""
        if not query or len(query.strip()) < 1:
            return []
        
        results = []
        
        try:
            # 1. 直接访问配置的资源网站
            sites = self._get_sites_by_type('resources', category)
            print(f"[DEBUG] 找到 {len(sites)} 个资源网站: {[site['domain'] for site in sites]}")
            timeout_per_site = self.config.get("settings", {}).get("site_timeout", 8)  # 每个网站的超时时间
            
            for i, site_info in enumerate(sites, 1):
                domain = site_info["domain"]
                search_urls = site_info.get("search_urls", [])
                
                print(f"[DEBUG] 开始搜索资源网站 ({i}/{len(sites)}): {domain}")
                
                if search_urls:
                    # 有直接搜索URL的资源网站
                    print(f"[DEBUG] {domain} 使用直接搜索URL: {search_urls}")
                    direct_results = self._search_direct_site(domain, query, search_urls, timeout_per_site)
                    
                    # 对直接访问结果进行相关性过滤
                    filtered_results = []
                    for result in direct_results:
                        if self._is_relevant_content(result.get("title", ""), result.get("url", ""), query):
                            filtered_results.append(result)
                        else:
                            print(f"[DEBUG] 过滤{domain}不相关内容: {result.get('title', '')} - {result.get('url', '')}")
                    
                    results.extend(filtered_results)
                    print(f"[DEBUG] {domain} 直接访问返回: {len(direct_results)} 条，过滤后: {len(filtered_results)} 条")
                else:
                    print(f"[DEBUG] {domain} 没有配置搜索URL，跳过")
            
            print(f"[DEBUG] 资源搜索完成，共搜索了 {len(sites)} 个网站（每个网站超时{timeout_per_site}秒），获得 {len(results)} 条结果")
            
            # 去重
            seen = set()
            dedup = []
            
            for item in results:
                url = item.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    dedup.append(item)
            
            # 按相关性排序，字符匹配度高的优先级更高，但不过滤任何结果
            def get_priority_score(item):
                title = item.get('title', '').lower()
                url = item.get('url', '').lower()
                query_lower = query.lower()
                
                score = 0
                
                # 基础匹配分数
                score += title.count(query_lower) * 10
                
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
                    else:
                        # 即使没有匹配，也给一个基础分数，确保不被过滤
                        score += 1
                
                

                
                return score
            
            dedup.sort(key=get_priority_score, reverse=True)
            
            print(f"[DEBUG] 资源搜索总计: {len(results)} 条结果，去重后: {len(dedup)} 条")
            return dedup
            
        except Exception as e:
            print(f"[DEBUG] 资源搜索异常: {e}")
            traceback.print_exc()
            return []
    
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.config
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None, category: str = 'custom') -> dict:
        """添加网站"""
        try:
            # 获取资源网站配置
            resource_sites = self.config.get("resource_sites", {})
            
            # 如果分类不是custom，需要创建或使用指定分类
            if category != 'custom':
                if category not in resource_sites:
                    # 创建新分类
                    resource_sites[category] = {
                        "domains": [],
                        "enabled": True,
                        "domain_status": {},
                        "search_urls": {}
                    }
                
                target_config = resource_sites[category]
            else:
                # 使用custom分类
                target_config = resource_sites.get("custom", {})
            
            # 获取域名列表
            domains = target_config.get("domains", [])
            
            # 检查域名是否已存在
            if domain in domains:
                # 更新搜索URL
                if search_urls:
                    search_urls_dict = target_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    target_config["search_urls"] = search_urls_dict
                    resource_sites[category] = target_config
                    self.config["resource_sites"] = resource_sites
                    self._save_config()
                return {'success': True, 'action': 'updated', 'message': f'资源搜索网站 {domain} 已更新'}
            else:
                # 添加新域名
                domains.append(domain)
                target_config["domains"] = domains
                
                # 添加搜索URL
                if search_urls:
                    search_urls_dict = target_config.get("search_urls", {})
                    search_urls_dict[domain] = search_urls
                    target_config["search_urls"] = search_urls_dict
                
                # 设置域名状态为启用
                domain_status = target_config.get("domain_status", {})
                domain_status[domain] = True
                target_config["domain_status"] = domain_status
                
                resource_sites[category] = target_config
                self.config["resource_sites"] = resource_sites
                self._save_config()
                
                return {'success': True, 'action': 'added', 'message': f'资源搜索网站 {domain} 添加成功'}
                
        except Exception as e:
            print(f"[DEBUG] 添加资源搜索网站失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 从所有分类中删除指定域名
            for category, config in sites_config.items():
                # 从域名列表中删除
                domains = config.get("domains", [])
                if domain in domains:
                    domains.remove(domain)
                    config["domains"] = domains
                    print(f"[DEBUG] 从分类 {category} 中删除域名: {domain}")
                
                # 从搜索URL中删除
                search_urls = config.get("search_urls", {})
                if domain in search_urls:
                    del search_urls[domain]
                    config["search_urls"] = search_urls
                
                # 从域名状态中删除
                domain_status = config.get("domain_status", {})
                if domain in domain_status:
                    del domain_status[domain]
                    config["domain_status"] = domain_status
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 删除资源网站: {domain} ({site_type})")
        except Exception as e:
            print(f"[DEBUG] 删除资源网站失败: {e}")
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        if "blacklist" not in self.config:
            self.config["blacklist"] = {"domains": [], "enabled": True}
        
        if domain not in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].append(domain)
            self._save_config()
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        if "blacklist" in self.config and domain in self.config["blacklist"]["domains"]:
            self.config["blacklist"]["domains"].remove(domain)
            self._save_config()
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新域名状态
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "domain_status" not in config:
                        config["domain_status"] = {}
                    config["domain_status"][domain] = enabled
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 切换资源网站状态: {domain} -> {'启用' if enabled else '禁用'}")
        except Exception as e:
            print(f"[DEBUG] 切换资源网站状态失败: {e}")
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return []
            
            # 查找指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    search_urls = config.get("search_urls", {})
                    if domain in search_urls:
                        return search_urls[domain]
            
            return []
        except Exception as e:
            print(f"[DEBUG] 获取资源搜索URL失败: {e}")
            return []
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        try:
            # 根据网站类型获取配置
            if site_type == 'web':
                sites_config = self.config.get("web_sites", {})
            elif site_type == 'images':
                sites_config = self.config.get("image_sites", {})
            elif site_type == 'videos':
                sites_config = self.config.get("video_sites", {})
            elif site_type in ['files', 'resources']:
                sites_config = self.config.get("resource_sites", {})
            else:
                return
            
            # 更新指定域名的搜索URL
            for category, config in sites_config.items():
                if config.get("enabled", True):
                    if "search_urls" not in config:
                        config["search_urls"] = {}
                    config["search_urls"][domain] = search_urls
                    break
            
            # 保存配置
            self._save_config()
            print(f"[DEBUG] 更新资源网站 {domain} 的搜索URL: {search_urls}")
        except Exception as e:
            print(f"[DEBUG] 更新资源搜索URL失败: {e}")


class UnifiedSearch:
    """统一搜索接口，管理四种搜索类型"""
    
    def __init__(self, config_file: str = "sites_config.json"):
        """初始化统一搜索接口
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        # 先加载配置
        self.config = self._load_config()
        
        
        # 创建各个搜索类的实例，传入共享的配置
        self.web_search = WebSearch(config_file)
        self.web_search.config = self.config  # 共享配置
        self.image_search = ImageSearch(config_file)
        self.image_search.config = self.config  # 共享配置
        self.video_search = VideoSearch(config_file)
        self.video_search.config = self.config  # 共享配置
        self.resource_search = ResourceSearch(config_file)
        self.resource_search.config = self.config  # 共享配置
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[DEBUG] 加载配置失败: {e}")
        
        # 返回默认配置 - 使用main.py中的DEFAULT_CONFIG
        try:
            from main import DEFAULT_CONFIG
            return DEFAULT_CONFIG.copy()
        except ImportError:
            # 如果无法导入，返回最小配置
            return {
                "search_engines": {},
                "web_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "resource_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "video_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "image_sites": {"custom": {"domains": [], "enabled": True, "domain_status": {}, "search_urls": {}}},
                "blacklist": {"domains": [], "enabled": True},
                "settings": {"engine_max_results": 35, "site_timeout": 10}
            }
    
    def _save_config(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG] 保存配置失败: {e}")
            raise e  # 重新抛出异常，让调用方知道保存失败
    
    def search(self, query: str, search_type: str = 'web', page: int = 0, limit: Optional[int] = None, filter_mode: str = 'loose', category: str = '') -> List[Dict[str, Any]]:
        """统一搜索接口
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型 ('web', 'images', 'videos', 'resources')
            page: 页码，从0开始
            limit: 结果数量限制
            filter_mode: 过滤模式 ('loose', 'strict', 'none')
            category: 资源分类过滤（仅对resources类型有效）
            
        Returns:
            搜索结果列表
        """
        search_type = search_type.lower()
        
        if search_type == 'web':
            return self.web_search.search(query, page, limit, filter_mode)
        elif search_type == 'images':
            return self.image_search.search(query, page, limit)
        elif search_type == 'videos':
            return self.video_search.search(query, page, limit)
        elif search_type in ['files', 'resources']:
            return self.resource_search.search(query, page, limit, category)
        else:
            print(f"[DEBUG] 未知的搜索类型: {search_type}")
            return []
    
    
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.config
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None, category: str = 'custom') -> dict:
        """添加网站"""
        # 根据网站类型选择对应的搜索类
        if site_type == 'web':
            return self.web_search.add_site(domain, site_type, search_urls)
        elif site_type == 'images':
            return self.image_search.add_site(domain, site_type, search_urls)
        elif site_type == 'videos':
            return self.video_search.add_site(domain, site_type, search_urls)
        elif site_type in ['files', 'resources']:
            return self.resource_search.add_site(domain, site_type, search_urls, category)
        else:
            return {'success': False, 'message': f'未知的网站类型: {site_type}'}
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        if site_type == 'web':
            self.web_search.remove_site(domain, site_type)
        elif site_type == 'images':
            self.image_search.remove_site(domain, site_type)
        elif site_type == 'videos':
            self.video_search.remove_site(domain, site_type)
        elif site_type in ['files', 'resources']:
            self.resource_search.remove_site(domain, site_type)
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        self.web_search.add_to_blacklist(domain)
        self.image_search.add_to_blacklist(domain)
        self.video_search.add_to_blacklist(domain)
        self.resource_search.add_to_blacklist(domain)
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        self.web_search.remove_from_blacklist(domain)
        self.image_search.remove_from_blacklist(domain)
        self.video_search.remove_from_blacklist(domain)
        self.resource_search.remove_from_blacklist(domain)
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        if site_type == 'web':
            self.web_search.toggle_site_enabled(domain, site_type, enabled)
        elif site_type == 'images':
            self.image_search.toggle_site_enabled(domain, site_type, enabled)
        elif site_type == 'videos':
            self.video_search.toggle_site_enabled(domain, site_type, enabled)
        elif site_type in ['files', 'resources']:
            self.resource_search.toggle_site_enabled(domain, site_type, enabled)
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        if site_type == 'web':
            return self.web_search.get_site_search_urls(site_type, domain)
        elif site_type == 'images':
            return self.image_search.get_site_search_urls(site_type, domain)
        elif site_type == 'videos':
            return self.video_search.get_site_search_urls(site_type, domain)
        elif site_type in ['files', 'resources']:
            return self.resource_search.get_site_search_urls(site_type, domain)
        else:
            return []
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        if site_type == 'web':
            self.web_search.update_site_search_urls(site_type, domain, search_urls)
        elif site_type == 'images':
            self.image_search.update_site_search_urls(site_type, domain, search_urls)
        elif site_type == 'videos':
            self.video_search.update_site_search_urls(site_type, domain, search_urls)
        elif site_type in ['files', 'resources']:
            self.resource_search.update_site_search_urls(site_type, domain, search_urls)
    
    def add_category(self, name: str, description: str = '') -> dict:
        """添加资源分类"""
        try:
            # 获取资源分类配置
            resource_categories = self.config.get("resource_categories", {})
            
            # 检查分类是否已存在
            if name in resource_categories:
                return {'success': False, 'message': f'分类 "{name}" 已存在'}
            
            # 添加新分类
            resource_categories[name] = {
                "description": description,
                "created_at": time.time()
            }
            
            self.config["resource_categories"] = resource_categories
            self._save_config()
            
            return {'success': True, 'message': f'分类 "{name}" 添加成功'}
            
        except Exception as e:
            print(f"[DEBUG] 添加分类失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def delete_category(self, name: str) -> dict:
        """删除资源分类"""
        try:
            # 获取资源分类配置
            resource_categories = self.config.get("resource_categories", {})
            
            # 检查分类是否存在
            if name not in resource_categories:
                return {'success': False, 'message': f'分类 "{name}" 不存在'}
            
            # 检查是否有网站使用此分类
            resource_sites = self.config.get("resource_sites", {})
            if name in resource_sites and resource_sites[name].get("domains"):
                return {'success': False, 'message': f'分类 "{name}" 下还有网站，无法删除'}
            
            # 删除分类
            del resource_categories[name]
            self.config["resource_categories"] = resource_categories
            self._save_config()
            
            return {'success': True, 'message': f'分类 "{name}" 删除成功'}
            
        except Exception as e:
            print(f"[DEBUG] 删除分类失败: {e}")
            return {'success': False, 'message': f'删除失败: {str(e)}'}
    
    def add_site_to_category(self, domain: str, site_type: str, target_category: str) -> dict:
        """将网站添加到指定分类（支持多分类）"""
        try:
            if site_type not in ['files', 'resources']:
                return {'success': False, 'message': '只有资源网站支持分类'}
            
            # 获取资源网站配置
            resource_sites = self.config.get("resource_sites", {})
            
            # 检查网站是否存在于custom分类中（主分类）
            custom_sites = resource_sites.get("custom", {})
            if domain not in custom_sites.get("domains", []):
                return {'success': False, 'message': f'网站 {domain} 不存在'}
            
            # 确保目标分类存在
            if target_category not in resource_sites:
                resource_sites[target_category] = {
                    "domains": [],
                    "enabled": True
                }
            
            # 将网站添加到目标分类（如果尚未存在）
            target_config = resource_sites[target_category]
            domains = target_config.get("domains", [])
            
            if domain in domains:
                return {'success': True, 'message': f'网站 {domain} 已在分类 {target_category} 中'}
            
            # 只添加域名，不复制URL和状态
            domains.append(domain)
            target_config["domains"] = domains
            
            resource_sites[target_category] = target_config
            self.config["resource_sites"] = resource_sites
            self._save_config()
            
            return {'success': True, 'message': f'网站 {domain} 已添加到分类 {target_category}'}
            
        except Exception as e:
            print(f"[DEBUG] 添加网站到分类失败: {e}")
            return {'success': False, 'message': f'添加失败: {str(e)}'}
    
    def remove_site_from_category(self, domain: str, site_type: str, category: str) -> dict:
        """从指定分类中移除网站"""
        try:
            if site_type not in ['files', 'resources']:
                return {'success': False, 'message': '只有资源网站支持分类'}
            
            # 获取资源网站配置
            resource_sites = self.config.get("resource_sites", {})
            
            if category not in resource_sites:
                return {'success': False, 'message': f'分类 {category} 不存在'}
            
            config = resource_sites[category]
            domains = config.get("domains", [])
            
            if domain not in domains:
                return {'success': False, 'message': f'网站 {domain} 不在分类 {category} 中'}
            
            # 从分类中移除网站（只移除域名）
            domains.remove(domain)
            config["domains"] = domains
            
            resource_sites[category] = config
            self.config["resource_sites"] = resource_sites
            self._save_config()
            
            return {'success': True, 'message': f'网站 {domain} 已从分类 {category} 中移除'}
            
        except Exception as e:
            print(f"[DEBUG] 从分类移除网站失败: {e}")
            return {'success': False, 'message': f'移除失败: {str(e)}'}


# 为了保持向后兼容性，创建一个新的WebSearch类
class WebSearchCompat:
    """向后兼容的WebSearch类，实际使用UnifiedSearch"""
    
    def __init__(self, config_file: str = "sites_config.json"):
        self.unified_search = UnifiedSearch(config_file)
    
    def search_web(self, query: str, stype: str = 'web', page: int = 0, limit: Optional[int] = None, filter_mode: str = 'loose') -> List[Dict[str, Any]]:
        """向后兼容的搜索方法"""
        return self.unified_search.search(query, stype, page, limit, filter_mode)
    
    def get_all_sites(self) -> Dict[str, Any]:
        """获取所有网站配置"""
        return self.unified_search.get_all_sites()
    
    def add_site(self, domain: str, site_type: str, search_urls: Optional[List[str]] = None) -> dict:
        """添加网站"""
        return self.unified_search.add_site(domain, site_type, search_urls)
    
    def remove_site(self, domain: str, site_type: str) -> None:
        """删除网站"""
        self.unified_search.remove_site(domain, site_type)
    
    def add_to_blacklist(self, domain: str) -> None:
        """添加到黑名单"""
        self.unified_search.add_to_blacklist(domain)
    
    def remove_from_blacklist(self, domain: str) -> None:
        """从黑名单移除"""
        self.unified_search.remove_from_blacklist(domain)
    
    def toggle_site_enabled(self, domain: str, site_type: str, enabled: bool) -> None:
        """切换网站启用状态"""
        self.unified_search.toggle_site_enabled(domain, site_type, enabled)
    
    def get_site_search_urls(self, site_type: str, domain: str) -> list:
        """获取指定网站的搜索URL"""
        return self.unified_search.get_site_search_urls(site_type, domain)
    
    def update_site_search_urls(self, site_type: str, domain: str, search_urls: list) -> None:
        """更新指定网站的搜索URL"""
        self.unified_search.update_site_search_urls(site_type, domain, search_urls)