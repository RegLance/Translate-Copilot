"""系统会话监控模块 - 检测锁屏/解锁事件

通过 Windows WTS API 监听会话状态变化，
在锁屏时暂停鼠标钩子，在解锁后恢复，
避免长时间锁屏导致鼠标操作卡顿。
"""
import sys
import ctypes
import ctypes.wintypes
import threading
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


# Windows 常量
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

# Window message constants
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010

HWND_MESSAGE = ctypes.wintypes.HWND(-3)

# Window class style
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001

# LoadCursor
IDC_ARROW = 32512


# WNDCLASS 结构体
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.wintypes.HWND,
    ctypes.c_uint,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]


class SessionMonitor(QObject):
    """系统会话监控器

    监听 Windows 会话锁屏/解锁事件，通过 Qt 信号通知上层。
    使用隐藏的 Win32 窗口接收 WM_WTSSESSION_CHANGE 消息。
    """

    session_locked = pyqtSignal()
    session_unlocked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._wndproc_ref = None  # prevent GC of callback
        self._class_atom = None

    def start(self):
        """启动会话监控（在后台线程中创建消息窗口）"""
        if self._running:
            return

        if sys.platform != 'win32':
            print("[SessionMonitor] 仅支持 Windows 平台", file=sys.stderr)
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_message_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止会话监控"""
        self._running = False

        if self._hwnd:
            try:
                ctypes.windll.user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        self._hwnd = None
        self._thread = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Win32 窗口过程，处理会话变化消息"""
        if msg == WM_WTSSESSION_CHANGE:
            if wparam == WTS_SESSION_LOCK:
                print("[SessionMonitor] 系统已锁屏", file=sys.stderr)
                self.session_locked.emit()
            elif wparam == WTS_SESSION_UNLOCK:
                print("[SessionMonitor] 系统已解锁", file=sys.stderr)
                self.session_unlocked.emit()
            return 0
        elif msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0

        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run_message_loop(self):
        """在后台线程中运行 Win32 消息循环"""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hinstance = kernel32.GetModuleHandleW(None)

            # 保存回调引用，防止被垃圾回收
            self._wndproc_ref = WNDPROC(self._wnd_proc)

            class_name = "QTranslatorSessionMonitor"

            # 注册窗口类
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc_ref
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinstance
            wc.hIcon = None
            wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
            wc.hbrBackground = None
            wc.lpszMenuName = None
            wc.lpszClassName = class_name

            self._class_atom = user32.RegisterClassW(ctypes.byref(wc))
            if not self._class_atom:
                error = kernel32.GetLastError()
                # ERROR_CLASS_ALREADY_EXISTS = 1410, 可以继续使用
                if error != 1410:
                    print(f"[SessionMonitor] RegisterClassW 失败, error={error}", file=sys.stderr)
                    return

            # 创建隐藏的 message-only 窗口
            self._hwnd = user32.CreateWindowExW(
                0,                    # dwExStyle
                class_name,           # lpClassName
                "QTranslator Session Monitor",  # lpWindowName
                0,                    # dwStyle
                0, 0, 0, 0,          # x, y, width, height
                HWND_MESSAGE,         # hWndParent (message-only window)
                None,                 # hMenu
                hinstance,            # hInstance
                None,                 # lpParam
            )

            if not self._hwnd:
                error = kernel32.GetLastError()
                print(f"[SessionMonitor] CreateWindowExW 失败, error={error}", file=sys.stderr)
                return

            # 注册会话通知
            wtsapi32 = ctypes.windll.wtsapi32
            result = wtsapi32.WTSRegisterSessionNotification(
                self._hwnd, NOTIFY_FOR_THIS_SESSION
            )

            if not result:
                error = kernel32.GetLastError()
                print(f"[SessionMonitor] WTSRegisterSessionNotification 失败, error={error}", file=sys.stderr)
                # 清理窗口
                user32.DestroyWindow(self._hwnd)
                self._hwnd = None
                return

            print("[SessionMonitor] 会话监控已启动", file=sys.stderr)

            # 消息循环
            msg = ctypes.wintypes.MSG()
            while self._running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as e:
            print(f"[SessionMonitor] 消息循环异常: {e}", file=sys.stderr)
        finally:
            self._cleanup_win32()

    def _cleanup_win32(self):
        """清理 Win32 资源"""
        try:
            if self._hwnd:
                wtsapi32 = ctypes.windll.wtsapi32
                wtsapi32.WTSUnRegisterSessionNotification(self._hwnd)
                ctypes.windll.user32.DestroyWindow(self._hwnd)
                self._hwnd = None
        except Exception:
            pass

        try:
            if self._class_atom:
                hinstance = ctypes.windll.kernel32.GetModuleHandleW(None)
                ctypes.windll.user32.UnregisterClassW(
                    "QTranslatorSessionMonitor", hinstance
                )
                self._class_atom = None
        except Exception:
            pass

    def cleanup(self):
        """公开的清理方法"""
        self.stop()


# 全局实例
_monitor_instance: Optional[SessionMonitor] = None


def get_session_monitor() -> SessionMonitor:
    """获取全局会话监控实例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SessionMonitor()
    return _monitor_instance
