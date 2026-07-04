
# import time
# import yaml
# import cv2
# import math
# from pymavlink import mavutil

#
# from .utils import setup_logger, RateLimiter
# from .state import SystemState
# from .camera import CameraProcessor
# from .yolo_onnx import YOLODetector
# from .tracker import ObjectTracker
# from .mavlink_iface import MavlinkVehicle
# from .follow import PositionBasedFollow, bearing_error_from_bbox

# class DroneTrackingSystem:
#     def __init__(self, config_path: str):
#         with open(config_path, "r") as f:
#             self.cfg = yaml.safe_load(f)

#         self.log = setup_logger(self.cfg["system"].get("log_level", "INFO"))
#         self.state = SystemState.INITIALIZING

#         # Camera
#         vcfg = self.cfg["video"]
#         self.camera = CameraProcessor(
#             udp_ip=vcfg.get("udp_ip", "127.0.0.1"),
#             udp_port=int(vcfg.get("udp_port", 5600)),
#             width=int(vcfg.get("width", 640)),
#             height=int(vcfg.get("height", 480))
#         )

#         # YOLO
#         ycfg = self.cfg["yolo"]
#         self.detector = YOLODetector(
#             onnx_path=ycfg["onnx_path"],
#             input_size=int(ycfg.get("input_size", 640)),
#             conf_thres=float(ycfg.get("conf_thres", 0.25)),
#             iou_thres=float(ycfg.get("iou_thres", 0.45)),
#             class_name=str(ycfg.get("class_name", "drone")),
#             providers=ycfg.get("providers", ["CPUExecutionProvider"]),
#         )

#         # Tracker
#         tcfg = self.cfg["tracking"]
#         self.tracker = ObjectTracker(
#             iou_match_thres=float(tcfg.get("iou_match_thres", 0.20)),
#             max_lost_frames=int(tcfg.get("max_lost_frames", 10)),
#             smooth_alpha=float(tcfg.get("smooth_alpha", 0.90)), #0.25 di
#         )

#         # MAVLink
#         mcfg = self.cfg["mavlink"]
#         self.hunter = MavlinkVehicle(mcfg["hunter"]["conn"], int(mcfg["hunter"]["sysid"]), "HUNTER")
#         self.target = MavlinkVehicle(mcfg["target"]["conn"], int(mcfg["target"]["sysid"]), "TARGET(IRIS)")

#         # Follow strategy
#         fcfg = self.cfg["follow"]
#         self.follow = PositionBasedFollow(
#             follow_alt_m=float(fcfg.get("follow_alt_m", 30.0)),
#             follow_distance_m=float(fcfg.get("follow_distance_m", 30.0)),
#             bearing_kp=float(fcfg.get("bearing_kp", 0.9)),
#             max_bearing_deg=float(fcfg.get("max_bearing_deg", 35.0)),
#         )

#         self.repos_limiter = RateLimiter(float(fcfg.get("reposition_period_s", 0.3)))
#         self.lost_timeout_s = float(fcfg.get("lost_timeout_s", 4.0))
#         self.home_rtl_on_lost = bool(fcfg.get("home_rtl_on_lost", True))
#         self.display = bool(self.cfg["system"].get("display", True))
#         self._last_seen_t = 0.0

#         self._last_target_gps = None  # En son tespit edilen (lat, lon, alt)
#         self._last_target_hdg = 0.0   # En son tespit edilen drone yönü

#     def run(self):
#         self.log.info("Connecting MAVLink...")
#         self.hunter.connect()
  
#         self.target.connect()
#         self.log.info("MAVLink connected.")

#         self.log.info("Starting camera...")
#         self.camera.start()
#         """"""
#         self.log.info("Uçak hazırlanıyor (ARM ve Teleport)...")
        
#         for _ in range(15):
#             self.target.poll()
#             if self.target.lat is not None: break
#             time.sleep(0.5)

#         if self.target.lat is not None:
#             # Önce GUIDED mod ve ARM
#             self.hunter.set_mode("GUIDED")
#            # self.hunter.master.arducopter_arm() # Uçak için de çalışır
#             time.sleep(1)
        
#         self.hunter.teleport_behind_target(self.target, distance_m=15)
#         self.log.info("Hunter hedefin 15m arkasına yönlendirildi. 3 saniye bekleniyor...")
#         time.sleep(10) # Uçağın hedefe yaklaşması için süre tanı


#         """"""
#         try:
#             self.hunter.set_mode("GUIDED")
#             self.log.info("Hunter GUIDED moda alındı.")
#         except Exception as e:
#             self.log.warning(f"Hunter GUIDED set edilemedi: {e}")

#         self.state = SystemState.DETECTING
        
#         frame_idx = 0
#         dets = []
#         track = None
#         t_start = time.time()
#         display_fps = 0.0

#         while True:
#             # poll MAVLink
#             for _ in range(5):
#                 self.hunter.poll()
#                 self.target.poll()

#             frame = self.camera.get_frame()
#             if frame is None:
#                 time.sleep(0.005)
#                 continue

#             now = time.time()
#             frame_idx += 1

            
#             # Her 10 karede bir tespit (FPS'i korumak için)
#             if frame_idx % 10 == 0:
#                 dets = self.detector.detect(frame,last_track=track)
#                 track = self.tracker.update(dets,now)#eskisinde now yoktu

#                 # FPS hesapla
#                 dt = now - t_start
#                 display_fps = 10.0 / dt if dt > 0 else 0
#                 t_start = now
#             else:
#                 track = self.tracker.predict_only(now)    
            
#             """
#             dets = self.detector.detect(frame,last_track=track)
#             track = self.tracker.update(dets)

#                 # FPS hesapla
#             dt = now - t_start
#            # display_fps = dt if dt > 0 else 0
#             t_start = now
#             current_fps = 1.0 / dt if dt > 0 else 0
#             display_fps = (display_fps * 0.9) + (current_fps * 0.1) # Yumuşatılmış FPS
#             """
#             # Durum Mantığı
#             if track is not None:
#                 self._last_seen_t = now
#                 self.state = SystemState.FOLLOWING
#             else:
#                 if self.state == SystemState.FOLLOWING and (now - self._last_seen_t) > self.lost_timeout_s:
#                     self.state = SystemState.LOST_TARGET
#                 elif self.state != SystemState.FOLLOWING:
#                     self.state = SystemState.DETECTING
            
#             """
#             # FOLLOW logic
#             if self.state == SystemState.FOLLOWING and track is not None:
#                 if self._has_target_telemetry():
#                     cx, cy = track.center()
#                     bearing_err = bearing_error_from_bbox(frame.shape[1], cx, hfov_deg=78.0)
#                     target_heading = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)

