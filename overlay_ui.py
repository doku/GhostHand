from PyQt6.QtWidgets import QMainWindow, QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap

class OverlayWindow(QWidget):
    def __init__(self, hand_icon_path="ghost_hand.png", scroll_icon_path="scroll_icon.png"):
        super().__init__()
        # Window Flags for Transparency and Click-through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput # Click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # Fullscreen
        screen = QApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.setGeometry(0, 0, rect.width(), rect.height())
        
        self.hand_pos = None # (x, y)
        self.is_tracking = False
        self.is_sleep = False
        self.is_scrolling = False
        
        # Load Assets
        self.hand_pixmap = QPixmap(hand_icon_path)
        if self.hand_pixmap.isNull():
             self.hand_pixmap = QPixmap(32, 32)
             self.hand_pixmap.fill(Qt.GlobalColor.red)
             
        self.scroll_pixmap = QPixmap(scroll_icon_path)
        if self.scroll_pixmap.isNull():
             self.scroll_pixmap = QPixmap(32, 32)
             self.scroll_pixmap.fill(Qt.GlobalColor.cyan)
             
        # Scale if needed? For now assume assets are sized ok (e.g. 64x64)
        # Or scale them here
        if not self.hand_pixmap.isNull():
            self.hand_pixmap = self.hand_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if not self.scroll_pixmap.isNull():
             self.scroll_pixmap = self.scroll_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def update_hand_pose(self, x, y, is_tracking, is_sleep=False, is_scrolling=False):
        """
        Updates the visual hand position.
        """
        self.hand_pos = (x, y)
        self.is_tracking = is_tracking
        self.is_sleep = is_sleep
        self.is_scrolling = is_scrolling
        self.update() # Trigger paintEvent

    def paintEvent(self, event):
        if not self.hand_pos:
            return
            
        if self.is_sleep:
            return # Draw nothing when sleeping
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Determine Target Pixmap
        target_pixmap = self.hand_pixmap
        if self.is_scrolling:
            target_pixmap = self.scroll_pixmap
            
        if target_pixmap.isNull():
             return

        scaled_width = target_pixmap.width()
        scaled_height = target_pixmap.height()
        
        draw_x = self.hand_pos[0] - scaled_width / 2
        draw_y = self.hand_pos[1] - scaled_height / 2
        
        # Opacity
        opacity = 0.8 if (self.is_tracking or self.is_scrolling) else 0.4
        painter.setOpacity(opacity)
        
        painter.drawPixmap(int(draw_x), int(draw_y), target_pixmap)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OverlayWindow()
    window.show()
    
    # Test Animation
    timer = QTimer()
    x = 0
    def anim():
        global x
        x += 5
        if x > 1920: x = 0
        window.update_hand_pose(x, 500, True)
        
    timer.timeout.connect(anim)
    timer.start(16) # ~60 FPS
    
    sys.exit(app.exec())
