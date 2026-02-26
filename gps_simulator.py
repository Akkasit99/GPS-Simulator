import argparse
import datetime
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional

import os
import requests
import serial
import serial.tools.list_ports
from PIL import Image, ImageTk

# UI Import
from gps_app_ui import GPSAppUI
import customtkinter as ctk

import json
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_config_path():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, "config.json")

CONFIG_FILE = get_config_path()

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def as_utc_naive(ts: datetime.datetime) -> datetime.datetime:
    try:
        if not isinstance(ts, datetime.datetime):
            return datetime.datetime.utcnow()
        if ts.tzinfo is not None:
            return ts.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return ts
    except Exception:
        return datetime.datetime.utcnow()

class CarMarkerController:
    def __init__(self, mapw, image_path: str = "car.png", size=(40, 40)):
        self.mapw = mapw
        self.image_path = resource_path(image_path)
        self.size = size
        self.original_img = None
        self.marker = None
        self.last_heading = None
        self._icon_ref = None

    def _ensure_loaded(self) -> bool:
        if self.original_img is not None:
            return True
        try:
            if os.path.exists(self.image_path):
                self.original_img = Image.open(self.image_path).resize(self.size)
                return True
        except Exception:
            return False
        return False

    def clear(self):
        if self.marker is None:
            return
        try:
            self.marker.delete()
        except Exception:
            pass
        self.marker = None
        self.last_heading = None
        self._icon_ref = None

    def update(self, lat: float, lon: float, heading: float):
        if not self._ensure_loaded():
            return

        try:
            if self.marker is not None:
                deleted = bool(getattr(self.marker, "deleted", False))
                in_list = False
                try:
                    in_list = self.marker in getattr(self.mapw, "canvas_marker_list", [])
                except Exception:
                    in_list = True
                if deleted or not in_list:
                    self.marker = None
        except Exception:
            self.marker = None

        delta = None
        if self.last_heading is not None:
            try:
                delta = abs(((float(heading) - float(self.last_heading) + 180.0) % 360.0) - 180.0)
            except Exception:
                delta = None
        self.last_heading = heading

        if self.marker is None:
            rotated = self.original_img.rotate(-heading, expand=False, resample=Image.BICUBIC)
            photo = ImageTk.PhotoImage(rotated)
            self._icon_ref = photo
            self.marker = self.mapw.set_marker(lat, lon, icon=photo, text=None)
            try:
                setattr(self.marker, "_icon_ref", photo)
            except Exception:
                pass
            return

        try:
            self.marker.set_position(lat, lon)
        except Exception:
            self.marker = None
            return self.update(lat, lon, heading)

        if delta is not None and delta < 2.0:
            return

        rotated = self.original_img.rotate(-heading, expand=False, resample=Image.BICUBIC)
        photo = ImageTk.PhotoImage(rotated)
        try:
            self._icon_ref = photo
            self.marker.change_icon(photo)
            try:
                setattr(self.marker, "_icon_ref", photo)
            except Exception:
                pass
        except Exception:
            try:
                self.marker.delete()
            except Exception:
                pass
            self._icon_ref = photo
            self.marker = self.mapw.set_marker(lat, lon, icon=photo, text=None)
            try:
                setattr(self.marker, "_icon_ref", photo)
            except Exception:
                pass

