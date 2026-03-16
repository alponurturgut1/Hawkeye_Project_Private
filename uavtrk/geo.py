import math

EARTH_RADIUS_M = 6378137.0

def meters_to_lat(m: float) -> float:
    return (m / EARTH_RADIUS_M) * (180.0 / math.pi)

def meters_to_lon(m: float, lat_deg: float) -> float:
    lat_rad = math.radians(lat_deg)
    return (m / (EARTH_RADIUS_M * math.cos(lat_rad))) * (180.0 / math.pi)

def offset_gps(lat_deg: float, lon_deg: float, d_north_m: float, d_east_m: float):
    dlat = meters_to_lat(d_north_m)
    dlon = meters_to_lon(d_east_m, lat_deg)
    return lat_deg + dlat, lon_deg + dlon

def wrap180(deg: float) -> float:
    x = (deg + 180.0) % 360.0 - 180.0
    return x
