import cv2
import mediapipe as mp
import time

class VisionEngine:
    """
    Handles camera acquisition and MediaPipe Hands inference.
    Supports dynamic High Performance vs Low Power modes.
    """
    def __init__(self, high_performance=False):
        self.mp_hands = mp.solutions.hands
        self.high_performance = high_performance
        self.cap = None
        self.hands = None
        self.camera_index = 0
        
        self._init_system()

    def _init_system(self):
        # Release existing if any
        if self.hands: self.hands.close()
        if self.cap: self.cap.release()
        
        # Config based on mode
        if self.high_performance:
            print("Vision: High Performance Mode (HD + Full Model)")
            model_comp = 1
            w, h = 1280, 720
        else:
            print("Vision: Low Performance Mode (SD + Lite Model)")
            model_comp = 0
            w, h = 640, 480
            
        # Init Camera
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            
            if not self.cap.isOpened():
                print(f"Error: Could not open camera {self.camera_index}")
        except Exception as e:
            print(f"Camera Error: {e}")
        
        # Init MediaPipe
        self.hands = self.mp_hands.Hands(
            model_complexity=model_comp,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
            max_num_hands=1
        )
        
    def set_performance_mode(self, high_performance):
        """
        Switch between Lite (Low Spec) and Full (High Spec) models.
        """
        if self.high_performance == high_performance:
            return
        
        self.high_performance = high_performance
        # Re-initialize
        self._init_system()

    def get_frame(self):
        """
        Captures a frame, Processes it.
        Returns: 
            frame (image): Original frame (BGR).
            landmarks (NormalizedLandmarkList): Detected hand landmarks (or None).
            handedness (str): "Left" or "Right" (or None).
        """
        if not self.cap or not self.cap.isOpened():
             return None, None, None
             
        success, frame = self.cap.read()
        if not success:
            return None, None, None

        # FLIP FRAME HORIZONTALLY (Mirror View)
        frame = cv2.flip(frame, 1)

        # Process
        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Pass by reference to writeable=False to improve performance
        rgb_frame.flags.writeable = False
        results = self.hands.process(rgb_frame)
        rgb_frame.flags.writeable = True

        landmarks = None
        handedness = None
        
        if results.multi_hand_landmarks:
            landmarks = results.multi_hand_landmarks[0]
            if results.multi_handedness:
                handedness = results.multi_handedness[0].classification[0].label
            
        return frame, landmarks, handedness

    def release(self):
        if self.cap: self.cap.release()
        if self.hands: self.hands.close()

if __name__ == "__main__":
    ve = VisionEngine(high_performance=False)
    print("Camera opened. Press 'q' to quit.")
    try:
        while True:
            frame, landmarks, handedness = ve.get_frame()
            if frame is None:
                break
                
            if landmarks:
                h, w, _ = frame.shape
                cx, cy = int(landmarks.landmark[8].x * w), int(landmarks.landmark[8].y * h)
                cv2.circle(frame, (cx, cy), 10, (255, 0, 0), -1)
                if handedness:
                    cv2.putText(frame, handedness, (cx, cy-40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)

            cv2.imshow("Vision Test", frame)
            if cv2.waitKey(5) & 0xFF == ord('q'):
                break
    finally:
        ve.release()
        cv2.destroyAllWindows()
