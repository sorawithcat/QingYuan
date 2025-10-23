#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from qingyuan_core import QingYuan
from flask import Flask, request, jsonify, send_from_directory
import os

# 默认配置
DEFAULT_CONFIG = {
    "search_engines": {
        "baidu": {
            "name": "百度",
            "base_url": "https://www.baidu.com",
            "search_paths": {
                "web": "/s",
                "images": "/s?wd={query}&t=image",
                "videos": "/s?wd={query}&t=video"
            },
            "enabled": True
        },
        "bing": {
            "name": "Bing",
            "base_url": "https://www.bing.com",
            "search_paths": {
                "web": "/search",
                "images": "/images/search",
                "videos": "/videos/search"
            },
            "enabled": True
        },
        "sogou": {
            "name": "搜狗",
            "base_url": "https://www.sogou.com",
            "search_paths": {
                "web": "/web",
                "images": "/images",
                "videos": "/video"
            },
            "enabled": True
        }
    },
    "web_sites": {
        "custom": {
            "domains": [
                "baidu.com",
                "bing.com",
                "sogou.com"
            ],
            "search_urls": {
                "baidu.com": [
                    "https://www.baidu.com/s?wd={query}",
                    "https://www.baidu.com/s?wd={query}&pn=10",
                    "https://www.baidu.com/s?wd={query}&pn=20"
                ],
                "sogou.com": [
                    "https://sogou.com/web?query={query}&_asf=www.sogou.com&_ast=&w=01019900&p=40040100&ie=utf8&from=index-nologin&s_from=index&sourceid=9_01_03",
                    "https://sogou.com/web?query={query}&_asf=www.sogou.com&_ast=&w=01019900&p=40040101&ie=utf8&from=index-nologin&s_from=index&sourceid=9_01_03",
                    "https://sogou.com/web?query={query}&_asf=www.sogou.com&_ast=&w=01019900&p=40040102&ie=utf8&from=index-nologin&s_from=index&sourceid=9_01_03"
                ],
                "bing.com": [
                    "https://www.bing.com/search?q={query}",
                    "https://www.bing.com/search?q={query}&first=11",
                    "https://www.bing.com/search?q={query}&first=21"
                ]
            },
            "enabled": True,
            "domain_status": {
                "baidu.com": True,
                "bing.com": True,
                "sogou.com": True
            }
        }
    },
    "resource_sites": {
        "custom": {
            "domains": [
                "bbs.3dmgame.com",
                "ggbases.dlgal.com",
                "gugu3.com",
                "linovelib.com",
                "www.gamer520.com",
                "inarigal.com",
                "www.flysheep6.com"
            ],
            "search_urls": {
                "bbs.3dmgame.com": [
                    "https://bbs.3dmgame.com/search.php?mod=forum&searchsubmit=yes&kw={query}",
                    "https://bbs.3dmgame.com/search.php?mod=forum&searchsubmit=yes&kw={query}&srchtype=title"
                ],
                "ggbases.dlgal.com": [
                    "https://ggbases.dlgal.com/search.so?p=0&title={query}&advanced=0",
                    "https://ggbases.dlgal.com/search.so?p=0&title={query}&advanced=1"
                ],
                "gugu3.com": [
                    "https://www.gugu3.com/search?q={query}",
                    "https://www.gugu3.com/"
                ],
                "linovelib.com": [
                    "https://www.linovelib.com/search?keyword={query}",
                    "https://www.linovelib.com/"
                ],
                "www.gamer520.com": [
                    "https://www.gamer520.com/?s={query}"
                ],
                "inarigal.com": [
                    "https://inarigal.com/?search={query}"
                ],
                "www.flysheep6.com": [
                    "https://www.flysheep6.com/?s={query}"
                ]
            },
            "enabled": True,
            "domain_status": {
                "bbs.3dmgame.com": True,
                "www.gamer520.com": True,
                "inarigal.com": True,
                "www.flysheep6.com": True
            }
        }
    },
    "video_sites": {
        "custom": {
            "domains": [
                "bilibili.com"
            ],
            "enabled": True,
            "domain_status": {
                "bilibili.com": True
            },
            "search_urls": {
                "bilibili.com": [
                    "https://search.bilibili.com/video?keyword={query}",
                    "https://search.bilibili.com/video?keyword={query}&order=totalrank&duration=0&tids_1=0"
                ]
            }
        }
    },
    "image_sites": {
        "custom": {
            "domains": [],
            "enabled": True,
            "domain_status": {},
            "search_urls": {}
        }
    },
    "blacklist": {
        "domains": [
            "microsoft.com",
            "microsofttranslator.com"
        ],
        "enabled": True
    },
    "settings": {
        "engine_max_results": 35,
        "site_timeout": 10
    }
}

