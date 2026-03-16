
"""
#eskisi

from dataclasses import dataclass
from typing import Optional
import time

def iou_xyxy(a, b):
    ax1,ay1,ax2,ay2 = a
    bx1,by1,bx2,by2 = b
    ix1,iy1 = max(ax1,bx1), max(ay1,by1)
    ix2,iy2 = min(ax2,bx2), min(ay2,by2)
    iw,ih = max(0, ix2-ix1), max(0, iy2-iy1)
    inter = iw*ih
    area_a = max(0, ax2-ax1)*max(0, ay2-ay1)
    area_b = max(0, bx2-bx1)*max(0, by2-by1)
    return inter / (area_a + area_b - inter + 1e-9)

@dataclass
class TrackedObject:
    bbox_xyxy: tuple
    conf: float
    last_seen: float
    lost_frames: int = 0

    def center(self):
        x1,y1,x2,y2 = self.bbox_xyxy
        return (0.5*(x1+x2), 0.5*(y1+y2))

class ObjectTracker:
    def __init__(self, iou_match_thres: float, max_lost_frames: int, smooth_alpha: float):
        self.iou_match_thres = iou_match_thres
        self.max_lost_frames = max_lost_frames
        self.smooth_alpha = smooth_alpha
        self.track: Optional[TrackedObject] = None

    def update(self, detections):
        now = time.time()

        if self.track is None:
            if detections:
                best = max(detections, key=lambda d: d.conf)
                self.track = TrackedObject(best.bbox_xyxy, best.conf, now, 0)
                return self.track
            return None

        # match
        best_iou = 0.0
        best_det = None
        for d in detections:
            v = iou_xyxy(self.track.bbox_xyxy, d.bbox_xyxy)
            if v > best_iou:
                best_iou = v
                best_det = d

        if best_det is not None and best_iou >= self.iou_match_thres:
            # smoothing bbox
            a = self.smooth_alpha
            x1,y1,x2,y2 = self.track.bbox_xyxy
            nx1,ny1,nx2,ny2 = best_det.bbox_xyxy
            sm = ( (1-a)*x1 + a*nx1,
                   (1-a)*y1 + a*ny1,
                   (1-a)*x2 + a*nx2,
                   (1-a)*y2 + a*ny2 )
            self.track.bbox_xyxy = sm
            self.track.conf = best_det.conf
            self.track.last_seen = now
            self.track.lost_frames = 0
            return self.track

        # no match
        self.track.lost_frames += 1
        if self.track.lost_frames > self.max_lost_frames:
            self.track = None
            return None
        return self.track
"""

import numpy as np
import cv2
from dataclasses import dataclass
from typing import Optional, List

def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-9)

@dataclass
class TrackedObject:
    bbox_xyxy: tuple  # (x1, y1, x2, y2)
    conf: float
    class_id: int
    last_seen: float

    def center(self):
        x1, y1, x2, y2 = self.bbox_xyxy
        return (0.5 * (x1 + x2), 0.5 * (y1 + y2))


"""#eskisi
class KalmanBoxTracker:
    def __init__(self, bbox):
        # Initialize OpenCV Kalman Filter
        # State: [x, y, w, h, vx, vy, vw, vh] (Position + Velocity)
        # Measurement: [x, y, w, h] (YOLO output)
        self.kf = cv2.KalmanFilter(8, 4)
        
        # Matrix Setup
        self.kf.measurementMatrix = np.array(np.eye(4, 8), np.float32)
        self.kf.transitionMatrix = np.array(np.eye(8, 8), np.float32)
        
        # Time Step (assuming 30 FPS, dt = 1/30)
        # Position += Velocity * dt
        for i in range(4):
            self.kf.transitionMatrix[i, i+4] = 1.0 

        # Process Noise (Q) - How much we think the drone changes speed (Acceleration)
        # Low = smoother, High = faster response to turns
        self.kf.processNoiseCov = np.eye(8, dtype=np.float32) * 0.03
        self.kf.processNoiseCov[4:, 4:] *= 5.0 # Give more flexibility to velocity changes

        # Measurement Noise (R) - How much we trust YOLO
        # Low = trust YOLO, High = trust prediction
        self.kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 0.1 

        # Initialize state with first detection
        x1, y1, x2, y2 = bbox
        self.kf.statePost = np.array([[x1], [y1], [x2-x1], [y2-y1], [0], [0], [0], [0]], np.float32)
        self.kf.errorCovPost = np.eye(8, dtype=np.float32)

        self.time_since_update = 0
        self.history = []

    def update(self, bbox):
       # Update the state with a new YOLO measurement 
        self.time_since_update = 0
        x1, y1, x2, y2 = bbox
        # Convert xyxy to xywh
        measurement = np.array([[np.float32(x1)], [np.float32(y1)], [np.float32(x2-x1)], [np.float32(y2-y1)]])
        self.kf.correct(measurement)

    def predict(self):
        #Advances the state vector using current velocity 
        prediction = self.kf.predict()
        x = prediction[0, 0]
        y = prediction[1, 0]
        w = prediction[2, 0]
        h = prediction[3, 0]
        self.time_since_update += 1
        return (x, y, x+w, y+h)

    def get_state(self):
        # Returns current (x1, y1, x2, y2) 
        s = self.kf.statePost
        x, y, w, h = s[0,0], s[1,0], s[2,0], s[3,0]
        return (x, y, x+w, y+h)
    """
