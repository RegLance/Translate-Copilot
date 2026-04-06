"""鼠标悬停检测模块"""
import time
from typing import Optional, Callable, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path
from pynput import mouse
from PyQt6.QtCore import QTimer, QObject, pyqtSignal

try:
    from ..config import get_config
except ImportError:
    from config import get_config


@dataclass
class MousePosition:
    """鼠标位置信息"""
    x: int
    y: int
    timestamp: float


class HoverDetector(QObject):
    """鼠标悬停检测器

    检测用户选中文本后鼠标悬停的事件。
    工作流程：
    1. 监听鼠标释放事件（用户完成选择）
    2. 记录鼠标位置，启动悬停计时器
    3. 如果鼠标在设定时间内未移动，触发翻译
    4. 如果鼠标移动，取消计时器
    """

    # 信号定义
    hover_triggered = pyqtSignal()  # 悬停触发信号
    selection_detected = pyqtSignal()  # 选择检测信号

    def __init__(self):
        """初始化悬停检测器"""
        super().__init__()

        self._mouse_listener: Optional[mouse.Listener] = None
        self._hover_timer: Optional[QTimer] = None
        self._last_position: Optional[MousePosition] = None
        self._is_enabled = True
        self._is_hovering = False

        # 加载配置
        self._delay_ms = get_config().get('hover.delay_ms', 300)
        self._area_padding = get_config().get('hover.area_padding', 15)

        # 初始化计时器
        self._init_timer()

    def _init_timer(self):
        """初始化悬停计时器"""
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_hover_timeout)

    def start(self):
        """启动检测"""
        if self._mouse_listener is not None:
            return

        self._mouse_listener = mouse.Listener(
            on_release=self._on_mouse_release,
            on_move=self._on_mouse_move
        )
        self._mouse_listener.start()
        print("悬停检测器已启动")

    def stop(self):
        """停止检测"""
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None

        if self._hover_timer is not None:
            self._hover_timer.stop()

        print("悬停检测器已停止")

    def set_enabled(self, enabled: bool):
        """设置是否启用检测"""
        self._is_enabled = enabled
        if not enabled:
            self._hover_timer.stop()
            self._is_hovering = False

    def set_delay(self, delay_ms: int):
        """设置悬停延迟时间"""
        self._delay_ms = delay_ms

    def _on_mouse_release(self, button, x, y):
        """鼠标释放事件处理"""
        if not self._is_enabled:
            return

        # 只处理左键释放
        if button != mouse.Button.left:
            return

        # 记录位置
        self._last_position = MousePosition(x=x, y=y, timestamp=time.time())
        self._is_hovering = True

        # 发送选择检测信号
        self.selection_detected.emit()

        # 启动悬停计时器
        self._hover_timer.start(self._delay_ms)

    def _on_mouse_move(self, x, y):
        """鼠标移动事件处理"""
        if not self._is_enabled or not self._is_hovering:
            return

        # 检查是否移动超出允许区域
        if self._last_position is not None:
            dx = abs(x - self._last_position.x)
            dy = abs(y - self._last_position.y)

            # 如果移动超出阈值，取消悬停
            if dx > self._area_padding or dy > self._area_padding:
                self._hover_timer.stop()
                self._is_hovering = False

    def _on_hover_timeout(self):
        """悬停时间到达处理"""
        if not self._is_enabled:
            return

        self._is_hovering = False
        self.hover_triggered.emit()

    def get_last_position(self) -> Optional[Tuple[int, int]]:
        """获取最后一次鼠标位置"""
        if self._last_position is not None:
            return (self._last_position.x, self._last_position.y)
        return None

    def cleanup(self):
        """清理资源"""
        self.stop()


# 全局悬停检测器实例
_detector_instance: Optional[HoverDetector] = None


def get_hover_detector() -> HoverDetector:
    """获取全局悬停检测器实例"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = HoverDetector()
    return _detector_instance