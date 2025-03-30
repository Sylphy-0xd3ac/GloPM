#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
import json
import time
import requests
import configparser
from pathlib import Path
from rich.console import Console
from rich.progress import Progress
from rich.panel import Panel
from rich.text import Text
from tabulate import tabulate
from datetime import datetime
import getpass
from concurrent.futures import ThreadPoolExecutor

console = Console()

# 配置文件路径
CONFIG_DIR = Path.home() / ".glopm"
CONFIG_FILE = CONFIG_DIR / "config.ini"
CACHE_DIR = CONFIG_DIR / "cache"
DEFAULT_API_URL = "http://127.0.0.1:3000/api"

# 应用信息
APP_NAME = "GloPM 包管理器"
APP_VERSION = "1.0.0"

def print_welcome():
    """打印欢迎信息"""
    welcome_text = Text()
    welcome_text.append(f"\n欢迎使用 {APP_NAME} ", style="bold green")
    welcome_text.append(f"v{APP_VERSION}\n", style="blue")

    panel = Panel(welcome_text, title="欢迎", border_style="green")
    console.print(panel)

def ensure_path_exists(path):
    """确保路径存在"""
    if isinstance(path, str):
        path = Path(path)
    
    if not path.exists():
        if path.suffix:  # 如果有后缀，说明是文件
            path.parent.mkdir(parents=True, exist_ok=True)
        else:  # 否则是目录
            path.mkdir(parents=True, exist_ok=True)
        return False
    return True

def check_file_exists(file_path, error_message=None):
    """检查文件是否存在，不存在则打印错误信息并返回False"""
    if not os.path.exists(file_path):
        if error_message:
            print_error(error_message)
        return False
    return True

def load_config():
    """加载配置文件"""
    config = configparser.ConfigParser()
    ensure_path_exists(CONFIG_DIR)
    
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    
    # 确保所有必要的配置节都存在
    sections = ['auth', 'settings', 'user_info']
    for section in sections:
        if section not in config:
            config[section] = {}
    
    # 设置默认值
    if 'api_url' not in config['settings']:
        config['settings']['api_url'] = DEFAULT_API_URL
    
    return config

def save_config(config):
    """保存配置文件"""
    ensure_path_exists(CONFIG_DIR)
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def get_auth_headers():
    """获取认证头信息"""
    config = load_config()
    if 'user_id' not in config['auth'] or 'api_key' not in config['auth']:
        console.print(Panel(
            "您尚未登录，请先使用 login 命令登录系统。",
            title="需要登录",
            border_style="red"
        ))
        sys.exit(1)
    
    return {
        'x-user-id': config['auth']['user_id'],
        'x-api-key': config['auth']['api_key']
    }

def get_api_url():
    """获取API URL"""
    config = load_config()
    return config['settings']['api_url']