class KalmanBoxTracker:
    def __init__(self, bbox):
        # State: [x, y, w, h, vx, vy] (w ve h için hız takibi kaldırıldı)
        self.kf = cv2.KalmanFilter(6, 4)
        
        # Ölçüm matrisi: Ölçtüğümüz değerler [x, y, w, h]
        self.kf.measurementMatrix = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, 1, 0, 0]
        ], np.float32)
        
        # Geçiş matrisi: x = x + vx, y = y + vy
        self.kf.transitionMatrix = np.array([
            [1, 0, 0, 0, 1, 0], # x += vx
            [0, 1, 0, 0, 0, 1], # y += vy
            [0, 0, 1, 0, 0, 0], # w sabit kalma eğiliminde
            [0, 0, 0, 1, 0, 0], # h sabit kalma eğiliminde
            [0, 0, 0, 0, 1, 0], # vx
            [0, 0, 0, 0, 0, 1]  # vy
        ], np.float32)

        # Q (Süreç Gürültüsü): Çok yüksek olursa Kalman YOLO'yu çok sert takip eder (titrer)
        # Çok düşük olursa drone dönünce kutu geride kalır.
        self.kf.processNoiseCov = np.eye(6, dtype=np.float32) * 0.01
        self.kf.processNoiseCov[4:, 4:] *= 2.0 # Hız değişimine (ivmeye) biraz daha izin ver

        # R (Ölçüm Gürültüsü): YOLO kutusuna ne kadar güveniyoruz?
        self.kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 0.05 

        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        self.kf.statePost = np.array([[x1], [y1], [w], [h], [0], [0]], np.float32)
        self.kf.errorCovPost = np.eye(6, dtype=np.float32)

        self.time_since_update = 0

    def predict(self):
        prediction = self.kf.predict()
        x, y, w, h = prediction[:4, 0]
        self.time_since_update += 1
        return (float(x), float(y), float(x + w), float(y + h))

    def update(self, bbox):
        self.time_since_update = 0
        x1, y1, x2, y2 = bbox
        measurement = np.array([[np.float32(x1)], [np.float32(y1)], [np.float32(x2-x1)], [np.float32(y2-y1)]])
        self.kf.correct(measurement)

    def get_state(self):
        s = self.kf.statePost
        x, y, w, h = s[0,0], s[1,0], s[2,0], s[3,0]
        return (float(x), float(y), float(x + w), float(y + h))

class ObjectTracker:
    def __init__(self, iou_match_thres: float, max_lost_frames: int, smooth_alpha: float):
        self.iou_match_thres = iou_match_thres
        self.max_lost_frames = max_lost_frames
        self.tracker: Optional[KalmanBoxTracker] = None
        self.current_conf = 0.0

    def update(self, detections: List, now: float):
        """
        Call this every time you have NEW detections (e.g. every 10 frames)
        """
        if self.tracker is None:
            if detections:
                best = max(detections, key=lambda d: d.conf)
                self.tracker = KalmanBoxTracker(best.bbox_xyxy)
                self.current_conf = best.conf
                return TrackedObject(best.bbox_xyxy, best.conf, 0, now)
            return None

        # Predict first (Kalman step)
        pred_bbox = self.tracker.predict()

        if not detections:
            # No detections, but is the prediction valid?
            if self.tracker.time_since_update > self.max_lost_frames:
                self.tracker = None
                return None
            # Return the predicted box (GHOST TRACKING)
            return TrackedObject(pred_bbox, self.current_conf, 0, now)

        # Matching Logic
        best_iou = 0.0
        best_det = None
        for d in detections:
            # Compare YOLO box with Kalman Predicted box
            iou = iou_xyxy(pred_bbox, d.bbox_xyxy)
            if iou > best_iou:
                best_iou = iou
                best_det = d

        if best_det and best_iou >= self.iou_match_thres:
            # Found a match Correct the Kalman Filter
            self.tracker.update(best_det.bbox_xyxy)
            self.current_conf = best_det.conf
            # Return the CORRECTED position
            return TrackedObject(self.tracker.get_state(), best_det.conf, 0, now)
        
        else:
            # No match found, use prediction
            if self.tracker.time_since_update > self.max_lost_frames:
                self.tracker = None
                return None
            return TrackedObject(pred_bbox, self.current_conf, 0, now)

    def predict_only(self, now: float):
        """
        Yolo çalışmıyorken burası olucak önemli!!!
        Drone un anlık hızına göre olası konumu belirleme işi burası.
        """
        if self.tracker is None:
            return None
        
        pred_bbox = self.tracker.predict()
        
        if self.tracker.time_since_update > self.max_lost_frames:
            self.tracker = None
            return None
            
        return TrackedObject(pred_bbox, self.current_conf, 0, now)