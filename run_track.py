from uavtrk.system import DroneTrackingSystem
import time 

def main():
    system = DroneTrackingSystem(config_path="config.yaml")
#    
    """"""
    system.hunter.connect()
    system.target.connect()
    
    
    print("Telemetri bekleniyor...")
    for i in range(10):
        system.hunter.poll()
        system.target.poll()
        time.sleep(1)
        if system.target.lat is not None:
            print(f"Hedef bulundu: {system.target.lat}, {system.target.lon}")
            break
   
   
    if system.target.lat is not None:
        print("Işınlama başlatılıyor...")
        system.hunter.teleport_behind_target(system.target, distance_m=15)
        time.sleep(1) # Komutun işlenmesi için kısa bir es
   
    """"""
    system.run()

if __name__ == "__main__":
    main()