def format_date(date_str):
    """格式化日期字符串"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return date_str

def print_success(message):
    """打印成功信息"""
    console.print(Panel(
        message,
        title="操作成功",
        border_style="green"
    ))

def print_error(message):
    """打印错误信息"""
    console.print(Panel(
        message,
        title="操作失败",
        border_style="red"
    ))

def print_info(message, title="信息"):
    """打印一般信息"""
    console.print(Panel(
        message,
        title=title,
        border_style="blue"
    ))

def handle_response(response, success_handler, error_handler=None):
    """统一处理API响应"""
    if 200 <= response.status_code < 300:
        return success_handler(response)
    else:
        error = response.json().get('error', '未知错误')
        if error_handler:
            return error_handler(error)
        else:
            print_error(f"请求失败：{error}")
            return None

def api_request(method, endpoint, data=None, files=None, headers=None, stream=False, status_message=None):
    """统一的API请求处理函数"""
    api_url = get_api_url()
    url = f"{api_url}/{endpoint}"
    
    try:
        with console.status(status_message or f"[bold green]正在处理请求...[/bold green]"):
            if method.lower() == 'get':
                response = requests.get(url, headers=headers, params=data, stream=stream)
            elif method.lower() == 'post':
                response = requests.post(url, headers=headers, json=data if files is None else None, 
                                        data=None if files is None else data, files=files)
            elif method.lower() == 'delete':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"不支持的请求方法: {method}")
        
        return response
    except requests.RequestException as e:
        print_error(f"网络请求错误：{str(e)}。\n请检查您的网络连接后重试。")
        sys.exit(1)

def save_auth_info(user_id, api_key, username):
    """保存认证信息到配置文件"""
    config = load_config()
    config['auth']['user_id'] = str(user_id)
    config['auth']['api_key'] = api_key
    config['user_info']['username'] = username
    save_config(config)

def clear_auth_info():
    """清除认证信息"""
    config = load_config()
    username = config['user_info'].get('username', '用户')
    config['auth'] = {}
    config['user_info'] = {}
    save_config(config)
    return username

def confirm_action(message, confirm_value=None):
    """确认操作"""
    console.print(f"[bold yellow]{message}[/bold yellow]")
    if confirm_value:
        confirm = input(f"请输入 '{confirm_value}' 以确认: ")
        return confirm == confirm_value
    else:
        confirm = input("确认操作？(y/N): ").lower()
        return confirm == 'y'

def download_file(url, output_path=None, headers=None, progress_callback=None):
    """
    通用文件下载函数
    
    参数:
        url: 下载URL
        output_path: 输出文件路径，如果为None则从响应头获取
        headers: 请求头
        progress_callback: 进度回调函数，接收已下载大小和总大小两个参数
    
    返回:
        (bool, str): (是否成功, 文件路径或错误信息)
    """
    try:
        with requests.get(url, headers=headers, stream=True) as response:
            if response.status_code != 200:
                return False, f"下载失败，状态码: {response.status_code}"
            
            # 获取文件名
            if not output_path:
                content_disposition = response.headers.get('content-disposition', '')
                if 'filename=' in content_disposition:
                    output_path = content_disposition.split('filename=')[1].strip('"\'')
                else:
                    output_path = f"download_{int(datetime.now().timestamp())}"
            
            # 确保输出目录存在
            ensure_path_exists(os.path.dirname(output_path) or '.')
            
            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            
            # 下载文件
            with open(output_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)
            
            return True, output_path
    except Exception as e:
        return False, str(e)

def get_cached_package_info(package_name, max_age=3600):
    """获取缓存的包信息，如果缓存过期则返回None"""
    ensure_path_exists(CACHE_DIR)
    cache_file = CACHE_DIR / f"{package_name}.json"
    if os.path.exists(cache_file):
        # 检查缓存是否过期
        if time.time() - os.path.getmtime(cache_file) < max_age:
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
    return None

def cache_package_info(package_name, info):
    """缓存包信息"""
    ensure_path_exists(CACHE_DIR)
    cache_file = CACHE_DIR / f"{package_name}.json"
    try:
        with open(cache_file, 'w') as f:
            json.dump(info, f)
    except:
        # 忽略缓存错误
        pass

def batch_operation(items, operation_func, parallel=False, max_workers=4):
    """批量执行操作，支持并行处理"""
    results = []
    
    if parallel and len(items) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(operation_func, item) for item in items]
            for future in futures:
                results.append(future.result())
    else:
        for item in items:
            results.append(operation_func(item))
    
    return results

def interactive_login():
    """交互式登录"""
    username = input("用户名: ")
    password = getpass.getpass("密码: ")
    
    response = api_request(
        'post', 
        'auth/login', 
        data={'username': username, 'password': password},
        status_message="[bold green]正在验证您的身份，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        result = resp.json()
        save_auth_info(result['user_id'], result['apiKey'], username)
        print_success(f"欢迎回来，{username}！\n\n您已成功登录。")
        return True
    
    def error_handler(error):
        print_error(f"登录失败：{error}。\n请检查您的用户名和密码是否正确。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def interactive_register():
    """交互式注册"""
    username = input("请设置用户名: ")
    password = getpass.getpass("请设置密码: ")
    confirm_password = getpass.getpass("请确认密码: ")
    
    if password != confirm_password:
        print_error("两次输入的密码不一致，请重新注册。")
        return False
    
    response = api_request(
        'post', 
        'auth/register', 
        data={'username': username, 'password': password},
        status_message="[bold green]正在为您注册账户，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        result = resp.json()
        save_auth_info(result['user_id'], result['apiKey'], username)
        print_success(f"尊敬的 {username}，欢迎您使用 {APP_NAME}！\n\n"
                     f"• 您的账户已成功创建。\n"
                     f"• 已为您自动登录。\n"
                     f"• 您现在可以开始发布和下载包了。")
        return True
    
    def error_handler(error):
        print_error(f"很抱歉，注册过程中遇到了问题：{error}。\n请稍后再试或联系管理员获取帮助。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def register(args):
    """注册新用户"""
    if not args.username or not args.password:
        return interactive_register()
    
    response = api_request(
        'post', 
        'auth/register', 
        data={'username': args.username, 'password': args.password},
        status_message="[bold green]正在为您注册账户，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        result = resp.json()
        save_auth_info(result['user_id'], result['apiKey'], args.username)
        print_success(f"尊敬的 {args.username}，欢迎您使用 {APP_NAME}！\n\n"
                     f"• 您的账户已成功创建。\n"
                     f"• 已为您自动登录。\n"
                     f"• 您现在可以开始发布和下载包了。")
        return True
    
    def error_handler(error):
        print_error(f"很抱歉，注册过程中遇到了问题：{error}。\n请稍后再试或联系管理员获取帮助。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def login(args):
    """用户登录"""
    if not args.username or not args.password:
        return interactive_login()
    
    response = api_request(
        'post', 
        'auth/login', 
        data={'username': args.username, 'password': args.password},
        status_message="[bold green]正在验证您的身份，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        result = resp.json()
        save_auth_info(result['user_id'], result['apiKey'], args.username)
        print_success(f"欢迎回来，{args.username}！\n\n您已成功登录。")
        return True
    
    def error_handler(error):
        print_error(f"登录失败：{error}。\n请检查您的用户名和密码是否正确。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def logout(args):
    """退出登录"""
    username = clear_auth_info()
    print_success(f"再见，{username}！您已退出。\n期待您的再次使用。")

def publish(args):
    """发布包"""
    headers = get_auth_headers()
    
    # 检查文件是否存在
    if not check_file_exists(args.file, f"文件 {args.file} 不存在。\n请检查文件路径是否正确。"):
        return False
    
    # 准备表单数据
    files = {
        'file': (os.path.basename(args.file), open(args.file, 'rb'), 'application/octet-stream')
    }
    data = {
        'packageName': args.name,
        'version': args.version,
        'description': args.description
    }
    
    response = api_request(
        'post',
        'packages/publish',
        headers=headers,
        data=data,
        files=files,
        status_message=f"[bold green]正在发布 {args.name}@{args.version}，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        # 清除缓存
        cache_file = CACHE_DIR / f"{args.name}.json"
        if os.path.exists(cache_file):
            os.remove(cache_file)
            
        print_success(f"包 {args.name}@{args.version} 发布成功！\n\n"
                     f"• 包名：{args.name}\n"
                     f"• 版本：{args.version}\n"
                     f"• 描述：{args.description}")
        return True
    
    def error_handler(error):
        print_error(f"发布失败：{error}。\n请检查包名和版本是否符合规范。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def download(args):
    """下载包"""
    url = f"{get_api_url()}/packages/{args.name}/download/{args.version}"
    
    with Progress() as progress:
        task = progress.add_task(f"[green]下载 {args.name}@{args.version}...", total=100)
        
        def update_progress(downloaded, total):
            if total > 0:
                progress.update(task, completed=int(downloaded * 100 / total))
        
        success, result = download_file(
            url, 
            args.output, 
            progress_callback=update_progress
        )
        
        if success:
            file_size_kb = os.path.getsize(result) / 1024
            print_success(f"包 {args.name}@{args.version} 下载成功！\n\n"
                         f"• 包名：{args.name}\n"
                         f"• 版本：{args.version}\n"
                         f"• 保存位置：{result}\n"
                         f"• 文件大小：{file_size_kb:.2f} KB")
            return True
        else:
            print_error(f"下载失败：{result}。\n请检查包名和版本是否正确或网络连接。")
            return False

def search(args):
    """搜索包"""
    response = api_request(
        'get',
        f"packages/search?query={args.query}",
        status_message=f"[bold green]正在搜索\"{args.query}\"相关的包，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        packages = resp.json()
        
        if not packages:
            print_info(f"很抱歉，未找到与\"{args.query}\"相关的包。\n请尝试使用其他关键词搜索。", title="搜索结果")
            return True
        
        # 使用 tabulate 格式化表格
        headers = ["包名", "描述", "更新时间"]
        table_data = []
        for pkg in packages:
            table_data.append([
                pkg.get('name', 'N/A'),
                pkg.get('description', 'N/A'),
                format_date(pkg.get('updatedAt', 'N/A'))
            ])
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid",
            numalign="right"
        )
        
        print_info(f"找到 {len(packages)} 个与\"{args.query}\"相关的包：\n\n{table}", title="搜索结果")
        return True
    
    def error_handler(error):
        print_error(f"搜索失败：{error}。\n请稍后再试。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def get_latest_version(args):
    """获取包的最新版本"""
    # 尝试从缓存获取
    cached_info = get_cached_package_info(args.name)
    if cached_info and 'latest_version' in cached_info:
        version_info = cached_info['latest_version']
        
        # 使用 tabulate 格式化表格
        headers = ["版本", "描述", "文件大小", "发布时间"]
        table_data = [[
            version_info.get('version', 'N/A'),
            version_info.get('description', 'N/A'),
            f"{version_info.get('fileSize', 0) / 1024:.2f} KB",
            format_date(version_info.get('publishedAt', 'N/A'))
        ]]
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid"
        )
        
        print_info(f"包 {args.name} 的最新版本信息 (缓存)：\n\n{table}", title="版本信息")
        return True
    
    # 缓存未命中，从服务器获取
    response = api_request(
        'get',
        f"packages/{args.name}/latestVersion",
        status_message=f"[bold green]正在获取 {args.name} 的最新版本信息，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        version_info = resp.json()
        
        if 'message' in version_info and version_info['message'] == '暂无版本':
            print_info(f"包 {args.name} 暂无版本信息。", title="版本信息")
            return True
        
        # 缓存版本信息
        cache_package_info(args.name, {'latest_version': version_info})
        
        # 使用 tabulate 格式化表格
        headers = ["版本", "描述", "文件大小", "发布时间"]
        table_data = [[
            version_info.get('version', 'N/A'),
            version_info.get('description', 'N/A'),
            f"{version_info.get('fileSize', 0) / 1024:.2f} KB",
            format_date(version_info.get('publishedAt', 'N/A'))
        ]]
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid"
        )
        
        print_info(f"包 {args.name} 的最新版本信息：\n\n{table}", title="版本信息")
        return True
    
    def error_handler(error):
        print_error(f"获取失败：{error}。\n请检查包名是否正确。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def list_versions(args):
    """列出包的所有版本"""
    # 尝试从缓存获取
    cached_info = get_cached_package_info(args.name)
    if cached_info and 'versions' in cached_info:
        versions = cached_info['versions']
        
        if not versions:
            print_info(f"包 {args.name} 暂无版本记录。", title="版本列表")
            return True
        
        # 使用 tabulate 格式化表格
        headers = ["版本", "描述", "文件大小", "发布时间"]
        table_data = []

        print(versions)
        
        for ver in versions:
            table_data.append([
                ver.get('version', 'N/A'),
                ver.get('description', 'N/A'),
                f"{ver.get('fileSize', 0) / 1024:.2f} KB",
                format_date(ver.get('publishedAt', 'N/A')),
            ])
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid",
            numalign="right"
        )
        
        print_info(f"包 {args.name} 共有 {len(versions)} 个版本 (缓存)：\n\n{table}", title="版本列表")
        return True
    
    # 缓存未命中，从服务器获取
    response = api_request(
        'get',
        f"packages/{args.name}/versions",
        status_message=f"[bold green]正在获取 {args.name} 的版本列表，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        versions = resp.json()
        
        # 缓存版本信息
        cache_package_info(args.name, {'versions': versions})
        
        if not versions:
            print_info(f"包 {args.name} 暂无版本记录。", title="版本列表")
            return True
        
        # 使用 tabulate 格式化表格
        headers = ["版本", "描述", "文件大小", "发布时间"]
        table_data = []
        
        for ver in versions:
            table_data.append([
                ver.get('version', 'N/A'),
                ver.get('description', 'N/A'),
                f"{ver.get('fileSize', 0) / 1024:.2f} KB",
                format_date(ver.get('publishedAt', 'N/A')),
            ])
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid",
            numalign="right"
        )
        
        print_info(f"包 {args.name} 共有 {len(versions)} 个版本：\n\n{table}", title="版本列表")
        return True
    
    def error_handler(error):
        print_error(f"获取失败：{error}。\n请检查包名是否正确。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def batch_download(args):
    """批量下载包"""
    if not args.packages:
        print_error("请指定要下载的包列表。")
        return False
    
    packages = []
    for pkg_spec in args.packages:
        parts = pkg_spec.split('@')
        if len(parts) == 2:
            packages.append({'name': parts[0], 'version': parts[1]})
        else:
            # 如果没有指定版本，获取最新版本
            response = api_request(
                'get',
                f"packages/{parts[0]}/latestVersion",
                status_message=f"[bold green]正在获取 {parts[0]} 的最新版本信息...[/bold green]"
            )
            
            if response.status_code == 200:
                version_info = response.json()
                if 'version' in version_info:
                    packages.append({'name': parts[0], 'version': version_info['version']})
                else:
                    print_error(f"包 {parts[0]} 暂无版本，跳过下载。")
            else:
                print_error(f"获取包 {parts[0]} 的版本信息失败，跳过下载。")
    
    if not packages:
        print_error("没有有效的包可下载。")
        return False
    
    print_info(f"准备下载 {len(packages)} 个包...", title="批量下载")
    
    def download_single(pkg):
        pkg_name = pkg['name']
        pkg_version = pkg['version']
        url = f"{get_api_url()}/packages/{pkg_name}/download/{pkg_version}"
        
        console.print(f"[bold green]正在下载 {pkg_name}@{pkg_version}...[/bold green]")
        success, result = download_file(url, f"{pkg_name}-{pkg_version}.pkg")
        
        if success:
            file_size_kb = os.path.getsize(result) / 1024
            console.print(f"[green]✓ {pkg_name}@{pkg_version} 下载成功 ({file_size_kb:.2f} KB)[/green]")
            return True
        else:
            console.print(f"[red]✗ {pkg_name}@{pkg_version} 下载失败: {result}[/red]")
            return False
    
    results = batch_operation(packages, download_single, parallel=args.parallel, max_workers=args.workers)
    
    success_count = sum(1 for r in results if r)
    print_info(f"批量下载完成: {success_count}/{len(packages)} 个包下载成功。", title="下载结果")
    return success_count == len(packages)

def delete_package(args):
    """删除包"""
    headers = get_auth_headers()
    
    # 确认删除
    if not args.force and not confirm_action(f"警告：您即将删除包 {args.name}，此操作不可逆！"):
        print_info("已取消删除操作。", title="操作取消")
        return
    
    response = api_request(
        'delete',
        f"packages/{args.name}",
        headers=headers,
        status_message=f"[bold green]正在删除包 {args.name}，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        print_success(f"包 {args.name} 已成功删除。\n该包的所有版本和相关文件已被永久移除。")
        return True
    
    def error_handler(error):
        print_error(f"删除失败：{error}。\n请检查包名是否正确或确认您有权限删除此包。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def batch_delete_packages(args):
    """批量删除包"""
    headers = get_auth_headers()
    
    if not args.packages:
        print_error("请指定要删除的包列表。")
        return False
    
    # 确认删除
    if not args.force:
        package_list = ", ".join(args.packages)
        if not confirm_action(f"警告：您即将删除以下包：{package_list}，此操作不可逆！"):
            print_info("已取消删除操作。", title="操作取消")
            return False
    
    print_info(f"准备删除 {len(args.packages)} 个包...", title="批量删除")
    
    def delete_single(pkg_name):
        console.print(f"[bold green]正在删除包 {pkg_name}...[/bold green]")
        
        response = api_request(
            'delete',
            f"packages/{pkg_name}",
            headers=headers
        )
        
        def success_handler(resp):
            console.print(f"[green]✓ {pkg_name} 删除成功[/green]")
            return True
        
        def error_handler(error):
            try:
                error = response.json().get('error', '未知错误')
            except:
                error = f"状态码: {response.status_code}"
            console.print(f"[red]✗ {pkg_name} 删除失败: {error}[/red]")
            return False
        
        return handle_response(response, success_handler, error_handler)

    results = batch_operation(args.packages, delete_single, parallel=args.parallel, max_workers=args.workers)
    
    success_count = sum(1 for r in results if r)
    print_info(f"批量删除完成: {success_count}/{len(args.packages)} 个包删除成功。", title="删除结果")
    return success_count == len(args.packages)

def config_cmd(args):
    """配置管理"""
    config = load_config()
    
    if args.show:
        # 显示当前配置
        headers = ["配置项", "值"]
        table_data = [
            ["API URL", config['settings']['api_url']]
        ]
        
        if 'user_id' in config['auth']:
            table_data.append(["用户 ID", config['auth']['user_id']])
            table_data.append(["API Key", config['auth']['api_key'][:6] + "..." if config['auth']['api_key'] else "未设置"])
            table_data.append(["用户名", config['user_info'].get('username', '未知')])
        else:
            table_data.append(["用户 ID", "未登录"])
            table_data.append(["API Key", "未登录"])
            table_data.append(["用户名", "未登录"])
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="fancy_grid"
        )
        
        print_info(f"当前配置信息：\n\n{table}", title="配置详情")
    elif args.set_api:
        # 设置 API URL
        config['settings']['api_url'] = args.set_api
        save_config(config)
        print_success(f"API URL 已成功设置为：{args.set_api}")
    elif args.clear_cache:
        # 清除缓存
        if os.path.exists(CACHE_DIR):
            import shutil
            shutil.rmtree(CACHE_DIR)
            ensure_path_exists(CACHE_DIR)
            print_success("缓存已成功清除。")
        else:
            print_info("缓存目录不存在，无需清除。")

def delete_account(args):
    """删除用户账户"""
    headers = get_auth_headers()
    config = load_config()
    username = config['user_info'].get('username', '用户')
    
    # 确认删除
    if not args.force:
        console.print(f"[bold red]警告：您即将删除您的账户，此操作不可逆！所有您发布的包将无法再被管理。[/bold red]")
        confirm = input("请输入您的用户名以确认删除账户: ")
        
        if confirm != username:
            print_info("用户名不匹配，已取消删除操作。", title="操作取消")
            return
    
    response = api_request(
        'delete',
        'auth/',
        headers=headers,
        status_message="[bold green]正在删除您的账户，请稍候...[/bold green]"
    )
    
    def success_handler(resp):
        # 清除本地配置
        clear_auth_info()
        print_success(f"尊敬的 {username}，您的账户已成功删除。\n感谢您曾经使用我们的服务。")
        return True
    
    def error_handler(error):
        print_error(f"删除账户失败：{error}。\n请稍后再试或联系管理员获取帮助。")
        return False
    
    return handle_response(response, success_handler, error_handler)

def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 命令行工具 v{APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 注册命令
    register_parser = subparsers.add_parser("register", help="注册新用户")
    register_parser.add_argument("-u", "--username", help="用户名")
    register_parser.add_argument("-p", "--password", help="密码")
    register_parser.set_defaults(func=register)
    
    # 登录命令
    login_parser = subparsers.add_parser("login", help="用户登录")
    login_parser.add_argument("-u", "--username", help="用户名")
    login_parser.add_argument("-p", "--password", help="密码")
    login_parser.set_defaults(func=login)
    
    # 退出登录命令
    logout_parser = subparsers.add_parser("logout", help="退出登录")
    logout_parser.set_defaults(func=logout)
    
    # 发布包命令
    publish_parser = subparsers.add_parser("publish", help="发布包")
    publish_parser.add_argument("name", help="包名")
    publish_parser.add_argument("version", help="版本号")
    publish_parser.add_argument("description", help="包描述")
    publish_parser.add_argument("file", help="包文件路径")
    publish_parser.set_defaults(func=publish)
    
    # 下载包命令
    download_parser = subparsers.add_parser("download", help="下载包")
    download_parser.add_argument("name", help="包名")
    download_parser.add_argument("version", help="版本号")
    download_parser.add_argument("-o", "--output", help="输出文件路径")
    download_parser.set_defaults(func=download)
    
    # 批量下载命令
    batch_download_parser = subparsers.add_parser("batch-download", help="批量下载包")
    batch_download_parser.add_argument("packages", nargs="+", help="包规格列表，格式: 包名[@版本]")
    batch_download_parser.add_argument("-p", "--parallel", action="store_true", help="并行下载")
    batch_download_parser.add_argument("-w", "--workers", type=int, default=4, help="并行下载的工作线程数")
    batch_download_parser.set_defaults(func=batch_download)
    
    # 搜索包命令
    search_parser = subparsers.add_parser("search", help="搜索包")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.set_defaults(func=search)
    
    # 获取最新版本命令
    version_parser = subparsers.add_parser("version", help="获取包的最新版本")
    version_parser.add_argument("name", help="包名")
    version_parser.set_defaults(func=get_latest_version)
    
    # 列出所有版本命令
    list_parser = subparsers.add_parser("list", help="列出包的所有版本")
    list_parser.add_argument("name", help="包名")
    list_parser.set_defaults(func=list_versions)
    
    # 删除包命令
    delete_parser = subparsers.add_parser("delete", help="删除包")
    delete_parser.add_argument("name", help="包名")
    delete_parser.add_argument("-f", "--force", action="store_true", help="强制删除，不提示确认")
    delete_parser.set_defaults(func=delete_package)

    # 批量删除包命令
    batch_delete_parser = subparsers.add_parser("batch-delete", help="批量删除包")
    batch_delete_parser.add_argument("packages", nargs="+", help="包规格列表，格式: 包名")
    batch_delete_parser.add_argument("-p", "--parallel", action="store_true", help="并行删除")
    batch_delete_parser.add_argument("-w", "--workers", type=int, default=4, help="并行删除的工作线程数")
    batch_delete_parser.set_defaults(func=batch_delete_packages)
    
    # 配置命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("--show", action="store_true", help="显示当前配置")
    config_parser.add_argument("--set-api", help="设置 API URL")
    config_parser.add_argument("--clear-cache", action="store_true", help="清除缓存")
    config_parser.set_defaults(func=config_cmd)
    
    # 删除账户命令
    delete_account_parser = subparsers.add_parser("delete-account", help="删除用户账户")
    delete_account_parser.add_argument("-f", "--force", action="store_true", help="强制删除，不提示确认")
    delete_account_parser.set_defaults(func=delete_account)
    
    args = parser.parse_args()
    
    if not args.command:
        print_welcome()
        parser.print_help()
        return
    
    args.func(args)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]操作已取消，感谢您的使用！[/bold yellow]")
        sys.exit(0)