# 创建全局实例，避免重复创建
qingyuan = QingYuan()

def main():
    app = Flask(__name__, static_folder='public', static_url_path='')

    @app.post('/api/search')
    def api_search():
        data = request.get_json(force=True) or {}
        q = (data.get('q') or '').strip()
        stype = (data.get('stype') or 'web')
        page = int(data.get('page') or 0)
        category = data.get('category', '')  # 添加分类参数
        
        # 使用新的分离式搜索系统，所有搜索类型使用相同的结果数量
        limit = 60 
        res = qingyuan.web_search.search(q, search_type=stype, page=page, limit=limit, category=category)
        return jsonify({"results": res})

    @app.get('/')
    def index():
        return send_from_directory('public', 'index.html')

    @app.get('/admin')
    def admin():
        return send_from_directory('public', 'admin.html')

    # 配置管理API
    @app.get('/api/config')
    def get_config():
        """获取配置"""
        try:
            config = qingyuan.web_search.get_all_sites()
            return jsonify(config)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/add-site')
    def add_site():
        """添加网站"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain')
            site_type = data.get('siteType')
            search_urls = data.get('searchUrls', [])
            category = data.get('category', 'custom')  # 添加分类参数
            
            if not domain or not site_type:
                return jsonify({'error': '缺少必要参数'}), 400
            
            result = qingyuan.web_search.add_site(domain, site_type, search_urls, category)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/remove-site')
    def remove_site():
        """删除网站"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain')
            site_type = data.get('siteType')
            
            if not domain or not site_type:
                return jsonify({'error': '缺少必要参数'}), 400
            
            # 新的统一搜索接口直接使用短名称
            qingyuan.web_search.remove_site(domain, site_type)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/toggle-site')
    def toggle_site():
        """切换网站状态"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain')
            site_type = data.get('siteType')
            enabled = data.get('enabled')
            
            if not domain or not site_type or enabled is None:
                return jsonify({'error': '缺少必要参数'}), 400
            
            # 新的统一搜索接口直接使用短名称
            qingyuan.web_search.toggle_site_enabled(domain, site_type, enabled)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/blacklist')
    def manage_blacklist():
        """管理黑名单"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain')
            action = data.get('action')
            
            if not domain or not action:
                return jsonify({'error': '缺少必要参数'}), 400
            
            if action == 'add':
                qingyuan.web_search.add_to_blacklist(domain)
            elif action == 'remove':
                qingyuan.web_search.remove_from_blacklist(domain)
            else:
                return jsonify({'error': '无效的操作'}), 400
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/settings')
    def save_settings():
        """保存设置"""
        try:
            data = request.get_json(force=True) or {}
            engine_max_results = data.get('engineMaxResults')
            site_timeout = data.get('siteTimeout')
            
            # 更新配置
            if 'settings' not in qingyuan.web_search.config:
                qingyuan.web_search.config['settings'] = {}
            
            if engine_max_results is not None:
                qingyuan.web_search.config['settings']['engine_max_results'] = engine_max_results
            
            if site_timeout is not None:
                qingyuan.web_search.config['settings']['site_timeout'] = site_timeout
            
            qingyuan.web_search._save_config()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500



    @app.get('/api/config/search-urls/<site_type>')
    def get_search_urls(site_type: str):
        """获取指定类型的搜索URL配置"""
        try:
            config = qingyuan.web_search.get_all_sites()
            if site_type in config and 'custom' in config[site_type]:
                search_urls = config[site_type]['custom'].get('search_urls', {})
                return jsonify(search_urls)
            return jsonify({})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/search-urls/<site_type>')
    def update_search_urls(site_type: str):
        """更新指定类型的搜索URL配置"""
        try:
            data = request.get_json(force=True) or {}
            search_urls = data.get('searchUrls', {})
            
            # 新的统一搜索接口需要分别更新每个域名的搜索URL
            for domain, urls in search_urls.items():
                qingyuan.web_search.update_site_search_urls(site_type, domain, urls)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.get('/api/config/sites/<site_type>/urls/<domain>')
    def get_site_urls(site_type: str, domain: str):
        """获取指定网站的搜索URL"""
        try:
            urls = qingyuan.web_search.get_site_search_urls(site_type, domain)
            return jsonify({'searchUrls': urls})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/sites/<site_type>/edit')
    def edit_site(site_type: str):
        """编辑网站配置"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain', '').strip()
            search_urls = data.get('searchUrls', [])
            
            if not domain:
                return jsonify({'error': '域名不能为空'}), 400
            
            qingyuan.web_search.update_site_search_urls(site_type, domain, search_urls)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/reset')
    def reset_config():
        """重置配置到硬编码的默认配置"""
        try:
            # 使用默认配置变量
            new_config = DEFAULT_CONFIG.copy()
            
            # 更新主配置
            qingyuan.web_search.config = new_config
            
            # 更新各个搜索类的配置
            qingyuan.web_search.web_search.config = new_config
            qingyuan.web_search.image_search.config = new_config
            qingyuan.web_search.video_search.config = new_config
            qingyuan.web_search.resource_search.config = new_config
            
            # 保存重置后的配置到文件
            qingyuan.web_search._save_config()
            
            print(f"[DEBUG] 配置已重置，新配置包含 {len(new_config.get('web_sites', {}).get('custom', {}).get('domains', []))} 个网页网站")
            print(f"[DEBUG] 新配置包含 {len(new_config.get('resource_sites', {}).get('custom', {}).get('domains', []))} 个资源网站")
            
            return jsonify({'success': True, 'message': '配置已重置到默认配置'})
        except Exception as e:
            print(f"[DEBUG] 重置配置失败: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/categories')
    def manage_categories():
        """管理资源分类"""
        try:
            data = request.get_json(force=True) or {}
            action = data.get('action')
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            sites = data.get('sites', [])  # 获取选中的网站列表
            
            if not name:
                return jsonify({'error': '分类名称不能为空'}), 400
            
            if action == 'add':
                # 添加分类
                result = qingyuan.web_search.add_category(name, description)
                
                # 如果分类添加成功且有选中的网站，将网站添加到新分类
                if result.get('success') and sites:
                    for site in sites:
                        domain = site.get('domain')
                        if domain:
                            # 将网站添加到新分类（支持多分类）
                            qingyuan.web_search.add_site_to_category(domain, 'resources', name)
                
                return jsonify(result)
            elif action == 'delete':
                # 删除分类
                result = qingyuan.web_search.delete_category(name)
                return jsonify(result)
            else:
                return jsonify({'error': '无效的操作'}), 400
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/remove-site-from-category')
    def remove_site_from_category():
        """从分类中移除网站"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain', '').strip()
            site_type = data.get('siteType', '')
            category = data.get('category', '').strip()
            
            if not domain or not site_type or not category:
                return jsonify({'error': '缺少必要参数'}), 400
            
            result = qingyuan.web_search.remove_site_from_category(domain, site_type, category)
            return jsonify(result)
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.post('/api/config/add-site-to-category')
    def add_site_to_category():
        """添加网站到分类"""
        try:
            data = request.get_json(force=True) or {}
            domain = data.get('domain', '').strip()
            site_type = data.get('siteType', '')
            category = data.get('category', '').strip()
            
            if not domain or not site_type or not category:
                return jsonify({'error': '缺少必要参数'}), 400
            
            result = qingyuan.web_search.add_site_to_category(domain, site_type, category)
            return jsonify(result)
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # 自动打开浏览器
    import webbrowser
    import threading
    import time
    import atexit
    import signal
    import sys
    
    def open_browser():
        time.sleep(1.5)  # 等待服务器启动
        webbrowser.open('http://127.0.0.1:8787')
    
    def cleanup_on_exit():
        """程序退出时的清理函数"""
        print("\n程序正在退出...")
        sys.exit(0)
    
    def signal_handler(signum, frame):
        """信号处理器"""
        cleanup_on_exit()
    
    # 注册退出处理函数
    atexit.register(cleanup_on_exit)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 在新线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    print("=" * 50)
    print("WATER清源已启动！")
    print("访问地址：http://127.0.0.1:8787")
    print("管理界面：http://127.0.0.1:8787/admin")
    print("关闭浏览器窗口即可退出程序")
    print("按 Ctrl+C 也可停止服务")
    print("=" * 50)
    
    # 安全配置选项
    import socket
    
    def get_local_ip():
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    # 显示网络信息
    local_ip = get_local_ip()
    print(f"本机IP地址：{local_ip}")
    print(f"局域网访问：http://{local_ip}:8787")
    print("注意：127.0.0.1 只能本机访问，局域网IP可以同网络设备访问")
    
    try:
        app.run(host='127.0.0.1', port=8787, debug=False)
    except KeyboardInterrupt:
        print("\n收到退出信号，程序正在关闭...")
        cleanup_on_exit()
    except Exception as e:
        print(f"\n程序异常退出: {e}")
        cleanup_on_exit()

if __name__ == "__main__":
    main()