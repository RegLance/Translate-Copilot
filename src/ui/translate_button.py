"""翻译图标按钮组件 - Translate Copilot"""
import sys
import math
from typing import Optional, Tuple
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QCursor

try:
    from ..config import get_config
except ImportError:
    from config import get_config


# 按钮尺寸（18px）
BUTTON_SIZE = 18

# 鼠标离开按钮多少像素后自动隐藏（使用逻辑坐标）
HIDE_DISTANCE_THRESHOLD = 50


class TranslateButton(QWidget):
    """翻译图标按钮

    选中文本后显示的小图标，点击后触发翻译。
    显示 "T" 字符代表 Translate。

    特性：
    - 小巧的圆形图标按钮
    - 跟随选区/鼠标位置显示
    - 点击触发翻译
    - 鼠标距离按钮一定距离后自动隐藏
    """

    # 信号
    clicked = pyqtSignal()
    hidden = pyqtSignal()

    def __init__(self):
        super().__init__()

        config = get_config()
        self._auto_hide_delay = 5000

        self._selected_text: str = ""
        self._auto_hide_timer: Optional[QTimer] = None
        self._mouse_check_timer: Optional[QTimer] = None  # 定时检查鼠标距离
        self._is_just_shown: bool = False  # 刚显示的短暂时间内不检测距离

        self._setup_ui()
        self._setup_window_properties()
        self._setup_auto_hide_timer()
        self._setup_mouse_check_timer()

    def _setup_window_properties(self):
        """设置窗口属性"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # 显示但不激活
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)

    def _setup_ui(self):
        """设置 UI"""
        self._icon_label = QLabel(self)
        self._icon_label.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = self._create_icon()
        self._icon_label.setPixmap(pixmap)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._icon_label)

        self.setMouseTracking(True)

    def _create_icon(self) -> QPixmap:
        """创建翻译图标 - 显示 "T" 字符（半透明背景）"""
        pixmap = QPixmap(BUTTON_SIZE, BUTTON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制圆形背景（半透明蓝色，透明度约50%）
        painter.setBrush(QColor(0, 120, 212, 128))  # 半透明蓝色
        painter.setPen(Qt.PenStyle.NoPen)  # 无边框
        painter.drawEllipse(0, 0, BUTTON_SIZE, BUTTON_SIZE)

        # 绘制 "T" 字符
        painter.setPen(QColor(255, 255, 255, 230))  # 半透明白色
        font = QFont("Arial", 10, QFont.Weight.Bold)  # 10px字体在18px按钮中合适
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")

        painter.end()

        return pixmap

    def _setup_auto_hide_timer(self):
        """设置自动隐藏计时器"""
        self._auto_hide_timer = QTimer()
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide)

    def _setup_mouse_check_timer(self):
        """设置鼠标距离检测定时器"""
        self._mouse_check_timer = QTimer()
        self._mouse_check_timer.setInterval(100)  # 每100ms检查一次
        self._mouse_check_timer.timeout.connect(self._check_mouse_distance)

    def _check_mouse_distance(self):
        """检查鼠标距离，如果离按钮太远则隐藏"""
        if self._is_just_shown or not self.isVisible():
            return

        # 获取鼠标当前位置（逻辑坐标）
        cursor_pos = QCursor.pos()
        mouse_x, mouse_y = cursor_pos.x(), cursor_pos.y()

        # 获取按钮的几何区域
        button_x = self.x()
        button_y = self.y()
        button_w = self.width()
        button_h = self.height()

        # 计算鼠标到按钮中心的距离
        center_x = button_x + button_w // 2
        center_y = button_y + button_h // 2
        distance = math.sqrt((mouse_x - center_x) ** 2 + (mouse_y - center_y) ** 2)

        # 检查鼠标是否在按钮区域附近
        # 如果距离超过阈值，则隐藏按钮
        if distance > HIDE_DISTANCE_THRESHOLD:
            # 额外检查：鼠标不在按钮内部
            if not (button_x <= mouse_x <= button_x + button_w and
                    button_y <= mouse_y <= button_y + button_h):
                print(f"[DEBUG] 鼠标距离按钮 {distance:.1f}px > {HIDE_DISTANCE_THRESHOLD}px，隐藏按钮", file=sys.stderr)
                self.hide()
                return

        # 重置自动隐藏计时器
        self._auto_hide_timer.stop()
        self._auto_hide_timer.start(self._auto_hide_delay)

    def show_at_position(self, pos: Optional[Tuple[int, int]], selected_text: str = ""):
        """在指定位置显示图标按钮"""
        if pos is None:
            cursor_pos = QCursor.pos()
            x, y = cursor_pos.x(), cursor_pos.y()
        else:
            x, y = pos

        self._selected_text = selected_text

        # 计算显示位置（鼠标右下方）
        new_x = x + 8
        new_y = y + 8

        # 确保不超出屏幕边界
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableVirtualGeometry()
                # 如果右边超出，放到左边
                if new_x + BUTTON_SIZE > screen_geo.x() + screen_geo.width():
                    new_x = x - BUTTON_SIZE - 8
                # 如果下边超出，放到上边
                if new_y + BUTTON_SIZE > screen_geo.y() + screen_geo.height():
                    new_y = y - BUTTON_SIZE - 8
                # 确保不超出左边
                if new_x < screen_geo.x():
                    new_x = screen_geo.x() + 5
                # 确保不超出上边
                if new_y < screen_geo.y():
                    new_y = screen_geo.y() + 5
        except Exception:
            pass

        print(f"[DEBUG] 翻译按钮显示在 ({new_x}, {new_y})", file=sys.stderr)

        # 先隐藏确保重置状态
        super().hide()

        self.move(new_x, new_y)
        self._is_just_shown = True

        # 使用 show() 和 raise_() 确保窗口显示并置顶
        self.show()
        self.raise_()
        self.activateWindow()

        # 强制更新窗口
        self.update()

        # 启动鼠标距离检测
        self._mouse_check_timer.start()

        # 启动自动隐藏计时器
        self._auto_hide_timer.start(self._auto_hide_delay)

        # 500ms 后重置刚显示状态，开始检测距离
        QTimer.singleShot(500, self._reset_just_shown)

    def get_selected_text(self) -> str:
        """获取保存的选中文本"""
        return self._selected_text

    def set_selected_text(self, text: str):
        """设置选中的文本"""
        self._selected_text = text

    def hide(self):
        """隐藏按钮"""
        print("[DEBUG] TranslateButton.hide() 被调用", file=sys.stderr)
        self._auto_hide_timer.stop()
        self._mouse_check_timer.stop()
        self._selected_text = ""
        super().hide()
        self.hidden.emit()

    def _on_auto_hide(self):
        """自动隐藏"""
        print("[DEBUG] _on_auto_hide 触发", file=sys.stderr)
        self.hide()

    def enterEvent(self, event):
        """鼠标进入 - 暂停自动隐藏"""
        self._auto_hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开 - 重启自动隐藏"""
        if self._is_just_shown:
            super().leaveEvent(event)
            return
        # 离开按钮后设置一个较短的超时后隐藏
        self._auto_hide_timer.start(1000)
        super().leaveEvent(event)

    def _reset_just_shown(self):
        """重置刚显示状态"""
        self._is_just_shown = False
        print("[DEBUG] 距离检测已启用", file=sys.stderr)

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            print("[DEBUG] 按钮被点击，发送 clicked 信号", file=sys.stderr)
            self.clicked.emit()
            self.hide()
        super().mousePressEvent(event)


# 全局实例
_button_instance: Optional[TranslateButton] = None


def get_translate_button() -> TranslateButton:
    """获取全局翻译按钮实例"""
    global _button_instance
    if _button_instance is None:
        _button_instance = TranslateButton()
    return _button_instance