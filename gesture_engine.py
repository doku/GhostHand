import math
import time
from collections import deque

class GestureState:
    SLEEP = "SLEEP"
    IDLE = "IDLE"      # Hand detected, but not in tracking pose
    TRACKING = "TRACKING" # Clutch engaged (Strictly One Finger Up)
    CLICK_PENDING = "CLICK_PENDING"
    SCROLLING = "SCROLLING"

class GestureAction:
    NONE = "NONE"
    CLICK = "CLICK"
    WAKE = "WAKE"
    SLEEP = "SLEEP"
    SCROLL = "SCROLL"

class GestureManager:
    """
    Analyzes landmarks to trigger defined actions.
    """
    def __init__(self):
        # Thresholds (Normalized 0.0 - 1.0)
        self.CLICK_THRESHOLD = 0.14     # Thumb Separated = Open
        
        # Wave Settings
        self.WAVE_HISTORY_SIZE = 20     # Frames to track for wave
        self.WAVE_MOVEMENT_THRESHOLD = 0.4 # Total X travel required
        self.WAVE_COOLDOWN = 2.0        # Seconds between toggles
        
        # Hold to Wake Settings
        self.HOLD_TIME_REQUIRED = 1.0   # Seconds to hold still
        self.HOLD_STABILITY_THRESH = 0.05 # Movement variance allowed
        self.hold_start_time = 0
        
        self.current_state = GestureState.SLEEP # Start in SLEEP
        self.prev_state = GestureState.SLEEP
        
        # State tracking for click
        self.was_thumb_closed = False 
        
        # Wave tracking
        self.wrist_history = deque(maxlen=self.WAVE_HISTORY_SIZE)
        self.last_toggle_time = 0
        
    def set_click_threshold(self, val):
        self.CLICK_THRESHOLD = val

    def _is_palm_facing(self, landmarks, handedness):
        """
        Determines if the palm is facing the camera using winding order (Cross Product Z).
        Assumption: Frame is mirrored (Selfie view).
        """
        if not handedness:
            return True # Fallback if unknown
            
        # Landmarks: 0=Wrist, 5=IndexMCP, 17=PinkyMCP
        p0 = landmarks.landmark[0]
        p5 = landmarks.landmark[5]
        p17 = landmarks.landmark[17]
        
        # Vectors 0->5 and 0->17
        # Note: MP y increases downwards. x increases right.
        v1_x = p5.x - p0.x
        v1_y = p5.y - p0.y
        
        v2_x = p17.x - p0.x
        v2_y = p17.y - p0.y
        
        # Cross Product Z component (2D determinant)
        # cp_z = (v1_x * v2_y) - (v1_y * v2_x)
        cp_z = (v1_x * v2_y) - (v1_y * v2_x)
        
        # Logic for Mirrored Frame:
        # Right Hand Palm: Thumb on Left, Pinky on Right. V1(-x,-y), V2(+x,-y). CP > 0.
        # Left Hand Palm: Thumb on Right, Pinky on Left. V1(+x,-y), V2(-x,-y). CP < 0.
        
        if handedness == "Right":
            return cp_z > 0
        elif handedness == "Left":
            return cp_z < 0
        
        return True
        
    def _detect_hold_to_wake(self, landmarks):
        """
        Detects if user is holding open palm steadily.
        """
        # 1. Check Open Palm (5 fingers)
        tips_ids = [4, 8, 12, 16, 20]
        pips_ids = [2, 6, 10, 14, 18] # thumb uses IP (3) vs MCP(2). MediaPipe: 4=Tip, 3=IP, 2=MCP. 
        # For thumb, check tip vs MCP logic? Or just check if it's far from index?
        # Simple heuristic: x dist of thumb tip from index mcp?
        # Let's use the standard "fingers extended" logic for 4 fingers + thumb check.
        
        fingers_open = 0
        # Index to Pinky
        for i in range(1, 5):
            if landmarks.landmark[tips_ids[i]].y < landmarks.landmark[pips_ids[i]].y:
                fingers_open += 1
        
        # Thumb: Tip further from index MCP than IP? Or just use general shape.
        # Let's assume 4 fingers open is 'Open Palm' enough for wake.
        if fingers_open < 4:
            self.hold_start_time = 0
            return False

        # 2. Check Stability (Wrist History)
        # We need history. process() appends to wrist_history.
        if len(self.wrist_history) < self.WAVE_HISTORY_SIZE:
             return False
             
        x_min = min(self.wrist_history)
        x_max = max(self.wrist_history)
        diff = x_max - x_min
        
        if diff < self.HOLD_STABILITY_THRESH:
            # Stable
            if self.hold_start_time == 0:
                self.hold_start_time = time.time()
                # print("Hold Started...")
            elif (time.time() - self.hold_start_time) > self.HOLD_TIME_REQUIRED:
                self.hold_start_time = 0 # Reset
                return True
        else:
            # Moving
            self.hold_start_time = 0
            
        return False
        
    def _detect_wave(self):
        """
        Detects if user is waving (Open Palm, moving side to side).
        """
        if len(self.wrist_history) < self.WAVE_HISTORY_SIZE:
            return False
            
        # 1. (Open Palm check moved to caller)
            
        # 2. Check X Movement Variance
        x_min = min(self.wrist_history)
        x_max = max(self.wrist_history)
        
        # EDGE REJECTION:
        # Ignore if the movement touches the edges (Swipe Across)
        # 0.0 = Left Edge, 1.0 = Right Edge
        if x_min < 0.1 or x_max > 0.9:
            return False
            
        diff = x_max - x_min
        
        if diff > 0.15: # 15% range
             return True
             
        return False

    def process(self, landmarks, handedness=None):
        """
        Returns (state, action)
        """
        current_time = time.time()
        
        if not landmarks:
            self.hold_start_time = 0 # Lost hand, reset hold
            return self.current_state, GestureAction.NONE
            
        # Calc basic features
        thumb_tip = landmarks.landmark[4]
        index_tip = landmarks.landmark[8]
        middle_tip = landmarks.landmark[12]
        ring_tip = landmarks.landmark[16]
        pinky_tip = landmarks.landmark[20]
        
        wrist = landmarks.landmark[0]
        
        # Finger States (Basic y-check vs PIP/MCP for simplicity)
        index_mcp = landmarks.landmark[5]
        middle_mcp = landmarks.landmark[9]
        ring_mcp = landmarks.landmark[13]
        pinky_mcp = landmarks.landmark[17]
        
        is_index_up = index_tip.y < index_mcp.y
        is_middle_up = middle_tip.y < middle_mcp.y
        is_ring_up = ring_tip.y < ring_mcp.y
        is_pinky_up = pinky_tip.y < pinky_mcp.y
        
        # Fingers Open Count (for generic "Hand Open")
        fingers_open = 0
        if is_index_up: fingers_open += 1
        if is_middle_up: fingers_open += 1
        if is_ring_up: fingers_open += 1
        if is_pinky_up: fingers_open += 1
        
        # Palm Check
        is_palm = self._is_palm_facing(landmarks, handedness)

        # --- GLOBAL WAKE/SLEEP CHECK ---
        
        # A. Hold to Wake (Only if Sleeping)
        if self.current_state == GestureState.SLEEP:
             # Important: We must update history for stability check
             self.wrist_history.append(landmarks.landmark[0].x)
             
             # Require Palm Facing for Hold-to-Wake
             if is_palm and self._detect_hold_to_wake(landmarks):
                 self.last_toggle_time = current_time
                 self.current_state = GestureState.IDLE
                 self.wrist_history.clear()
                 return self.current_state, GestureAction.WAKE
        
        # B. Wave Detection (Wake OR Sleep)
        self.wrist_history.append(landmarks.landmark[0].x)
        if (current_time - self.last_toggle_time > self.WAVE_COOLDOWN):
            # Require 3+ fingers to count as a "Hand Open" Wave
            # AND Require Palm Facing to prevent Back-of-hand swipes
            if fingers_open >= 3 and is_palm:
                if self._detect_wave():
                    self.last_toggle_time = current_time
                    
                    if self.current_state == GestureState.SLEEP:
                        self.current_state = GestureState.IDLE
                        return self.current_state, GestureAction.WAKE
                    else:
                        self.current_state = GestureState.SLEEP
                        return self.current_state, GestureAction.SLEEP
                        
        # If Sleeping, do nothing else
        if self.current_state == GestureState.SLEEP:
            return self.current_state, GestureAction.NONE

        # --- NORMAL OPERATION ---
        
        # Extract key points
        thumb_tip = landmarks.landmark[4]
        index_mcp = landmarks.landmark[5]   # Base of index finger
        
        index_pip = landmarks.landmark[6]
        
        middle_pip = landmarks.landmark[10]
        ring_pip = landmarks.landmark[14]
        pinky_pip = landmarks.landmark[18]
        
        # 1. Track ONLY if Index is UP and others are DOWN
        is_tracking_pose = is_index_up and (not is_middle_up) and (not is_ring_up) and (not is_pinky_up)
        
        # 2. Scroll Pose: Index + Middle UP. Ring + Pinky DOWN.
        # Thumb: Relaxed. No strict check prevents hand strain.
        # This allows both "Three Finger Gun" and "Peace Sign" to scroll.
        
        # Calculate scale reference (Wrist to Index MCP) represents hand size
        scale_ref = math.sqrt((wrist.x - index_mcp.x)**2 + (wrist.y - index_mcp.y)**2)
        if scale_ref < 0.01: scale_ref = 0.01 # Prevent div/0

        # Calculate thumb action distance (Thumb Tip to Index MCP)
        raw_dist = math.sqrt((thumb_tip.x - index_mcp.x)**2 + (thumb_tip.y - index_mcp.y)**2)
        
        # Normalized Ratio (Scale Invariant)
        click_ratio = raw_dist / scale_ref
        
        is_thumb_closed = click_ratio < self.CLICK_THRESHOLD
        is_thumb_open = not is_thumb_closed
        
        is_scroll_pose = is_index_up and is_middle_up and (not is_ring_up) and (not is_pinky_up)
        
        # State Machine
        action = GestureAction.NONE
        new_state = self.current_state # Default keep current (IDLE/TRACKING)

        if is_tracking_pose:
            new_state = GestureState.TRACKING
            
            # Click Trigger
            if self.was_thumb_closed and is_thumb_open:
                 print(f"CLICK TRIGGERED! Ratio: {click_ratio:.3f} (Thresh: {self.CLICK_THRESHOLD})")
                 action = GestureAction.CLICK
                 new_state = GestureState.CLICK_PENDING 
                 
        elif is_scroll_pose:
            new_state = GestureState.SCROLLING
            action = GestureAction.SCROLL # Continuous action?
            
        else:
            new_state = GestureState.IDLE

        self.was_thumb_closed = is_thumb_closed
        self.prev_state = self.current_state
        self.current_state = new_state
        
        return self.current_state, action
