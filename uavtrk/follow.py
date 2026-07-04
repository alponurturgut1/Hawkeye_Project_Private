import math
from .geo import offset_gps, wrap180

class PositionBasedFollow:
    def __init__(self, follow_alt_m: float, follow_distance_m: float, bearing_kp: float, max_bearing_deg: float):
        self.follow_alt_m = follow_alt_m
        self.follow_distance_m = follow_distance_m
        self.bearing_kp = bearing_kp
        self.max_bearing_deg = max_bearing_deg
    """
    def compute_follow_point(self, target_lat, target_lon, target_heading_deg,
                             bearing_error_deg):
        
        #Takip fikri: a
        #- hedefin heading’ine göre arkasında follow_distance_m kadar geride bir GPS noktası üret
        #- bearing error (kameradan) büyükse, noktayı hafif yana kaydır (uçağın yaklaşımını düzeltir)
        
        # error clamp
        be = max(-self.max_bearing_deg, min(self.max_bearing_deg, bearing_error_deg))
        lateral = self.bearing_kp * be / self.max_bearing_deg * (0.6 * self.follow_distance_m)

        # hedefin arkasına: heading + 180 yönünde offset
        back_deg = (target_heading_deg + 180.0) % 360.0
        back_rad = math.radians(back_deg)

        dn = self.follow_distance_m * math.cos(back_rad)
        de = self.follow_distance_m * math.sin(back_rad)

        # lateral kaydırma: heading’e dik eksen
        # left is negative, right positive
        left_deg = (target_heading_deg - 90.0) % 360.0
        left_rad = math.radians(left_deg)
        dn += lateral * math.cos(left_rad)
        de += lateral * math.sin(left_rad)

        lat2, lon2 = offset_gps(target_lat, target_lon, dn, de)
        return lat2, lon2, self.follow_alt_m
    """
    def compute_follow_point(self, target_lat, target_lon, target_alt, target_heading_deg,
                             bearing_error_deg):
        """
        GÜNCELLENMİŞ Takip Mantığı:
        - Artık target_alt (Drone'un anlık yüksekliği) parametresini alıyor.
        - follow_distance_m yerine çok yakın (2m) bir mesafeye yapışıyor.
        - Sabit follow_alt_m yerine drone'un o anki yüksekliğini döndürüyor.
        """
        # Drone'a tam üzerine binmemesi ama çok yakın takip etmesi için mesafe
        # Eğer config'ten gelsin istersen self.follow_distance_m kullanabilirsin 
        # ama "yapışsın" dediğin için buraya 2.0m sabitliyorum.
        dist = 2.0 #2.0 idi

        # Kamera hata payını (bearing error) temizle
        be = max(-self.max_bearing_deg, min(self.max_bearing_deg, bearing_error_deg))
        # Lateral kaydırma: Uçak drone'u tam ortalamak için sağa/sola hafif manevra yapar
        lateral = self.bearing_kp * be / self.max_bearing_deg * (0.6 * dist)

        # Hedefin arkasına: heading + 180 yönünde offset (kuyruğuna gitmek için)
        back_deg = (target_heading_deg + 180.0) % 360.0
        back_rad = math.radians(back_deg)

        dn = dist * math.cos(back_rad)
        de = dist * math.sin(back_rad)

        # Lateral kaydırma: heading’e dik eksen (Kameranın drone'u kaçırmaması için)
        left_deg = (target_heading_deg - 90.0) % 360.0
        left_rad = math.radians(left_deg)
        dn += lateral * math.cos(left_rad)
        de += lateral * math.sin(left_rad)

        # Yeni GPS koordinatlarını hesapla
        lat2, lon2 = offset_gps(target_lat, target_lon, dn, de)
        
        # --- KRİTİK DEĞİŞİKLİK ---
        # Eskiden return lat2, lon2, self.follow_alt_m şeklindeydi.
        # Şimdi drone'un o anki yüksekliğini (target_alt) döndürüyoruz.
        return lat2, lon2, target_alt
def bearing_error_from_bbox(frame_w: int, bbox_center_x: float, hfov_deg: float = 78.0):
    """
    Görüntü merkezinden sapmayı basitçe açısal hataya çevir.
    hfov_deg: kameranın yatay görüş açısı (SDF’deki değere göre ayarla)
    """
    cx = frame_w * 0.5
    norm = (bbox_center_x - cx) / cx   # [-1..1]
    return norm * (hfov_deg * 0.5)
