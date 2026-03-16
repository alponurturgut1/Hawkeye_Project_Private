from pymavlink import mavutil
import time
from follow import PositionBasedFollow # Senin dosyan

# Bağlantılar
# Hunter (Uçak) - Instance 0 (Port 14570 veya 5760)
hunter = mavutil.mavlink_connection('udp:127.0.0.1:14570')
# Target (Drone) - Instance 1 (Port 14580 veya 5770)
target = mavutil.mavlink_connection('udp:127.0.0.1:14580')

follower_logic = PositionBasedFollow(follow_alt_m=30, follow_distance_m=20, bearing_kp=0.5, max_bearing_deg=30)

def get_location(conn):
    msg = conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True)
    return msg.lat/1e7, msg.lon/1e7, msg.relative_alt/1000.0, msg.hdg/100.0

def set_target_location(conn, lat, lon, alt):
    # Plane için GUIDED modunda hedef nokta gönderme
    conn.mav.set_position_target_global_int_send(
        0, conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000, # Sadece Lat, Lon, Alt kullan
        int(lat * 1e7), int(lon * 1e7), alt,
        0, 0, 0, 0, 0, 0, 0, 0)
def set_drone_velocity(conn, vx, vy, vz):
    conn.mav.set_position_target_local_ned_send(
        0, conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000111111000111, # Sadece hız (velocity) kullan
        0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0)
# ANA DÖNGÜ
while True:
    try:
        # 1. Hedefin (Drone) konumunu ve yönünü al
        t_lat, t_lon, t_alt, t_hdg = get_location(target)
        
        # 2. Takip noktasını hesapla (Kameradan hata gelmediğini varsayalım: 0)
        # Eğer kamera entegre edersen bearing_error_from_bbox'tan gelen değeri ver
        new_lat, new_lon, new_alt = follower_logic.compute_follow_point(t_lat, t_lon, t_hdg, 0)
        
        # 3. Hunter'a (Uçak) yeni hedefi gönder
        set_target_location(hunter, new_lat, new_lon, new_alt)
        
        # 4. Drone'u sağa hareket ettir (Test için)
        # Buraya drone'a Velocity komutu gönderen bir kod eklenebilir
        #set_drone_velocity(target, 0, 2, 0) # Drone'u sürekli 2 m/s sağa (East) iter
        time.sleep(0.1)
    except KeyboardInterrupt:
        break