#                     lat_sp, lon_sp, alt_sp = self.follow.compute_follow_point(
#                         self.target.lat, self.target.lon, target_heading, bearing_err
#                     )
                    
#                     if self.repos_limiter.ready():
#                         self.hunter.cmd_do_reposition(lat_sp, lon_sp, alt_sp)
            
#             """

#             """eskisi son
#              if self.state == SystemState.FOLLOWING and track is not None:
#                 if self._has_target_telemetry():
#                     # --- HIZ SENKRONİZASYONU EKLEMESİ ---
                    
#                     # 1. Mesafe hesapla (Hunter ve Target arası)
#                     dx = (self.target.lat - self.hunter.lat) * 111320
#                     dy = (self.target.lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.target.lat))
#                     distance = math.sqrt(dx**2 + dy**2)

#                     # 2. Hız kontrolcüsü (P-Controller)
#                     target_distance = 10.0  # Aradaki ideal mesafe (metre)
#                     base_speed = 18.0       # Uçağın normal seyir hızı (m/s)
#                     error = distance - target_distance
                    
#                     # Mesafe fazlaysa hızlan, azsa yavaşla
#                     new_speed = base_speed + (error * 0.5) 
                    
#                     # Güvenlik sınırları (Uçak stall olmasın veya aşırı hızlanmasın)
#                     new_speed = max(min(new_speed, 25.0), 13.0)

#                     # 3. Hız komutunu gönder (Rate limiter içine koyuyoruz ki MAVLink'i yormasın)
#                     if self.repos_limiter.ready():
#                         self.hunter.set_airspeed(new_speed)
#                         self.log.info(f"Mesafe: {distance:.1f}m, Yeni Hız: {new_speed:.1f}m/s")
#                     # HIZ SENKRONİZASYONU BİTİŞ ---

#                     # Mevcut Takip Kodu (Bearing ve Reposition)
#                     cx, cy = track.center()
#                     bearing_err = bearing_error_from_bbox(frame.shape[1], cx, hfov_deg=78.0)
#                     target_heading = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)

#                     lat_sp, lon_sp, alt_sp = self.follow.compute_follow_point(
#                         self.target.lat, self.target.lon,self.target.alt_m ,target_heading, bearing_err
#                     )
                    
#                     if self.repos_limiter.ready():
#                         self.hunter.cmd_do_reposition(lat_sp, lon_sp, alt_sp)
            
#             """
#             """son son eskisi
#             now=time.time()
#             # FOLLOW logic
#             if track is not None and self._has_target_telemetry():
#                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
#                 self._last_target_hdg = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)
#                 self._last_seen_t = now
#                 self.state = SystemState.FOLLOWING

#             # 2. Eğer elimizde en az bir kere alınmış bir konum varsa (Hafıza)
#             if self._last_target_gps is not None:
#                 # Mesafe hesapla (Hunter ile Son Bilinen Drone Konumu arası)
#                 dx = (self._last_target_gps[0] - self.hunter.lat) * 111320
#                 dy = (self._last_target_gps[1] - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
#                 distance = math.sqrt(dx**2 + dy**2)

#                 # --- HIZ KONTROLÜ (P-Controller) ---
#                 target_distance = 2.0  # Hedef mesafe (Çok yakın takip istediğin için 2m yaptım)
#                 base_speed = 18.0
#                 error = distance - target_distance
#                 new_speed = base_speed + (error * 0.6) # Katsayıyı biraz artırdım ki daha çevik olsun
#                 new_speed = max(min(new_speed, 25.0), 13.0) # Güvenlik sınırları

#                 # --- HEDEF NOKTA HESAPLAMA ---
#                 # Eğer drone şu an görünüyorsa bearing_err hesapla, görünmüyorsa 0 kabul et
#                 bearing_err = 0.0
#                 if track is not None:
#                     cx, cy = track.center()
#                     bearing_err = bearing_error_from_bbox(frame.shape[1], cx, hfov_deg=78.0)

#                 # Takip noktasını hesapla (follow.py'deki yeni target_alt alan fonksiyonu kullanıyoruz)
#                 lat_sp, lon_sp, alt_sp = self.follow.compute_follow_point(
#                     self._last_target_gps[0], 
#                     self._last_target_gps[1], 
#                     self._last_target_gps[2], # target_alt (drone yüksekliği)
#                     self._last_target_hdg, 
#                     bearing_err
#                 )
                
#                 # --- KOMUTLARI GÖNDER (Rate Limiter ile) ---
#                 if self.repos_limiter.ready():
#                     # Hız ayarla
#                     self.hunter.set_airspeed(new_speed)
#                     # Koordinata git (Reposition)
#                     self.hunter.cmd_do_reposition(lat_sp, lon_sp, alt_sp)
                    
#                     if track is not None:
#                         self.log.info(f"TAKİP: Mesafe: {distance:.1f}m, Hız: {new_speed:.1f}m/s")
#                     else:
#                         self.log.info(f"KAYIP: Son konuma gidiliyor... Mesafe: {distance:.1f}m")
           
#            """
            
#             # --- AGRESİF VE DAİRE ÇİZMEYEN TAKİP MANTIĞI (HIZ VEKTÖRÜ) ---
#             """
#             now = time.time()
            
#             # 1. Hafıza Güncelleme: Drone görünüyorsa konumunu kaydet
#             if track is not None and self._has_target_telemetry():
#                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
#                 self._last_target_hdg = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)
#                 self._last_seen_t = now
#                 self.state = SystemState.FOLLOWING

#             # 2. Eğer drone en az bir kez görüldüyse kontrolü ele al
#             if self._last_target_gps is not None:
#                 # Koordinat farklarını hesapla
#                 target_lat, target_lon, target_alt = self._last_target_gps
                
#                 # Enlem ve boylam farklarını metreye çevir
#                 d_lat = (target_lat - self.hunter.lat) * 111320
#                 d_lon = (target_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
#                 distance = math.sqrt(d_lat**2 + d_lon**2)

#                 # --- HEDEF AÇI (BEARING) HESAPLA ---
#                 # Uçağın burnunu tam hedefe dikmek için gereken açı
#                 target_bearing_rad = math.atan2(d_lon, d_lat)

#                 # --- HIZ KONTROLÜ (P-Controller) ---
#                 base_speed = 18.0
#                 # Hedefe yaklaştıkça hızını drone ile eşitle, uzaksa gazla
#                 # Uçağın daire çizmemesi için hedef mesafeyi 0 değil 10m gibi düşünmek daha stabildir
#                 error = distance - 5.0 
#                 new_speed = base_speed + (error * 0.8)
#                 new_speed = max(min(new_speed, 26.0), 12.0) # Stall olmasın diye min 12, max 26

