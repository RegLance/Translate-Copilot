"""文本捕获模块 - 使用 selection-hook 进行跨应用文本选择捕获，并添加剪贴板轮询作为补充"""
import sys
import os
import json
import time
import subprocess
import threading
from typing import Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    from pynput import mouse
except ImportError:
    mouse = None


@dataclass
class SelectionInfo:
    """选择信息"""
    text: str
    bounds: Optional[Tuple[int, int, int, int]] = None  # (x, y, width, height)
    method: str = "selection-hook"  # 捕获方法
    error: Optional[str] = None


class ClipboardPoller:
    """剪贴板轮询器 - 作为 selection-hook 的补充检测方式

    用于解决某些应用（如 MobaXterm 终端）不触发 UI Automation 选择事件的问题。
    这些应用通常有"选中即复制"功能，所以可以通过检测剪贴板变化来捕获选择。

    重要：
    1. 只在支持"选中即复制"的终端应用（如 MobaXterm）中激活
    2. 只在"选择时间窗口"内检测剪贴板变化，避免误触发用户主动复制操作
    """

    # 支持"选中即复制"的终端应用列表
    TERMINAL_APPS = [
        'mobaxterm',      # MobaXterm
        'xshell',         # Xshell
        'securecrt',      # SecureCRT
        'putty',          # PuTTY
        'windowsterminal', # Windows Terminal
        'cmd',            # 命令提示符
        'powershell',     # PowerShell
        'conda',          # Anaconda Prompt
        'alacritty',      # Alacritty
        'hyper',          # Hyper Terminal
        'fluentterminal', # Fluent Terminal
        'terminus',       # Terminus
    ]

    def __init__(self, on_change_callback):
        """初始化剪贴板轮询器

        Args:
            on_change_callback: 剪贴板内容变化时的回调函数，接收 (text, timestamp) 参数
        """
        self._callback = on_change_callback
        self._last_clipboard_text: str = ""
        self._last_clipboard_time: float = 0
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._poll_interval = 0.1  # 100ms 轮询间隔（更快检测）
        self._lock = threading.Lock()

        # 选择时间窗口：只有鼠标释放后短时间内才触发
        self._selection_window_start: float = 0
        self._selection_window_duration: float = 1.0  # 1秒窗口

        # 鼠标监听器（用于开启选择窗口）
        self._mouse_listener: Optional[object] = None

        # 获取初始剪贴板内容
        self._init_clipboard()

    def _init_clipboard(self):
        """初始化剪贴板内容"""
        try:
            if pyperclip:
                self._last_clipboard_text = pyperclip.paste() or ""
            elif sys.platform == 'win32':
                import ctypes
                # 使用 Windows API 获取剪贴板文本
                ctypes.windll.user32.OpenClipboard(0)
                try:
                    hwnd = ctypes.windll.user32.GetClipboardData(1)  # CF_TEXT
                    if hwnd:
                        text = ctypes.windll.kernel32.GlobalLock(hwnd)
                        if text:
                            buffer = ctypes.c_char_p(text)
                            self._last_clipboard_text = buffer.value.decode('utf-8', errors='replace') if buffer.value else ""
                            ctypes.windll.kernel32.GlobalUnlock(hwnd)
                finally:
                    ctypes.windll.user32.CloseClipboard()
        except Exception:
            self._last_clipboard_text = ""

    def start(self):
        """启动轮询和鼠标监听"""
        if self._running:
            return

        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        # 启动鼠标监听器（监听左键释放来开启选择窗口）
        if mouse:
            self._mouse_listener = mouse.Listener(
                on_release=self._on_mouse_release
            )
            self._mouse_listener.start()
            print("[ClipboardPoller] 剪贴板轮询和鼠标监听已启动", file=sys.stderr)
        else:
            print("[ClipboardPoller] 剪贴板轮询已启动（无鼠标监听）", file=sys.stderr)

    def stop(self):
        """停止轮询和鼠标监听"""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

        print("[ClipboardPoller] 剪贴板轮询已停止", file=sys.stderr)

    def _on_mouse_release(self, button, x, y):
        """鼠标释放事件处理 - 开启选择窗口

        当用户在终端应用中释放鼠标左键时（可能刚完成划词选择），开启选择窗口。
        如果终端应用有"选中即复制"功能，剪贴板变化会在窗口内被检测到。
        """
        # 只处理左键释放
        if mouse and button != mouse.Button.left:
            return

        # 检测当前前台窗口是否是终端应用
        if self._is_terminal_app():
            self.set_selection_window()

    def _is_terminal_app(self) -> bool:
        """检测当前前台窗口是否是支持"选中即复制"的终端应用

        Returns:
            bool: 如果前台窗口是终端应用返回 True，否则返回 False
        """
        if sys.platform != 'win32':
            return False

        try:
            import ctypes

            # 获取前台窗口句柄
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False

            # 方法1: 获取窗口标题检查
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.lower()

                # 检查窗口标题是否包含终端应用名称
                for terminal in self.TERMINAL_APPS:
                    if terminal in title:
                        print(f"[ClipboardPoller] 检测到终端应用: {title}", file=sys.stderr)
                        return True

            # 方法2: 获取进程名检查
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # 使用 ctypes 获取进程名
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010

            h_process = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                False, pid.value
            )

            if h_process:
                try:
                    # 获取进程映像名称
                    buffer = ctypes.create_unicode_buffer(260)
                    size = ctypes.c_ulong(260)
                    ctypes.windll.psapi.GetModuleBaseNameW(
                        h_process, None, buffer, size
                    )
                    process_name = buffer.value.lower()

                    # 检查进程名是否包含终端应用名称
                    for terminal in self.TERMINAL_APPS:
                        if terminal in process_name:
                            print(f"[ClipboardPoller] 检测到终端进程: {process_name}", file=sys.stderr)
                            return True
                finally:
                    ctypes.windll.kernel32.CloseHandle(h_process)

        except Exception as e:
            print(f"[ClipboardPoller] 检测终端应用失败: {e}", file=sys.stderr)

        return False

    def _poll_loop(self):
        """轮询循环"""
        while self._running:
            try:
                self._check_clipboard()
            except Exception as e:
                # 忽略错误，继续轮询
                pass
            time.sleep(self._poll_interval)

    def _check_clipboard(self):
        """检查剪贴板是否有变化

        只有在选择时间窗口内检测到的变化才会触发回调。
        """
        # 首先检查是否在选择窗口内（不在窗口内直接跳过）
        if not self._is_in_selection_window():
            return

        try:
            current_text = ""

            # 使用 pyperclip 或 Windows API 获取剪贴板内容
            if pyperclip:
                current_text = pyperclip.paste() or ""
            elif sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.OpenClipboard(0)
                try:
                    hwnd = ctypes.windll.user32.GetClipboardData(1)  # CF_TEXT
                    if hwnd:
                        text = ctypes.windll.kernel32.GlobalLock(hwnd)
                        if text:
                            buffer = ctypes.c_char_p(text)
                            current_text = buffer.value.decode('utf-8', errors='replace') if buffer.value else ""
                            ctypes.windll.kernel32.GlobalUnlock(hwnd)
                finally:
                    ctypes.windll.user32.CloseClipboard()

            current_time = time.time()

            with self._lock:
                # 检查是否有变化
                if current_text and current_text != self._last_clipboard_text:
                    # 排除太短的变化（可能是误操作）
                    if len(current_text.strip()) >= 1:
                        self._last_clipboard_text = current_text
                        self._last_clipboard_time = current_time

                        # 重置选择窗口（防止重复触发）
                        self._selection_window_start = 0

                        # 触发回调
                        if self._callback:
                            self._callback(current_text, current_time)

        except Exception:
            pass

    def get_last_text(self) -> Tuple[str, float]:
        """获取最后一次剪贴板文本和时间"""
        with self._lock:
            return self._last_clipboard_text, self._last_clipboard_time

    def set_selection_window(self):
        """设置选择时间窗口

        当鼠标释放（用户完成选择动作）时调用此方法。
        只有在此后的短时间内检测到的剪贴板变化才会触发回调。
        这可以有效区分：
        - 终端划词选择（选中即复制）→ 在窗口内，触发图标
        - 用户主动 Ctrl+C 复制 → 不在窗口内，不触发图标
        """
        with self._lock:
            self._selection_window_start = time.time()
            print("[ClipboardPoller] 选择窗口已开启", file=sys.stderr)

    def _is_in_selection_window(self) -> bool:
        """检查当前是否在选择时间窗口内"""
        with self._lock:
            if self._selection_window_start == 0:
                return False
            elapsed = time.time() - self._selection_window_start
            return elapsed < self._selection_window_duration