def save_config_file(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def haversine(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    s1 = math.sin(dlat / 2.0)
    s2 = math.sin(dlon / 2.0)
    c = s1 * s1 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * s2 * s2
    return 2 * R * math.asin(math.sqrt(c))


def bearing(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def interpolate(a: Tuple[float, float], b: Tuple[float, float], distance_from_a_m: float) -> Tuple[float, float]:
    total = haversine(a, b)
    if total <= 0.0:
        return b
    f = max(0.0, min(1.0, distance_from_a_m / total))
    lat = a[0] + (b[0] - a[0]) * f
    lon = a[1] + (b[1] - a[1]) * f
    return lat, lon


def nmea_checksum(s: str) -> str:
    c = 0
    for ch in s:
        c ^= ord(ch)
    return f"{c:02X}"


def format_gprmc(ts: datetime.datetime, lat: float, lon: float, speed_kmh: float, course_deg: float) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    ddmmyy = utc.strftime("%d%m%y")
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    lat_abs = abs(lat)
    lon_abs = abs(lon)
    lat_deg = int(lat_abs)
    lon_deg = int(lon_abs)
    lat_min = (lat_abs - lat_deg) * 60.0
    lon_min = (lon_abs - lon_deg) * 60.0
    lat_str = f"{lat_deg:02d}{lat_min:05.2f}"
    lon_str = f"{lon_deg:03d}{lon_min:05.2f}"
    spd_kts = speed_kmh * 0.539957
    cog = course_deg
    mag_var = 0.0
    mag_dir = "W"
    body = f"GPRMC,{tt}.00,A,{lat_str},{ns},{lon_str},{ew},{spd_kts:.1f},{cog:.1f},{ddmmyy},{mag_var:.1f},{mag_dir},A"
    return f"${body}*{nmea_checksum(body)}"


def format_gnrmc(ts: datetime.datetime, lat: float, lon: float, speed_kmh: float, course_deg: float) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    ddmmyy = utc.strftime("%d%m%y")
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    lat_abs = abs(lat)
    lon_abs = abs(lon)
    lat_deg = int(lat_abs)
    lon_deg = int(lon_abs)
    lat_min = (lat_abs - lat_deg) * 60.0
    lon_min = (lon_abs - lon_deg) * 60.0
    # Use higher precision to match user example
    lat_str = f"{lat_deg:02d}{lat_min:09.6f}"
    lon_str = f"{lon_deg:03d}{lon_min:09.6f}"
    spd_kts = speed_kmh * 0.539957
    cog = course_deg
    # Format matches user request: $GNRMC,042717.000,A,1340.822925,N,10036.183983,E,0.63,134.90,060226,,,A,V*0B
    body = f"GNRMC,{tt}.000,A,{lat_str},{ns},{lon_str},{ew},{spd_kts:.2f},{cog:.2f},{ddmmyy},,,A,V"
    return f"${body}*{nmea_checksum(body)}"


def dd_to_nmea_lat(lat: float) -> Tuple[str, str]:
    deg = int(abs(lat))
    minutes = (abs(lat) - deg) * 60.0
    return f"{deg:02d}{minutes:06.4f}", ("N" if lat >= 0 else "S")


def dd_to_nmea_lon(lon: float) -> Tuple[str, str]:
    deg = int(abs(lon))
    minutes = (abs(lon) - deg) * 60.0
    return f"{deg:03d}{minutes:06.4f}", ("E" if lon >= 0 else "W")


def format_gngns(ts: datetime.datetime, lat: float, lon: float, mode=None, num_sv=None, hdop=None, alt_m: float = None, geoid_sep: float = None, age_diff: float = None, diff_station: str = None) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    lat_str, ns = dd_to_nmea_lat(lat)
    lon_str, ew = dd_to_nmea_lon(lon)
    # Ensure values are not None/empty for 0 requirement
    mode_str = mode if mode else "N"
    num_sv = num_sv if num_sv is not None else 0
    hdop = hdop if hdop is not None else 0.0
    alt_m = alt_m if alt_m is not None else 0.0
    geoid_sep = geoid_sep if geoid_sep is not None else 0.0
    age_diff = age_diff if age_diff is not None else 0.0
    diff_station = diff_station if diff_station else "0000"
    body = f"GNGNS,{tt}.00,{lat_str},{ns},{lon_str},{ew},{mode_str},{num_sv:d},{hdop:.1f},{alt_m:.1f},{geoid_sep:.1f},{age_diff:.1f},{diff_station}"
    return f"${body}*{nmea_checksum(body)}"

def format_gpgga(ts: datetime.datetime, lat: float, lon: float, fix_quality=None, num_sv=None, hdop=None, alt_m: float = None, geoid_sep: float = None) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    lat_str, ns = dd_to_nmea_lat(lat)
    lon_str, ew = dd_to_nmea_lon(lon)
    dgps_age = 0
    dgps_station = 0
    # Ensure values are not None/empty for 0 requirement
    fix_quality = fix_quality if fix_quality is not None else 0
    num_sv = num_sv if num_sv is not None else 0
    hdop = hdop if hdop is not None else 0.0
    alt_m = alt_m if alt_m is not None else 0.0
    geoid_sep = geoid_sep if geoid_sep is not None else 0.0
    body = f"GPGGA,{tt}.00,{lat_str},{ns},{lon_str},{ew},{fix_quality},{num_sv:d},{hdop:.1f},{alt_m:.1f},M,{geoid_sep:.1f},M,{dgps_age},{dgps_station}"
    return f"${body}*{nmea_checksum(body)}"

def format_gpsacp(ts: datetime.datetime, lat: float, lon: float, speed_kmh: float, course_deg: float, alt_m: float, nsat_gps: int = 0, nsat_glonass: int = 0) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    ddmmyy = utc.strftime("%d%m%y")
    lat_str, ns = dd_to_nmea_lat(lat)
    lon_str, ew = dd_to_nmea_lon(lon)
    
    hdop = 0.0
    fix = 1
    speed_knots = speed_kmh * 0.539957
    
    body = f"GPSACP,{tt}.00,{lat_str},{ns},{lon_str},{ew},{hdop:.1f},{alt_m:.1f},{fix},{course_deg:.1f},{speed_kmh:.1f},{speed_knots:.1f},{ddmmyy},{nsat_gps},{nsat_glonass}"
    return f"${body}*{nmea_checksum(body)}"

def format_patt(ts: datetime.datetime, roll_deg: float, pitch_deg: float, yaw_deg: float) -> str:
    utc = as_utc_naive(ts)
    tt = utc.strftime("%H%M%S")
    body = f"PATT,{tt}.00,{roll_deg:.1f},{pitch_deg:.1f},{yaw_deg:.1f}"
    return f"${body}*{nmea_checksum(body)}"

def osrm_route(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(points) < 2:
        return points
    coords = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    routes = data.get("routes", [])
    if not routes:
        return points
    geom = routes[0]["geometry"]["coordinates"]
    return [(c[1], c[0]) for c in geom]

def osrm_route_full(points: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], float]:
    if len(points) < 2:
        return points, 0.0
    coords = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    routes = data.get("routes", [])
    if not routes:
        return points, 0.0
    geom = routes[0]["geometry"]["coordinates"]
    dist_m = float(routes[0].get("distance", 0.0))
    return [(c[1], c[0]) for c in geom], dist_m

def osrm_route_leg_info(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[List[Tuple[float, float]], float]:
    coords = f"{a[1]},{a[0]};{b[1]},{b[0]}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    routes = data.get("routes", [])
    if not routes:
        return [a, b], 0.0
    geom = routes[0]["geometry"]["coordinates"]
    dist_m = float(routes[0].get("distance", 0.0))
    return [(c[1], c[0]) for c in geom], dist_m

def osrm_route_with_legs(points: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], List[int], float]:
    route: List[Tuple[float, float]] = []
    leg_starts: List[int] = []
    total_distance_m = 0.0
    if len(points) < 2:
        return points, [0], 0.0
    for i in range(len(points) - 1):
        leg, dist_m = osrm_route_leg_info(points[i], points[i + 1])
        total_distance_m += dist_m
        if i == 0:
            leg_starts.append(0)
            route.extend(leg)
        else:
            leg_starts.append(len(route))
            if leg:
                route.extend(leg[1:])
    return route, leg_starts, total_distance_m

def geocode_address(addr: str) -> Optional[Tuple[float, float]]:
    addr = addr.strip()
    if not addr:
        return None
    if "," in addr:
        parts = addr.split(",")
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lat, lon
        except Exception:
            pass
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": addr, "format": "json", "countrycodes": "th", "limit": 1}
    headers = {"User-Agent": "GPS-Simulator/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    j = r.json()
    if not j:
        return None
    return float(j[0]["lat"]), float(j[0]["lon"])

def project_distance_on_polyline(route_pts: List[Tuple[float, float]], cum_d: List[float], lat: float, lon: float) -> float:
    best = float("inf")
    best_d = 0.0
    for j in range(len(route_pts) - 1):
        a = route_pts[j]
        b = route_pts[j + 1]
        x, y = lat, lon
        x1, y1 = a
        x2, y2 = b
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            d = math.hypot(x - x1, y - y1)
            t = 0.0
            seg_len = 0.0
        else:
            t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
            t = max(0.0, min(1.0, t))
            px = x1 + t * dx
            py = y1 + t * dy
            d = math.hypot(x - px, y - py)
            seg_len = haversine(a, b)
        if d < best:
            best = d
            best_d = cum_d[j] + seg_len * t
    return best_d

class RouteSimulator:
    def __init__(self, route_points: List[Tuple[float, float]], speed_kmh: float, tick_seconds: int = 10, leg_starts: Optional[List[int]] = None, leg_speeds: Optional[List[float]] = None, zone_indices: Optional[List[Tuple[int, int, float]]] = None, leg_is_waypoint: Optional[List[bool]] = None, cum_d: Optional[List[float]] = None, leg_trigger_dists: Optional[List[float]] = None, zone_ranges: Optional[List[Tuple[float, float, float]]] = None, elevations: Optional[List[float]] = None):
        self.route_points = route_points
        self.elevations = elevations or [0.0] * len(route_points)
        self.leg_starts = leg_starts or [0]
        self.leg_speeds = leg_speeds or [speed_kmh]
        self.leg_is_waypoint = leg_is_waypoint or [False] * len(self.leg_starts)
        self.current_leg_idx = 0
        self.default_speed_kmh = speed_kmh
        self.speed_kmh = 0.0
        self.zone_indices = zone_indices or []
        self.tick_seconds = tick_seconds
        self.segment_index = 0
        self.offset_in_segment = 0.0
        self.current = route_points[0] if route_points else (0.0, 0.0)
        self.prev = self.current
        self.running = False
        self.lock = threading.Lock()
        self.cum_d = cum_d
        if not self.cum_d:
            self.cum_d = [0.0]
            for j in range(len(self.route_points) - 1):
                self.cum_d.append(self.cum_d[-1] + haversine(self.route_points[j], self.route_points[j + 1]))
        self.prev_travel_d = 0.0
        self.next_trigger_idx = 0
        self.leg_triggers: List[Tuple[float, int]] = []
        if leg_trigger_dists:
            for i in range(1, len(leg_trigger_dists) + 1):
                self.leg_triggers.append((leg_trigger_dists[i - 1], i))
        elif self.leg_starts and len(self.leg_starts) > 1:
            for i in range(1, len(self.leg_starts)):
                idx = self.leg_starts[i]
                d = self.cum_d[idx] if 0 <= idx < len(self.cum_d) else self.cum_d[-1]
                self.leg_triggers.append((d, i))
        self.zone_ranges = zone_ranges or []
        if not self.zone_ranges and self.zone_indices:
            for s, e, zspd in self.zone_indices:
                sd = self.cum_d[s] if 0 <= s < len(self.cum_d) else self.cum_d[0]
                ed = self.cum_d[e] if 0 <= e < len(self.cum_d) else self.cum_d[-1]
                if sd > ed:
                    sd, ed = ed, sd
                self.zone_ranges.append((sd, ed, zspd))
        base0 = self.leg_speeds[0] if self.leg_speeds else self.default_speed_kmh
        self.target_speed_kmh = base0
        self.accel_kmh_per_s = 4.0
        self.decel_kmh_per_s = 4.0
        self.manual_target: Optional[float] = None
        self.accel_override_kmh_per_s: Optional[float] = None
        self.decel_override_kmh_per_s: Optional[float] = None

    def step(self) -> Optional[Tuple[float, float, float, float]]:
        with self.lock:
            if not self.running or len(self.route_points) < 2:
                return None

            dist_tick = self.speed_kmh * 1000.0 / 3600.0 * self.tick_seconds
            self.prev_travel_d = self.cum_d[self.segment_index] + self.offset_in_segment
            travel_d = self.prev_travel_d

            while dist_tick > 0 and self.segment_index < len(self.route_points) - 1:
                a = self.route_points[self.segment_index]
                b = self.route_points[self.segment_index + 1]
                seg_len = haversine(a, b)
                remain = seg_len - self.offset_in_segment
                if dist_tick < remain:
                    self.prev = self.current
                    self.offset_in_segment += dist_tick
                    self.current = interpolate(a, b, self.offset_in_segment)
                    dist_tick = 0
                else:
                    dist_tick -= remain
                    self.segment_index += 1
                    self.offset_in_segment = 0.0
                    self.prev = self.current
                    self.current = b
                travel_d = self.cum_d[self.segment_index] + self.offset_in_segment
                while self.next_trigger_idx < len(self.leg_triggers):
                    td, idx = self.leg_triggers[self.next_trigger_idx]
                    if self.prev_travel_d < td <= travel_d:
                        self.current_leg_idx = idx
                        self.next_trigger_idx += 1
                    else:
                        break

            if self.segment_index >= len(self.route_points) - 1:
                self.running = False

            slope_grade = 0.0
            current_alt = 0.0
            
            if self.segment_index < len(self.route_points) - 1:
                a = self.route_points[self.segment_index]
                b = self.route_points[self.segment_index + 1]
                seg_len = haversine(a, b)
                
                e1 = self.elevations[self.segment_index]
                e2 = self.elevations[self.segment_index + 1]
                
                if seg_len > 1.0:
                    slope_grade = (e2 - e1) / seg_len
                
                # Interpolate altitude
                f = self.offset_in_segment / seg_len if seg_len > 0 else 0.0
                current_alt = e1 + (e2 - e1) * f
            elif self.segment_index < len(self.elevations):
                current_alt = self.elevations[self.segment_index]

            # --- Slope Speed Limit (Uphill Physics) ---
            # Limit max speed based on steepness
            slope_limit_kmh = 1e9
            if slope_grade > 0.0:
                 # Example: 10% grade (0.1) -> 120 / (1 + 0.1*15) = 120 / 2.5 = 48 km/h
                 slope_limit_kmh = 150.0 / (1.0 + slope_grade * 15.0)

            base_accel = 4.0
            base_decel = 4.0
            accel_factor = 1.0 - (slope_grade * 5.0)
            decel_factor = 1.0 + (slope_grade * 5.0)
            accel_factor = min(2.0, max(0.3, accel_factor))
            decel_factor = min(2.0, max(0.3, decel_factor))
            current_accel = max(1.0, base_accel * accel_factor)
            current_decel = max(1.0, base_decel * decel_factor)

            if self.manual_target is not None:
                base_target = float(self.manual_target)
            else:
                in_zone_speed = None
                for sd, ed, zspd in self.zone_ranges:
                    if sd <= travel_d <= ed:
                        in_zone_speed = zspd
                if in_zone_speed is not None:
                    base_target = float(in_zone_speed)
                else:
                    base_idx = self.current_leg_idx
                    base_target = float(self.leg_speeds[base_idx] if base_idx < len(self.leg_speeds) else self.default_speed_kmh)

            corner_limit_kmh = 1e9
            if current_decel > 0.0 and len(self.route_points) >= 3:
                max_lookahead_m = 250.0
                max_vertices = 20
                start_idx = max(0, int(self.segment_index))
                end_idx = min(len(self.route_points) - 3, start_idx + max_vertices)
                a_ms2 = current_decel * (1000.0 / 3600.0)
                for idx in range(start_idx, end_idx + 1):
                    vtx_i = idx + 1
                    d_to_vtx = float(self.cum_d[vtx_i]) - float(travel_d)
                    if d_to_vtx <= 0.0:
                        continue
                    if d_to_vtx > max_lookahead_m:
                        break
                    p1 = self.route_points[idx]
                    p2 = self.route_points[idx + 1]
                    p3 = self.route_points[idx + 2]
                    b1 = bearing(p1, p2)
                    b2 = bearing(p2, p3)
                    ang = abs((b2 - b1 + 180.0) % 360.0 - 180.0)
                    if ang < 20.0:
                        continue
                    corner_speed_kmh = max(20.0, 120.0 - (ang * 1.1))
                    v_corner = corner_speed_kmh / 3.6
                    v_allow = math.sqrt(max(0.0, (v_corner * v_corner) + (2.0 * a_ms2 * d_to_vtx)))
                    corner_limit_kmh = min(corner_limit_kmh, v_allow * 3.6)

            if corner_limit_kmh < 1e8:
                self.target_speed_kmh = min(base_target, corner_limit_kmh, slope_limit_kmh)
            else:
                self.target_speed_kmh = min(base_target, slope_limit_kmh)

            if self.speed_kmh < self.target_speed_kmh:
                rate_up = self.accel_override_kmh_per_s if self.accel_override_kmh_per_s is not None else current_accel
                delta_up = rate_up * self.tick_seconds
                self.speed_kmh = min(self.speed_kmh + delta_up, self.target_speed_kmh)
                if abs(self.speed_kmh - self.target_speed_kmh) <= 0.01:
                    self.accel_override_kmh_per_s = None
            elif self.speed_kmh > self.target_speed_kmh:
                rate_down = self.decel_override_kmh_per_s if self.decel_override_kmh_per_s is not None else current_decel
                delta_down = rate_down * self.tick_seconds
                self.speed_kmh = max(self.speed_kmh - delta_down, self.target_speed_kmh)
                if abs(self.speed_kmh - self.target_speed_kmh) <= 0.01:
                    self.decel_override_kmh_per_s = None
            
            brg = bearing(self.prev, self.current)
            return self.current[0], self.current[1], brg, current_alt

    def start(self):
        with self.lock:
            self.running = True

    def stop(self):
        with self.lock:
            self.running = False

    def update_all_speeds(self, new_speed: float):
        with self.lock:
            self.default_speed_kmh = new_speed
            self.target_speed_kmh = new_speed
            self.manual_target = new_speed
            # Update all leg speeds to the new manual speed
            if self.leg_speeds:
                self.leg_speeds = [new_speed] * len(self.leg_speeds)
            # Update all speed zones to the new manual speed as well
            if self.zone_ranges:
                self.zone_ranges = [(s, e, new_speed) for (s, e, _) in self.zone_ranges]
    def brake(self):
        with self.lock:
            self.manual_target = 0.0
            self.target_speed_kmh = 0.0
            self.decel_override_kmh_per_s = None
    def accelerate_to(self, new_speed: float):
        with self.lock:
            self.speed_kmh = 0.0
            self.manual_target = new_speed
            self.target_speed_kmh = new_speed
            self.accel_override_kmh_per_s = None
    def emergency_brake(self, seconds: float = 3.0):
        with self.lock:
            self.manual_target = 0.0
            self.target_speed_kmh = 0.0
            cur = max(0.0, float(self.speed_kmh))
            self.decel_override_kmh_per_s = (cur / max(0.1, seconds))
    def boost_start(self, target_speed: float, seconds: float = 3.0):
        with self.lock:
            self.speed_kmh = 0.0
            self.manual_target = target_speed
            self.target_speed_kmh = target_speed
            self.accel_override_kmh_per_s = (max(0.0, float(target_speed)) / max(0.1, seconds))



altitude_cache = {}

def get_altitude_m(lat: float, lon: float) -> float:
    key = (round(lat, 5), round(lon, 5))
    v = altitude_cache.get(key)
    if v is not None:
        return v
    try:
        # Use Open-Meteo API (More reliable than open-elevation)
        r = requests.get("https://api.open-meteo.com/v1/elevation", params={"latitude": lat, "longitude": lon}, timeout=5)
        j = r.json()
        elevations = j.get("elevation", [])
        if elevations:
            v = float(elevations[0])
        else:
            v = 0.0
    except Exception:
        v = 0.0
    altitude_cache[key] = v
    return v

def batch_get_elevations(coords: List[Tuple[float, float]]) -> List[float]:
    if not coords:
        return []
    chunk_size = 100
    results = [0.0] * len(coords)
    def fetch_chunk(start_idx):
        chunk = coords[start_idx : start_idx + chunk_size]
        try:
            # Open-Meteo batch request
            lats = ",".join(f"{lat:.6f}" for lat, lon in chunk)
            lons = ",".join(f"{lon:.6f}" for lat, lon in chunk)
            r = requests.get("https://api.open-meteo.com/v1/elevation", params={"latitude": lats, "longitude": lons}, timeout=10)
            j = r.json()
            elevations = j.get("elevation", [])
            for i, elev in enumerate(elevations):
                if start_idx + i < len(results):
                    results[start_idx + i] = float(elev) if elev is not None else 0.0
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for i in range(0, len(coords), chunk_size):
            futures.append(executor.submit(fetch_chunk, i))
        for f in futures:
            f.result()
    return results


def run_headless(args):
    start = geocode_address(args.start)
    end = geocode_address(args.end)
    waypoints = []
    for w in args.waypoint:
        loc = geocode_address(w)
        if loc:
            waypoints.append(loc)
    pts = [start] + waypoints + [end]
    pts = [p for p in pts if p]
    route, _ = osrm_route_full(pts)
    elevations = batch_get_elevations(route)
    sim = RouteSimulator(route, args.speed, tick_seconds=10, elevations=elevations)
    sim.start()
    start_ts = datetime.datetime.utcnow()
    ticks = args.ticks if args.ticks > 0 else 20
    for _ in range(ticks):
        res = sim.step()
        if not res:
            break
        lat, lon, cog, alt = res
        ts = datetime.datetime.utcnow()
        line = f"{ts.isoformat()} lat={lat:.6f}, lon={lon:.6f}, alt={alt:.1f} m, speed={args.speed:.1f} km/h, course={cog:.1f} deg"
        print(line)
        time.sleep(10)

def main_gui():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = ctk.CTk()
    try:
        app.iconbitmap(resource_path("icon_app.ico"))
    except Exception:
        pass
    app.title("GPS Simulator 1.2")
    app.geometry("1100x700")

    is_app_running = True

    # Helper functions needed for UI Init
    def get_serial_ports():
        return [p.device for p in serial.tools.list_ports.comports()]

    # Initialize Callbacks with pre-requisites
    callbacks = {
        'get_ports': get_serial_ports
    }
    
    # Initialize UI (creates vars)
    ui = GPSAppUI(app, callbacks)

    # State variables
    waypoints: List[Tuple[float, float, float]] = []
    route_line = None
    simulator: Optional[RouteSimulator] = None
    speed_zone_start: Optional[Tuple[float, float, float]] = None
    speed_zones_coords: List[Tuple[Tuple[float, float], Tuple[float, float], float]] = []
    car_ctrl = CarMarkerController(ui.mapw)

    sim_time_base: Optional[datetime.datetime] = None
    sim_time_real_anchor: Optional[float] = None
    sim_time_accum_s: float = 0.0
    sim_time_base_text_last: str = ""
    sim_time_mode_last: str = ""

    current_lat = 0.0
    current_lon = 0.0
    current_cog = 0.0
    last_altitude_m = 0.0
    executor = ThreadPoolExecutor(max_workers=2)
    serial_conn = None
    route_build_after_id = None
    route_build_seq = 0
    route_build_inflight = False
    route_cache = {}
    elevations_cache = {}
    geocode_cache = {}

    # Load Config
    cfg_data = load_config()
    if cfg_data:
        try:
            if "start" in cfg_data: ui.vars['start_var'].set(cfg_data["start"])
            if "speed" in cfg_data: ui.vars['speed_var'].set(cfg_data["speed"])
            if "hz" in cfg_data: ui.vars['hz_var'].set(cfg_data["hz"])
            if "log_sec" in cfg_data: ui.vars['log_sec_var'].set(cfg_data["log_sec"])
            if "time_mode" in cfg_data: ui.vars['time_mode_var'].set(cfg_data["time_mode"])
            if "base_date" in cfg_data: ui.vars['base_date_var'].set(cfg_data["base_date"])
            if "base_clock" in cfg_data: ui.vars['base_clock_var'].set(cfg_data["base_clock"])
            if "sat_total" in cfg_data: 
                ui.vars['sat_total_var'].set(cfg_data["sat_total"])
                # Update satellite details based on total
                try:
                    tot = int(cfg_data["sat_total"])
                    gps_c = int(tot * 0.6)
                    glo_c = tot - gps_c
                    ui.vars['sat_gps_var'].set(str(gps_c))
                    ui.vars['sat_glonass_var'].set(str(glo_c))
                except:
                    pass
            if "serial_port" in cfg_data: ui.vars['serial_port_var'].set(cfg_data["serial_port"])
            if "serial_baud" in cfg_data: ui.vars['serial_baud_var'].set(cfg_data["serial_baud"])
            if "send_gngns" in cfg_data: ui.vars['send_gngns'].set(bool(cfg_data["send_gngns"]))
            if "send_gprmc" in cfg_data: ui.vars['send_gprmc'].set(bool(cfg_data["send_gprmc"]))
            if "send_gnrmc" in cfg_data: ui.vars['send_gnrmc'].set(bool(cfg_data["send_gnrmc"]))
            if "send_gpgga" in cfg_data: ui.vars['send_gpgga'].set(bool(cfg_data["send_gpgga"]))
            if "send_gpsacp" in cfg_data: ui.vars['send_gpsacp'].set(bool(cfg_data["send_gpsacp"]))
        except Exception:
            pass
    ui.vars['end_var'].set("")

    def parse_base_date_time_text(date_text: str, clock_text: str) -> Optional[datetime.datetime]:
        d = str(date_text).strip()
        t = str(clock_text).strip()
        if not d and not t:
            return None
        d = d.replace("-", "/")
        t = t.replace(":", ".")
        if not d:
            return None
        if not t:
            t = "00.00"
        s = f"{d} {t}".strip()
        fmts = (
            "%d/%m/%Y %H.%M",
            "%d/%m/%Y %H.%M.%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
        )
        for f in fmts:
            try:
                return datetime.datetime.strptime(s, f)
            except Exception:
                continue
        try:
            dt = datetime.datetime.strptime(d, "%d/%m/%Y")
            return dt.replace(hour=0, minute=0, second=0)
        except Exception:
            return None

    def maybe_migrate_base_time_config():
        try:
            if ui.vars.get("base_date_var") and str(ui.vars["base_date_var"].get()).strip():
                return
            if ui.vars.get("base_clock_var") and str(ui.vars["base_clock_var"].get()).strip():
                return
        except Exception:
            pass
        try:
            old = cfg_data.get("base_time") if isinstance(cfg_data, dict) else None
        except Exception:
            old = None
        if not old:
            return
        try:
            s = str(old).strip()
            parts = s.split()
            if len(parts) >= 1 and ui.vars.get("base_date_var"):
                ui.vars["base_date_var"].set(parts[0])
            if len(parts) >= 2 and ui.vars.get("base_clock_var"):
                ui.vars["base_clock_var"].set(parts[1].replace(":", "."))
        except Exception:
            pass

    maybe_migrate_base_time_config()

    def pause_sim_clock():
        nonlocal sim_time_real_anchor, sim_time_accum_s
        if sim_time_real_anchor is None:
            return
        try:
            sim_time_accum_s += max(0.0, float(time.time() - float(sim_time_real_anchor)))
        except Exception:
            pass
        sim_time_real_anchor = None

    def ensure_sim_clock_running(reset_if_base_changed: bool = True):
        nonlocal sim_time_base, sim_time_real_anchor, sim_time_accum_s, sim_time_base_text_last, sim_time_mode_last
        mode = str(ui.vars.get("time_mode_var").get() if ui.vars.get("time_mode_var") else "machine").strip().lower()
        base_date_text = str(ui.vars.get("base_date_var").get() if ui.vars.get("base_date_var") else "").strip()
        base_clock_text = str(ui.vars.get("base_clock_var").get() if ui.vars.get("base_clock_var") else "").strip()
        base_text = f"{base_date_text} {base_clock_text}".strip()
        running = bool(simulator and getattr(simulator, "running", False))
        changed_mode = mode != sim_time_mode_last
        changed_manual_base = (mode == "manual" and base_text != sim_time_base_text_last)
        if reset_if_base_changed and (changed_mode or changed_manual_base):
            if mode == "machine":
                sim_time_base = datetime.datetime.utcnow()
            else:
                parsed = parse_base_date_time_text(base_date_text, base_clock_text)
                if parsed is None and (base_date_text or base_clock_text):
                    return
                if parsed is not None:
                    parsed = parsed - datetime.timedelta(hours=7)
                sim_time_base = parsed if parsed is not None else datetime.datetime.utcnow()
            sim_time_accum_s = 0.0
            sim_time_real_anchor = time.time() if running else None
            sim_time_base_text_last = base_text
            sim_time_mode_last = mode

        if sim_time_base is None:
            if mode == "machine":
                sim_time_base = datetime.datetime.utcnow()
            else:
                parsed = parse_base_date_time_text(base_date_text, base_clock_text)
                if parsed is not None:
                    parsed = parsed - datetime.timedelta(hours=7)
                sim_time_base = parsed if parsed is not None else datetime.datetime.utcnow()
            sim_time_base_text_last = base_text
            sim_time_mode_last = mode

        if running and sim_time_real_anchor is None:
            sim_time_real_anchor = time.time()

    def get_sim_time_utc() -> datetime.datetime:
        nonlocal sim_time_base, sim_time_real_anchor, sim_time_accum_s
        
        # If Machine mode, ALWAYS return current UTC time (Real-time)
        try:
            mode = str(ui.vars.get("time_mode_var").get() if ui.vars.get("time_mode_var") else "machine").strip().lower()
            if mode == "machine":
                return datetime.datetime.utcnow()
        except Exception:
            return datetime.datetime.utcnow()

        try:
            ensure_sim_clock_running(reset_if_base_changed=True)
        except Exception:
            pass
        if sim_time_base is None:
            return datetime.datetime.utcnow()
        base = sim_time_base + datetime.timedelta(seconds=float(sim_time_accum_s))
        if sim_time_real_anchor is None:
            return base
        try:
            return base + datetime.timedelta(seconds=max(0.0, float(time.time() - float(sim_time_real_anchor))))
        except Exception:
            return base

    # Helper functions for UI interaction
    # get_serial_ports moved up

    def toggle_serial():
        nonlocal serial_conn
        if serial_conn and serial_conn.is_open:
            try:
                serial_conn.close()
            except:
                pass
            serial_conn = None
            ui.update_serial_btn(False, "", "")
        else:
            try:
                port = ui.vars['serial_port_var'].get()
                baud = int(ui.vars['serial_baud_var'].get())
                if not port:
                    ui.vars['serial_status_var'].set("Error: No Port Selected")
                    return
                serial_conn = serial.Serial(port, baud, timeout=1)
                ui.update_serial_btn(True, port, baud)
            except Exception as e:
                print(f"Serial Error: {e}")
                ui.set_serial_error(str(e)[:20])

    def get_interval_ms():
        try:
            hz = float(ui.vars['hz_var'].get())
            log_sec = float(ui.vars['log_sec_var'].get())
            if hz <= 0.0:
                hz = 1.0
            if log_sec <= 0.0:
                log_sec = 1.0
            # Formula: Send (Hz) packets per (Log Time) seconds
            # Interval = (Log Time * 1000) / Hz
            return max(1, int((log_sec * 1000.0) / hz))
        except Exception:
            return 1000

    def get_log_interval_ms():
        # Throttle screen log updates to prevent UI freezing
        # Since Log Time now controls transmission rate, we use a fixed throttle for display
        return 200


    def update_alt_async(lat: float, lon: float):
        try:
            v = get_altitude_m(lat, lon)
            def cb():
                nonlocal last_altitude_m
                last_altitude_m = v
                try:
                    ui.vars['altitude_display_var'].set(f"Altitude: {v:.1f} m")
                except:
                    pass
            app.after(0, cb)
        except Exception:
            pass


    def refresh_markers():
        # Clear existing markers
        if ui.markers["start"]:
            ui.markers["start"].delete()
            ui.markers["start"] = None
        if ui.markers["end"]:
            ui.markers["end"].delete()
            ui.markers["end"] = None
        if "dests" in ui.markers:
            for m in ui.markers["dests"]:
                try:
                    m.delete()
                except Exception:
                    pass
            ui.markers.pop("dests", None)

        def parse_latlon_text(v: str):
            try:
                parts = [p.strip() for p in str(v).split(",")]
                if len(parts) != 2:
                    return None
                return float(parts[0]), float(parts[1])
            except Exception:
                return None

        def resolve_location(v: str):
            t = str(v).strip()
            if not t:
                return None
            coords = parse_latlon_text(t)
            if coords:
                return coords
            cached = geocode_cache.get(t)
            if cached is not None:
                return cached
            loc = geocode_address(t)
            geocode_cache[t] = loc
            return loc

        # Start
        start_val = ui.vars['start_var'].get().strip()
        if start_val:
            loc = resolve_location(start_val)
            if loc:
                ui.markers["start"] = ui.mapw.set_marker(loc[0], loc[1], text="Start", marker_color_circle="#00C800", marker_color_outside="#00A000")

        # End
        end_val = ui.vars['end_var'].get().strip()
        if end_val:
            loc = resolve_location(end_val)
            if loc:
                ui.markers["end"] = ui.mapw.set_marker(loc[0], loc[1], text="End")  # Default Red

    def build_route_worker(seq: int, start_text: str, end_text: str, wp_snapshot, default_speed: float, zones_snapshot):
        try:
            def resolve_location(v: str):
                t = str(v).strip()
                if not t:
                    return None
                try:
                    parts = [p.strip() for p in str(t).split(",")]
                    if len(parts) == 2:
                        return float(parts[0]), float(parts[1])
                except Exception:
                    pass
                cached = geocode_cache.get(t)
                if cached is not None:
                    return cached
                loc = geocode_address(t)
                geocode_cache[t] = loc
                return loc

            s = resolve_location(start_text)
            e = resolve_location(end_text)

            pts: List[Tuple[float, float]] = []
            if s:
                pts.append(s)
            for (wl, wo, _ws) in wp_snapshot:
                pts.append((float(wl), float(wo)))
            if e:
                pts.append(e)
            if len(pts) < 2:
                return seq, None

            key = tuple((round(p[0], 6), round(p[1], 6)) for p in pts)
            cached_route = route_cache.get(key)
            if cached_route is None:
                route, total_distance_m = osrm_route_full(pts)
                route_cache[key] = (route, total_distance_m)
            else:
                route, total_distance_m = cached_route

            elev_cached = elevations_cache.get(key)
            if elev_cached is None:
                elevations = batch_get_elevations(route)
                if not elevations:
                    elevations = [0.0] * len(route)
                elevations_cache[key] = elevations
            else:
                elevations = elev_cached

            cum_d = [0.0]
            for j in range(len(route) - 1):
                cum_d.append(cum_d[-1] + haversine(route[j], route[j + 1]))

            leg_trigger_dists: List[float] = []
            for i, p in enumerate(pts):
                if i == 0:
                    continue
                d = project_distance_on_polyline(route, cum_d, p[0], p[1])
                leg_trigger_dists.append(d)

            leg_speeds: List[float] = [float(default_speed)]
            for (_wl, _wo, ws) in wp_snapshot:
                leg_speeds.append(float(ws))
            if len(leg_speeds) < len(pts) - 1:
                leg_speeds.extend([leg_speeds[-1]] * (len(pts) - 1 - len(leg_speeds)))

            zone_ranges: List[Tuple[float, float, float]] = []
            for ((s_lat, s_lon), (e_lat, e_lon), spd) in zones_snapshot:
                sd = project_distance_on_polyline(route, cum_d, s_lat, s_lon)
                ed = project_distance_on_polyline(route, cum_d, e_lat, e_lon)
                if sd > ed:
                    sd, ed = ed, sd
                zone_ranges.append((sd, ed, float(spd)))

            return seq, {
                "pts": pts,
                "route": route,
                "total_distance_m": total_distance_m,
                "cum_d": cum_d,
                "leg_speeds": leg_speeds,
                "leg_trigger_dists": leg_trigger_dists,
                "zone_ranges": zone_ranges,
                "elevations": elevations,
                "default_speed": float(default_speed),
            }
        except Exception:
            return seq, None

    def build_route():
        nonlocal route_build_after_id, route_build_seq, route_build_inflight
        route_build_after_id = None
        try:
            default_speed = float(ui.vars['speed_var'].get())
        except Exception:
            default_speed = 60.0
        start_text = ui.vars['start_var'].get()
        end_text = ui.vars['end_var'].get()
        wp_snapshot = list(waypoints)
        zones_snapshot = list(speed_zones_coords)

        route_build_seq += 1
        seq = route_build_seq
        route_build_inflight = True

        fut = executor.submit(build_route_worker, seq, start_text, end_text, wp_snapshot, default_speed, zones_snapshot)

        def on_done(done_fut):
            try:
                res_seq, payload = done_fut.result()
            except Exception:
                res_seq, payload = seq, None

            def apply_result():
                nonlocal route_build_inflight, simulator, route_line
                if res_seq != route_build_seq:
                    return
                route_build_inflight = False
                if not payload:
                    return

                was_running = bool(simulator and getattr(simulator, "running", False))
                if simulator:
                    try:
                        simulator.stop()
                    except Exception:
                        pass

                zone_info_items = []
                for zi, (sd, ed, spd) in enumerate(payload["zone_ranges"]):
                    dist_m = max(0.0, float(ed) - float(sd))
                    zone_info_items.append(f"{zi+1}: {dist_m/1000.0:.2f} km @ {int(spd)} km/h")
                if zone_info_items:
                    ui.vars['speed_zone_info_var'].set("ระยะช่วงความเร็ว: " + ", ".join(zone_info_items))
                else:
                    ui.vars['speed_zone_info_var'].set("ระยะช่วงความเร็ว: -")

                ui.mapw.delete_all_path()
                route_line = ui.draw_path(payload["route"])

                pts = payload["pts"]
                legs_count = max(0, len(pts) - 1)
                leg_is_wp: List[bool] = []
                if legs_count > 0:
                    leg_is_wp = [False] + [True] * (legs_count - 1)

                simulator = RouteSimulator(
                    payload["route"],
                    payload["default_speed"],
                    tick_seconds=0.2,
                    leg_speeds=payload["leg_speeds"],
                    leg_is_waypoint=leg_is_wp,
                    cum_d=payload["cum_d"],
                    leg_trigger_dists=payload["leg_trigger_dists"],
                    zone_ranges=payload["zone_ranges"],
                    elevations=payload["elevations"],
                )

                ui.vars['distance_var'].set(f"ระยะทางรวม: {payload['total_distance_m']/1000.0:.2f} km")
                if payload["route"]:
                    car_ctrl.update(payload["route"][0][0], payload["route"][0][1], 0.0)
                    ui.car_marker = car_ctrl.marker
                update_travel_time()

                if was_running:
                    simulator.start()
                    try:
                        schedule_log()
                        schedule_nmea()
                    except Exception:
                        pass

            app.after(0, apply_result)

        fut.add_done_callback(on_done)

    def schedule_build_route(immediate: bool = False):
        nonlocal route_build_after_id
        if route_build_after_id is not None:
            try:
                app.after_cancel(route_build_after_id)
            except Exception:
                pass
            route_build_after_id = None
        delay_ms = 1 if immediate else 250
        route_build_after_id = app.after(delay_ms, build_route)

    def try_auto_route():
        refresh_markers()
        s = ui.vars['start_var'].get().strip()
        e = ui.vars['end_var'].get().strip()
        
        if s and e:
            schedule_build_route()

    def geocode_to_var(var: ctk.StringVar, label: str):
        val = var.get().strip()
        loc = geocode_address(val)
        if loc:
            lat, lon = loc
            var.set(f"{lat:.6f},{lon:.6f}")
            ui.set_map_center(lat, lon, zoom=12)
            try_auto_route()

    def normalize_coords(c):
        try:
            lat, lon = c
            return float(lat), float(lon)
        except Exception:
            lat = getattr(c, "latitude", None) or getattr(c, "lat", None)
            lon = getattr(c, "longitude", None) or getattr(c, "lng", None)
            if lat is None or lon is None:
                return None
            return float(lat), float(lon)

    def set_start_at(c):
        norm = normalize_coords(c)
        if not norm:
            return
        lat, lon = norm
        ui.vars['start_var'].set(f"{lat:.6f},{lon:.6f}")
        try_auto_route()

    def set_end_at(c):
        norm = normalize_coords(c)
        if not norm:
            return
        lat, lon = norm
        
        # Auto-chain: if simulation finished, move old end to start
        nonlocal simulator
        should_chain = False
        if simulator:
            try:
                # Check if we are at the end of the route (tolerance 20m)
                total_dist = float(simulator.cum_d[-1]) if simulator.cum_d else 0.0
                curr_dist = float(getattr(simulator, "prev_travel_d", 0.0))
                if total_dist > 0 and curr_dist >= total_dist - 20.0:
                    should_chain = True
            except Exception:
                pass
        
        if should_chain:
            old_end = ui.vars['end_var'].get()
            if old_end:
                ui.vars['start_var'].set(old_end)

        ui.vars['end_var'].set(f"{lat:.6f},{lon:.6f}")
        try_auto_route()

    def redraw_waypoint_markers():
        try:
            for m in ui.markers.get("wps", []):
                try:
                    m.delete()
                except Exception:
                    pass
        except Exception:
            pass
        ui.markers["wps"] = []
        for i, (lat, lon, _spd) in enumerate(waypoints, start=1):
            try:
                m = ui.mapw.set_marker(float(lat), float(lon), text=f"จุดผ่าน{i}", marker_color_circle="#3498DB", marker_color_outside="#1F618D")
                ui.markers["wps"].append(m)
            except Exception:
                pass

    def add_pass_through_at(c):
        norm = normalize_coords(c)
        if not norm:
            return
        lat, lon = norm
        try:
            spd = float(ui.vars['speed_var'].get())
        except Exception:
            spd = 60.0
        waypoints.append((lat, lon, spd))
        redraw_waypoint_markers()
        try_auto_route()

    def remove_last_pass_through():
        if not waypoints:
            return
        try:
            waypoints.pop()
        except Exception:
            return
        redraw_waypoint_markers()
        try_auto_route()

    def remove_pass_through_near(c):
        norm = normalize_coords(c)
        if not norm:
            return
        if not waypoints:
            return
        lat, lon = norm
        best_i = None
        best_m = None
        for i, (wl, wo, _ws) in enumerate(waypoints):
            d = haversine((float(lat), float(lon)), (float(wl), float(wo)))
            if best_m is None or d < best_m:
                best_m = d
                best_i = i
        if best_i is None:
            return
        if best_m is None or best_m > 120.0:
            return
        try:
            waypoints.pop(best_i)
        except Exception:
            return
        redraw_waypoint_markers()
        try_auto_route()

    def clear_all_pass_through():
        if not waypoints:
            return
        waypoints.clear()
        redraw_waypoint_markers()
        try_auto_route()

    def on_speed_zone_start(c):
        norm = normalize_coords(c)
        if not norm:
            return
        lat, lon = norm
        spd_default = float(ui.vars['speed_var'].get())
        
        try:
            val = ui.prompt_speed_input(title="กำหนดความเร็ว waypoint", text="ระบุความเร็ว (km/h):")
            if val is None:
                spd = None
            else:
                spd = float(val)
                if spd <= 0:
                    spd = None
        except Exception:
            spd = spd_default

        if spd is None:
            return
        nonlocal speed_zone_start
        speed_zone_start = (lat, lon, spd)
        mk = ui.add_marker(lat, lon, text=f"เริ่มช่วงความเร็ว ({int(spd)} km/h)\n{lat:.6f}, {lon:.6f}")
        ui.zone_markers["start"].append(mk)

    def on_speed_zone_end(c):
        norm = normalize_coords(c)
        if not norm:
            return
        lat, lon = norm
        nonlocal speed_zone_start
        if speed_zone_start is None:
            return
        s_lat, s_lon, s_spd = speed_zone_start
        speed_zones_coords.append(((s_lat, s_lon), (lat, lon), s_spd))
        speed_zone_start = None
        mk = ui.add_marker(lat, lon, text=f"สิ้นสุดช่วงความเร็ว\n{lat:.6f}, {lon:.6f}")
        ui.zone_markers["end"].append(mk)
        try_auto_route()

    def clear_all():
        ui.clear_map()
        ui.markers["start"] = None
        ui.markers["end"] = None
        ui.markers["wps"] = []
        waypoints.clear()
        
        nonlocal speed_zone_start
        speed_zone_start = None
        speed_zones_coords.clear()
        
        ui.zone_markers["start"].clear()
        ui.zone_markers["end"].clear()
        
        nonlocal route_line
        route_line = None
        
        ui.logbox.configure(state="normal")
        ui.logbox.delete("1.0", "end")
        ui.logbox.configure(state="disabled")
        
        ui.vars['start_var'].set("")
        ui.vars['end_var'].set("")
        ui.vars['distance_var'].set("ระยะทางรวม: -")
        ui.vars['speed_zone_info_var'].set("ระยะช่วงความเร็ว: -")
        ui.vars['travel_time_var'].set("เวลาเดินทางโดยประมาณ: -")
        ui.vars['start_time_display_var'].set("เริ่ม: -")
        ui.vars['eta_display_var'].set("คาดว่าจะถึง: -")
        ui.vars['mode_var'].set("none")
        
        nonlocal simulator
        simulator = None

        nonlocal sim_time_base, sim_time_real_anchor, sim_time_accum_s, sim_time_base_text_last, sim_time_mode_last
        sim_time_base = None
        sim_time_real_anchor = None
        sim_time_accum_s = 0.0
        sim_time_base_text_last = ""
        sim_time_mode_last = ""
        car_ctrl.clear()
        ui.car_marker = None

    def update_travel_time():
        try:
            nonlocal simulator
            if not simulator or not getattr(simulator, "cum_d", None):
                ui.vars['travel_time_var'].set("เวลาเดินทางโดยประมาณ: -")
                ui.vars['eta_display_var'].set("คาดว่าจะถึง: -")
                for k in ("_smooth_ts", "_spd_s", "_secs_s"):
                    if hasattr(update_travel_time, k):
                        try:
                            delattr(update_travel_time, k)
                        except Exception:
                            pass
                return

            total_m = float(simulator.cum_d[-1])
            traveled_m = float(getattr(simulator, "prev_travel_d", 0.0))
            remaining_m = max(0.0, total_m - traveled_m)
            remaining_km = remaining_m / 1000.0
            
            spd = 0.0
            try:
                spd = float(ui.vars['speed_var'].get())
            except Exception:
                pass

            if spd <= 1.0 and getattr(simulator, "running", False):
                 try:
                     spd = float(getattr(simulator, "speed_kmh", 0.0))
                 except:
                     pass

            if spd <= 0.0:
                ui.vars['travel_time_var'].set("เวลาเดินทางโดยประมาณ: -")
                ui.vars['eta_display_var'].set("คาดว่าจะถึง: -")
                for k in ("_smooth_ts", "_spd_s", "_secs_s"):
                    if hasattr(update_travel_time, k):
                        try:
                            delattr(update_travel_time, k)
                        except Exception:
                            pass
                return
            
            if remaining_km <= 0.005 and total_m > 0:
                 ui.vars['travel_time_var'].set("เวลาเดินทางโดยประมาณ: 00:00:00")
                 ui.vars['eta_display_var'].set("คาดว่าจะถึง: ถึงแล้ว")
                 for k in ("_smooth_ts", "_spd_s", "_secs_s"):
                     if hasattr(update_travel_time, k):
                         try:
                             delattr(update_travel_time, k)
                         except Exception:
                             pass
                 return

            now_ts = time.time()
            prev_ts = getattr(update_travel_time, "_smooth_ts", None)
            if prev_ts is None:
                prev_ts = now_ts
            dt = max(0.1, float(now_ts - float(prev_ts)))
            update_travel_time._smooth_ts = now_ts

            spd_s = float(getattr(update_travel_time, "_spd_s", spd))
            spd_s = spd_s + (0.25 * (float(spd) - spd_s))
            update_travel_time._spd_s = spd_s
            spd_use = max(0.1, spd_s)

            secs_inst = int((remaining_km / spd_use) * 3600.0)
            prev_secs = int(getattr(update_travel_time, "_secs_s", secs_inst))
            jitter_tol = 5
            step_up = max(1, int(round(3.0 * dt)))
            step_down = max(1, int(round(8.0 * dt)))
            step_time = max(1, int(round(dt)))

            if secs_inst > prev_secs + jitter_tol:
                secs = min(secs_inst, prev_secs + step_up)
            elif secs_inst < prev_secs - jitter_tol:
                secs = max(secs_inst, prev_secs - step_down)
            else:
                secs = max(secs_inst, prev_secs - step_time)

            update_travel_time._secs_s = secs
            h = secs // 3600
            m = (secs % 3600) // 60
            s = secs % 60
            ui.vars['travel_time_var'].set(f"เวลาเดินทางโดยประมาณ: {h:02d}:{m:02d}:{s:02d}")
            
            # ETA is now fixed at Start, only update if NOT running (e.g. preview)
            if not getattr(simulator, "running", False):
                try:
                    now = get_sim_time_utc()
                    eta = now + datetime.timedelta(seconds=secs)
                    # Convert to Local (UTC+7) for display
                    eta_local = eta + datetime.timedelta(hours=7)
                    ui.vars['eta_display_var'].set(f"คาดว่าจะถึง: {eta_local.strftime('%d/%m/%Y %H:%M:%S')}")
                except Exception:
                    pass
        except Exception:
            pass

    def on_speed_changed(*_):
        try:
            t = str(ui.vars['speed_var'].get())
            s = "".join(ch for ch in t if ch.isdigit())
            if s != t:
                ui.vars['speed_var'].set(s)
            if not s:
                return
            val = float(int(s))
            nonlocal simulator
            if simulator:
                simulator.update_all_speeds(val)
            try:
                ui.update_speed_slider(val)
            except Exception:
                pass
            update_travel_time()
        except Exception:
            pass
    ui.vars['speed_var'].trace_add("write", on_speed_changed)

    def start_sim():
        nonlocal simulator
        ensure_sim_clock_running()
        if not simulator:
            schedule_build_route(immediate=True)

            def try_start(retries=30):
                nonlocal simulator
                if not is_app_running:
                    return
                if simulator:
                    simulator.start()
                    schedule_move()
                    schedule_log()
                    schedule_nmea()
                    return
                if retries <= 0:
                    return
                app.after(100, lambda: try_start(retries - 1))

            try_start()
            return
        
        # Set Start Time Display and Fixed ETA
        try:
            start_ts = get_sim_time_utc()
            start_ts_local = start_ts + datetime.timedelta(hours=7)
            ui.vars['start_time_display_var'].set(f"เริ่ม: {start_ts_local.strftime('%d/%m/%Y %H:%M:%S')}")
            
            # Calculate Fixed ETA based on current remaining distance and speed
            try:
                total_m = float(simulator.cum_d[-1])
                traveled_m = float(getattr(simulator, "prev_travel_d", 0.0))
                remaining_m = max(0.0, total_m - traveled_m)
                spd = float(ui.vars['speed_var'].get())
                if spd > 0:
                    seconds_needed = (remaining_m / 1000.0) / spd * 3600
                    eta = start_ts + datetime.timedelta(seconds=seconds_needed)
                    eta_local = eta + datetime.timedelta(hours=7)
                    ui.vars['eta_display_var'].set(f"คาดว่าจะถึง: {eta_local.strftime('%d/%m/%Y %H:%M:%S')}")
            except Exception:
                pass
        except Exception:
            pass

        simulator.start()
        schedule_move()
        schedule_log()
        schedule_nmea()

    def stop_sim():
        nonlocal simulator
        if simulator:
            simulator.stop()
        pause_sim_clock()

    def brake_now():
        nonlocal simulator
        if simulator:
            simulator.brake()

    def start_go():
        nonlocal simulator
        if simulator:
            try:
                t = str(ui.vars['speed_var'].get())
                s = "".join(ch for ch in t if ch.isdigit())
                val = float(int(s)) if s else float(simulator.default_speed_kmh)
            except Exception:
                val = float(getattr(simulator, "default_speed_kmh", 10.0))
            simulator.accelerate_to(val)

    def emergency_brake_now():
        nonlocal simulator
        if simulator:
            simulator.emergency_brake(3.0)

    def boost_start_now():
        nonlocal simulator
        if simulator:
            try:
                t = str(speed_var.get())
                s = "".join(ch for ch in t if ch.isdigit())
                val = float(int(s)) if s else float(simulator.default_speed_kmh)
            except Exception:
                val = float(getattr(simulator, "default_speed_kmh", 10.0))
            simulator.boost_start(val, 3.0)

    def schedule_move():
        nonlocal simulator
        if not is_app_running:
            return
        
        step_ms = 100
        try:
            req_interval = get_interval_ms()
            step_ms = min(100, req_interval)
            if simulator:
                simulator.tick_seconds = (step_ms / 1000.0)
        except Exception:
            step_ms = 100

        if not simulator:
            app.after(step_ms, schedule_move)
            return
        if not simulator.running:
            pause_sim_clock()
            try:
                if not hasattr(schedule_move, "_arrived_notified") or not schedule_move._arrived_notified:
                    ui.log("[ถึงจุดหมายแล้ว]")
                    schedule_move._arrived_notified = True
            except Exception:
                pass
            app.after(step_ms, schedule_move)
            return
        try:
            schedule_move._arrived_notified = False
        except Exception:
            pass
        res = simulator.step()
        if res:
            lat, lon, cog, alt = res
            nonlocal current_lat, current_lon, current_cog, last_altitude_m
            current_lat = lat
            current_lon = lon
            current_cog = cog
            last_altitude_m = alt
            
            car_ctrl.update(lat, lon, cog)
            ui.car_marker = car_ctrl.marker
            
            try:
                ui.vars['altitude_display_var'].set(f"Altitude: {alt:.1f} m")
            except:
                pass
            
            current_speed = simulator.speed_kmh if simulator else 0.0
            try:
                ui.vars['speed_display_var'].set(f"ความเร็วปัจจุบัน: {current_speed:.0f} km/h")
                ui.vars['speed_big_var'].set(f"{int(round(current_speed))}")
            except Exception:
                pass
            
            try:
                # Update travel time every 1 second or if speed changes significantly
                now_ms = int(time.time() * 1000)
                if not hasattr(schedule_move, "_last_time_update"):
                    schedule_move._last_time_update = 0
                
                should_update = False
                if now_ms - schedule_move._last_time_update >= 1000:
                    should_update = True
                
                if not hasattr(schedule_move, "_last_speed"):
                    schedule_move._last_speed = None
                if schedule_move._last_speed is None or abs(current_speed - schedule_move._last_speed) >= 0.1:
                    schedule_move._last_speed = current_speed
                    should_update = True

                if should_update:
                    schedule_move._last_time_update = now_ms
                    update_travel_time()
            except Exception:
                pass
        app.after(step_ms, schedule_move)

    def schedule_log():
        nonlocal simulator
        if not is_app_running:
            return
        if not simulator or not simulator.running:
            return
        log_lat = current_lat
        log_lon = current_lon
        if ui.car_marker and getattr(ui.car_marker, "position", None):
            try:
                pos = ui.car_marker.position
                log_lat, log_lon = float(pos[0]), float(pos[1])
            except Exception:
                pass
        try:
            if not simulator or not simulator.running:
                executor.submit(update_alt_async, log_lat, log_lon)
        except Exception:
            pass
        app.after(get_interval_ms(), schedule_log)

    def schedule_nmea():
        nonlocal simulator
        if not is_app_running:
            return
        if not simulator or not simulator.running:
            return
        ts = get_sim_time_utc()
        nmea_lat = current_lat
        nmea_lon = current_lon
        if ui.car_marker and getattr(ui.car_marker, "position", None):
            try:
                pos = ui.car_marker.position
                nmea_lat, nmea_lon = float(pos[0]), float(pos[1])
            except Exception:
                pass
        
        try:
            if not simulator or not simulator.running:
                executor.submit(update_alt_async, nmea_lat, nmea_lon)
        except Exception:
            pass
        
        alt_m = last_altitude_m
        spd_kmh = float(getattr(simulator, "speed_kmh", 0.0))
        try:
            sv_total = int(ui.vars['sat_total_var'].get()) if str(ui.vars['sat_total_var'].get()).strip() else 0
        except Exception:
            sv_total = 0
        try:
            sv_gps = int(ui.vars['sat_gps_var'].get()) if str(ui.vars['sat_gps_var'].get()).strip() else 0
        except Exception:
            sv_gps = 0
        try:
            sv_glonass = int(ui.vars['sat_glonass_var'].get()) if str(ui.vars['sat_glonass_var'].get()).strip() else 0
        except Exception:
            sv_glonass = 0
            
        gngns = format_gngns(ts, nmea_lat, nmea_lon, "A", sv_total, 0.0, alt_m)
        gprmc = format_gprmc(ts, nmea_lat, nmea_lon, spd_kmh, current_cog)
        gnrmc = format_gnrmc(ts, nmea_lat, nmea_lon, spd_kmh, current_cog)
        gpgga = format_gpgga(ts, nmea_lat, nmea_lon, 1, sv_total, 0.0, alt_m, 0.0)
        gpsacp = format_gpsacp(ts, nmea_lat, nmea_lon, spd_kmh, current_cog, alt_m, sv_gps, sv_glonass)
        
        # Check enabled NMEA
        do_gngns = True
        do_gprmc = True
        do_gnrmc = True
        do_gpgga = True
        do_gpsacp = True
        try:
             do_gngns = ui.vars['send_gngns'].get()
             do_gprmc = ui.vars['send_gprmc'].get()
             do_gnrmc = ui.vars['send_gnrmc'].get()
             do_gpgga = ui.vars['send_gpgga'].get()
             do_gpsacp = ui.vars['send_gpsacp'].get()
        except Exception:
             pass

        nmea_list = []
        if do_gngns: nmea_list.append(gngns)
        if do_gprmc: nmea_list.append(gprmc)
        if do_gnrmc: nmea_list.append(gnrmc)
        if do_gpgga: nmea_list.append(gpgga)
        if do_gpsacp: nmea_list.append(gpsacp)

        try:
            for n in nmea_list:
                print(f"NMEA: {n}")
        except Exception:
            pass

        if serial_conn and serial_conn.is_open and nmea_list:
            try:
                data = "\r\n".join(nmea_list) + "\r\n"
                serial_conn.write(data.encode('ascii'))
            except Exception as e:
                print(f"Serial Write Error: {e}")

        try:
            now_ms = int(time.time() * 1000.0)
            if not hasattr(schedule_nmea, "_last_log_ms"):
                schedule_nmea._last_log_ms = 0
            if now_ms - schedule_nmea._last_log_ms >= get_log_interval_ms():
                schedule_nmea._last_log_ms = now_ms
                for n in nmea_list:
                    ui.log(f"{n}")
                ui.log("-------------------------")
        except Exception:
            pass
        app.after(get_interval_ms(), schedule_nmea)

    callbacks.update({
        'geocode': geocode_to_var,
        'on_speed_changed': on_speed_changed,
        'toggle_serial': toggle_serial,
        'start_sim': start_sim,
        'stop_sim': stop_sim,
        'clear_all': clear_all,
        'brake': brake_now,
        'start_go': start_go,
        'emergency_brake': emergency_brake_now,
        'boost_start': boost_start_now,
    })
    
    # Setup Map Commands
    ui.set_map_center(15.8700, 100.9925, zoom=6)
    ui.mapw.add_left_click_map_command(lambda c: None)
    try:
        ui.mapw.add_right_click_menu_command(label="ตั้ง start ที่นี่", command=set_start_at, pass_coords=True)
        ui.mapw.add_right_click_menu_command(label="ตั้ง end ที่นี่", command=set_end_at, pass_coords=True)
        ui.mapw.add_right_click_menu_command(label="เพิ่มจุดผ่าน", command=add_pass_through_at, pass_coords=True)
        ui.mapw.add_right_click_menu_command(label="ลบจุดผ่านล่าสุด", command=lambda: remove_last_pass_through(), pass_coords=False)
        ui.mapw.add_right_click_menu_command(label="ล้างจุดผ่านทั้งหมด", command=lambda: clear_all_pass_through(), pass_coords=False)
        ui.mapw.add_right_click_menu_command(label="เริ่มช่วงความเร็วที่นี่", command=on_speed_zone_start, pass_coords=True)
        ui.mapw.add_right_click_menu_command(label="สิ้นสุดช่วงความเร็วที่นี้", command=on_speed_zone_end, pass_coords=True)
    except Exception:
        pass
    
    ui.apply_map_font()

    def on_closing():
        nonlocal is_app_running
        is_app_running = False
        try:
            cfg = {
                "start": ui.vars['start_var'].get(),
                "end": "",
                "speed": ui.vars['speed_var'].get(),
                "hz": ui.vars['hz_var'].get(),
                "log_sec": ui.vars['log_sec_var'].get(),
                "base_date": ui.vars['base_date_var'].get(),
                "base_clock": ui.vars['base_clock_var'].get(),
                "base_time": (str(ui.vars['base_date_var'].get()).strip() + " " + str(ui.vars['base_clock_var'].get()).strip()).strip(),
                "time_mode": ui.vars['time_mode_var'].get(),
                "sat_total": ui.vars['sat_total_var'].get(),
                "serial_port": ui.vars['serial_port_var'].get(),
                "serial_baud": ui.vars['serial_baud_var'].get(),
                "send_gngns": ui.vars['send_gngns'].get(),
                "send_gprmc": ui.vars['send_gprmc'].get(),
                "send_gnrmc": ui.vars['send_gnrmc'].get(),
                "send_gpgga": ui.vars['send_gpgga'].get(),
                "send_gpsacp": ui.vars['send_gpsacp'].get()
            }
            save_config_file(cfg)
        except Exception:
            pass

        try:
            if simulator:
                simulator.stop()
        except:
            pass
            
        try:
            executor.shutdown(wait=False)
        except:
            pass
            
        try:
            if serial_conn and serial_conn.is_open:
                serial_conn.close()
        except:
            pass
        
        try:
            app.quit()
            app.destroy()
        except:
            pass

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true")
    p.add_argument("--start", type=str, default="")
    p.add_argument("--end", type=str, default="")
    p.add_argument("--waypoint", type=str, nargs="*", default=[])
    p.add_argument("--speed", type=float, default=60.0)
    p.add_argument("--ticks", type=int, default=12)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.headless:
        run_headless(args)
    else:
        main_gui()
