import ctypes
import win32api
import win32con

# Structures for SendInput
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [("type", ctypes.c_ulong),
                ("ki", _INPUT)]

class InputController:
    """
    Interfaces with Windows user32.dll / pywin32 to control the mouse.
    """
    def __init__(self):
        self.screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        self.screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

    def move_cursor_relative(self, dx, dy, sensitivity=2.0):
        """
        Moves the cursor relative to its current position.
        dx, dy: normalized deltas (-1.0 to 1.0) or raw pixel deltas.
        sensitivity: multiplier for the movement.
        """
        # Calculate pixel delta
        pixel_dx = int(dx * sensitivity)
        pixel_dy = int(dy * sensitivity)
        
        if pixel_dx == 0 and pixel_dy == 0:
            return

        # Use SendInput for relative movement
        # MOUSEEVENTF_MOVE (0x0001) moves relative to current position
        # unless MOUSEEVENTF_ABSOLUTE is set.
        
        flags = win32con.MOUSEEVENTF_MOVE
        
        inp = INPUT()
        inp.type = 0 # INPUT_MOUSE
        inp.ki.mi.dx = pixel_dx
        inp.ki.mi.dy = pixel_dy
        inp.ki.mi.dwFlags = flags
        inp.ki.mi.time = 0
        inp.ki.mi.mouseData = 0
        
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def left_click(self):
        """
        Performs a full left click (down + up).
        """
        self._send_mouse_event(win32con.MOUSEEVENTF_LEFTDOWN)
        self._send_mouse_event(win32con.MOUSEEVENTF_LEFTUP)

    def _send_mouse_event(self, flags):
        inp = INPUT()
        inp.type = 0 # INPUT_MOUSE
        inp.ki.mi.dwFlags = flags
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        
    def scroll_vertical(self, steps):
        """
        Scrolls the mouse wheel.
        steps: +1 for up (away from user), -1 for down (towards user).
        Multiplier applied for speed.
        """
        # WHEEL_DELTA is 120
        amount = int(steps * 120)
        
        inp = INPUT()
        inp.type = 0 # INPUT_MOUSE
        inp.ki.mi.dx = 0
        inp.ki.mi.dy = 0
        inp.ki.mi.dwFlags = win32con.MOUSEEVENTF_WHEEL
        inp.ki.mi.time = 0
        inp.ki.mi.mouseData = amount
        inp.ki.mi.dwExtraInfo = None
        
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

if __name__ == "__main__":
    import time
    ic = InputController()
    print("Moving cursor in square pattern...")
    for _ in range(4):
        ic.move_cursor_relative(50, 0, 1) # Right
        time.sleep(0.5)
        ic.move_cursor_relative(0, 50, 1) # Down
        time.sleep(0.5)
        ic.move_cursor_relative(-50, 0, 1) # Left
        time.sleep(0.5)
        ic.move_cursor_relative(0, -50, 1) # Up
        time.sleep(0.5)
