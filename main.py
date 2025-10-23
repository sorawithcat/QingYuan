#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from qingyuan_core import QingYuan
from flask import Flask, request, jsonify, send_from_directory
import os

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
        
        # 使用新的分离式搜索系统，所有搜索类型使用相同的结果数量
        limit = 60 
        res = qingyuan.web_search.search(q, search_type=stype, page=page, limit=limit)
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
            
            if not domain or not site_type:
                return jsonify({'error': '缺少必要参数'}), 400
            
            result = qingyuan.web_search.add_site(domain, site_type, search_urls)
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