#                 # --- HIZ VEKTÖRLERİNİ OLUŞTUR (VX, VY) ---
#                 # Uçağın kuzey (vx) ve doğu (vy) yönündeki hız bileşenleri
#                 vx = new_speed * math.cos(target_bearing_rad)
#                 vy = new_speed * math.sin(target_bearing_rad)

#                 # --- KOMUTU GÖNDER (SADECE HIZ VE YÜKSEKLİK) ---
#                 if self.repos_limiter.ready():
#                     # ArduPilot'a koordinat değil, hız vektörü gönderiyoruz (Daire çizmez!)
#                     self.hunter.master.mav.set_position_target_global_int_send(
#                         0,       # time_boot_ms
#                         self.hunter.master.target_system, 
#                         self.hunter.master.target_component,
#                         mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
#                         0b0000111111000111, # MASK: Sadece VX, VY, VZ ve Alt'ı kullan
#                         0, 0, target_alt,   # Lat/Lon 0 (maskelendi), sadece Alt (Drone yüksekliği)
#                         vx, vy, 0,          # Kuzey ve Doğu hız vektörleri
#                         0, 0, 0,            # İvmeler (boş)
#                         0, 0                # Yaw (boş)
#                     )
                    
#                     status = "TAKİP" if track is not None else "KAYIP (HAFIZA)"
#                     self.log.info(f"{status}: Mesafe: {distance:.1f}m, Hız: {new_speed:.1f}m/s, Açı: {math.degrees(target_bearing_rad):.1f}")
#             """
#             """
#             # --- GÜNCELLENMİŞ AGRESİF TAKİP MANTIĞI ---
#             now = time.time()
            
#             # 1. Hafıza Güncelleme: Drone görünüyorsa verileri tazele
#             if track is not None and self._has_target_telemetry():
#                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
#                 self._last_target_hdg = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)
#                 self._last_seen_t = now
#                 self.state = SystemState.FOLLOWING

#             # 2. Takip Uygulaması
#             if self._last_target_gps is not None:
#                 target_lat, target_lon, target_alt = self._last_target_gps
                
#                 # Mevcut mesafe hesaplama
#                 d_lat = (target_lat - self.hunter.lat) * 111320
#                 d_lon = (target_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
#                 distance = math.sqrt(d_lat**2 + d_lon**2)

#                 # Kamera hatasını (bearing error) al
#                 bearing_err = 0.0
#                 if track is not None:
#                     cx, cy = track.center()
#                     bearing_err = bearing_error_from_bbox(frame.shape[1], cx, hfov_deg=78.0)

#                 # --- HEDEF NOKTAYI HESAPLA ---
#                 # follow.py içindeki fonksiyonu kullanarak drone'un 2 metre arkasını hedefle
#                 lat_sp, lon_sp, alt_sp = self.follow.compute_follow_point(
#                     target_lat, 
#                     target_lon, 
#                     target_alt, 
#                     self._last_target_hdg, 
#                     bearing_err
#                 )

#                 # --- HIZ KONTROLÜ (P-Controller) ---
#                 base_speed = 18.0
#                 # Aradaki fark 2 metreden fazlaysa hızlan, azsa yavaşla
#                 error = distance - 2.0 
#                 new_speed = base_speed + (error * 0.7)
#                 new_speed = max(min(new_speed, 25.0), 13.0) # Stall ve Over-speed koruması

#                 # --- KOMUTLARI GÖNDER ---
#                 if self.repos_limiter.ready():
#                     # Hız komutunu gönder
#                     self.hunter.set_airspeed(new_speed)
                    
#                     # Uçağı doğrudan hesaplanan takip noktasına gönder
#                     # (NAVL1_PERIOD 7 sayesinde uçak artık burada daire çizmeyecek, hedefe yapışacak)
#                     self.hunter.cmd_do_reposition(lat_sp, lon_sp, alt_sp)
                    
#                     status = "TAKİP" if track is not None else "KAYIP (HAFIZA)"
#                     self.log.info(f"{status}: Mesafe: {distance:.1f}m, Hız: {new_speed:.1f}m/s")
           
#             """
#             """
#             # --- AGRESİF VE DAİRE ÇİZMEYEN TAKİP MANTIĞI ---
#             now = time.time()
#             if track is not None and self._has_target_telemetry():
#                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
#                 self._last_target_hdg = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)
#                 self._last_seen_t = now
#                 self.state = SystemState.FOLLOWING

#             if self._last_target_gps is not None:
#                 t_lat, t_lon, t_alt = self._last_target_gps
                
#                 # 1. Mesafe ve Açı Hesapla
#                 d_lat = (t_lat - self.hunter.lat) * 111320
#                 d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
#                 bearing_rad = math.atan2(d_lon, d_lat)
#                 distance = math.sqrt(d_lat**2 + d_lon**2)

#                 # 2. SANAL HEDEF OLUŞTUR (Daire Çizmemesi İçin Kritik Nokta)
#                 # Uçağa drone'un olduğu yeri değil, drone'un önünde 500 metrelik bir hedef veriyoruz.
#                 # Uçak "nasıl olsa daha çok yolum var" deyip düz gitmeye devam edecek, 
#                 # ama biz her saniye hedefi drone'un 500m önüne güncellediğimiz için
#                 # uçak aslında drone'u mermi gibi kovalayacak.
#                 look_ahead_m = 500.0
#                 future_lat = t_lat + (look_ahead_m * math.cos(bearing_rad) / 111320.0)
#                 future_lon = t_lon + (look_ahead_m * math.sin(bearing_rad) / (111320.0 * math.cos(math.radians(t_lat))))

#                 # 3. Hız Ayarı (P-Controller)
#                 base_speed = 18.0
#                 error = distance - 5.0 # 5 metre mesafede kalmaya çalış
#                 speed = max(min(base_speed + (error * 1.0), 28.0), 14.0)

#                 # 4. KOMUTLARI GÖNDER
#                 if self.repos_limiter.ready():
#                     # Hızı ayarla
#                     self.hunter.set_airspeed(speed)
                    
#                     # Uçağı drone'un 500m ilerisindeki hayali noktaya yönlendir
#                     # Bu sayede uçak asla "vardım" diyemeyecek ve daire çizmeyecek!
#                     self.hunter.cmd_do_reposition(future_lat, future_lon, t_alt)
                    
