from pymavlink import mavutil
import time
import math
class MavlinkVehicle:
    def __init__(self, conn: str, sysid: int, name: str):
        self.conn_str = conn
        self.sysid = sysid
        self.name = name
        self.master = None

        # state
        self.lat = None
        self.lon = None
        self.alt_m = None
        self.hdg_deg = None
        self.armed = False
        self.mode = None
        self.last_pos_t = 0.0

    def connect(self, timeout_s=30):
        self.master = mavutil.mavlink_connection(self.conn_str)
        self.master.wait_heartbeat(timeout=timeout_s)

        # request streams (ArduPilot için)
        self.master.mav.request_data_stream_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            10, 1
        )

    def poll(self):
        msg = self.master.recv_match(blocking=False)
        if msg is None:
            return

        mtype = msg.get_type()
        if mtype == "GLOBAL_POSITION_INT":
            self.lat = msg.lat / 1e7
            self.lon = msg.lon / 1e7
            self.alt_m = msg.relative_alt / 1000.0
            self.last_pos_t = time.time()
        elif mtype == "VFR_HUD":
            self.hdg_deg = float(msg.heading)  # 0..360
        elif mtype == "HEARTBEAT":
            self.armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
            self.mode = mavutil.mode_string_v10(msg)

    def set_mode(self, mode: str):
        # ArduPilot mode set
        if mode not in self.master.mode_mapping():
            raise RuntimeError(f"{self.name}: mode mapping yok: {mode}")
        mode_id = self.master.mode_mapping()[mode]
        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

    def arm(self):
        self.master.arducopter_arm()
        self.master.motors_armed_wait()

    def disarm(self):
        self.master.arducopter_disarm()
        self.master.motors_disarmed_wait()

    def cmd_do_reposition(self, lat_deg: float, lon_deg: float, alt_m: float, ground_speed=-1.0):
        """
        ArduPlane GUIDED takip için pratik: hedefin yakınına "reposition".
        """
        self.master.mav.command_int_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION,
            0, 0,
            ground_speed,   # param1: ground speed (-1 keep)
            0, 0, 0,        # param2-4
            int(lat_deg * 1e7),
            int(lon_deg * 1e7),
            float(alt_m)
        )

    def cmd_rtl(self):
        self.set_mode("RTL")

    def set_airspeed(self, speed_mps):
        """Uçağın hedef hızını (m/s) ayarlar."""
    # ArduPlane hızı cm/s olarak tuttuğu için 100 ile çarpıyoruz
        speed_cm_s = int(speed_mps * 100)
    # Parametre ismi ArduPlane için TRIM_ARSPD_CM
        self.master.mav.param_set_send(
        self.master.target_system,
        self.master.target_component,
        b'TRIM_ARSPD_CM',
        speed_cm_s,
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
        )    


    def teleport_behind_target(self, target_vehicle, distance_m=15):
        # Sadece koordinat kontrolü yapalım, heading yoksa 0 kabul et
        if target_vehicle.lat is None:
            print("Hata: Hedef koordinatı hala yok!")
            return
        
        import math
        # Heading yoksa uçağın açısını, o da yoksa 0'ı kullan
        target_hdg = target_vehicle.hdg_deg if target_vehicle.hdg_deg is not None else 0.0
        
        angle_rad = math.radians((target_hdg + 180) % 360)
        dn = distance_m * math.cos(angle_rad)
        de = distance_m * math.sin(angle_rad)
        
        new_lat = target_vehicle.lat + (dn / 111319.9)
        new_lon = target_vehicle.lon + (de / (111319.9 * math.cos(math.radians(target_vehicle.lat))))
        
        self.set_mode("GUIDED")
        time.sleep(0.5) # Modun oturması için bekle
        
        # Uçağı ARM et (Arm olmadan GUIDED komutu gitmez)
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0
        )
        time.sleep(0.5)

        self.cmd_do_reposition(new_lat, new_lon, target_vehicle.alt_m)
        print(f"Işınlama Komutu Gönderildi: {new_lat}, {new_lon}, Alt: {target_vehicle.alt_m}")
        
    def set_velocity_and_heading(self, velocity_x, velocity_y, target_alt):
        """Uçağı koordinata değil, doğrudan bir hız vektörüne yönlendirir."""
    # Bu mesaj uçağın daire çizme mantığını devre dışı bırakır
        self.master.mav.set_position_target_global_int_send(
        0,       # time_boot_ms
        self.master.target_system, self.master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111000111, # Sadece hız (VX, VY, VZ) ve yükseklik kullan
        0, 0, target_alt,   # Lat/Lon 0 (maskelendi), sadece Alt
        velocity_x, velocity_y, 0, # X ve Y hız vektörleri
        0, 0, 0, # İvmeler (kullanılmıyor)
        0, 0     # Yaw ve Yaw Rate
    ) 
        
    def set_attitude(self, roll_deg, pitch_deg, yaw_rate=0, thrust=0.5):
        """
        Uçağın gövde açılarını (Attitude) doğrudan kontrol eder.
        roll_deg: Sağ-Sol yatış.
        pitch_deg: Aşağı-Yukarı yunuslama.
        thrust: 0.0 - 1.0 arası motor gücü.
        """
        # Radyana çevir
        r = math.radians(roll_deg)
        p = math.radians(pitch_deg)
        y_rate = math.radians(yaw_rate)

        # Quaternion hesapla (ArduPilot Euler açısı değil, Quaternion kabul eder)
        q = self._get_quaternion(r, p, 0)

        # MAVLink mesajı gönder
        # Type mask: 0b10000111 (Sadece Body Rate'leri görmezden gel, Attitude ve Thrust kullan)
        self.master.mav.set_attitude_target_send(
            0, # time_boot_ms
            self.master.target_system, self.master.target_component,
            0b00000000, # Maske: Hepsini kullan
            q,          # Quaternion açısı
            0, 0, y_rate, # Roll/Pitch/Yaw hızları
            thrust      # Motor gücü (0.0 - 1.0)
        )

    def _get_quaternion(self, roll, pitch, yaw):
        """Euler açılarından Quaternion'a dönüşüm."""
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)

        q = [0] * 4
        q[0] = cy * cr * cp + sy * sr * sp # w
        q[1] = cy * sr * cp - sy * cr * sp # x
        q[2] = cy * cr * sp + sy * sr * cp # y
        q[3] = sy * cr * cp - cy * sr * sp # z
        return q   