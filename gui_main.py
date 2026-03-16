# import tkinter as tk
# from tkinter import ttk
# import threading
# from uavtrk.system import DroneTrackingSystem

# class UAVControlApp:
#     def __init__(self, root):
#         self.root = root
#         self.root.title("Gemini UAV GKS - Tkinter")
#         self.root.geometry("400x500")

#         # Sistemi Başlat (Arka planda çalışması için Thread kullanıyoruz)
#         self.system = DroneTrackingSystem(config_path="config.yaml")
#         self.sys_thread = threading.Thread(target=self.system.run, daemon=True)
#         self.sys_thread.start()

#         self.setup_ui()

#     def setup_ui(self):
#         # --- Başlık ---
#         ttk.Label(self.root, text="UAV Takip ve Kamikaze Sistemi", font=("Arial", 14, "bold")).pack(pady=10)

#         # --- Takip Mesafesi (Slider) ---
#         self.dist_label = ttk.Label(self.root, text=f"Takip Mesafesi: {self.system.param_dist}m")
#         self.dist_label.pack(pady=(20, 0))
#         self.dist_scale = ttk.Scale(self.root, from_=5, to=100, orient="horizontal", command=self.update_dist)
#         self.dist_scale.set(self.system.param_dist)
#         self.dist_scale.pack(fill="x", padx=40)

#         # --- Takip İrtifası (Slider) ---
#         self.alt_label = ttk.Label(self.root, text=f"Takip İrtifa Farkı: {self.system.param_alt}m")
#         self.alt_label.pack(pady=(20, 0))
#         self.alt_scale = ttk.Scale(self.root, from_=-10, to=20, orient="horizontal", command=self.update_alt)
#         self.alt_scale.set(self.system.param_alt)
#         self.alt_scale.pack(fill="x", padx=40)

#         # --- Kamikaze (CARP) Butonu ---
#         self.carp_btn = tk.Button(self.root, text="🚀 CARP (KAMIKAZE)", bg="red", fg="white", 
#                                  font=("Arial", 12, "bold"), height=3, command=self.toggle_kamikaze)
#         self.carp_btn.pack(pady=40, fill="x", padx=40)

#         # --- RTL Butonu ---
#         ttk.Button(self.root, text="Eve Dön (RTL)", command=self.system.hunter.cmd_rtl).pack(fill="x", padx=40)

#     def update_dist(self, val):
#         self.system.param_dist = float(val)
#         self.dist_label.config(text=f"Takip Mesafesi: {int(float(val))}m")

#     def update_alt(self, val):
#         self.system.param_alt = float(val)
#         self.alt_label.config(text=f"Takip İrtifa Farkı: {int(float(val))}m")

#     def toggle_kamikaze(self):
#         self.system.is_kamikaze = not self.system.is_kamikaze
#         if self.system.is_kamikaze:
#             self.carp_btn.config(text="🛑 CARP IPTAL", bg="orange", fg="black")
#         else:
#             self.carp_btn.config(text="🚀 CARP (KAMIKAZE)", bg="red", fg="white")

# if __name__ == "__main__":
#     root = tk.Tk()
#     app = UAVControlApp(root)
#     root.mainloop()

import tkinter as tk
from tkinter import ttk
import threading
import time
from uavtrk.system import DroneTrackingSystem

class UAVControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UAV Ground Control - AutoBrake")
        self.root.geometry("400x600")

        self.system = DroneTrackingSystem(config_path="config.yaml")
        self.system.current_thrust = 0.0 # Başlangıç değeri
        
        self.sys_thread = threading.Thread(target=self.system.run, daemon=True)
        self.sys_thread.start()

        self.setup_ui()
        self.update_live_data() # Canlı veriyi başlat

    def setup_ui(self):
        ttk.Label(self.root, text="UAV COMMAND CENTER", font=("Arial", 14, "bold")).pack(pady=10)

        # Gaz Yüzdesi (Live Bar)
        ttk.Label(self.root, text="Motor Gücü (Thrust %):").pack(pady=(10, 0))
        self.thrust_bar = ttk.Progressbar(self.root, orient="horizontal", length=300, mode="determinate")
        self.thrust_bar.pack(pady=5)
        self.thrust_val_label = ttk.Label(self.root, text="%0")
        self.thrust_val_label.pack()

        # Mesafe Slider
        self.dist_label = ttk.Label(self.root, text=f"Takip Mesafesi: {self.system.param_dist}m")
        self.dist_label.pack(pady=(20, 0))
        self.dist_scale = ttk.Scale(self.root, from_=10, to=80, orient="horizontal", command=self.update_dist)
        self.dist_scale.set(self.system.param_dist)
        self.dist_scale.pack(fill="x", padx=40)

        # İrtifa Slider
        self.alt_label = ttk.Label(self.root, text=f"İrtifa Farkı: {self.system.param_alt}m")
        self.alt_label.pack(pady=(20, 0))
        self.alt_scale = ttk.Scale(self.root, from_=-5, to=15, orient="horizontal", command=self.update_alt)
        self.alt_scale.set(self.system.param_alt)
        self.alt_scale.pack(fill="x", padx=40)

        # Butonlar
        self.carp_btn = tk.Button(self.root, text="🚀 CARP (KAMIKAZE)", bg="red", fg="white", 
                                 font=("Arial", 12, "bold"), height=3, command=self.toggle_kamikaze)
        self.carp_btn.pack(pady=30, fill="x", padx=40)

        ttk.Button(self.root, text="RTL (Eve Dön)", command=self.system.hunter.cmd_rtl).pack(fill="x", padx=40)

    def update_live_data(self):
        # System.py içindeki thrust değerini al ve barı güncelle
        thrust_pct = int(self.system.current_thrust * 100)
        self.thrust_bar['value'] = thrust_pct
        self.thrust_val_label.config(text=f"%{thrust_pct}")
        
        # 100ms sonra tekrar güncelle (10Hz)
        self.root.after(100, self.update_live_data)

    def update_dist(self, val):
        self.system.param_dist = float(val)
        self.dist_label.config(text=f"Takip Mesafesi: {int(float(val))}m")

    def update_alt(self, val):
        self.system.param_alt = float(val)
        self.alt_label.config(text=f"İrtifa Farkı: {int(float(val))}m")

    def toggle_kamikaze(self):
        self.system.is_kamikaze = not self.system.is_kamikaze
        if self.system.is_kamikaze:
            self.carp_btn.config(text="🛑 CARP IPTAL", bg="orange")
        else:
            self.carp_btn.config(text="🚀 CARP (KAMIKAZE)", bg="red")

if __name__ == "__main__":
    root = tk.Tk()
    app = UAVControlApp(root)
    root.mainloop()