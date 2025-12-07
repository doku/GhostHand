import sys
import os
import traceback
import ctypes # For Single Instance Lock (moved up)
import json
import time
import cv2
import numpy as np
import mediapipe as mp

# Setup Logging for Debugging Standalone Crashes
# This redirects all print() and error output to ghost_hand.log
log_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__)), "ghost_hand.log")
sys.stdout = open(log_path, "a", buffering=1)
sys.stderr = sys.stdout
print(f"--- GhostHand Starting ---")

def exception_hook(exctype, value, tb):
    print("Uncaught exception:")
    traceback.print_exception(exctype, value, tb)
    sys.exit(1)

sys.excepthook = exception_hook

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog, 
                             QVBoxLayout, QHBoxLayout, QSlider, QLabel, QPushButton, 
                             QWidget, QStyle, QCheckBox, QMessageBox, QComboBox, QInputDialog)
from PyQt6.QtCore import QThread, pyqtSignal, QObject, Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap

from vision_core import VisionEngine
from input_controller import InputController
from gesture_engine import GestureManager, GestureState, GestureAction
from overlay_ui import OverlayWindow
from smoothing import OneEuroFilter

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Ensure config is stored in the same directory as the executable (not temp dir)
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(application_path, "config.json")

DEFAULT_PROFILE = {
    "sensitivity_x": 1500.0,
    "sensitivity_y": 1500.0,
    "click_threshold": 0.20,
    "keep_awake": False,
    "high_performance": False,
    "invert_scroll": False
}