class TextCapture:
    """文本捕获类 - 使用 selection-hook Node.js 服务，并添加剪贴板轮询作为补充"""

    def __init__(self):
        """初始化文本捕获"""
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._last_selection: Optional[dict] = None
        self._last_capture_time: float = 0
        self._lock = threading.Lock()
        self._running = False
        self._ready = False
        self._node_path: Optional[str] = None

        # 剪贴板轮询器（作为补充检测方式）
        self._clipboard_poller: Optional[ClipboardPoller] = None
        self._clipboard_source_time: float = 0  # 剪贴板来源时间

        # 查找 Node.js 路径
        self._find_node()

        # 启动服务
        self._start_service()

        # 启动剪贴板轮询（作为补充检测）
        self._start_clipboard_poller()

    def _find_node(self):
        """查找 Node.js 可执行文件路径"""
        # Windows 上查找 node.exe
        if sys.platform == 'win32':
            # 尝试常见路径
            common_paths = [
                "node",  # PATH 中
                r"C:\Program Files\nodejs\node.exe",
                r"C:\Program Files (x86)\nodejs\node.exe",
            ]

            # 检查 PATH 环境变量
            path_env = os.environ.get('PATH', '').split(os.pathsep)
            for p in path_env:
                node_exe = os.path.join(p, 'node.exe')
                if os.path.isfile(node_exe):
                    self._node_path = node_exe
                    return

            # 尝试直接使用 node（在 PATH 中）
            self._node_path = "node"
        else:
            self._node_path = "node"

    def _get_service_path(self) -> str:
        """获取 selection-service.js 的路径"""
        # 相对于当前文件的路径
        current_dir = Path(__file__).parent
        project_root = current_dir.parent.parent  # src/core -> src -> hover-translator
        service_path = project_root / "native" / "selection-service.js"
        return str(service_path)

    def _start_service(self):
        """启动 Node.js 选择监控服务"""
        if self._process is not None:
            return

        service_path = self._get_service_path()
        if not os.path.exists(service_path):
            print(f"错误: selection-service.js 不存在: {service_path}", file=sys.stderr)
            return

        try:
            # 启动 Node.js 子进程
            self._process = subprocess.Popen(
                [self._node_path, service_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            self._running = True

            # 启动读取线程
            self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self._reader_thread.start()

            # 等待就绪信号
            timeout = 5.0
            start_time = time.time()
            while not self._ready and time.time() - start_time < timeout:
                time.sleep(0.1)

            if self._ready:
                print("[TextCapture] selection-hook 服务已启动", file=sys.stderr)
            else:
                print("[TextCapture] 警告: selection-hook 服务启动超时", file=sys.stderr)

        except Exception as e:
            print(f"[TextCapture] 启动服务失败: {e}", file=sys.stderr)
            self._process = None
            self._running = False

    def _start_clipboard_poller(self):
        """启动剪贴板轮询器（作为补充检测方式）"""
        if self._clipboard_poller is not None:
            return

        self._clipboard_poller = ClipboardPoller(self._on_clipboard_change)
        self._clipboard_poller.start()

    def _on_clipboard_change(self, text: str, timestamp: float):
        """剪贴板内容变化回调

        当剪贴板内容变化时，将其作为选择数据存储。
        这主要用于处理那些不触发 UI Automation 选择事件的应用（如 MobaXterm）。
        """
        # 检查是否与当前选择相同（避免重复）
        with self._lock:
            current_text = self._last_selection.get('text', '') if self._last_selection else ''
            if text == current_text:
                return

            # 存储剪贴板数据作为选择
            self._last_selection = {
                'text': text,
                'x': 0,
                'y': 0,
                'program': 'clipboard',
                'timestamp': timestamp
            }
            self._last_capture_time = timestamp
            self._clipboard_source_time = timestamp

        print(f"[TextCapture] 剪贴板变化检测: '{text[:30]}...' (来自终端类应用)", file=sys.stderr)

    def _read_output(self):
        """读取 Node.js 进程的输出（在后台线程运行）"""
        if not self._process or not self._process.stdout:
            return

        try:
            while self._running:
                line = self._process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # 检查就绪信号
                    if data.get('ready'):
                        self._ready = True
                        continue

                    # 检查错误
                    if data.get('error'):
                        print(f"[TextCapture] 服务错误: {data['error']}", file=sys.stderr)
                        continue

                    # 存储选择数据
                    with self._lock:
                        self._last_selection = data
                        self._last_capture_time = time.time()

                except json.JSONDecodeError:
                    # 忽略非 JSON 输出
                    pass

        except Exception as e:
            if self._running:
                print(f"[TextCapture] 读取输出错误: {e}", file=sys.stderr)

    def capture(self) -> SelectionInfo:
        """捕获当前选中的文本"""
        with self._lock:
            if self._last_selection:
                data = self._last_selection
                text = data.get('text', '')
                x = data.get('x', 0)
                y = data.get('y', 0)

                return SelectionInfo(
                    text=text,
                    bounds=(x, y, 0, 0) if x or y else None,
                    method="selection-hook"
                )

        return SelectionInfo(text="", method="selection-hook")

    def capture_direct(self) -> str:
        """直接捕获文本（简化版本，用于主流程）"""
        with self._lock:
            if self._last_selection:
                return self._last_selection.get('text', '')
        return ""

    def clear_selection(self):
        """清除缓存的选中内容（在翻译完成后调用）"""
        with self._lock:
            self._last_selection = None

    def has_new_selection(self, since_time: float) -> bool:
        """检查是否有新的选择（自指定时间以来）"""
        with self._lock:
            return self._last_capture_time > since_time

    def get_last_capture_time(self) -> float:
        """获取最后一次捕获的时间"""
        with self._lock:
            return self._last_capture_time

    def is_ready(self) -> bool:
        """检查服务是否就绪"""
        return self._ready

    def cleanup(self):
        """清理资源"""
        self._running = False

        # 停止剪贴板轮询器
        if self._clipboard_poller:
            self._clipboard_poller.stop()
            self._clipboard_poller = None

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        self._ready = False
        print("[TextCapture] 服务已停止", file=sys.stderr)

    def __del__(self):
        """析构函数"""
        self.cleanup()


# 全局文本捕获实例
_capture_instance: Optional[TextCapture] = None


def get_text_capture() -> TextCapture:
    """获取全局文本捕获实例"""
    global _capture_instance
    if _capture_instance is None:
        _capture_instance = TextCapture()
    return _capture_instance


def capture_selection() -> SelectionInfo:
    """快捷函数：捕获当前选择"""
    return get_text_capture().capture()


def capture_text_direct() -> str:
    """快捷函数：直接捕获文本"""
    return get_text_capture().capture_direct()


def clear_text_capture():
    """快捷函数：清除缓存"""
    get_text_capture().clear_selection()