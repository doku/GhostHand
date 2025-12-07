Technical Requirements Specification: Project "Ghost Hand"

Version: 1.1.0
Status: Draft / Iteration 2

1. Project Overview

The "Ghost Hand" project is a Windows-based Human-Computer Interaction (HCI) utility. It creates an invisible system overlay that utilizes a webcam to track user hand movements and map them to the Windows cursor. The system includes a visual "Virtual Hand" that reveals itself upon specific activation gestures, allowing users to control the mouse without physical contact.

2. System Architecture

The application follows a modular architecture to ensure separation of concerns between vision processing, state management, and rendering.

2.1 Modules

Vision Engine (vision_core.py): Handles camera acquisition and MediaPipe inference.

Gesture Manager (gesture_engine.py): A scalable state machine that analyzes landmarks to trigger defined actions. Designed to allow easy addition of new gesture definitions.

Input Injector (input_controller.py): Interfaces with Windows user32.dll to move the physical cursor.

Overlay Renderer (overlay_ui.py): A PyQt6 transparent window that draws the virtual hand guidance.

Main Controller (main.py): Orchestrates data flow between modules.

3. Functional Requirements

3.1 Vision & Tracking

FR-01 Hand Capture: The system shall use the default system camera (Index 0) to capture frames at a minimum of 30 FPS.

FR-02 Landmark Detection: The system shall detect 21 hand landmarks using MediaPipe Hands.

FR-03 Relative Coordinate Mapping:

The system shall not map hand position absolutely to screen pixels.

Logic: The system shall calculate the delta (change in position) of the tracking centroid between the current frame and the previous frame.

Function: update_cursor_relative(dx, dy, sensitivity_factor)

Clutch: Cursor movement only occurs when the "Tracking Pose" (see FR-06) is valid.

3.2 Mouse Control & Gestures

FR-04 Input Injection: The system shall update the Windows cursor position using SendInput (Win32 API) for sub-10ms latency.

FR-05 Smoothing: The system shall apply a smoothing algorithm (e.g., One Euro Filter or Kalman Filter) to the raw coordinate deltas before applying them to the cursor.

FR-06 Gesture Definitions (Extendable):

The system shall use a dictionary-based or class-based structure for gestures to allow future expansion.

Gesture A: Tracking Pose ( The "Clutch")

Definition: Index Finger Tip (8) and Middle Finger Tip (12) are touching (Distance < TRACKING_THRESHOLD) AND Palm is facing camera.

Action: Enable Cursor Movement (Relative).

Gesture B: Primary Click (Left Click)

Definition: Transition from "Tracking Pose" to "Separated Pose" (Index and Middle finger distance > CLICK_THRESHOLD).

Action: Trigger Windows Left Mouse Click (Down + Up).

Logic: The cursor must freeze position immediately upon separation to prevent jitter during the click.

3.3 The "Invisible" Overlay

FR-07 Transparency: The application window must be full-screen, frameless, and visually transparent (Alpha = 0) by default.

FR-08 Click-Through Capability: The overlay must not intercept mouse clicks. It must use the Windows Extended Style WS_EX_TRANSPARENT so interactions pass through to the underlying OS.

FR-09 Virtual Hand Rendering:

Style: The overlay shall render a semi-transparent, realistic hand graphic (masked image or 3D model projection) rather than a simple skeleton.

Feedback: The graphic shall visually deform or change state (e.g., color shift or animation) to indicate when "Tracking Pose" is active vs inactive.

3.4 Interaction Logic (State Machine)

FR-10 Activation (The "Wave"):

State: System starts in SLEEP mode.

Trigger: User performs a "Wave" gesture (rapid lateral movement).

Result: System transitions to ACTIVE mode. Overlay Opacity fades in.

FR-11 Timeout: If no hand is detected for 5 seconds, system returns to SLEEP mode.

3.5 System Tray Integration

FR-12 Taskbar Icon: The app shall minimize to the system tray.

FR-13 Context Menu: Right-clicking the tray icon provides: "Settings", "Pause", "Exit".

4. Development Phases

Phase 1: The Base System (Proof of Concept)

Goal: Verify MediaPipe efficiency and Relative Cursor logic.

Step 1.1: Setup Python environment with opencv-python, mediapipe, pywin32.

Step 1.2: Implement VisionEngine to detect Index and Middle finger landmarks.

Step 1.3: Implement InputController with relative movement logic (dx, dy).

Step 1.4: Implement the "Clutch" logic: Only move cursor when Index+Middle fingers are touching.

Phase 2: The Visual Overlay

Goal: Create the "Invisible" window and Realistic Hand Graphics.

Step 2.1: Create a PyQt6 Fullscreen transparent window with WS_EX_TRANSPARENT.

Step 2.2: Load a realistic hand asset (PNG with transparency) and map its position/rotation to the MediaPipe palm coordinates.

Step 2.3: Implement visual feedback: Change hand graphic opacity/tint when in "Tracking Pose".

Phase 3: Gesture Logic & Refinement

Goal: Tuning the interaction feel.

Step 3.1: Implement the GestureManager to handle the "Separation = Click" event.

Step 3.2: Tune the TRACKING_THRESHOLD vs CLICK_THRESHOLD to prevent accidental clicks while moving.

Step 3.3: Implement SmoothingFilter to make relative movement feel like a high-end touchpad.

Phase 4: Productization

Goal: User experience and Settings.

Step 4.1: Add System Tray icon.

Step 4.2: Build a Settings Dialog to adjust Sensitivity, Click Threshold, and Smoothing Factor.

Step 4.3: Compile to .exe.