DEFAULT_ROOT_CONFIG = {
    "current_profile": "Default",
    "profiles": {
        "Default": DEFAULT_PROFILE.copy()
    }
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_ROOT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            
            # Migration Logic: Check if it's a legacy flat config
            if "profiles" not in data:
                print("Migrating legacy config to profiles...")
                new_config = DEFAULT_ROOT_CONFIG.copy()
                # Copy known keys to Default profile
                for key in DEFAULT_PROFILE:
                    if key in data:
                        new_config["profiles"]["Default"][key] = data[key]
                
                return new_config
            
                return new_config
            
            data = sanitize_config(data)
            return data
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_ROOT_CONFIG.copy()

def sanitize_config(config):
    # Ensure all profiles have valid values
    if "profiles" not in config:
        config["profiles"] = DEFAULT_ROOT_CONFIG["profiles"].copy()
        
    for name, p in config["profiles"].items():
        # Enforce Minimums/Defaults
        if p.get("sensitivity_x", 0) < 100: p["sensitivity_x"] = 1500.0
        if p.get("sensitivity_y", 0) < 100: p["sensitivity_y"] = 1500.0
        if p.get("click_threshold", 0) < 0.05: p["click_threshold"] = 0.20
        if p.get("click_threshold", 0) > 1.0: p["click_threshold"] = 0.20 # Sanity check cap
        
        # Ensure Keys exist
        for k, v in DEFAULT_PROFILE.items():
            if k not in p:
                p[k] = v
                
    return config

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print("Config saved.")
    except Exception as e:
        print(f"Error saving config: {e}")

class SettingsDialog(QDialog):
    # Signals to worker
    sensitivity_changed = pyqtSignal(float, float) 
    keep_awake_toggled = pyqtSignal(bool)
    high_perf_toggled = pyqtSignal(bool)
    click_threshold_changed = pyqtSignal(float)
    invert_scroll_toggled = pyqtSignal(bool)
    wake_requested = pyqtSignal()
    
    # Signal to App to save config
    config_changed = pyqtSignal()

    def __init__(self, config_ref):
        super().__init__()
        self.setWindowTitle("Ghost Hand Settings")
        self.setFixedSize(320, 520)
        self.config = config_ref
        
        layout = QVBoxLayout()
        
        # --- PROFILE HEADER ---
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Profile:"))
        
        self.combo_profile = QComboBox()
        self.refresh_profiles_list()
        self.combo_profile.currentTextChanged.connect(self.change_profile)
        profile_layout.addWidget(self.combo_profile)
        
        btn_add = QPushButton("+")
        btn_add.setFixedWidth(30)
        btn_add.clicked.connect(self.add_profile)
        profile_layout.addWidget(btn_add)
        
        btn_del = QPushButton("-")
        btn_del.setFixedWidth(30)
        btn_del.clicked.connect(self.delete_profile)
        profile_layout.addWidget(btn_del)
        
        layout.addLayout(profile_layout)
        layout.addWidget(QLabel("<i>Settings apply to selected profile</i>"))
        
        # --- CONTROLS ---
        
        # Sensitivity X
        layout.addWidget(QLabel("Horizontal Sensitivity (X):"))
        self.slider_x = QSlider(Qt.Orientation.Horizontal)
        self.slider_x.setRange(100, 5000)
        self.slider_x.valueChanged.connect(self.on_ui_changed)
        layout.addWidget(self.slider_x)
        self.label_x = QLabel("1500")
        layout.addWidget(self.label_x)
        
        # Sensitivity Y
        layout.addWidget(QLabel("Vertical Sensitivity (Y):"))
        self.slider_y = QSlider(Qt.Orientation.Horizontal)
        self.slider_y.setRange(100, 5000)
        self.slider_y.valueChanged.connect(self.on_ui_changed)
        layout.addWidget(self.slider_y)
        self.label_y = QLabel("1500")
        layout.addWidget(self.label_y)
        
        # Click Threshold
        layout.addWidget(QLabel("Click Threshold (Pinch Ratio):"))
        self.slider_click = QSlider(Qt.Orientation.Horizontal)
        self.slider_click.setRange(50, 800) # 0.05 to 0.80
        self.slider_click.valueChanged.connect(self.on_ui_changed)
        layout.addWidget(self.slider_click)
        self.label_click = QLabel("0.200")
        layout.addWidget(self.label_click)
        
        # Keep Awake
        self.chk_keep_awake = QCheckBox("Keep Awake (Disable Sleep Wave)")
        self.chk_keep_awake.toggled.connect(self.on_ui_changed)
        layout.addWidget(self.chk_keep_awake)
        
        # High Perf
        self.chk_high_perf = QCheckBox("High Performance (HD + Better AI)")
        self.chk_high_perf.setToolTip("Requires restart of camera (brief pause).")
        self.chk_high_perf.toggled.connect(self.on_ui_changed)
        layout.addWidget(self.chk_high_perf)
        
        # Invert Scroll
        self.chk_invert_scroll = QCheckBox("Invert Scroll Direction")
        self.chk_invert_scroll.setToolTip("Natural Scrolling (Hand Down = Content Up).")
        self.chk_invert_scroll.toggled.connect(self.on_ui_changed)
        layout.addWidget(self.chk_invert_scroll)
        
        # Wake Up Button
        btn_wake = QPushButton("Wake Up Now")
        btn_wake.clicked.connect(self.wake_requested.emit)
        layout.addWidget(btn_wake)
        
        # Close Button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        
        self.setLayout(layout)
        
        # Initial Load
        self.load_profile_to_ui(self.config["current_profile"])

    def refresh_profiles_list(self):
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        self.combo_profile.addItems(list(self.config["profiles"].keys()))
        self.combo_profile.setCurrentText(self.config["current_profile"])
        self.combo_profile.blockSignals(False)

    def change_profile(self, name):
        if not name: return
        self.config["current_profile"] = name
        self.load_profile_to_ui(name)
        self.config_changed.emit() # Save new current selection

    def load_profile_to_ui(self, name):
        if name not in self.config["profiles"]: return
        p = self.config["profiles"][name]
        
        # Block signals so we don't trigger "on_ui_changed" repeatedly during load
        # However, we DO want to notify the worker of the new values.
        # So we update UI (blocking), then manually emit signals.
        
        self.blockSignals(True)
        
        sx = int(p.get("sensitivity_x", 1500))
        sy = int(p.get("sensitivity_y", 1500))
        ct = int(p.get("click_threshold", 0.20) * 1000)
        
        print(f"DEBUG: Loading Profile '{name}' -> SX:{sx} SY:{sy} CT:{ct}")
        
        self.slider_x.setValue(sx)
        self.slider_y.setValue(sy)
        self.slider_click.setValue(ct)
        self.chk_keep_awake.setChecked(p.get("keep_awake", False))
        self.chk_high_perf.setChecked(p.get("high_performance", False))
        self.chk_invert_scroll.setChecked(p.get("invert_scroll", False))
        
        # Update Labels
        self.label_x.setText(str(self.slider_x.value()))
        self.label_y.setText(str(self.slider_y.value()))
        self.label_click.setText(f"{self.slider_click.value()/1000:.3f}")
        
        self.blockSignals(False)
        
        # Now Emit Updates to Worker
        self.emit_all_updates()

    def add_profile(self):
        name, ok = QInputDialog.getText(self, "Add Profile", "Profile Name:")
        if ok and name:
            if name in self.config["profiles"]:
                QMessageBox.warning(self, "Error", "Profile already exists.")
                return
            
            # Clone current
            current_data = self.config["profiles"][self.config["current_profile"]].copy()
            self.config["profiles"][name] = current_data
            self.config["current_profile"] = name
            
            self.refresh_profiles_list()
            self.load_profile_to_ui(name)
            self.config_changed.emit()

    def delete_profile(self):
        name = self.combo_profile.currentText()
        if name == "Default":
            QMessageBox.warning(self, "Error", "Cannot delete Default profile.")
            return
        
        del self.config["profiles"][name]
        self.config["current_profile"] = "Default"
        self.refresh_profiles_list()
        self.load_profile_to_ui("Default")
        self.config_changed.emit()

    def on_ui_changed(self):
        # Update Labels
        val_x = self.slider_x.value()
        val_y = self.slider_y.value()
        val_click = self.slider_click.value() / 1000.0
        
        self.label_x.setText(str(val_x))
        self.label_y.setText(str(val_y))
        self.label_click.setText(f"{val_click:.3f}")
        
        # Update Config Object
        curr = self.config["current_profile"]
        p = self.config["profiles"][curr]
        
        p["sensitivity_x"] = float(val_x)
        p["sensitivity_y"] = float(val_y)
        p["click_threshold"] = val_click
        p["keep_awake"] = self.chk_keep_awake.isChecked()
        p["high_performance"] = self.chk_high_perf.isChecked()
        p["invert_scroll"] = self.chk_invert_scroll.isChecked()
        
        # Save
        self.config_changed.emit()
        
        # Send to Worker
        self.emit_all_updates()

    def emit_all_updates(self):
        val_x = self.slider_x.value()
        val_y = self.slider_y.value()
        val_click = self.slider_click.value() / 1000.0
        
        self.sensitivity_changed.emit(float(val_x), float(val_y))
        self.click_threshold_changed.emit(val_click)
        self.keep_awake_toggled.emit(self.chk_keep_awake.isChecked())
        self.high_perf_toggled.emit(self.chk_high_perf.isChecked())
        self.invert_scroll_toggled.emit(self.chk_invert_scroll.isChecked())


class VisionWorker(QThread):
    # Signals
    update_overlay_signal = pyqtSignal(int, int, bool, bool, bool) # x, y, is_tracking, is_sleep, is_scrolling
    finished_signal = pyqtSignal()
    
    def __init__(self, debug_mode=False): # Default debug False
        super().__init__()
        self.running = True
        self.debug_mode = debug_mode
        self.sensitivity_x = 1500.0
        self.sensitivity_y = 1500.0
        self.keep_awake = False
        self.request_wake = False
        self.invert_scroll = False
        
        # Perf Switch Logic
        self.request_perf_switch = False
        self.pending_perf_state = False 
        
        # Click Thresh Logic
        self.pending_click_thresh = -1.0
        self.current_click_thresh_val = 0.20
        
        # Drawing Utils
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_hands_style = mp.solutions.hands
        
    def set_performance_mode(self, enabled):
        if self.pending_perf_state != enabled: # Only if changed
            self.pending_perf_state = enabled
            self.request_perf_switch = True
            print(f"Performance Switch Requested: {enabled}")
    
    def set_click_threshold(self, val):
        self.pending_click_thresh = val
        self.current_click_thresh_val = val

    def set_sensitivity(self, x, y):
        self.sensitivity_x = x
        self.sensitivity_y = y
        
    def set_keep_awake(self, enabled):
        self.keep_awake = enabled
        
    def trigger_wake(self):
        self.request_wake = True
        
    def set_invert_scroll(self, enabled):
        self.invert_scroll = enabled
    
    def set_debug(self, enabled):
        self.debug_mode = enabled

    def run(self):
        print(f"Vision Worker Started (Debug={self.debug_mode})...")
        try:
            vision = VisionEngine(high_performance=self.pending_perf_state)
            input_ctrl = InputController()
            gesture_mgr = GestureManager()
            
            screen_w = input_ctrl.screen_width
            screen_h = input_ctrl.screen_height
            
            prev_x, prev_y = 0, 0
            first_frame = True
            
            smoother = OneEuroFilter(min_cutoff=0.1, beta=0.5) 
            
            print("System Ready.")
            
            window_open = False

            while self.running:
                # Perf Switch Check
                if self.request_perf_switch:
                    print("Switching Performance Mode...")
                    vision.set_performance_mode(self.pending_perf_state)
                    self.request_perf_switch = False
                
                # Click Threshold Check
                if self.pending_click_thresh > 0:
                     gesture_mgr.set_click_threshold(self.pending_click_thresh)
                     self.pending_click_thresh = -1.0
                     
                # Force Wake Check
                if self.request_wake:
                    gesture_mgr.current_state = GestureState.IDLE
                    print("MANUAL WAKE UP!")
                    self.request_wake = False
                
                # Update
                frame, landmarks, handedness = vision.get_frame()
                if frame is None:
                    break

                state = GestureState.SLEEP
                action = GestureAction.NONE
                
                ui_x, ui_y = 0, 0
                is_tracking = False
                is_scrolling = False

                if landmarks:
                    state, action = gesture_mgr.process(landmarks, handedness)
                    
                    if action == GestureAction.WAKE:
                        print("WAKE UP!")
                    elif action == GestureAction.SLEEP:
                        if self.keep_awake:
                            # print("SLEEP BLOCKED")
                            gesture_mgr.current_state = GestureState.IDLE
                            state = GestureState.IDLE
                        else:
                            print("GOING TO SLEEP...")
                            
                    if self.keep_awake and state == GestureState.SLEEP:
                         gesture_mgr.current_state = GestureState.IDLE
                         state = GestureState.IDLE
                    
                    # Calculate Cursor Source (Index Tip)
                    i_tip = landmarks.landmark[8]
                    raw_x, raw_y = i_tip.x, i_tip.y
                    
                    curr_x_norm, curr_y_norm = smoother.filter(raw_x, raw_y)
                    
                    ui_x = int(curr_x_norm * screen_w)
                    ui_y = int(curr_y_norm * screen_h)
                    
                    if first_frame:
                        prev_x, prev_y = curr_x_norm, curr_y_norm
                        first_frame = False

                    # MOVE
                    if state == GestureState.TRACKING or state == GestureState.CLICK_PENDING:
                        is_tracking = True
                        dx = curr_x_norm - prev_x
                        dy = curr_y_norm - prev_y
                        input_ctrl.move_cursor_relative(dx, dy, sensitivity=self.sensitivity_x)
                    
                    # SCROLL
                    elif state == GestureState.SCROLLING:
                        is_scrolling = True
                        dy = curr_y_norm - prev_y
                        if abs(dy) > 0.002: # Deadzone
                            dir = -1.0 if dy > 0 else 1.0 
                            magnitude = abs(dy) * 50.0 
                            
                            if self.invert_scroll:
                                dir = -dir
                                
                            input_ctrl.scroll_vertical(dir * magnitude)

                    # CLICK
                    if action == GestureAction.CLICK:
                        input_ctrl.left_click()
                        print("CLICK!")

                    prev_x, prev_y = curr_x_norm, curr_y_norm
                    
                    # Debug Draw (Silhouette Mode)
                    if self.debug_mode:
                        h, w, c = frame.shape
                        debug_frame = np.zeros((h, w, c), dtype=np.uint8)
                        
                        self.mp_drawing.draw_landmarks(
                            debug_frame, 
                            landmarks, 
                            self.mp_hands_style.HAND_CONNECTIONS,
                            self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                            self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
                        )
                        
                        cx, cy = int(curr_x_norm * w), int(curr_y_norm * h)
                        status_color = (100, 100, 100)
                        if state == GestureState.IDLE: status_color = (255, 255, 255)
                        if state == GestureState.TRACKING: status_color = (0, 255, 0)
                        if state == GestureState.SCROLLING: status_color = (255, 255, 0)
                        if state == GestureState.CLICK_PENDING: status_color = (0, 0, 255)
                        if state == GestureState.SLEEP: status_color = (50, 50, 150)

                        cv2.circle(debug_frame, (cx, cy), 8, status_color, -1)
                        cv2.putText(debug_frame, f"State: {state}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                        if handedness:
                            cv2.putText(debug_frame, f"Hand: {handedness}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                             
                        cv2.imshow("Ghost Hand Debug (Silhouette)", debug_frame)
                        window_open = True
                else:
                    if self.debug_mode:
                        h, w, c = frame.shape
                        debug_frame = np.zeros((h, w, c), dtype=np.uint8)
                        cv2.putText(debug_frame, "No Hand Detected", (30, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
                        cv2.imshow("Ghost Hand Debug (Silhouette)", debug_frame)
                        window_open = True
                        
                    first_frame = True

                # Signal
                is_sleep = (state == GestureState.SLEEP)
                if landmarks:
                    self.update_overlay_signal.emit(ui_x, ui_y, is_tracking, is_sleep, is_scrolling)
                
                # Check Input
                if self.debug_mode:
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        self.running = False
                else:
                    if window_open:
                        cv2.destroyAllWindows()
                        cv2.waitKey(1)
                        window_open = False
                        
            vision.release()
            cv2.destroyAllWindows()
            self.finished_signal.emit()
            
        except Exception as e:
            print(f"Vision Worker Crashed: {e}")
            import traceback
            traceback.print_exc()
            
    def stop(self):
        self.running = False

class GhostHandApp(QObject):
    def __init__(self):
        super().__init__()
        
        # Single Instance Lock
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.mutex_handle = self.kernel32.CreateMutexW(None, False, "GhostHandMutex")
        if ctypes.get_last_error() == 183: # ERROR_ALREADY_EXISTS
            print("GhostHand is already running! Exiting.")
            sys.exit(0)

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Load Config (Root Object)
        self.config = load_config()
        save_config(self.config) 
        print(f"Loaded Profile: {self.config['current_profile']}")
        
        # Init Settings from Current Profile
        curr_p_name = self.config["current_profile"]
        if curr_p_name not in self.config["profiles"]:
            curr_p_name = "Default"
            self.config["current_profile"] = "Default"
            
        profile = self.config["profiles"][curr_p_name]
        
        # Load Icon
        self.icon = QIcon(resource_path("ghost_hand.png"))
        if self.icon.isNull():
             self.icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
             
        # Window Icon
        self.app.setWindowIcon(self.icon)
        
        # Overlay
        self.overlay = OverlayWindow(
            hand_icon_path=resource_path("ghost_hand.png"),
            scroll_icon_path=resource_path("scroll_icon.png")
        )
        self.overlay.show()
        
        # Worker - Init with Config
        self.worker = VisionWorker(debug_mode=False)
        self.worker.sensitivity_x = float(profile.get("sensitivity_x", 1500))
        self.worker.sensitivity_y = float(profile.get("sensitivity_y", 1500))
        self.worker.keep_awake = profile.get("keep_awake", False)
        self.worker.pending_perf_state = profile.get("high_performance", False)
        self.worker.current_click_thresh_val = float(profile.get("click_threshold", 0.20))
        self.worker.pending_click_thresh = float(profile.get("click_threshold", 0.20))
        self.worker.invert_scroll = profile.get("invert_scroll", False)
        
        self.worker.request_perf_switch = True
        
        # Connect Signal
        self.worker.update_overlay_signal.connect(self.overlay.update_hand_pose)
        self.worker.finished_signal.connect(self.app.quit)
        
        # Settings Dialog
        self.settings_dlg = None
        
        # Tray Icon
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip(f"Ghost Hand [{curr_p_name}]")
        
        # Tray Menu
        self.menu = QMenu()
        
        self.action_settings = QAction("Settings", self.app)
        self.action_settings.triggered.connect(self.open_settings)
        self.menu.addAction(self.action_settings)
        
        self.action_debug = QAction("Toggle Camera View", self.app)
        self.action_debug.setCheckable(True)
        self.action_debug.setChecked(False) 
        self.action_debug.triggered.connect(self.toggle_debug)
        self.menu.addAction(self.action_debug)
        
        self.menu.addSeparator()
        
        self.action_exit = QAction("Exit", self.app)
        self.action_exit.triggered.connect(self.exit_app)
        self.menu.addAction(self.action_exit)
        
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        
        self.app.aboutToQuit.connect(self.cleanup)
        
    def run(self):
        self.worker.start()
        sys.exit(self.app.exec())
        
    def open_settings(self):
        if not self.settings_dlg:
            self.settings_dlg = SettingsDialog(self.config)
            
            # Connect to Worker
            self.settings_dlg.sensitivity_changed.connect(self.worker.set_sensitivity)
            self.settings_dlg.keep_awake_toggled.connect(self.worker.set_keep_awake)
            self.settings_dlg.high_perf_toggled.connect(self.worker.set_performance_mode)
            self.settings_dlg.click_threshold_changed.connect(self.worker.set_click_threshold)
            self.settings_dlg.wake_requested.connect(self.worker.trigger_wake)
            self.settings_dlg.invert_scroll_toggled.connect(self.worker.set_invert_scroll)
            
            # Connect to Config Saver
            self.settings_dlg.config_changed.connect(self.save_current_config)
            
        self.settings_dlg.show()
        self.settings_dlg.raise_()
        self.settings_dlg.activateWindow()
        
    def save_current_config(self):
        save_config(self.config)
        # Update Tray Tooltip
        p_name = self.config["current_profile"]
        self.tray.setToolTip(f"Ghost Hand [{p_name}]")

    def toggle_debug(self, checked):
        self.worker.set_debug(checked)
        
    def exit_app(self):
        self.worker.stop()
        self.app.quit()
        
    def cleanup(self):
        self.worker.stop()
        self.worker.wait()
        self.overlay.close()

if __name__ == "__main__":
    app_instance = GhostHandApp()
    app_instance.run()
