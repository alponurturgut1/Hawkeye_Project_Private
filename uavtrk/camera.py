
"""

import cv2
import threading
import time

class CameraProcessor:
    def __init__(self, use_gstreamer: bool, gst_pipeline: str, opencv_source, width: int, height: int):
        self.use_gstreamer = use_gstreamer
        self.gst_pipeline = gst_pipeline
        self.opencv_source = opencv_source
        self.width = width
        self.height = height

        self.cap = None
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

        self.fps = 0.0

    def start(self):
        if self.use_gstreamer:
            self.cap = cv2.VideoCapture(self.gst_pipeline, cv2.CAP_GSTREAMER)
        else:
            self.cap = cv2.VideoCapture(self.opencv_source)

        # Bazı kaynaklarda set işe yarar
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            raise RuntimeError("Camera stream açılamadı. GStreamer pipeline / kaynak hatalı olabilir.")

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()

    def _loop(self):
        t0 = time.time()
        n = 0
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame = frame
            n += 1
            t1 = time.time()
            if t1 - t0 >= 1.0:
                self.fps = n / (t1 - t0)
                t0 = t1
                n = 0

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()
"""



import cv2
import threading
import time
import socket
import numpy as np

class CameraProcessor:
    def __init__(self, udp_ip="127.0.0.1", udp_port=5600, width=640, height=480):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.width = width
        self.height = height

        self.sock = None
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

        self.fps = 0.0

    def start(self):
        # UDP Soketini oluşturuyoruz
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Aynı portun tekrar kullanılabilmesi için izin veriyoruz
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.udp_ip, self.udp_port))
        
        # Soket zaman aşımı (timeout) ekleyelim ki veri gelmezse kilitlenmesin
        self.sock.settimeout(2.0)

        print(f"UDP Dinleniyor: {self.udp_ip}:{self.udp_port} üzerinden görüntü bekleniyor...")

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.sock:
            self.sock.close()

    def _loop(self):
        t0 = time.time()
        n = 0
        while self._running:
            try:
                # UDP paketini al (64KB standart limit, JPG paketleri için yeterli)
                data, _ = self.sock.recvfrom(65507)
                
                # Byte verisini numpy dizisine, oradan da görüntüye çevir
                nparr = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Gerekirse boyutu burada tekrar doğrula
                    if frame.shape[1] != self.width or frame.shape[0] != self.height:
                        frame = cv2.resize(frame, (self.width, self.height))

                    with self._lock:
                        self._frame = frame
                    n += 1
                
                # FPS Hesaplama
                t1 = time.time()
                if t1 - t0 >= 1.0:
                    self.fps = n / (t1 - t0)
                    t0 = t1
                    n = 0

            except socket.timeout:
                print("Veri bekleniyor (Timeout)... Bridge scriptinin çalıştığından emin ol.")
                continue
            except Exception as e:
                print(f"Döngü hatası: {e}")
                time.sleep(0.01)

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()







