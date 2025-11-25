#!/usr/bin/env python3
"""
Vortinet CLI - 交互式命令行工具

主要功能:
1. 自动会话检测和智能选择
2. 支持节点名简写和批量打开终端
3. readline 集成：历史记录、Tab 补全
4. 丰富的信息展示：拓扑、链路、节点详情
5. rich 库美化输出

使用方式:
    # 交互模式
    sudo -E .venv/bin/python vortinet_cli.py
    
    # 直接执行命令
    sudo -E .venv/bin/python vortinet_cli.py shell H1 H2 H3
    sudo -E .venv/bin/python vortinet_cli.py topology
"""

import sys
import os
import argparse
import docker
import subprocess
import readline
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from vortinet.utils import ResourceTracker, cleanup_all, list_sessions

# rich 库用于美化输出
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.layout import Layout
from rich import box
from rich.text import Text

# 黑白极客风格配色
GEEK_COLORS = {
    'primary': 'bright_white',
    'secondary': 'white',
    'accent': 'bright_cyan',
    'dim': 'dim white',
    'success': 'bright_white',
    'error': 'bright_red',
    'warning': 'bright_yellow',
    'info': 'bright_cyan'
}

GEEK_LOGO = """[bright_white]
██╗   ██╗ ██████╗ ██████╗ ████████╗██╗███╗   ██╗███████╗████████╗
██║   ██║██╔═══██╗██╔══██╗╚══██╔══╝██║████╗  ██║██╔════╝╚══██╔══╝
██║   ██║██║   ██║██████╔╝   ██║   ██║██╔██╗ ██║█████╗     ██║   
╚██╗ ██╔╝██║   ██║██╔══██╗   ██║   ██║██║╚██╗██║██╔══╝     ██║   
 ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ██║██║ ╚████║███████╗   ██║   
  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   
[/bright_white]"""

# 延迟导入 DeploymentController
DeploymentController = None


def _import_deployment_controller():
    """延迟导入 DeploymentController"""
    global DeploymentController
    if DeploymentController is None:
        from vortinet.deployment import DeploymentController as DC
        DeploymentController = DC
    return DeploymentController


class CommandCompleter:
    """命令补全器"""
    
    def __init__(self, cli):
        self.cli = cli
        self.commands = [
            'help', 'quit', 'exit', 'clear',
            'list', 'sessions', 'switch', 'status', 'topology', 'links', 'info',
            'shell', 'exec', 'ping', 'ip', 'interfaces', 'route', 'routes',
            'cleanup'
        ]
    
    def complete(self, text, state):
        """补全函数"""
        line = readline.get_line_buffer()
        tokens = line.split()
        
        # 补全命令
        if len(tokens) <= 1:
            matches = [cmd for cmd in self.commands if cmd.startswith(text)]
            if state < len(matches):
                return matches[state] + ' '
            return None
        
        # 补全节点名
        cmd = tokens[0]
        if cmd in ['shell', 'exec', 'ping', 'ip', 'interfaces', 'route', 'routes', 'info']:
            node_names = self._get_node_names()
            matches = [name for name in node_names if name.startswith(text)]
            if state < len(matches):
                return matches[state] + ' '
        
        return None
    
    def _get_node_names(self) -> List[str]:
        """获取当前会话的节点名"""
        if self.cli.controller and self.cli.controller.deployed:
            return list(self.cli.controller.topology.nodes.keys())
        elif self.cli.current_session:
            # 从容器名中提取节点名
            try:
                containers = self.cli.client.containers.list(
                    all=True,
                    filters={'label': f'vortinet.session={self.cli.current_session}'}
                )
                prefix = self.cli.current_session[:6]
                return [c.name.replace(f"{prefix}-", "") for c in containers]
            except Exception:
                return []
        return []