#                     status = "TAKİP" if track is not None else "KAYIP (HAFIZA)"
#                     self.log.info(f"{status}: Mesafe: {distance:.1f}m, Hız: {speed:.1f}m/s")
#             """
#             # --- PROFESYONEL TAKİP VE KESKİN DÖNÜŞ MANTIĞI ---
#             now = time.time()
#             if track is not None and self._has_target_telemetry():
#                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
#                 self._last_target_hdg = self.target.hdg_deg if self.target.hdg_deg is not None else (self.hunter.hdg_deg or 0.0)
#                 self.state = SystemState.FOLLOWING

#             if self._last_target_gps is not None:
#                 t_lat, t_lon, t_alt = self._last_target_gps
                
#                 # 1. Mesafe ve Açı
#                 d_lat = (t_lat - self.hunter.lat) * 111320
#                 d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
#                 bearing_rad = math.atan2(d_lon, d_lat)
#                 distance = math.sqrt(d_lat**2 + d_lon**2)

#                 # 2. İrtifa Filtresi (Uçağın zıplamasını engeller)
#                 # Uçağın mevcut irtifası ile drone irtifası arasında yumuşak bir geçiş yap
#                 # Hedef irtifayı drone'un 2 metre üzerinde tut ki pervane rüzgarından etkilenmesin
#                 smooth_alt = (self.hunter.alt_m * 0.7) + ((t_alt + 2.0) * 0.3)

#                 # 3. Akıllı Sanal Hedef (Daireyi Bitiren Formül)
#                 # Mesafe kısaldıkça sanal hedefi daha uzağa atıyoruz ki uçak "keskin" dönsün
#                 look_ahead = 150.0 if distance < 30 else 50.0
#                 future_lat = t_lat + (look_ahead * math.cos(bearing_rad) / 111320.0)
#                 future_lon = t_lon + (look_ahead * math.sin(bearing_rad) / (111320.0 * math.cos(math.radians(t_lat))))

#                 # 4. Dinamik Hız
#                 # Dönüşlerde hızı biraz düşürelim ki daha keskin dönebilsin
#                 base_speed = 17.0
#                 if abs(math.degrees(bearing_rad) - (self.hunter.hdg_deg or 0)) > 30:
#                     base_speed = 15.0 # Keskin dönüşte yavaşla
                
#                 speed = max(min(base_speed + (distance - 10.0) * 0.5, 25.0), 14.0)

#                 if self.repos_limiter.ready():
#                     self.hunter.set_airspeed(speed)
#                     # REPOSITION komutunu sanal hedefe gönder
#                     self.hunter.cmd_do_reposition(future_lat, future_lon, smooth_alt)
                    
#                     self.log.info(f"TAKİP: Mesafe: {distance:.1f}m, Hız: {speed:.1f}m/s, Alt: {smooth_alt:.1f}m")
#             # --- TAKİP MANTIĞI BİTİŞ ---
#             # --- TAKİP MANTIĞI BİTİŞ ---
#             # Görselleştirme
#             if self.display:
#                 self._draw_overlay(frame, dets, track, display_fps)
#                 cv2.imshow("Hunter Tracking", frame)
#                 if cv2.waitKey(1) & 0xFF == 27:
#                     break
            
#         self.camera.stop()
#         cv2.destroyAllWindows()

import time
import yaml
import cv2
import math
from pymavlink import mavutil



from .utils import setup_logger, RateLimiter
from .state import SystemState
from .camera import CameraProcessor
from .yolo_onnx import YOLODetector
from .tracker import ObjectTracker
from .mavlink_iface import MavlinkVehicle
from .follow import PositionBasedFollow, bearing_error_from_bbox

# --- PID SINIFI (Döngü için gerekli matematik) ---
class PID:
    def __init__(self, kp, ki, kd, min_out, max_out):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.min_out, self.max_out = min_out, max_out
        self.integral = 0
        self.last_error = 0
        self.last_time = time.time()

    def compute(self, error):
        now = time.time()
        dt = now - self.last_time
        if dt <= 0: dt = 0.01
        
        self.integral += error * dt
        self.integral = max(min(self.integral, 10), -10) # Anti-windup
        
        derivative = (error - self.last_error) / dt
        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)
        
        self.last_error = error
        self.last_time = now
        return max(min(output, self.max_out), self.min_out)

