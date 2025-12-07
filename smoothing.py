import math
import time

class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0, freq=30.0):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        
        self.x_filter = LowPassFilter()
        self.y_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        
        self.last_time = None
        
    def filter(self, x, y, timestamp=None):
        # timestamp in seconds
        if timestamp is None:
            timestamp = time.time()
            
        if self.last_time is None:
            self.last_time = timestamp
            # Initialize
            self.x_filter.set_alpha(1.0) # No filtering on first value
            self.y_filter.set_alpha(1.0)
            return self.x_filter.filter(x), self.y_filter.filter(y)
            
        dt = timestamp - self.last_time
        self.last_time = timestamp
        
        # Avoid div by zero
        if dt <= 0: return self.x_filter.last_val, self.y_filter.last_val
        
        # Calculate velocity (dx/dt)
        dx_raw = (x - self.x_filter.last_val) / dt
        dy_raw = (y - self.y_filter.last_val) / dt
        
        # Filter velocity (optional but good for jittery derivative) - simplified here just magnitude?
        # Actually OneEuro uses the derivative of the signal to tune the alpha.
        # We process X and Y independently but usually share Beta tuning?
        # Let's keep it simple: use magnitude of change for adaptive cutoff.
        
        # Standard One Euro Filter Implementation:
        # 1. Estimate derivative (using raw change)
        target_dx = (x - self.x_filter.last_val) / dt
        target_dy = (y - self.y_filter.last_val) / dt
        
        # Filter the derivative
        edx = self.dx_filter.filter(abs(target_dx) + abs(target_dy)) # Combined magnitude proxy
        
        # Calculate Cutoff
        cutoff = self.min_cutoff + self.beta * abs(edx)
        
        # Calculate Alpha
        tau = 1.0 / (2 * math.pi * cutoff)
        alpha = 1.0 / (1.0 + tau / dt)
        
        return self.x_filter.filter(x, alpha), self.y_filter.filter(y, alpha)

class LowPassFilter:
    def __init__(self):
        self.last_val = None
        
    def set_alpha(self, alpha):
        self.forced_alpha = alpha
        
    def filter(self, val, alpha=None):
        if self.last_val is None:
            self.last_val = val
            return val
            
        if alpha is None: alpha = 1.0
        
        self.last_val = alpha * val + (1.0 - alpha) * self.last_val
        return self.last_val