class VortinetCLI:
    """Vortinet 命令行界面"""
    
    def __init__(self, controller=None):
        """
        初始化 CLI
        
        Args:
            controller: DeploymentController 实例（可选）
        """
        self.client = docker.from_env()
        self.controller = controller
        self.current_session = controller.resource_tracker.session_id if controller else None
        self.console = Console()
        self.interactive = False  # 是否处于交互模式
        
        # 配置 readline
        self._setup_readline()
    
    def _setup_readline(self):
        """配置 readline 支持历史和补全"""
        # 历史文件
        histfile = os.path.expanduser("~/.vortinet_history")
        try:
            readline.read_history_file(histfile)
            readline.set_history_length(1000)
        except FileNotFoundError:
            pass
        
        # 保存历史
        import atexit
        atexit.register(readline.write_history_file, histfile)
        
        # 配置补全
        completer = CommandCompleter(self)
        readline.set_completer(completer.complete)
        readline.parse_and_bind('tab: complete')
        
        # 配置 readline 行为
        readline.parse_and_bind('set editing-mode emacs')
        readline.parse_and_bind('set show-all-if-ambiguous on')
    
    def interactive_mode(self):
        """交互式模式主循环"""
        self.interactive = True
        
        # 显示欢迎信息
        self._show_welcome()
        
        # 自动选择会话
        if not self.controller:
            self._auto_select_session()
        
        # 主循环
        while True:
            try:
                # 构建提示符
                prompt = self._get_prompt()
                line = input(prompt).strip()
                
                if not line:
                    continue
                
                self.execute_command(line)
            
            except KeyboardInterrupt:
                self.console.print("\n[bright_yellow][!][/bright_yellow] Press 'quit' to exit")
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[bright_red][X][/bright_red] Error: {e}")
    
    def _show_welcome(self):
        """显示欢迎信息 - 黑白极客风格"""
        # 获取系统状态
        sessions = ResourceTracker.list_all_sessions(self.client)
        total_containers = sum(
            len(self.client.containers.list(all=True, filters={'label': f'vortinet.session={sid}'}))
            for sid in sessions.keys()
        )
        
        welcome_content = (
            f"{GEEK_LOGO}\n"
            f"[bright_white]              NETWORK TOPOLOGY CONTROL SYSTEM[/bright_white]\n"
            f"[dim white]                   [ AUTHENTICATED ][/dim white]\n\n"
            f"[white] > System Status: [bright_white][OPERATIONAL][/bright_white][/white]\n"
            f"[white] > Sessions Active: [bright_cyan]{len(sessions)}[/bright_cyan][/white]\n"
            f"[white] > Containers Running: [bright_cyan]{total_containers}[/bright_cyan][/white]\n\n"
            f"[dim white] [↑↓] Navigate History  [TAB] Auto-Complete  [CTRL+C] Exit[/dim white]"
        )
        
        welcome = Panel(
            welcome_content,
            border_style="white",
            box=box.DOUBLE,
            padding=(1, 2)
        )
        self.console.print(welcome)
        self.console.print()
    
    def _auto_select_session(self):
        """自动选择会话"""
        sessions = ResourceTracker.list_all_sessions(self.client)
        
        if not sessions:
            if self.interactive:
                self.console.print("[bright_yellow][!][/bright_yellow] No active sessions found")
                self.console.print("[dim white]    Run example scripts to create sessions[/dim white]\n")
            return
        
        if len(sessions) == 1:
            # 唯一会话，自动选择
            session_id = list(sessions.keys())[0]
            self.current_session = session_id
            if self.interactive:
                info = sessions[session_id]
                self.console.print(f"[bright_white][√][/bright_white] Auto-selected session: [bright_cyan]{info['project']}[/bright_cyan]")
                self.console.print(f"[white]    Session ID: [dim white]{session_id[:16]}...[/dim white][/white]\n")
        else:
            # 多个会话
            if self.interactive:
                self._select_from_multiple_sessions(sessions)
            else:
                # 非交互模式，选择第一个
                session_id = list(sessions.keys())[0]
                self.current_session = session_id
    
    def _select_from_multiple_sessions(self, sessions: Dict):
        """从多个会话中选择 - 黑白极客风格"""
        table = Table(title="[bright_white]┌─[ ACTIVE SESSIONS ]────────────────────────────────────────┐[/bright_white]", 
                     box=box.SIMPLE, show_header=True, header_style="bright_white")
        table.add_column("#", style="bright_cyan", justify="center", width=3)
        table.add_column("PROJECT", style="bright_white", width=20)
        table.add_column("SESSION_ID", style="dim white", width=15)
        table.add_column("CONTAINERS", justify="center", style="bright_white", width=12)
        table.add_column("TIMESTAMP", style="dim white", width=12)
        
        session_list = list(sessions.items())
        for idx, (session_id, info) in enumerate(session_list, 1):
            # 直接从 Docker API 查询容器数
            containers = self.client.containers.list(
                all=True,
                filters={'label': f'vortinet.session={session_id}'}
            )
            container_count = len(containers)
            
            # 容器数显示为进度条风格
            container_bar = "[" + "█" * container_count + "·" * (5 - min(container_count, 5)) + "]"
            table.add_row(
                str(idx),
                info['project'],
                session_id[:6] + "...",
                f"{container_bar} {container_count}",
                info['timestamp'][11:19]
            )
        
        self.console.print(table)
        self.console.print("[bright_white]└────────────────────────────────────────────────────────────┘[/bright_white]")
        self.console.print()
        
        # 临时禁用历史记录
        old_length = readline.get_current_history_length()
        
        choice = Prompt.ask(
            "[white]>>[/white] Select session",
            default='1',
            show_choices=False
        )
        
        # 删除这次输入的历史记录
        new_length = readline.get_current_history_length()
        if new_length > old_length:
            readline.remove_history_item(new_length - 1)
        
        if choice != 'skip':
            idx = int(choice) - 1
            session_id = session_list[idx][0]
            self.current_session = session_id
            self.console.print(f"[bright_white][√][/bright_white] Session switched → [bright_cyan]{sessions[session_id]['project']}[/bright_cyan]\n")
    
    def _get_prompt(self) -> str:
        """获取命令提示符 - 黑白极客风格"""
        if self.controller:
            project = self.controller.project_name
            return f"\033[1;37mvortinet\033[0m://\033[1;36m{project}\033[0m $ "
        elif self.current_session:
            sessions = ResourceTracker.list_all_sessions(self.client)
            if self.current_session in sessions:
                project = sessions[self.current_session]['project']
                return f"\033[1;37mvortinet\033[0m://\033[1;36m{project}\033[0m $ "
        
        return "\033[1;37mvortinet\033[0m://\033[1;90mroot@system\033[0m $ "
    
    def execute_command(self, line: str):
        """执行命令"""
        parts = line.split()
        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        # 命令映射
        commands = {
            'help': self.cmd_help,
            'quit': self.cmd_quit,
            'exit': self.cmd_quit,
            'clear': self.cmd_clear,
            'list': self.cmd_list,
            'sessions': self.cmd_sessions,
            'switch': self.cmd_switch,
            'status': self.cmd_status,
            'topology': self.cmd_topology,
            'links': self.cmd_links,
            'info': self.cmd_info,
            'shell': self.cmd_shell,
            'exec': self.cmd_exec,
            'ping': self.cmd_ping,
            'ip': self.cmd_ip,
            'interfaces': self.cmd_ip,
            'route': self.cmd_route,
            'routes': self.cmd_route,
            'cleanup': self.cmd_cleanup,
        }
        
        if cmd in commands:
            commands[cmd](args)
        else:
            self.console.print(f"[red]未知命令: {cmd}[/red]")
            self.console.print("[dim]输入 'help' 查看可用命令[/dim]")
    
    def cmd_help(self, args):
        """显示帮助信息"""
        table = Table(title="[bright_white]AVAILABLE COMMANDS[/bright_white]", box=box.ROUNDED, show_header=True, header_style="bright_white")
        table.add_column("COMMAND", style="bright_white", width=20)
        table.add_column("DESCRIPTION", style="white")
        table.add_column("EXAMPLE", style="dim white")
        
        commands_help = [
            ("会话管理", "", ""),
            ("list", "列出节点或会话", "list, list sessions"),
            ("sessions", "显示所有会话", "sessions"),
            ("switch [session]", "切换会话", "switch, switch 1"),
            ("status", "显示当前状态", "status"),
            ("topology", "显示拓扑结构", "topology"),
            ("links", "显示链路信息", "links"),
            ("info <node>", "显示节点详情", "info H1"),
            ("", "", ""),
            ("节点操作", "", ""),
            ("shell <nodes...>", "打开节点终端（支持多个）", "shell H1 H2 H3"),
            ("exec <node> <cmd>", "在节点中执行命令", 'exec H1 "ip addr"'),
            ("", "", ""),
            ("网络测试", "", ""),
            ("ping <src> <dst>", "测试连通性", "ping H1 10.10.0.5"),
            ("ip <node>", "显示 IP 配置", "ip H1"),
            ("route <node>", "显示路由表", "route H1"),
            ("", "", ""),
            ("资源管理", "", ""),
            ("cleanup [session]", "清理资源", "cleanup, cleanup 1, cleanup basic_topo"),
            ("", "", ""),
            ("其他", "", ""),
            ("help", "显示此帮助", "help"),
            ("clear", "清屏", "clear"),
            ("quit/exit", "退出 CLI", "quit"),
        ]
        
        for cmd, desc, example in commands_help:
            if not desc:  # 分类标题
                table.add_row(f"[bold yellow]{cmd}[/bold yellow]", "", "")
            else:
                table.add_row(cmd, desc, example)
        
        self.console.print(table)
        self.console.print()
        self.console.print("[bold]提示:[/bold]")
        self.console.print("  • 使用 [bright_cyan]↑↓[/bright_cyan] 键浏览历史命令")
        self.console.print("  • 使用 [bright_cyan]Tab[/bright_cyan] 键自动补全命令和节点名")
        self.console.print("  • [bright_cyan]shell[/bright_cyan] 命令支持批量打开多个终端窗口")
        self.console.print()
    
    def cmd_quit(self, args):
        """退出 CLI"""
        self.console.print("[bright_white]再见！[/bright_white]")
        sys.exit(0)
    
    def cmd_clear(self, args):
        """清屏"""
        os.system('clear' if os.name != 'nt' else 'cls')
    
    def cmd_list(self, args):
        """列出节点或会话"""
        what = args[0] if args else "nodes"
        
        if what == "nodes":
            self._list_nodes()
        elif what == "sessions":
            self.cmd_sessions([])
        else:
            self.console.print(f"[red]未知选项: {what}[/red]")
            self.console.print("[dim]用法: list [nodes|sessions][/dim]")
    
    def _list_nodes(self):
        """列出节点"""
        if not self.controller and not self.current_session:
            self.console.print("[bright_yellow][!][/bright_yellow] No session selected")
            return
        
        # 获取节点信息
        if self.controller and self.controller.deployed:
            nodes = self.controller.topology.nodes
            session_id = self.controller.resource_tracker.session_id
        else:
            # 从容器中获取
            nodes = self._get_nodes_from_containers()
            session_id = self.current_session
        
        if not nodes:
            self.console.print("[yellow]没有找到节点[/yellow]")
            return
        
        # 创建表格
        table = Table(
            title="[bright_white]NODE LIST[/bright_white]",
            box=box.HORIZONTALS,
            show_header=True,
            header_style="bright_white",
            title_style="bright_white",
            border_style="bright_white"
        )
        table.add_column("NODE", style="bright_white", width=15)
        table.add_column("TYPE", style="dim white", width=12)
        table.add_column("CONTAINER", style="dim white", width=12)
        table.add_column("IP ADDRESS", style="bright_cyan", width=18)
        table.add_column("STATUS", justify="center", width=8)
        
        prefix = session_id[:6] if session_id else ""
        
        for node_name, node in nodes.items():
            container_name = f"{prefix}-{node_name}" if prefix else node_name
            
            try:
                container = self.client.containers.get(container_name)
                container_id = container.short_id
                status = "🟢" if container.status == "running" else "🔴"
                
                # 获取 IP
                ips = []
                if self.controller:
                    # 从拓扑获取 IP
                    for iface in node.interfaces.values():
                        if hasattr(iface, 'ip_address') and iface.ip_address:
                            ips.append(f"{iface.ip_address}/{iface.subnet.prefixlen if hasattr(iface, 'subnet') else '24'}")
                
                # 如果拓扑中没有 IP，从容器网络中获取
                if not ips:
                    try:
                        # 执行命令获取 IP（使用更简单的方式）
                        exit_code, output = container.exec_run(
                            ["sh", "-c", "ip -4 addr show eth0 | grep inet | awk '{print $2}'"],
                            stdout=True,
                            stderr=False
                        )
                        if exit_code == 0 and output:
                            ip_line = output.decode('utf-8').strip()
                            if ip_line and ip_line != "N/A":
                                ips.append(ip_line)
                    except Exception:
                        pass
                
                ip_str = ", ".join(ips) if ips else "N/A"
                node_type = node.node_type if hasattr(node, 'node_type') else "host"
                
                table.add_row(node_name, node_type.upper(), container_id, ip_str, status)
            except docker.errors.NotFound:
                table.add_row(node_name, "UNKNOWN", "Not Found", "N/A", "🔴")
        
        self.console.print(table)
        self.console.print()
    
    def _get_nodes_from_containers(self) -> Dict:
        """从容器中获取节点信息"""
        if not self.current_session:
            return {}
        
        try:
            containers = self.client.containers.list(
                all=True,
                filters={'label': f'vortinet.session={self.current_session}'}
            )
            
            prefix = self.current_session[:6]
            nodes = {}
            for c in containers:
                node_name = c.name.replace(f"{prefix}-", "")
                nodes[node_name] = type('Node', (), {'node_type': 'host', 'interfaces': {}})()
            
            return nodes
        except Exception as e:
            self.console.print(f"[red]获取节点失败: {e}[/red]")
            return {}
    
    def cmd_sessions(self, args):
        """显示所有会话 - 黑白极客风格"""
        sessions = ResourceTracker.list_all_sessions(self.client)
        
        if not sessions:
            self.console.print("[bright_yellow][!][/bright_yellow] No active sessions")
            return
        
        table = Table(
            title="[bright_white]ACTIVE SESSIONS[/bright_white]",
            box=box.HORIZONTALS,
            show_header=True,
            header_style="bright_white",
            title_style="bright_white",
            border_style="bright_white"
        )
        table.add_column("PROJECT", style="bright_white", width=20)
        table.add_column("SESSION", style="dim white", width=18)
        table.add_column("STATUS", justify="center", style="bright_white", width=12)
        table.add_column("CONTAINERS", justify="center", style="bright_white", width=12)
        table.add_column("CURRENT", justify="center", width=8)
        
        for session_id, info in sessions.items():
            is_current = "[bright_white]▶[/bright_white]" if session_id == self.current_session else ""
            # 获取实际运行的容器数
            try:
                containers = self.client.containers.list(
                    all=True,
                    filters={'label': f'vortinet.session={session_id}'}
                )
                container_count = len(containers)
            except Exception:
                container_count = info.get('container_count', 0)
            
            status = "[bright_white][RUNNING][/bright_white]"
            container_bar = "[" + "█" * min(container_count, 5) + "·" * (5 - min(container_count, 5)) + "]"
            table.add_row(
                info['project'],
                session_id[:16] + "...",
                status,
                f"{container_bar} {container_count}",
                is_current
            )
        
        self.console.print(table)
        self.console.print()
    
    def cmd_switch(self, args):
        """切换会话"""
        sessions = ResourceTracker.list_all_sessions(self.client)
        
        if not sessions:
            self.console.print("[bright_yellow][!][/bright_yellow] No sessions available")
            return
        
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
            if self.current_session == session_id:
                self.console.print("[bright_yellow][!][/bright_yellow] Already in the only session")
            else:
                self.current_session = session_id
                info = sessions[session_id]
                self.console.print(f"[bright_white][√][/bright_white] Session switched → [bright_cyan]{info['project']}[/bright_cyan]")
            return
        
        if args:
            # 指定了会话序号或ID
            choice = args[0]
            session_list = list(sessions.items())
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(session_list):
                    session_id, info = session_list[idx]
                    self.current_session = session_id
                    self.console.print(f"[bright_white][√][/bright_white] Session switched → [bright_cyan]{info['project']}[/bright_cyan]\n")
                else:
                    self.console.print(f"[bright_red][X][/bright_red] Invalid session number: {choice}")
            else:
                # 尝试匹配会话ID或项目名
                matched = None
                for sid, sinfo in sessions.items():
                    if sid.startswith(choice) or sinfo['project'] == choice:
                        matched = (sid, sinfo)
                        break
                
                if matched:
                    self.current_session = matched[0]
                    self.console.print(f"[bright_white][√][/bright_white] Session switched → [bright_cyan]{matched[1]['project']}[/bright_cyan]\n")
                else:
                    self.console.print(f"[red]找不到匹配的会话: {choice}[/red]")
        else:
            # 显示会话列表并让用户选择
            self._select_from_multiple_sessions(sessions)
        
        self.console.print()
    
    def cmd_status(self, args):
        """显示当前状态"""
        if self.controller:
            info = Panel.fit(
                f"[bold]项目名称:[/bold] {self.controller.project_name}\n"
                f"[bold]会话 ID:[/bold] {self.controller.resource_tracker.session_id[:16]}...\n"
                f"[bold]已部署:[/bold] {'是' if self.controller.deployed else '否'}\n"
                f"[bold]节点数:[/bold] {len(self.controller.topology.nodes) if self.controller.deployed else 0}\n"
                f"[bold]链路数:[/bold] {len(self.controller.topology.links) if self.controller.deployed else 0}",
                title="部署状态",
                border_style="green"
            )
            self.console.print(info)
        elif self.current_session:
            sessions = ResourceTracker.list_all_sessions(self.client)
            if self.current_session in sessions:
                info_data = sessions[self.current_session]
                info = Panel.fit(
                    f"[bold]项目名称:[/bold] {info_data['project']}\n"
                    f"[bold]会话 ID:[/bold] {self.current_session[:16]}...\n"
                    f"[bold]容器数:[/bold] {info_data.get('container_count', 0)}\n"
                    f"[bold]创建时间:[/bold] {info_data['timestamp'][:19]}",
                    title="会话状态",
                    border_style="green"
                )
                self.console.print(info)
        else:
            self.console.print("[yellow]未连接到任何会话[/yellow]")
        
        self.console.print()
    
    def cmd_topology(self, args):
        """显示拓扑结构"""
        if not self.controller or not self.controller.deployed:
            # 从容器标签重建拓扑
            if not self.current_session:
                self.console.print("[yellow]未选择会话[/yellow]")
                return
            
            containers = self.client.containers.list(
                all=True,
                filters={'label': f'vortinet.session={self.current_session}'}
            )
            
            if not containers:
                self.console.print("[yellow]当前会话没有容器[/yellow]")
                return
            
            # 构建树形结构
            sessions = ResourceTracker.list_all_sessions(self.client)
            project_name = sessions.get(self.current_session, {}).get('project', 'Unknown')
            self.console.print(f"\n[bright_white]┌─[ TOPOLOGY TREE ]──────────────────────────────────────────┐[/bright_white]")
            tree = Tree(f"[bright_white]{project_name}[/bright_white]")
            
            # 查询 OVS bridges（交换机）
            ovs_switches = []
            try:
                import subprocess
                result = subprocess.run(
                    ['ovs-vsctl', 'list-br'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    session_prefix = self.current_session[:6]
                    for bridge_name in result.stdout.strip().split('\n'):
                        if bridge_name and bridge_name.startswith(session_prefix):
                            # 提取交换机名（去除前缀）
                            switch_name = bridge_name[len(session_prefix)+1:]  # +1 for '-'
                            if switch_name.startswith('ovs-'):
                                switch_name = switch_name[4:]  # 去除 'ovs-' 前缀
                            ovs_switches.append((bridge_name, switch_name))
            except Exception:
                pass
            
            # 显示交换机
            if ovs_switches:
                switch_branch = tree.add(f"[bright_yellow]SWITCHES[/bright_yellow] [dim white]({len(ovs_switches)})[/dim white]")
                for bridge_name, switch_name in ovs_switches:
                    switch_branch.add(f"🔀 [bright_white]{switch_name}[/bright_white] [dim white]OVS_SWITCH[/dim white]")
            
            # 按节点名分组
            node_branch = tree.add(f"[white]HOSTS[/white] [dim white]({len(containers)})[/dim white]")
            for container in sorted(containers, key=lambda c: c.name):
                # 从容器标签获取原始节点名（不带前缀），如果标签为空则从容器名提取
                node_name = container.labels.get('vortinet.node_name', '')
                if not node_name:
                    # 从容器名提取节点名（去除session前缀）
                    container_name = container.name
                    if container_name.startswith('/'):
                        container_name = container_name[1:]
                    # 假设格式为 prefix-NodeName
                    parts = container_name.split('-', 1)
                    node_name = parts[1] if len(parts) > 1 else container_name
                
                node_type = container.labels.get('vortinet.node_type', 'host').upper()
                status = "🟢" if container.status == 'running' else "🔴"
                
                # 获取 IP
                try:
                    exit_code, output = container.exec_run(
                        ["sh", "-c", "ip -4 addr show eth0 | grep inet | awk '{print $2}'"],
                        stdout=True,
                        stderr=False
                    )
                    ip = output.decode('utf-8').strip() if exit_code == 0 else "N/A"
                except:
                    ip = "N/A"
                
                type_label = f"[dim white]{node_type.upper()}[/dim white]"
                node_branch.add(f"{status} [bright_white]{node_name}[/bright_white] {type_label} ── [bright_cyan]{ip}[/bright_cyan]")
            
            self.console.print(tree)
            self.console.print("[bright_white]└────────────────────────────────────────────────────────────┘[/bright_white]\n")
            return
        
        topo = self.controller.topology
        
        # 使用 Tree 显示拓扑
        tree = Tree(f"[bright_white]拓扑: {topo.name}[/bright_white]")
        
        # 按类型分组节点
        switches = []
        hosts = []
        for name, node in topo.nodes.items():
            if 'switch' in node.node_type:
                switches.append((name, node))
            else:
                hosts.append((name, node))
        
        # 显示交换机及其连接
        if switches:
            switch_branch = tree.add("[bold yellow]交换机[/bold yellow]")
            for sw_name, sw_node in switches:
                sw_tree = switch_branch.add(f"[bright_white]{sw_name}[/bright_white] ({sw_node.node_type})")
                
                # 查找连接到此交换机的主机
                for link in topo.links.values():
                    if hasattr(link, 'switch') and link.switch.name == sw_name:
                        connected_hosts = [iface.node.name for iface in link.interfaces 
                                          if iface.node.name != sw_name]
                        for host_name in connected_hosts:
                            host_node = topo.nodes[host_name]
                            # 从 link 获取 subnet
                            ips = []
                            for iface in host_node.interfaces.values():
                                if hasattr(iface, 'ip_address') and iface.ip_address:
                                    if iface.link and hasattr(iface.link, 'subnet'):
                                        ips.append(f"{iface.ip_address}/{iface.link.subnet.prefixlen}")
                                    else:
                                        ips.append(str(iface.ip_address))
                            ip_str = ips[0] if ips else "N/A"
                            sw_tree.add(f"[bright_cyan]{host_name}[/bright_cyan] - {ip_str}")
        
        # 显示点对点链路
        p2p_links = [link for link in topo.links.values() 
                     if not hasattr(link, 'switch') or link.switch is None]
        if p2p_links:
            p2p_branch = tree.add("[bold yellow]点对点链路[/bold yellow]")
            for link in p2p_links:
                nodes = [iface.node.name for iface in link.interfaces]
                p2p_branch.add(f"[bright_cyan]{' ↔ '.join(nodes)}[/bright_cyan]")
        
        self.console.print(tree)
        self.console.print()
    
    def cmd_links(self, args):
        """显示链路信息"""
        if not self.controller or not self.controller.deployed:
            # 从容器标签重建链路信息
            if not self.current_session:
                self.console.print("[yellow]未选择会话[/yellow]")
                return
            
            containers = self.client.containers.list(
                all=True,
                filters={'label': f'vortinet.session={self.current_session}'}
            )
            
            if not containers:
                self.console.print("[yellow]当前会话没有容器[/yellow]")
                return
            
            # 创建链路表
            table = Table(title="网络连接", box=box.ROUNDED)
            table.add_column("节点", style="cyan")
            table.add_column("类型", style="green")
            table.add_column("IP 地址", style="yellow")
            table.add_column("网络", style="dim")
            
            for container in sorted(containers, key=lambda c: c.labels.get('vortinet.node_name', '')):
                node_name = container.labels.get('vortinet.node_name', container.name)
                node_type = container.labels.get('vortinet.type', 'host')
                
                # 获取 IP 和网络
                try:
                    exit_code, output = container.exec_run(
                        ["sh", "-c", "ip -4 addr show eth0 | grep inet | awk '{print $2}'"],
                        stdout=True,
                        stderr=False
                    )
                    ip = output.decode('utf-8').strip() if exit_code == 0 else "N/A"
                except:
                    ip = "N/A"
                
                # 获取连接的网络
                networks = list(container.attrs['NetworkSettings']['Networks'].keys())
                network_str = ", ".join(networks) if networks else "N/A"
                
                table.add_row(node_name, node_type, ip, network_str)
            
            self.console.print(table)
            self.console.print()
            return
        
        topo = self.controller.topology
        
        table = Table(title="链路列表", box=box.ROUNDED)
        table.add_column("链路名", style="cyan")
        table.add_column("类型", style="green")
        table.add_column("连接节点", style="yellow")
        table.add_column("子网", style="dim")
        
        for link_name, link in topo.links.items():
            if hasattr(link, 'switch') and link.switch:
                link_type = "交换链路"
                nodes = [link.switch.name] + [iface.node.name for iface in link.interfaces 
                                              if iface.node.name != link.switch.name]
                subnet = str(link.subnet) if hasattr(link, 'subnet') else "N/A"
            else:
                link_type = "点对点"
                nodes = [iface.node.name for iface in link.interfaces]
                subnet = str(link.subnet) if hasattr(link, 'subnet') else "N/A"
            
            table.add_row(link_name, link_type, " ↔ ".join(nodes), subnet)
        
        self.console.print(table)
        self.console.print()
    
    def cmd_info(self, args):
        """显示节点详情"""
        if not args:
            self.console.print("[red]用法: info <node>[/red]")
            return
        
        node_name = args[0]
        
        if self.controller and self.controller.deployed:
            if node_name not in self.controller.topology.nodes:
                self.console.print(f"[red]节点 {node_name} 不存在[/red]")
                return
            
            node = self.controller.topology.nodes[node_name]
            container_name = f"{self.controller.resource_tracker.session_id[:6]}-{node_name}"
        else:
            container_name = f"{self.current_session[:6]}-{node_name}" if self.current_session else node_name
        
        try:
            container = self.client.containers.get(container_name)
            
            # 构建信息面板
            info_text = f"[bold]节点名称:[/bold] {node_name}\n"
            info_text += f"[bold]容器 ID:[/bold] {container.id[:12]}\n"
            info_text += f"[bold]状态:[/bold] {container.status}\n"
            
            if self.controller and self.controller.deployed:
                info_text += f"[bold]类型:[/bold] {node.node_type}\n"
                info_text += f"[bold]接口:[/bold]\n"
                for iface_name, iface in node.interfaces.items():
                    if hasattr(iface, 'ip_address') and iface.ip_address:
                        info_text += f"  • {iface_name}: {iface.ip_address}/{iface.subnet.prefixlen}\n"
                    else:
                        info_text += f"  • {iface_name}: 无 IP\n"
            
            panel = Panel(info_text, title=f"节点信息 - {node_name}", border_style="cyan")
            self.console.print(panel)
            
        except docker.errors.NotFound:
            self.console.print(f"[red]容器 {container_name} 不存在[/red]")
        
        self.console.print()
    
    def cmd_shell(self, args):
        """打开节点终端（支持批量）"""
        if not args:
            self.console.print("[red]用法: shell <node1> [node2] [node3] ...[/red]")
            self.console.print("[dim]示例: shell H1 H2 H3[/dim]")
            return
        
        # 解析节点名并转换为容器名
        container_names = []
        for node_name in args:
            if self.controller and self.controller.deployed:
                if node_name in self.controller.topology.nodes:
                    prefix = self.controller.resource_tracker.session_id[:6]
                    container_names.append(f"{prefix}-{node_name}")
                else:
                    self.console.print(f"[yellow]警告: 节点 {node_name} 不存在，跳过[/yellow]")
            elif self.current_session:
                prefix = self.current_session[:6]
                container_names.append(f"{prefix}-{node_name}")
            else:
                container_names.append(node_name)
        
        if not container_names:
            self.console.print("[red]没有有效的节点[/red]")
            return
        
        # 批量打开终端
        self.console.print(f"[white][>][/white] Opening terminals...")
        
        # 检测可用的终端模拟器
        terminal_cmd = None
        display = os.environ.get('DISPLAY')
        if display:
            # 按优先级尝试不同的终端
            terminals = [
                'gnome-terminal',
                'konsole',
                'xfce4-terminal',
                'xterm',
            ]
            
            for term in terminals:
                try:
                    result = subprocess.run(['which', term], capture_output=True, text=True)
                    if result.returncode == 0:
                        terminal_cmd = term
                        break
                except Exception:
                    continue
        
        # 获取当前用户和 HOME（sudo 环境下需要）
        real_user = os.environ.get('SUDO_USER', os.environ.get('USER', 'root'))
        real_home = os.path.expanduser(f'~{real_user}')
        
        for container_name in container_names:
            try:
                # 检查容器是否存在
                container = self.client.containers.get(container_name)
                
                if terminal_cmd and display:
                    try:
                        # 创建临时脚本来启动容器shell
                        import tempfile
                        
                        # 检查当前用户是否有 docker 权限
                        can_docker = False
                        try:
                            result = subprocess.run(['docker', 'ps'], capture_output=True, timeout=1)
                            can_docker = (result.returncode == 0)
                        except:
                            pass
                        
                        docker_cmd = 'docker' if can_docker else 'sudo docker'
                        
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                            f.write(f'''#!/bin/bash
# 进入容器
{docker_cmd} exec -it {container_name} /bin/bash
# 容器退出后保持终端打开
echo ""
echo "容器已退出，按回车关闭..."
read
''')
                            script_path = f.name
                        
                        os.chmod(script_path, 0o755)
                        
                        # 获取 D-Bus 会话地址（用于 gnome-terminal）
                        dbus_addr = None
                        if terminal_cmd == 'gnome-terminal' and real_user:
                            try:
                                # 尝试获取用户的 D-Bus 会话地址
                                result = subprocess.run(
                                    ['sudo', '-u', real_user, 'bash', '-c', 
                                     'pgrep -u $USER gnome-session | head -1 | xargs -I{} cat /proc/{}/environ | tr "\\0" "\\n" | grep "^DBUS_SESSION_BUS_ADDRESS=" | cut -d= -f2-'],
                                    capture_output=True, text=True, timeout=2
                                )
                                if result.returncode == 0 and result.stdout.strip():
                                    dbus_addr = result.stdout.strip()
                            except:
                                pass
                        
                        # 构建命令
                        if terminal_cmd == 'gnome-terminal':
                            if real_user and real_user != 'root' and dbus_addr:
                                cmd = [
                                    'sudo', '-u', real_user,
                                    'DISPLAY=' + display,
                                    'HOME=' + real_home,
                                    'DBUS_SESSION_BUS_ADDRESS=' + dbus_addr,
                                    terminal_cmd, '--', 'bash', script_path
                                ]
                            elif real_user and real_user != 'root':
                                # 没有 D-Bus 地址，尝试直接运行
                                cmd = [
                                    'sudo', '-u', real_user,
                                    'DISPLAY=' + display,
                                    'HOME=' + real_home,
                                    terminal_cmd, '--', 'bash', script_path
                                ]
                            else:
                                cmd = [terminal_cmd, '--', 'bash', script_path]
                        elif terminal_cmd in ['konsole', 'xfce4-terminal', 'xterm']:
                            if real_user and real_user != 'root':
                                cmd = [
                                    'sudo', '-u', real_user,
                                    'DISPLAY=' + display,
                                    'HOME=' + real_home,
                                    terminal_cmd, '-e', 'bash', script_path
                                ]
                            else:
                                cmd = [terminal_cmd, '-e', 'bash', script_path]
                        else:
                            cmd = [terminal_cmd, 'bash', script_path]
                        
                        subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        self.console.print(f"[bright_white][√][/bright_white] Terminal launched → [bright_cyan]{container_name}[/bright_cyan]")
                    except Exception as e:
                        self.console.print(f"[bright_yellow][!][/bright_yellow] Failed to open terminal, using current shell")
                        if len(container_names) == 1:
                            subprocess.run(['sudo', 'docker', 'exec', '-it', container_name, '/bin/bash'])
                else:
                    # 无图形界面或找不到终端模拟器
                    if len(container_names) == 1:
                        self.console.print(f"[white][>][/white] Connecting to [bright_cyan]{container_name}[/bright_cyan]...")
                        subprocess.run(['sudo', 'docker', 'exec', '-it', container_name, '/bin/bash'])
                    else:
                        self.console.print(f"[bright_yellow][!][/bright_yellow] No display available, skipping {container_name}")
            
            except docker.errors.NotFound:
                self.console.print(f"[bright_red][X][/bright_red] Container not found: {container_name}")
            except Exception as e:
                self.console.print(f"[bright_red][X][/bright_red] Failed to open {container_name}: {e}")
        
        self.console.print()
    
    def cmd_exec(self, args):
        """在节点中执行命令"""
        if len(args) < 2:
            self.console.print("[red]用法: exec <node> <command>[/red]")
            return
        
        node_name = args[0]
        command = ' '.join(args[1:])
        
        # 转换节点名
        if self.controller and self.controller.deployed:
            if node_name in self.controller.topology.nodes:
                prefix = self.controller.resource_tracker.session_id[:6]
                container_name = f"{prefix}-{node_name}"
            else:
                container_name = node_name
        elif self.current_session:
            prefix = self.current_session[:6]
            container_name = f"{prefix}-{node_name}"
        else:
            container_name = node_name
        
        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run(command, stdout=True, stderr=True)
            
            if output:
                # 使用 Syntax 高亮输出
                output_text = output.decode('utf-8', errors='ignore')
                self.console.print(f"\n[bright_white]────────────────────────────────────────────────────[/bright_white]")
                self.console.print(f"[bright_white]{node_name}[/bright_white] [white]$[/white] {command}")
                self.console.print(f"[bright_white]────────────────────────────────────────────────────[/bright_white]")
                self.console.print(f"[white]{output_text}[/white]")
                self.console.print(f"[bright_white]────────────────────────────────────────────────────[/bright_white]\n")
            
            if exit_code != 0:
                self.console.print(f"[bright_yellow][!][/bright_yellow] Exit code: {exit_code}")
        
        except docker.errors.NotFound:
            self.console.print(f"[bright_red][X][/bright_red] Container not found: {container_name}")
        except Exception as e:
            self.console.print(f"[red]执行失败: {e}[/red]")
        
        self.console.print()
    
    def cmd_ping(self, args):
        """测试连通性"""
        if len(args) < 2:
            self.console.print("[red]用法: ping <src_node> <dst_ip>[/red]")
            return
        
        src_node = args[0]
        dst_ip = args[1]
        count = 4
        
        # 转换节点名
        if self.controller and self.controller.deployed:
            if src_node in self.controller.topology.nodes:
                prefix = self.controller.resource_tracker.session_id[:6]
                container_name = f"{prefix}-{src_node}"
            else:
                container_name = src_node
        elif self.current_session:
            prefix = self.current_session[:6]
            container_name = f"{prefix}-{src_node}"
        else:
            container_name = src_node
        
        self.console.print(f"[bright_white]正在从 {src_node} ping {dst_ip}...[/bright_white]\n")
        
        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run(
                f"ping -c {count} -W 2 {dst_ip}",
                stdout=True, stderr=True
            )
            
            if output:
                output_text = output.decode('utf-8', errors='ignore')
                self.console.print(Panel(
                    output_text,
                    title=f"Ping 测试: {src_node} → {dst_ip}",
                    border_style="green" if exit_code == 0 else "red"
                ))
            
            if exit_code == 0:
                self.console.print("[bright_white][√][/bright_white] 连通成功")
            else:
                self.console.print("[red]✗ 连通失败[/red]")
        
        except docker.errors.NotFound:
            self.console.print(f"[red]容器 {container_name} 不存在[/red]")
        except Exception as e:
            self.console.print(f"[red]Ping 失败: {e}[/red]")
        
        self.console.print()
    
    def cmd_ip(self, args):
        """显示 IP 配置"""
        if not args:
            self.console.print("[red]用法: ip <node>[/red]")
            return
        
        node_name = args[0]
        
        # 转换节点名
        if self.controller and self.controller.deployed:
            if node_name in self.controller.topology.nodes:
                prefix = self.controller.resource_tracker.session_id[:6]
                container_name = f"{prefix}-{node_name}"
            else:
                container_name = node_name
        elif self.current_session:
            prefix = self.current_session[:6]
            container_name = f"{prefix}-{node_name}"
        else:
            container_name = node_name
        
        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run("ip addr show", stdout=True, stderr=True)
            
            if output:
                self.console.print(Panel(
                    output.decode('utf-8', errors='ignore'),
                    title=f"[bright_cyan]{node_name}[/bright_cyan] - 网络接口",
                    border_style="white"
                ))
        
        except docker.errors.NotFound:
            self.console.print(f"[red]容器 {container_name} 不存在[/red]")
        except Exception as e:
            self.console.print(f"[red]执行失败: {e}[/red]")
        
        self.console.print()
    
    def cmd_route(self, args):
        """显示路由表"""
        if not args:
            self.console.print("[red]用法: route <node>[/red]")
            return
        
        node_name = args[0]
        
        # 转换节点名
        if self.controller and self.controller.deployed:
            if node_name in self.controller.topology.nodes:
                prefix = self.controller.resource_tracker.session_id[:6]
                container_name = f"{prefix}-{node_name}"
            else:
                container_name = node_name
        elif self.current_session:
            prefix = self.current_session[:6]
            container_name = f"{prefix}-{node_name}"
        else:
            container_name = node_name
        
        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run("ip route show", stdout=True, stderr=True)
            
            if output:
                self.console.print(Panel(
                    output.decode('utf-8', errors='ignore'),
                    title=f"[bright_cyan]{node_name}[/bright_cyan] - 路由表",
                    border_style="white"
                ))
        
        except docker.errors.NotFound:
            self.console.print(f"[red]容器 {container_name} 不存在[/red]")
        except Exception as e:
            self.console.print(f"[red]执行失败: {e}[/red]")
        
        self.console.print()
    
    def cmd_cleanup(self, args):
        """清理资源"""
        force = '-f' in args or '--force' in args
        
        # 检查是否指定了会话
        session_to_clean = None
        if args and not args[0].startswith('-'):
            # 第一个参数不是选项，可能是会话标识
            sessions = ResourceTracker.list_all_sessions(self.client)
            choice = args[0]
            
            if choice.isdigit():
                # 按序号选择
                session_list = list(sessions.items())
                idx = int(choice) - 1
                if 0 <= idx < len(session_list):
                    session_to_clean = session_list[idx][0]
                else:
                    self.console.print(f"[red]无效的会话序号: {choice}[/red]")
                    return
            else:
                # 按ID或项目名匹配
                for sid, sinfo in sessions.items():
                    if sid.startswith(choice) or sinfo['project'] == choice:
                        session_to_clean = sid
                        break
                
                if not session_to_clean:
                    self.console.print(f"[red]找不到匹配的会话: {choice}[/red]")
                    return
        
        if session_to_clean:
            # 清理指定会话
            sessions = ResourceTracker.list_all_sessions(self.client)
            project_name = sessions[session_to_clean]['project']
            
            if not force:
                # 临时禁用历史记录
                old_length = readline.get_current_history_length()
                
                confirmed = Confirm.ask(
                    f"[bright_yellow][!][/bright_yellow] Confirm cleanup session '{project_name}' [y/N]?",
                    default=False,
                    show_default=False
                )
                
                # 删除这次输入的历史记录
                new_length = readline.get_current_history_length()
                if new_length > old_length:
                    readline.remove_history_item(new_length - 1)
                
                if not confirmed:
                    self.console.print("[dim]已取消[/dim]")
                    return
            
            with self.console.status(f"[bright_white]正在清理会话 {project_name}...[/bright_white]"):
                # 使用 ResourceTracker 进行完整清理（容器 + OVS + veth）
                stats = ResourceTracker.cleanup_session(self.client, session_to_clean)
            
            # 显示清理结果
            result_table = Table(box=box.SIMPLE, show_header=False)
            result_table.add_column("", style="dim")
            result_table.add_column("", justify="right", style="bright_white")
            
            if stats['containers'] > 0:
                result_table.add_row("容器", str(stats['containers']))
            if stats['ovs_bridges'] > 0:
                result_table.add_row("OVS 网桥", str(stats['ovs_bridges']))
            if stats['veth_interfaces'] > 0:
                result_table.add_row("Veth 接口", str(stats['veth_interfaces']))
            
            self.console.print(f"[bright_white][√][/bright_white] Session cleaned → [bright_cyan]{project_name}[/bright_cyan]")
            self.console.print(result_table)
            
            if stats['errors']:
                self.console.print(f"[yellow]警告: {len(stats['errors'])} 个错误[/yellow]")
                for error in stats['errors'][:3]:  # 只显示前 3 个
                    self.console.print(f"  [dim]• {error}[/dim]")
            
            self.console.print()
            
            # 如果清理的是当前会话，重置当前会话
            if self.current_session == session_to_clean:
                self.current_session = None
        else:
            # 清理所有会话
            if not force:
                # 临时禁用历史记录
                old_length = readline.get_current_history_length()
                
                confirmed = Confirm.ask(
                    "[bright_yellow][!][/bright_yellow] Confirm cleanup ALL Vortinet resources [y/N]?",
                    default=False,
                    show_default=False
                )
                
                # 删除这次输入的历史记录
                new_length = readline.get_current_history_length()
                if new_length > old_length:
                    readline.remove_history_item(new_length - 1)
                
                if not confirmed:
                    self.console.print("[dim]已取消[/dim]")
                    return
            
            with self.console.status("[bright_white]正在清理资源...[/bright_white]"):
                stats = cleanup_all(verbose=False)
            
            # 显示清理结果
            result_table = Table(box=box.SIMPLE)
            result_table.add_column("资源类型", style="bright_white")
            result_table.add_column("清理数量", justify="right", style="bright_white")
            
            result_table.add_row("容器", str(stats['containers']))
            result_table.add_row("OVS 网桥", str(stats['ovs_bridges']))
            result_table.add_row("Veth 接口", str(stats['veth_interfaces']))
            
            self.console.print(Panel(
                result_table,
                title="[bright_white]✓ 清理完成[/bright_white]",
                border_style="white"
            ))
            
            if stats['errors']:
                self.console.print(f"\n[yellow]警告: {len(stats['errors'])} 个错误[/yellow]")
                for error in stats['errors'][:5]:  # 只显示前 5 个
                    self.console.print(f"  [dim]• {error}[/dim]")
            
            self.current_session = None
        
        self.console.print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Vortinet CLI - 交互式命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互模式
  %(prog)s
  
  # 批量打开终端
  %(prog)s shell H1 H2 H3
  
  # 显示拓扑
  %(prog)s topology
  
  # 清理资源
  %(prog)s cleanup -f
"""
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        help='要执行的命令'
    )
    
    parser.add_argument(
        'args',
        nargs='*',
        help='命令参数'
    )
    
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='跳过确认（用于 cleanup）'
    )
    
    args = parser.parse_args()
    
    cli = VortinetCLI()
    
    try:
        # 如果没有指定命令，进入交互模式
        if args.command is None:
            cli.interactive_mode()
            return 0
        
        # 执行指定的命令前，先选择会话
        cli._auto_select_session()
        
        # 执行指定的命令
        cmd_line = args.command + (' ' + ' '.join(args.args) if args.args else '')
        if args.force:
            cmd_line += ' -f'
        
        cli.execute_command(cmd_line)
        return 0
        
    except KeyboardInterrupt:
        print("\n\n已取消")
        return 130
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