class DroneTrackingSystem():
    def __init__(self, config_path: str):

        super().__init__() # QThread init

        with open(config_path, "r") as f:
            self.cfg = yaml.safe_load(f)

        self.log = setup_logger(self.cfg["system"].get("log_level", "INFO"))
        self.state = SystemState.INITIALIZING

        # Camera & YOLO & Tracker (Aynı kalıyor)
        vcfg = self.cfg["video"]
        self.camera = CameraProcessor(
            udp_ip=vcfg.get("udp_ip", "127.0.0.1"),
            udp_port=int(vcfg.get("udp_port", 5600)),
            width=int(vcfg.get("width", 640)),
            height=int(vcfg.get("height", 480))
        )

        ycfg = self.cfg["yolo"]
        self.detector = YOLODetector(
            onnx_path=ycfg["onnx_path"],
            input_size=int(ycfg.get("input_size", 640)),
            conf_thres=float(ycfg.get("conf_thres", 0.27)), #0.40 dı
            iou_thres=float(ycfg.get("iou_thres", 0.45)),
            class_name=str(ycfg.get("class_name", "drone")),
            providers=ycfg.get("providers", ["CPUExecutionProvider"]),
        )

        tcfg = self.cfg["tracking"]
        self.tracker = ObjectTracker(
            iou_match_thres=float(tcfg.get("iou_match_thres", 0.20)),
            max_lost_frames=int(tcfg.get("max_lost_frames", 10)),
            smooth_alpha=float(tcfg.get("smooth_alpha", 0.90)),
        )

        # MAVLink
        mcfg = self.cfg["mavlink"]
        self.hunter = MavlinkVehicle(mcfg["hunter"]["conn"], int(mcfg["hunter"]["sysid"]), "HUNTER")
        self.target = MavlinkVehicle(mcfg["target"]["conn"], int(mcfg["target"]["sysid"]), "TARGET(IRIS)")

        # --- PID KONTROLCÜLERİNİ BAŞLAT ---
        # Bu değerler uçağın ne kadar sert tepki vereceğini belirler
        
        """
        self.roll_pid = PID(kp=0.6, ki=0.02, kd=0.1, min_out=-50, max_out=50)   # Yatış açısı
        self.pitch_pid = PID(kp=2.5, ki=0.1, kd=0.2, min_out=-20, max_out=20)   # Yunuslama açısı
        self.thrust_pid = PID(kp=0.08, ki=0.01, kd=0.02, min_out=0.0, max_out=0.5) # Gaz eklemesi (0-1 arası)
        """
        # Roll PID: Ortalama sorunu için Kp'yi artırdık (0.6 -> 1.2) enson
        # self.roll_pid = PID(kp=1.2, ki=0.05, kd=0.15, min_out=-50, max_out=50)
        
        # # Pitch PID: İrtifa düşmemesi için Kp ve Pitch sınırını artırdık
        # self.pitch_pid = PID(kp=3.5, ki=0.2, kd=0.3, min_out=-25, max_out=25)
        
        # # Thrust PID: Mesafe takibi için
        # self.thrust_pid = PID(kp=0.15, ki=0.02, kd=0.05, min_out=0.0, max_out=0.5)
        
        # --- GÜNCELLENMİŞ KARARLI PID DEĞERLERİ ---

        # Roll PID: Ortalama sorununu çözmek için Kp iyi, ama salınımı önlemek için Kd tık artırıldı
        self.roll_pid = PID(kp=1.0, ki=0.02, kd=0.2, min_out=-45, max_out=45)
        
        # Pitch PID: Salınımı bitirmek için Kp düşürüldü (3.5 -> 1.8), Ki ciddi azaltıldı
        # Bu değerler uçağın daha "ağırbaşlı" yükselip alçalmasını sağlar.
        self.pitch_pid = PID(kp=1.8, ki=0.02, kd=0.4, min_out=-25, max_out=45) #20 idi
        
        # Thrust PID: Gazın sürekli artıp azalması da Pitch salınımını tetikler (Burun yukarı/aşağı kalkar)
        # Gaz tepkisini daha da yumuşattık.
        self.thrust_pid = PID(kp=0.1, ki=0.01, kd=0.02, min_out=0.0, max_out=0.4)




        fcfg = self.cfg["follow"]
        self.follow = PositionBasedFollow(
            follow_alt_m=float(fcfg.get("follow_alt_m", 30.0)),
            follow_distance_m=float(fcfg.get("follow_distance_m", 30.0)),
            bearing_kp=float(fcfg.get("bearing_kp", 0.9)),
            max_bearing_deg=float(fcfg.get("max_bearing_deg", 35.0)),
        )

        self.repos_limiter = RateLimiter(0.1) # PID kontrolü için 10Hz idealdir
        self.lost_timeout_s = float(fcfg.get("lost_timeout_s", 4.0))
        self.display = bool(self.cfg["system"].get("display", True))
        
        self._last_seen_t = 0.0
        self._last_target_gps = None
        self._last_target_hdg = 0.0


        self.param_dist = 15.0  # Takip Mesafesi
        self.param_alt = 1.5    # Takip İrtifa Farkı
        self.is_kamikaze = False
        self.is_running = True

    # def run(self):
    #     self.log.info("Sistem Başlatıldı...")

    #     self.log.info("Connecting MAVLink...")
    #     self.hunter.connect()
    #     self.target.connect()
    #     self.log.info("MAVLink connected.")

    #     self.camera.start()
        
    #     # Hazırlık (ARM & Teleport)
    #     self.log.info("Hazırlanıyor...")
    #     for _ in range(10):
    #         self.target.poll()
    #         time.sleep(0.2)

    #     #
    #     while self.target.lat is None:
    #         self.target.poll()
    #         time.sleep(0.1)    
        
    #     #
    #     self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
    #     self._last_seen_t = time.time()


    #     if self.target.lat:
    #         self.hunter.set_mode("GUIDED")
    #         time.sleep(1)
    #     #    
    #     self.log.info(f"Başlangıç GPS Hedefi Alındı: {self._last_target_gps}")    

    #     #self.state = SystemState.DETECTING
    #     self.state = SystemState.FOLLOWING # Direkt takip modunda başla

    #     frame_idx = 0
    #     display_fps = 0.0
    #     t_start = time.time()
    #     track = None

    #     while True:
    #         for _ in range(5):
    #             self.hunter.poll()
    #             self.target.poll()
    #         #    
    #         if self._has_target_telemetry():
    #             self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)

    #         frame = self.camera.get_frame()
    #         if frame is None: continue

    #         now = time.time()
    #         frame_idx += 1

    #         # YOLO & Tracking
    #         if frame_idx % 5 == 0: # 10 yerine 5
    #             dets = self.detector.detect(frame, last_track=track)
    #             track = self.tracker.update(dets, now)
                
    #             dt = now - t_start
    #             display_fps = 5.0 / dt if dt > 0 else 0
    #             t_start = now
    #         else:
    #             track = self.tracker.predict_only(now)

    #         # Durum Güncelleme
    #         if track is not None:
    #             self._last_seen_t = now
    #             self.state = SystemState.FOLLOWING
    #             if self._has_target_telemetry():
    #                 self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
            
    #         # --- LOW-LEVEL PID KONTROLÜ ---
    #         # --- LOW-LEVEL PID KONTROLÜ (Geri Dönüş Destekli) ---
    #         """
    #         if self._last_target_gps is not None:
    #             # 1. Mesafe ve Açı Farkı Hesapla
    #             d_lat = (self._last_target_gps[0] - self.hunter.lat) * 111320
    #             d_lon = (self._last_target_gps[1] - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
    #             distance = math.sqrt(d_lat**2 + d_lon**2)
                
    #             # Hedefe giden mutlak açı (Bearing)
    #             target_bearing = math.degrees(math.atan2(d_lon, d_lat)) % 360
    #             current_hdg = self.hunter.hdg_deg or 0.0
                
    #             # Uçağın burnu ile hedef arasındaki fark (-180 ile 180 arası)
    #             angle_diff = (target_bearing - current_hdg + 180) % 360 - 180

    #             # 2. KARAR MEKANİZMASI: Hedef arkada mı?
    #             if abs(angle_diff) > 90:
    #                 # HEDEF ARKADA: Sert ama güvenli dönüş yap
    #                 self.log.warning(f"GERİ DÖNÜŞ: Açı {angle_diff:.1f} | Hız Artırılıyor (Anti-Stall)")
                    
    #                 # 45 derece çok riskliyse 35-40 arası idealdir
    #                 target_roll = 40.0 if angle_diff > 0 else -40.0 
                    
    #                 # STALL ÖNLEME: Dönüşte burun düşer, o yüzden Pitch'i biraz daha artırıyoruz
    #                 target_pitch = 8.0 
                    
    #                 # KRİTİK: Dönüşte hızı ASLA düşürme, aksine motoru besle!
    #                 target_thrust = 0.7 # %70 güçle uçağı dönüşte tut
                
    #             else:
    #                 # HEDEF ÖNDE: Normal PID Takibi (Burada hız 15m takip için dinamik)
    #                 roll_error = 0.0
    #                 if track is not None:
    #                     cx, _ = track.center()
    #                     roll_error = (cx - (self.camera.width / 2)) / (self.camera.width / 2)
    #                 else:
    #                     roll_error = angle_diff / 45.0 

    #                 target_roll = self.roll_pid.compute(roll_error * 20.0)
                    
    #                 alt_error = (self._last_target_gps[2] + 2.0) - self.hunter.alt_m
    #                 target_pitch = self.pitch_pid.compute(alt_error)
                    
    #                 dist_error = distance - 15.0
    #                 thrust_mod = self.thrust_pid.compute(dist_error)
    #                 # Normal uçuşta 0.4 ile 0.9 arası gezsin
    #                 target_thrust = max(min(0.5 + thrust_mod, 0.9), 0.3)

    #             # 3. KOMUTU GÖNDER
    #             if self.repos_limiter.ready():
    #                 self.hunter.set_attitude(roll_deg=target_roll, pitch_deg=target_pitch, thrust=target_thrust)
    #                 self.log.info(f"CTRL -> R:{target_roll:.1f} P:{target_pitch:.1f} T:{target_thrust:.2f} Dist:{distance:.1f}")
    #         """
    #         # --- PROFESYONEL TAKİP VE GENİŞ DÖNÜŞ STRATEJİSİ ---
    #         # if self._last_target_gps is not None:
    #         #     # 1. Mesafe ve Açı Hesapla
    #         #     t_lat, t_lon, t_alt = self._last_target_gps
    #         #     d_lat = (t_lat - self.hunter.lat) * 111320
    #         #     d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
    #         #     distance = math.sqrt(d_lat**2 + d_lon**2)
                
    #         #     target_bearing = math.degrees(math.atan2(d_lon, d_lat)) % 360
    #         #     current_hdg = self.hunter.hdg_deg or 0.0
    #         #     angle_diff = (target_bearing - current_hdg + 180) % 360 - 180

    #         #     # --- STRATEJİ BELİRLEME ---
    #         #     # Hedef arkadaysa veya kameradan çıkıp çok yaklaşmışsa (daire çizme riski)
    #         #     if abs(angle_diff) > 70:
    #         #         # GENİŞ DÖNÜŞ (WAYBACK) MANTIĞI:
    #         #         # Hedefin üzerine gitme! Hedefin 50m gerisindeki bir sanal noktaya yönel.
    #         #         self.log.warning("GENİŞ DÖNÜŞ: Hedef arkada, hizalanmak için uzağa açılıyor...")
                    
    #         #         # Hedefin ters istikametinde bir nokta belirle
    #         #         back_bearing = math.radians(target_bearing + 180)
    #         #         offset_dist = 50.0 # 50 metre uzağa açıl
                    
    #         #         # Sanal 'hizalanma' noktası
    #         #         align_lat = t_lat + (offset_dist * math.cos(back_bearing) / 111320.0)
    #         #         align_lon = t_lon + (offset_dist * math.sin(back_bearing) / (111320.0 * math.cos(math.radians(t_lat))))
                    
    #         #         # Bu sanal noktaya göre yeni açı hesapla
    #         #         new_d_lat = (align_lat - self.hunter.lat) * 111320
    #         #         new_d_lon = (align_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
    #         #         new_bearing = math.degrees(math.atan2(new_d_lon, new_d_lat))
    #         #         new_angle_diff = (new_bearing - current_hdg + 180) % 360 - 180
                    
    #         #         target_roll = 35.0 if new_angle_diff > 0 else -35.0
    #         #         target_pitch = 5.0
    #         #         target_thrust = 0.65 # Stall olmamak için gaz ver
                
    #         #     else:
    #         #         # NORMAL TAKİP (Hedef ön bölgede)
    #         #         roll_error = 0.0
    #         #         if track is not None:
    #         #             cx, _ = track.center()
    #         #             roll_error = (cx - (self.camera.width / 2)) / (self.camera.width / 2)
    #         #         else:
    #         #             roll_error = angle_diff / 45.0 

    #         #         target_roll = self.roll_pid.compute(roll_error * 20.0)
                    
    #         #         # 2. HİZALAMA: İrtifa hatasını drone'un GPS irtifasına göre ayarla
    #         #         # Başlangıçta ve uçuş sırasında drone ile aynı irtifada (t_alt) kal
    #         #         alt_error = t_alt - self.hunter.alt_m
    #         #         target_pitch = self.pitch_pid.compute(alt_error)
                    
    #         #         dist_error = distance - 12.0
    #         #         thrust_mod = self.thrust_pid.compute(dist_error)
    #         #         target_thrust = max(min(0.5 + thrust_mod, 0.9), 0.3)

    #         #     # 3. KOMUTU GÖNDER
    #         #     if self.repos_limiter.ready():
    #         #         self.hunter.set_attitude(roll_deg=target_roll, pitch_deg=target_pitch, thrust=target_thrust)
    #         #         self.log.info(f"CTRL ->Target speed:{target_thrust:.1f}degıscek   Dist:{distance:.1f}m R:{target_roll:.1f} P:{target_pitch:.1f}")
            
    #         # --- KAMERA ÖNCELİKLİ (VİSUAL ONLY) KONTROL MANTIĞI ---
    #         if self.target.lat is not None and self.hunter.lat is not None:
    #             # En güncel GPS her zaman yedekte dursun
    #             t_lat, t_lon, t_alt = self.target.lat, self.target.lon, self.target.alt_m
    #             self._last_target_gps = (t_lat, t_lon, t_alt)

    #             # Temel Mesafe ve Açı (Sadece Karar Mekanizması İçin)
    #             d_lat = (t_lat - self.hunter.lat) * 111320
    #             d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
    #             distance = math.sqrt(d_lat**2 + d_lon**2)
                
    #             target_bearing = math.degrees(math.atan2(d_lon, d_lat)) % 360
    #             current_hdg = self.hunter.hdg_deg or 0.0
    #             angle_diff = (target_bearing - current_hdg + 180) % 360 - 180

    #             # 1. ROLL (YATIŞ) KONTROLÜ
    #             if track is not None:
    #                 # --- SADECE KAMERA ---
    #                 cx, _ = track.center()
    #                 # Kamera hatası: -1.0 (sol) ile +1.0 (sağ) arası
    #                 roll_error = (cx - (self.camera.width / 2)) / (self.camera.width / 2)
                    
    #                 # Ortalama sorunu için çarpanı artırdık (25 -> 35)
    #                 target_roll = self.roll_pid.compute(roll_error * 35.0)
    #                 self.log.info(f"MOD: KAMERA | Roll Err: {roll_error:.2f}")
    #             else:
    #                 # --- SADECE GPS (Kamera görmediğinde) ---
    #                 roll_error = angle_diff / 30.0 
    #                 target_roll = self.roll_pid.compute(roll_error * 25.0)
    #                 self.log.warning(f"MOD: GPS (Kayıp) | Angle Diff: {angle_diff:.1f}")

    #             # 2. PITCH (YUNUSLAMA) KONTROLÜ
    #             # Altına girmeyi engellemek için: Hedef her zaman drone'un 1.5m üstü
    #             alt_target = t_alt + 1.5 
    #             alt_error = alt_target - self.hunter.alt_m
                
    #             # Uçak aşağıda kalmışsa tırmanma tepkisini (Kp) manuel olarak körüklüyoruz
    #             p_input = alt_error * 1.8 if alt_error > 0 else alt_error
    #             target_pitch = self.pitch_pid.compute(p_input)

    #             # 3. THRUST (MOTOR) KONTROLÜ
    #             # Arkada kalma kontrolü
    #             if abs(angle_diff) > 80:
    #                 target_thrust = 0.75 # Sert dönüş için yüksek devir
    #             else:
    #                 dist_error = distance - 12.0 # 12 metre ideal takip
    #                 thrust_mod = self.thrust_pid.compute(dist_error)
    #                 # Altına girme durumunda (tırmanırken) motoru ekstra besle
    #                 climb_boost = 0.15 if alt_error > 2.0 else 0.0
    #                 target_thrust = max(min(0.55 + thrust_mod + climb_boost, 1.0), 0.3)

    #             # 4. KOMUTU GÖNDER
    #             if self.repos_limiter.ready():
    #                 self.hunter.set_attitude(roll_deg=target_roll, pitch_deg=target_pitch, thrust=target_thrust)
                    
    #                 # Loglama
    #                 status = "CAM" if track is not None else "GPS"
    #                 self.log.info(f"[{status}] Dist:{distance:.1f}m | R:{target_roll:.1f} P:{target_pitch:.1f} T:{target_thrust:.2f}")
    #         # Görselleştirme
    #         if self.display:
    #             self._draw_overlay(frame, [], track, display_fps)
    #             cv2.imshow("Hunter PID Tracking", frame)
    #             if cv2.waitKey(1) & 0xFF == 27: break
            
    #     self.camera.stop()
    #     cv2.destroyAllWindows()       

    # def run(self):
    #     self.log.info("Sistem Başlatıldı...")
    #     self.log.info("Connecting MAVLink...")
    #     self.hunter.connect()
    #     self.target.connect()
    #     self.log.info("MAVLink connected.")

    #     self.camera.start()
        
    #     while True:
    #         self.hunter.poll()
    #         self.target.poll()
    #         if self.hunter.lat is not None and self.target.lat is not None:
    #             break
    #         time.sleep(0.5)

    #     self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
    #     self.hunter.set_mode("GUIDED")
    #     self.state = SystemState.FOLLOWING 

    #     frame_idx = 0
    #     display_fps = 0.0
    #     t_start = time.time()
    #     track = None

    #     while self.is_running:
    #         for _ in range(5):
    #             self.hunter.poll()
    #             self.target.poll()

    #         frame = self.camera.get_frame()
    #         if frame is None: continue

    #         now = time.time()
    #         frame_idx += 1

    #         if frame_idx % 5 == 0:
    #             dets = self.detector.detect(frame, last_track=track)
    #             track = self.tracker.update(dets, now)
    #             dt = now - t_start
    #             display_fps = 5.0 / dt if dt > 0 else 0
    #             t_start = now
    #         else:
    #             track = self.tracker.predict_only(now)

    #         if self.target.lat is not None and self.hunter.lat is not None:
    #             t_lat, t_lon, t_alt = self.target.lat, self.target.lon, self.target.alt_m
                
    #             # Parametreler
    #             target_dist = 0.0 if self.is_kamikaze else self.param_dist
    #             target_alt_offset = 0.0 if self.is_kamikaze else self.param_alt
                
    #             d_lat = (t_lat - self.hunter.lat) * 111320
    #             d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
    #             distance = math.sqrt(d_lat**2 + d_lon**2)
                
    #             target_bearing = math.degrees(math.atan2(d_lon, d_lat)) % 360
    #             current_hdg = self.hunter.hdg_deg or 0.0
    #             angle_diff = (target_bearing - current_hdg + 180) % 360 - 180

    #             # --- KONTROL SEÇİMİ ---
                
    #             # 1. DURUM: DAİRE ÇİZME (Sadece Kamikaze DEĞİLSE ve mesafe yakınsa)
    #             if distance < 3.0 and not self.is_kamikaze:
    #                 target_roll = 35.0
    #                 target_pitch = 2.0
    #                 target_thrust = 0.45
    #                 status_text = "ORBIT (DAIRE)"
                
    #             # 2. DURUM: TAKİP VEYA KAMİKAZE (Kamera Öncelikli)
    #             else:
    #                 # ROLL: Kamera varsa her zaman kameraya güven (Kamikaze dahil)
    #                 if track is not None:
    #                     cx, _ = track.center()
    #                     roll_error = (cx - (self.camera.width / 2)) / (self.camera.width / 2)
    #                     target_roll = self.roll_pid.compute(roll_error * 35.0)
    #                     status_text = "VISUAL " + ("ATTACK" if self.is_kamikaze else "FOLLOW")
    #                 else:
    #                     # Kamera yoksa GPS yardımıyla yönel
    #                     roll_error = angle_diff / 30.0 
    #                     target_roll = self.roll_pid.compute(roll_error * 25.0)
    #                     status_text = "GPS " + ("ATTACK" if self.is_kamikaze else "FOLLOW")

    #                 # PITCH: Kamikaze ise doğrudan drone irtifasına, takip ise offsetli
    #                 alt_target = t_alt + target_alt_offset
    #                 alt_error = alt_target - self.hunter.alt_m
    #                 # Kamikaze dalışında aşağı doğru daha agresif olması için:
    #                 p_input = alt_error * 2.0 if self.is_kamikaze else (alt_error * 1.8 if alt_error > 0 else alt_error)
    #                 target_pitch = self.pitch_pid.compute(p_input)

    #                 # THRUST: Kamikaze ise tam gaz
    #                 if self.is_kamikaze:
    #                     target_thrust = 1.0 
    #                 else:
    #                     dist_error = distance - target_dist
    #                     thrust_mod = self.thrust_pid.compute(dist_error)
    #                     target_thrust = max(min(0.55 + thrust_mod, 0.9), 0.3)

    #             # Komut Gönder
    #             if self.repos_limiter.ready():
    #                 self.hunter.set_attitude(roll_deg=target_roll, pitch_deg=target_pitch, thrust=target_thrust)
    #                 self.log.info(f"[{status_text}] Dist:{distance:.1f}m R:{target_roll:.1f} P:{target_pitch:.1f} T:{target_thrust:.2f}")

    #         if self.display:
    #             self._draw_overlay(frame, [], track, display_fps)
    #             cv2.imshow("Hunter Control Panel System", frame)
    #             if cv2.waitKey(1) & 0xFF == 27: break
            
    #     self.camera.stop()
    #     cv2.destroyAllWindows() 
    def run(self):
        self.log.info("Sistem Başlatıldı...")
        self.log.info("Connecting MAVLink...")
        self.hunter.connect()
        self.target.connect()
        self.log.info("MAVLink connected.")

        self.camera.start()
        
        while True:
            self.hunter.poll()
            self.target.poll()
            if self.hunter.lat is not None and self.target.lat is not None:
                break
            time.sleep(0.5)

        self._last_target_gps = (self.target.lat, self.target.lon, self.target.alt_m)
        self.hunter.set_mode("GUIDED")
        self.state = SystemState.FOLLOWING 

        frame_idx = 0
        display_fps = 0.0
        t_start = time.time()
        track = None

        while self.is_running:
            for _ in range(5):
                self.hunter.poll()
                self.target.poll()

            frame = self.camera.get_frame()
            if frame is None: continue

            now = time.time()
            frame_idx += 1

            if frame_idx % 5 == 0:
                dets = self.detector.detect(frame, last_track=track)
                track = self.tracker.update(dets, now)
                dt = now - t_start
                display_fps = 5.0 / dt if dt > 0 else 0
                t_start = now
            else:
                track = self.tracker.predict_only(now)

            if self.target.lat is not None and self.hunter.lat is not None:
                t_lat, t_lon, t_alt = self.target.lat, self.target.lon, self.target.alt_m
                
                # Parametreler
                target_dist = 0.0 if self.is_kamikaze else self.param_dist
                target_alt_offset = 0.0 if self.is_kamikaze else self.param_alt
                
                d_lat = (t_lat - self.hunter.lat) * 111320
                d_lon = (t_lon - self.hunter.lon) * 111320 * math.cos(math.radians(self.hunter.lat))
                distance = math.sqrt(d_lat**2 + d_lon**2)
                
                target_bearing = math.degrees(math.atan2(d_lon, d_lat)) % 360
                current_hdg = self.hunter.hdg_deg or 0.0
                angle_diff = (target_bearing - current_hdg + 180) % 360 - 180

                # --- 1. YÖNLENDİRME (ROLL & PITCH) ---
                if track is not None:
                    cx, _ = track.center()
                    roll_error = (cx - (self.camera.width / 2)) / (self.camera.width / 2)
                    target_roll = self.roll_pid.compute(roll_error * 35.0)
                    status_text = "VISUAL " + ("ATTACK" if self.is_kamikaze else "FOLLOW")
                else:
                    roll_error = angle_diff / 30.0 
                    target_roll = self.roll_pid.compute(roll_error * 25.0)
                    status_text = "GPS " + ("ATTACK" if self.is_kamikaze else "FOLLOW")

                alt_target = t_alt + target_alt_offset
                alt_error = alt_target - self.hunter.alt_m
                p_input = alt_error * 2.0 if self.is_kamikaze else (alt_error * 1.8 if alt_error > 0 else alt_error)
                target_pitch = self.pitch_pid.compute(p_input)

                # --- 2. DİNAMİK AUTO-BRAKE (THRUST) ---
                if self.is_kamikaze:
                    target_thrust = 1.0

                    alt_target = t_alt - 2.0 
                    alt_error = alt_target - self.hunter.alt_m
                    
                    # if distance < 3.25:
                    #     # Doğrudan -35 derece dalış emri (Otopilot limitlerini zorlar)
                    #     target_pitch = -35.0 
                    #     status_text = "🚀 TERMINAL ATTACK (FULL DOWN)"
                    # # else:
                    #     # Uzaktaysak PID ile yaklaşmaya devam et ama agresif katsayıyla
                    #     target_pitch = self.pitch_pid.compute(alt_error * 3.5)
                    #     target_pitch = max(min(target_pitch, 20), -25)
                else:
                    dist_error = distance - target_dist
                    thrust_mod = self.thrust_pid.compute(dist_error)
                    base_thrust = 0.45 
                    
                    # Eğer ayarlanan mesafenin altına düşersek üssel fren yap
                    if dist_error < 0:
                        # math.exp ile mesafe azaldıkça gazı sertçe kesiyoruz
                        brake_factor = math.exp(dist_error / 6.0) 
                        target_thrust = (base_thrust + thrust_mod) * brake_factor
                        status_text += " (BRAKING)"
                    else:
                        target_thrust = base_thrust + thrust_mod

                    # Güvenlik sınırı: 0.25 (Stall olmamak için) ile 0.85 arası
                    target_thrust = max(min(target_thrust, 0.85), 0.25)

                # Arayüz için güncel thrust'ı kaydet (Thrust Bar için)
                self.current_thrust = target_thrust

                # Komut Gönder
                if self.repos_limiter.ready():
                    self.hunter.set_attitude(roll_deg=target_roll, pitch_deg=target_pitch, thrust=target_thrust)
                    self.log.info(f"[{status_text}] Dist:{distance:.1f}m T:{target_thrust:.2f}")

            if self.display:
                self._draw_overlay(frame, [], track, display_fps)
                cv2.imshow("Hunter Control Panel System", frame)
                if cv2.waitKey(1) & 0xFF == 27: break
            
        self.camera.stop()
        cv2.destroyAllWindows()
    def _has_target_telemetry(self) -> bool:
        return (self.target.lat is not None and self.target.lon is not None)

    def _draw_overlay(self, frame, dets, track, fps):
        # 1. Tespit edilen tüm kutular (Yeşil)
        for d in dets:
            x1, y1, x2, y2 = map(int, d.bbox_xyxy)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
            cv2.putText(frame, f"{d.conf:.2f}", (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # 2. Takip edilen ana kutu (Kırmızı - Daha Kalın)
        if track is not None:
            x1, y1, x2, y2 = map(int, track.bbox_xyxy)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(frame, "TARGET", (x1, y2 + 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # 3. Bilgi Paneli (Sol Üst)
        cv2.putText(frame, f"STATE: {self.state.name}", (10, 25), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 55), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # 4. Hedef Koordinat Bilgisi (Sağ Alt - Opsiyonel)
        if self.target.lat:
            cv2.putText(frame, f"Tgt: {self.target.lat:.5f}, {self.target.lon:.5f}", (frame.shape[1]-250, frame.shape[0]-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
