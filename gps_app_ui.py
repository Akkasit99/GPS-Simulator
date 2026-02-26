import customtkinter as ctk
import tkinter as tk
from tkintermapview import TkinterMapView
import datetime

class GPSAppUI:
    def __init__(self, parent, callbacks):
        self.parent = parent
        self.callbacks = callbacks
        self.vars = {}
        self.init_vars()
        self.car_marker = None
        self.markers = {"start": None, "end": None, "wps": []}
        self.zone_markers = {"start": [], "end": []}
        self.setup_ui()

    def init_vars(self):
        self.vars['start_var'] = ctk.StringVar()
        self.vars['end_var'] = ctk.StringVar()
        self.vars['speed_var'] = ctk.StringVar(value="60")
        self.vars['hz_var'] = ctk.StringVar(value="1")
        self.vars['log_sec_var'] = ctk.StringVar(value="10")
        self.vars['base_date_var'] = ctk.StringVar(value="")
        self.vars['base_clock_var'] = ctk.StringVar(value="")
        self.vars['time_mode_var'] = ctk.StringVar(value="machine")
        self.vars['map_style_var'] = ctk.StringVar(value="ปกติ")
        self.vars['map_satellite_var'] = ctk.StringVar(value="off")
        self.vars['sat_total_var'] = ctk.StringVar(value="8")
        self.vars['sat_gps_var'] = ctk.StringVar(value="5")
        self.vars['sat_glonass_var'] = ctk.StringVar(value="3")
        self.vars['distance_var'] = ctk.StringVar(value="ระยะทางรวม: -")
        self.vars['speed_zone_info_var'] = ctk.StringVar(value="ระยะช่วงความเร็ว: -")
        self.vars['travel_time_var'] = ctk.StringVar(value="เวลาเดินทางโดยประมาณ: -")
        self.vars['eta_display_var'] = ctk.StringVar(value="คาดว่าจะถึง: -")
        self.vars['start_time_display_var'] = ctk.StringVar(value="เริ่ม: -")
        self.vars['altitude_display_var'] = ctk.StringVar(value="Altitude: - m")
        self.vars['serial_port_var'] = ctk.StringVar()
        self.vars['serial_baud_var'] = ctk.StringVar(value="115200")
        self.vars['serial_status_var'] = ctk.StringVar(value="Status: Disconnected")
        self.vars['speed_display_var'] = ctk.StringVar(value="Speed: 0.0 km/h")
        self.vars['speed_big_var'] = ctk.StringVar(value="0")
        self.vars['mode_var'] = ctk.StringVar(value="none")
        self.vars['send_gngns'] = ctk.BooleanVar(value=True)
        self.vars['send_gprmc'] = ctk.BooleanVar(value=True)
        self.vars['send_gnrmc'] = ctk.BooleanVar(value=True)
        self.vars['send_gpgga'] = ctk.BooleanVar(value=True)
        self.vars['send_gpsacp'] = ctk.BooleanVar(value=True)

    def setup_ui(self):
        # Configure Grid
        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

        # Split: Left (Controls) / Right (Map)
        self.split = tk.PanedWindow(self.parent, orient="horizontal", sashwidth=4, bg="#2C3E50")
        self.split.pack(fill="both", expand=True)

        left_width = 400
        self.left = ctk.CTkFrame(self.split, width=left_width, corner_radius=0)
        self.right = ctk.CTkFrame(self.split)
        
        self.split.add(self.left, minsize=left_width)
        self.split.add(self.right, minsize=300)

        self.create_left_panel()
        self.create_right_panel()

    def create_left_panel(self):
        self.left.grid_rowconfigure(0, weight=1)
        self.left.grid_columnconfigure(0, weight=1)

        self.left_scroll = ctk.CTkScrollableFrame(self.left, corner_radius=0, width=int(self.left.cget("width")))
        self.left_scroll.grid(row=0, column=0, sticky="nsew")

        # Header
        ctk.CTkLabel(self.left_scroll, text="แผงควบคุม GPS Simulator", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=10, pady=(15, 10))

        # 1. Route Configuration
        self.create_route_config()

        # 2. Simulation Settings
        self.create_sim_settings()

        # 3. Connection (Serial)
        self.create_connection_settings()
        
        # 3.5 NMEA Selection
        self.create_nmea_settings()

        # 4. Action Buttons
        self.create_action_buttons()

    def create_route_config(self):
        route_frame = ctk.CTkFrame(self.left_scroll)
        route_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(route_frame, text="ตั้งค่าเส้นทาง", font=ctk.CTkFont(weight="bold")).pack(padx=10, pady=(5,0), anchor="w")
        
        # Start Row
        start_row = ctk.CTkFrame(route_frame, fg_color="transparent")
        start_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(start_row, text="จุดเริ่ม:", width=40).pack(side="left")
        start_entry = ctk.CTkEntry(start_row, textvariable=self.vars['start_var'])
        start_entry.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(start_row, text="ค้นหา", width=60, command=lambda: self.callbacks['geocode'](self.vars['start_var'], "Start")).pack(side="left")

        # End Row
        end_row = ctk.CTkFrame(route_frame, fg_color="transparent")
        end_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(end_row, text="ปลายทาง:", width=40).pack(side="left")
        end_entry = ctk.CTkEntry(end_row, textvariable=self.vars['end_var'])
        end_entry.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(end_row, text="ค้นหา", width=60, command=lambda: self.callbacks['geocode'](self.vars['end_var'], "End")).pack(side="left")

    def create_sim_settings(self):
        sim_frame = ctk.CTkFrame(self.left_scroll)
        sim_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(sim_frame, text="ตั้งค่าการจำลอง", font=ctk.CTkFont(weight="bold")).pack(padx=10, pady=(5,0), anchor="w")

        # Speed Row
        speed_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        speed_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(speed_row, text="ความเร็ว (km/h):").pack(side="left", padx=5)
        speed_entry = ctk.CTkEntry(speed_row, textvariable=self.vars['speed_var'], width=100)
        speed_entry.pack(side="left", padx=5)
        
        # Bind speed entry
        speed_entry.bind("<Return>", lambda e: self.callbacks['on_speed_changed']())
        
        def on_slider_change(v):
            try:
                self.vars['speed_var'].set(f"{float(v):.0f}")
            except Exception:
                pass
                
        self.speed_slider = ctk.CTkSlider(sim_frame, from_=0, to=200, command=on_slider_change)
        self.speed_slider.pack(fill="x", padx=10, pady=(2,6))

        # Dashboard
        dash_frame = ctk.CTkFrame(sim_frame, corner_radius=12)
        dash_frame.pack(fill="x", padx=10, pady=(0,4))
        dash_frame.grid_columnconfigure(0, weight=1)
        dash_frame.grid_columnconfigure(1, weight=0)
        
        ctk.CTkLabel(dash_frame, textvariable=self.vars['speed_big_var'], font=ctk.CTkFont(size=56, weight="bold")).grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(dash_frame, text="km/h", font=ctk.CTkFont(size=20)).grid(row=0, column=1, sticky="e", padx=8, pady=4)
        ctk.CTkLabel(sim_frame, textvariable=self.vars['speed_display_var'], font=ctk.CTkFont(size=14, weight="bold")).pack(padx=10, pady=(0,4), anchor="w")

        # Altitude
        alt_frame = ctk.CTkFrame(sim_frame, corner_radius=12, fg_color="#2C3E50")
        alt_frame.pack(fill="x", padx=10, pady=(0,4))
        ctk.CTkLabel(alt_frame, textvariable=self.vars['altitude_display_var'], font=ctk.CTkFont(size=18, weight="bold"), text_color="#ECF0F1").pack(padx=10, pady=5)

        # Hz Control
        hz_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        hz_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(hz_row, text="ส่งข้อมูล (Hz):").pack(side="left", padx=5)
        ctk.CTkLabel(hz_row, textvariable=self.vars['hz_var'], width=30).pack(side="left", padx=2)
        
        def on_hz_slider(v):
            self.vars['hz_var'].set(f"{int(v)}")
        
        hz_slider = ctk.CTkSlider(hz_row, from_=1, to=10, number_of_steps=9, command=on_hz_slider)
        try:
            hz_slider.set(int(self.vars['hz_var'].get()))
        except:
            hz_slider.set(1)
        hz_slider.pack(side="left", fill="x", expand=True, padx=5)

        # Log Interval
        log_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        log_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(log_row, text="เวลา Log (วินาที):").pack(side="left", padx=5)
        ctk.CTkLabel(log_row, textvariable=self.vars['log_sec_var'], width=30).pack(side="left", padx=2)
        
        def on_log_slider(v):
            self.vars['log_sec_var'].set(f"{int(v)}")
            
        log_slider = ctk.CTkSlider(log_row, from_=1, to=60, number_of_steps=59, command=on_log_slider)
        try:
            log_slider.set(int(float(self.vars['log_sec_var'].get())))
        except:
            log_slider.set(10)
        log_slider.pack(side="left", fill="x", expand=True, padx=5)

        mode_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(mode_row, text="โหมดเวลา:").pack(side="left", padx=5)

        self.base_time_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        ctk.CTkLabel(self.base_time_row, text="เริ่มส่ง:").pack(side="left", padx=5)

        def open_date_picker():
            top = ctk.CTkToplevel(self.parent)
            top.title("เลือกวันที่")
            top.resizable(False, False)
            top.transient(self.parent)
            top.grab_set()

            try:
                top.attributes("-topmost", True)
                top.after(200, lambda: top.attributes("-topmost", False))
            except Exception:
                pass

            container = ctk.CTkFrame(top, fg_color="white", border_color="black", border_width=2, corner_radius=0)
            container.pack(fill="both", expand=True, padx=10, pady=10)

            today = datetime.date.today()

            def parse_current_date():
                s = str(self.vars.get("base_date_var").get()).strip()
                try:
                    return datetime.datetime.strptime(s, "%d/%m/%Y").date()
                except Exception:
                    return today

            current = parse_current_date()
            if current > today:
                current = today
            state = {"year": current.year, "month": current.month}

            header = ctk.CTkFrame(container, fg_color="white")
            header.pack(fill="x", padx=10, pady=(10, 6))

            btn_style = {
                "fg_color": "white",
                "hover_color": "#f0f0f0",
                "text_color": "black",
                "border_color": "black",
                "border_width": 1,
                "corner_radius": 10,
            }

            month_names = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

            combo_style = {
                "fg_color": "white",
                "text_color": "black",
                "border_color": "black",
                "border_width": 1,
                "button_color": "#f0f0f0",
                "button_hover_color": "#e6e6e6",
                "dropdown_fg_color": "white",
                "dropdown_text_color": "black",
                "dropdown_hover_color": "#f0f0f0",
            }

            def allowed_month_values(y: int):
                if int(y) == int(today.year):
                    return month_names[: int(today.month)]
                return month_names

            years = [str(y) for y in range(int(today.year) - 20, int(today.year) + 1)]

            ctk.CTkLabel(header, text="เดือน", text_color="black").pack(side="left", padx=(6, 6))
            month_cb = ctk.CTkComboBox(header, values=allowed_month_values(int(state["year"])), width=120, **combo_style)
            month_cb.pack(side="left", padx=(0, 10), pady=2)
            ctk.CTkLabel(header, text="ปี", text_color="black").pack(side="left", padx=(0, 6))
            year_cb = ctk.CTkComboBox(header, values=years, width=110, **combo_style)
            year_cb.pack(side="left", padx=(0, 6), pady=2)

            suppress_callbacks = {"value": False}

            def clamp_state(year: int, month: int):
                min_year = int(today.year) - 20
                y = max(min_year, min(int(today.year), int(year)))
                m = max(1, min(12, int(month)))
                if y == int(today.year):
                    m = min(int(today.month), m)
                allowed = allowed_month_values(y)
                if month_names[m - 1] not in allowed:
                    m = int(len(allowed))
                state["year"] = y
                state["month"] = m

            def sync_controls():
                suppress_callbacks["value"] = True
                try:
                    year_cb.set(str(int(state["year"])))
                    allowed = allowed_month_values(int(state["year"]))
                    month_cb.configure(values=allowed)
                    month_cb.set(month_names[int(state["month"]) - 1])
                finally:
                    suppress_callbacks["value"] = False

            def on_year_selected(value=None):
                if suppress_callbacks["value"]:
                    return
                raw = str(value if value is not None else year_cb.get()).strip()
                try:
                    y = int(raw)
                except Exception:
                    y = int(state["year"])
                clamp_state(y, int(state["month"]))
                sync_controls()
                draw_days()

            def on_month_selected(value=None):
                if suppress_callbacks["value"]:
                    return
                raw = str(value if value is not None else month_cb.get()).strip()
                if raw in month_names:
                    m = month_names.index(raw) + 1
                else:
                    m = int(state["month"])
                clamp_state(int(state["year"]), m)
                sync_controls()
                draw_days()

            try:
                year_cb.configure(command=on_year_selected)
                month_cb.configure(command=on_month_selected)
            except Exception:
                pass

            try:
                year_cb.configure(state="readonly")
                month_cb.configure(state="readonly")
            except Exception:
                pass

            clamp_state(int(state["year"]), int(state["month"]))
            sync_controls()

            grid = ctk.CTkFrame(container, fg_color="white")
            grid.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            dow = ctk.CTkFrame(grid, fg_color="white")
            dow.pack(fill="x", pady=(0, 6))
            for name in ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"]:
                ctk.CTkLabel(dow, text=name, width=44, text_color="black").pack(side="left")

            days = ctk.CTkFrame(grid, fg_color="white")
            days.pack(fill="both", expand=True)

            footer = ctk.CTkFrame(container, fg_color="white")
            footer.pack(fill="x", padx=10, pady=(0, 10))

            def close():
                try:
                    top.grab_release()
                except Exception:
                    pass
                top.destroy()

            def pick(d: int):
                try:
                    dt = datetime.date(int(state["year"]), int(state["month"]), int(d))
                    if dt > today:
                        return
                    self.vars["base_date_var"].set(dt.strftime("%d/%m/%Y"))
                except Exception:
                    pass
                close()

            def pick_today():
                try:
                    self.vars["base_date_var"].set(today.strftime("%d/%m/%Y"))
                except Exception:
                    pass
                close()

            ctk.CTkButton(footer, text="วันนี้", width=140, command=pick_today, **btn_style).pack(side="left")
            ctk.CTkButton(footer, text="ปิด", width=140, command=close, **btn_style).pack(side="right")

            def draw_days():
                for w in days.winfo_children():
                    try:
                        w.destroy()
                    except Exception:
                        pass

                y, m = int(state["year"]), int(state["month"])
                first = datetime.date(y, m, 1)
                start_col = int(first.weekday())
                if m == 12:
                    next_month = datetime.date(y + 1, 1, 1)
                else:
                    next_month = datetime.date(y, m + 1, 1)
                num_days = int((next_month - first).days)

                row = 0
                col = 0
                for _ in range(start_col):
                    ctk.CTkLabel(days, text="", width=44).grid(row=row, column=col, padx=3, pady=3)
                    col += 1

                for d in range(1, num_days + 1):
                    try:
                        dd = datetime.date(y, m, d)
                        is_future = dd > today
                    except Exception:
                        is_future = False
                    b = ctk.CTkButton(days, text=str(d), width=44, height=32, command=lambda dd=d: pick(dd), **btn_style)
                    if is_future:
                        try:
                            b.configure(state="disabled", fg_color="#f2f2f2", hover_color="#f2f2f2", text_color="#888888", border_color="#cccccc")
                        except Exception:
                            pass
                    b.grid(row=row, column=col, padx=3, pady=3)
                    col += 1
                    if col >= 7:
                        col = 0
                        row += 1

            draw_days()

        self.base_date_entry = ctk.CTkEntry(self.base_time_row, textvariable=self.vars['base_date_var'], width=120)
        self.base_date_entry.pack(side="left", padx=(5, 4))
        ctk.CTkButton(
            self.base_time_row,
            text="เลือก",
            width=60,
            fg_color="white",
            hover_color="#f0f0f0",
            text_color="black",
            border_color="black",
            border_width=1,
            command=open_date_picker,
        ).pack(side="left", padx=(0, 6))
        self.base_clock_hour_var = ctk.StringVar(value="00")
        self.base_clock_minute_var = ctk.StringVar(value="00")

        hour_values = [f"{h:02d}" for h in range(24)]
        minute_values = [f"{m:02d}" for m in range(60)]

        self.base_clock_hour_cb = ctk.CTkComboBox(self.base_time_row, values=hour_values, variable=self.base_clock_hour_var, width=62)
        self.base_clock_hour_cb.pack(side="left", padx=(4, 2))
        ctk.CTkLabel(self.base_time_row, text=":").pack(side="left", padx=0)
        self.base_clock_minute_cb = ctk.CTkComboBox(self.base_time_row, values=minute_values, variable=self.base_clock_minute_var, width=62)
        self.base_clock_minute_cb.pack(side="left", padx=(2, 5))

        def set_base_clock_from_picker():
            if getattr(set_base_clock_from_picker, "_busy", False):
                return
            try:
                set_base_clock_from_picker._busy = True
                hh = str(self.base_clock_hour_var.get()).strip()
                mm = str(self.base_clock_minute_var.get()).strip()
                if hh in hour_values and mm in minute_values:
                    self.vars['base_clock_var'].set(f"{hh}.{mm}")
            finally:
                set_base_clock_from_picker._busy = False

        def sync_clock_picker_from_var():
            if getattr(sync_clock_picker_from_var, "_busy", False):
                return
            try:
                sync_clock_picker_from_var._busy = True
                t = str(self.vars['base_clock_var'].get()).strip()
                t = t.replace(":", ".")
                parts = [p for p in t.split(".") if p != ""]
                hh = parts[0] if len(parts) >= 1 else ""
                mm = parts[1] if len(parts) >= 2 else ""
                if hh.isdigit():
                    hh = f"{int(hh):02d}"
                if mm.isdigit():
                    mm = f"{int(mm):02d}"
                if hh in hour_values:
                    self.base_clock_hour_var.set(hh)
                if mm in minute_values:
                    self.base_clock_minute_var.set(mm)
            finally:
                sync_clock_picker_from_var._busy = False

        try:
            self.base_clock_hour_var.trace_add("write", lambda *_: set_base_clock_from_picker())
            self.base_clock_minute_var.trace_add("write", lambda *_: set_base_clock_from_picker())
        except Exception:
            pass
        try:
            self.vars['base_clock_var'].trace_add("write", lambda *_: sync_clock_picker_from_var())
        except Exception:
            pass
        sync_clock_picker_from_var()

        def update_time_controls():
            mode = str(self.vars.get('time_mode_var').get() if self.vars.get('time_mode_var') else "machine").strip().lower()
            if mode == "machine":
                try:
                    if self.base_time_row.winfo_manager():
                        self.base_time_row.pack_forget()
                except Exception:
                    pass
                return

            if not self.base_time_row.winfo_manager():
                try:
                    self.base_time_row.pack(after=mode_row, fill="x", padx=5, pady=2)
                except Exception:
                    self.base_time_row.pack(fill="x", padx=5, pady=2)

            try:
                d = str(self.vars['base_date_var'].get()).strip()
            except Exception:
                d = ""
            try:
                t = str(self.vars['base_clock_var'].get()).strip()
            except Exception:
                t = ""
            if not d or not t:
                try:
                    import datetime
                    now = datetime.datetime.now()
                    if not d:
                        self.vars['base_date_var'].set(now.strftime("%d/%m/%Y"))
                    if not t:
                        self.vars['base_clock_var'].set(now.strftime("%H.%M"))
                except Exception:
                    pass

        ctk.CTkSwitch(
            mode_row,
            text="ใช้เวลาเครื่อง",
            variable=self.vars['time_mode_var'],
            onvalue="machine",
            offvalue="manual",
            command=update_time_controls,
        ).pack(side="left", padx=5)
        try:
            self.vars['time_mode_var'].trace_add("write", lambda *_: update_time_controls())
        except Exception:
            pass
        update_time_controls()

        map_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        map_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(map_row, text="แผนที่:").pack(side="left", padx=5)
        try:
            curr_map_style = str(self.vars["map_style_var"].get()).strip()
        except Exception:
            curr_map_style = ""
        if curr_map_style != "ปกติ":
            self.vars["map_style_var"].set("ปกติ")
        ctk.CTkSwitch(
            map_row,
            text="ดาวเทียมมีชื่อ",
            variable=self.vars["map_satellite_var"],
            onvalue="on",
            offvalue="off",
            command=lambda: self.apply_map_style(self.vars.get("map_style_var").get() if self.vars.get("map_style_var") else "ปกติ"),
        ).pack(side="left", padx=5)
        try:
            self.vars["map_satellite_var"].trace_add(
                "write",
                lambda *_: self.apply_map_style(self.vars.get("map_style_var").get() if self.vars.get("map_style_var") else "ปกติ"),
            )
        except Exception:
            pass

        # Satellite Control
        sat_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        sat_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(sat_row, text="ดาวเทียมรวม:").pack(side="left", padx=5)
        ctk.CTkLabel(sat_row, textvariable=self.vars['sat_total_var'], width=30).pack(side="left", padx=2)

        def on_sat_slider(v):
            total = int(v)
            self.vars['sat_total_var'].set(str(total))
            gps = int(total * 0.6)
            glo = total - gps
            self.vars['sat_gps_var'].set(str(gps))
            self.vars['sat_glonass_var'].set(str(glo))

        self.sat_slider = ctk.CTkSlider(sat_row, from_=0, to=30, number_of_steps=30, command=on_sat_slider)
        try:
            self.sat_slider.set(int(self.vars['sat_total_var'].get()))
        except:
            self.sat_slider.set(8)
        self.sat_slider.pack(side="left", fill="x", expand=True, padx=5)

        # Satellite Detail Label
        sat_info_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        sat_info_row.pack(fill="x", padx=5, pady=0)
        ctk.CTkLabel(sat_info_row, text="(GPS:", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=(80,2))
        ctk.CTkLabel(sat_info_row, textvariable=self.vars['sat_gps_var'], text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=0)
        ctk.CTkLabel(sat_info_row, text="/ GLO:", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=2)
        ctk.CTkLabel(sat_info_row, textvariable=self.vars['sat_glonass_var'], text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=0)
        ctk.CTkLabel(sat_info_row, text=")", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=0)

        # Info Labels
        ctk.CTkLabel(sim_frame, textvariable=self.vars['distance_var']).pack(padx=10, pady=0, anchor="w")
        ctk.CTkLabel(sim_frame, textvariable=self.vars['speed_zone_info_var']).pack(padx=10, pady=0, anchor="w")
        ctk.CTkLabel(sim_frame, textvariable=self.vars['travel_time_var']).pack(padx=10, pady=0, anchor="w")
        ctk.CTkLabel(sim_frame, textvariable=self.vars['start_time_display_var']).pack(padx=10, pady=0, anchor="w")
        ctk.CTkLabel(sim_frame, textvariable=self.vars['eta_display_var']).pack(padx=10, pady=0, anchor="w")
        ctk.CTkLabel(sim_frame, text="* คลิกขวาที่แผนที่เพื่อเพิ่มจุดแวะ/ความเร็ว", font=ctk.CTkFont(size=11), text_color="gray").pack(padx=10, pady=(0,5), anchor="w")

    def create_connection_settings(self):
        conn_frame = ctk.CTkFrame(self.left_scroll)
        conn_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(conn_frame, text="การเชื่อมต่อ Serial", font=ctk.CTkFont(weight="bold")).pack(padx=10, pady=(5,0), anchor="w")
        
        serial_row = ctk.CTkFrame(conn_frame, fg_color="transparent")
        serial_row.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(serial_row, text="COM:", width=40).pack(side="left")
        
        ports = self.callbacks['get_ports']()
        self.port_cb = ctk.CTkComboBox(serial_row, values=ports if ports else ["No Ports"], variable=self.vars['serial_port_var'], width=100)
        self.port_cb.pack(side="left", padx=2)
        try:
            self.port_cb.bind("<Button-1>", lambda _e: self.refresh_ports())
            self.port_cb.bind("<FocusIn>", lambda _e: self.refresh_ports())
        except Exception:
            pass
        self.start_port_auto_refresh()
        
        ctk.CTkLabel(serial_row, text="Baud:").pack(side="left", padx=(5, 2))
        ctk.CTkComboBox(serial_row, values=["9600", "115200", "38400"], variable=self.vars['serial_baud_var'], width=80).pack(side="left", padx=2)
        
        self.serial_btn = ctk.CTkButton(conn_frame, text="เชื่อมต่อ", fg_color="#3498DB", command=lambda: self.callbacks['toggle_serial']())
        self.serial_btn.pack(padx=10, pady=5, fill="x")
        
        self.serial_status_lbl = ctk.CTkLabel(conn_frame, textvariable=self.vars['serial_status_var'], font=ctk.CTkFont(size=11))
        self.serial_status_lbl.pack(padx=10, pady=(0,5), anchor="w")

    def create_nmea_settings(self):
        nmea_frame = ctk.CTkFrame(self.left_scroll)
        nmea_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(nmea_frame, text="เลือกข้อมูล NMEA ที่จะส่ง", font=ctk.CTkFont(weight="bold")).pack(padx=10, pady=(5,0), anchor="w")

        grid = ctk.CTkFrame(nmea_frame, fg_color="transparent")
        grid.pack(fill="x", padx=5, pady=2)
        
        ctk.CTkCheckBox(grid, text="GNGNS", variable=self.vars['send_gngns']).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ctk.CTkCheckBox(grid, text="GPRMC", variable=self.vars['send_gprmc']).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ctk.CTkCheckBox(grid, text="GNRMC", variable=self.vars['send_gnrmc']).grid(row=0, column=2, padx=5, pady=2, sticky="w")
        ctk.CTkCheckBox(grid, text="GPGGA", variable=self.vars['send_gpgga']).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        ctk.CTkCheckBox(grid, text="GPSACP", variable=self.vars['send_gpsacp']).grid(row=1, column=1, padx=5, pady=2, sticky="w")

    def create_action_buttons(self):
        action_frame = ctk.CTkFrame(self.left_scroll, fg_color="transparent")
        action_frame.pack(padx=10, pady=5, fill="x")
        action_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        ctk.CTkButton(action_frame, text="START", fg_color="#2ECC71", hover_color="#27AE60", command=lambda: self.callbacks['start_sim']()).grid(row=0, column=0, padx=2, sticky="ew")
        ctk.CTkButton(action_frame, text="STOP", fg_color="#E74C3C", hover_color="#D62C1A", command=lambda: self.callbacks['stop_sim']()).grid(row=0, column=1, padx=2, sticky="ew")
        ctk.CTkButton(action_frame, text="CLEAR", fg_color="#F5A327", hover_color="#7F8C8D", command=lambda: self.callbacks['clear_all']()).grid(row=0, column=2, padx=2, sticky="ew")
        
        ctk.CTkButton(action_frame, text="เบรก", fg_color="#C0392B", hover_color="#A93226", command=lambda: self.callbacks['brake']()).grid(row=1, column=0, padx=2, pady=(6,0), sticky="ew")
        ctk.CTkButton(action_frame, text="ออกรถ", fg_color="#3498DB", hover_color="#2980B9", command=lambda: self.callbacks['start_go']()).grid(row=1, column=1, padx=2, pady=(6,0), sticky="ew")
        
        ctk.CTkButton(action_frame, text="เบรกฉุกเฉิน)", fg_color="#922B21", hover_color="#7B241C", command=lambda: self.callbacks['emergency_brake']()).grid(row=2, column=0, padx=2, pady=(6,0), sticky="ew")
        ctk.CTkButton(action_frame, text="ออกตัวพุ่ง)", fg_color="#1F618D", hover_color="#1A5276", command=lambda: self.callbacks['boost_start']()).grid(row=2, column=1, padx=2, pady=(6,0), sticky="ew")

    def create_right_panel(self):
        # Vertical Split: Map (Top) / Log (Bottom)
        self.right_split = tk.PanedWindow(self.right, orient="vertical", sashwidth=4, bg="#2C3E50")
        self.right_split.pack(fill="both", expand=True)

        # Map Container (Top)
        self.map_container = ctk.CTkFrame(self.right_split, corner_radius=0, fg_color="transparent")
        self.right_split.add(self.map_container, stretch="always")

        # Log Container (Bottom)
        self.log_frame = ctk.CTkFrame(self.right_split, corner_radius=0)
        self.right_split.add(self.log_frame, minsize=30, stretch="never", height=180)

        # Map
        self.mapw = TkinterMapView(self.map_container, corner_radius=0)
        self.mapw.pack(fill="both", expand=True)
        self.apply_map_style(self.vars.get("map_style_var").get() if self.vars.get("map_style_var") else "ปกติ")

        # Log Header
        log_hdr = ctk.CTkFrame(self.log_frame, height=24, fg_color="transparent")
        log_hdr.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(log_hdr, text="Simulation Log", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        
        self.log_expanded = True
        self.toggle_btn = ctk.CTkButton(log_hdr, text="Hide", width=50, height=20, fg_color="#F58F00", hover_color="#D97E00", command=self.toggle_log_display)
        self.toggle_btn.pack(side="right")
        
        # LogBox
        self.logbox = ctk.CTkTextbox(self.log_frame, height=140)
        self.logbox.pack(fill="both", expand=True, padx=5, pady=(0,5))
        self.logbox.configure(state="disabled")

    def apply_map_style(self, style: str):
        s = str(style or "").strip()
        satellite_on = False
        try:
            satellite_on = str(self.vars.get("map_satellite_var").get()).strip().lower() == "on"
        except Exception:
            satellite_on = False

        if satellite_on:
            url = "https://mt0.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}"
            overlay_url = None
            max_zoom = 22
        else:
            url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            overlay_url = None
            max_zoom = 22

        try:
            if not hasattr(self, "mapw") or self.mapw is None:
                return
            self.mapw.set_tile_server(url, max_zoom=max_zoom)
            try:
                if hasattr(self.mapw, "set_overlay_tile_server"):
                    self.mapw.set_overlay_tile_server(overlay_url)
            except Exception:
                pass
        except Exception:
            pass

    def toggle_log_display(self):
        self.log_expanded = not self.log_expanded
        if self.log_expanded:
            self.logbox.pack(fill="both", expand=True, padx=5, pady=(0,5))
            self.log_frame.configure(height=180)
            self.toggle_btn.configure(text="Hide")
        else:
            self.logbox.pack_forget()
            self.log_frame.configure(height=30)
            self.toggle_btn.configure(text="Show")

    def refresh_ports(self):
        try:
            ports = self.callbacks['get_ports']()
            if not ports:
                ports = ["No Ports"]
            self.port_cb.configure(values=ports)
            
            curr = self.vars['serial_port_var'].get()
            if curr not in ports:
                self.vars['serial_port_var'].set(ports[0])
        except Exception:
            pass

    def start_port_auto_refresh(self):
        try:
            prev = getattr(self, "_port_auto_refresh_after_id", None)
            if prev is not None:
                try:
                    self.parent.after_cancel(prev)
                except Exception:
                    pass

            def tick():
                try:
                    if not self.parent.winfo_exists():
                        return
                except Exception:
                    return
                self.refresh_ports()
                try:
                    self._port_auto_refresh_after_id = self.parent.after(1500, tick)
                except Exception:
                    pass

            self._port_auto_refresh_after_id = self.parent.after(500, tick)
        except Exception:
            pass

    def update_speed_slider(self, val):
        try:
            self.speed_slider.set(val)
        except:
            pass

    def update_serial_btn(self, connected, port, baud):
        if connected:
            self.serial_btn.configure(text="ยกเลิกการเชื่อมต่อ", fg_color="#E74C3C", hover_color="#D62C1A")
            self.vars['serial_status_var'].set(f"เชื่อมต่อแล้ว: {port} @ {baud}")
            self.serial_status_lbl.configure(text_color="green")
        else:
            self.serial_btn.configure(text="เชื่อมต่อ", fg_color="#3498DB", hover_color="#2980B9")
            self.vars['serial_status_var'].set("สถานะ: ไม่ได้เชื่อมต่อ")
            self.serial_status_lbl.configure(text_color="gray")

    def set_serial_error(self, msg):
        self.vars['serial_status_var'].set(f"Error: {msg}...")
        self.serial_status_lbl.configure(text_color="red")

    def prompt_speed_input(self, title, text):
        from customtkinter import CTkInputDialog
        dlg = CTkInputDialog(title=title, text=text)
        return dlg.get_input()

    def apply_map_font(self):
        try:
            from tkinter import font as tkfont
            # Increase font size for right-click menu
            f = tkfont.Font(family="Sarabun", size=24, weight="bold")
            m = None
            # Attempt to find the menu widget in TkinterMapView
            for attr in ("right_click_menu", "_right_click_menu", "rc_menu", "menu_right_click"):
                mm = getattr(self.mapw, attr, None)
                if mm:
                    m = mm
                    break
            if m:
                try:
                    m.configure(font=f)
                    # Also try to configure entry font if possible, though standard Menu doesn't always support it easily
                except Exception:
                    pass
            else:
                # Retry if not found yet (sometimes init is delayed)
                self.parent.after(500, self.apply_map_font)
        except Exception:
            pass

    def log(self, message):
        try:
            self.logbox.configure(state="normal")
            self.logbox.insert("end", message + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        except Exception:
            pass

    def clear_map(self):
        self.mapw.delete_all_marker()
        self.mapw.delete_all_path()

    def set_map_center(self, lat, lon, zoom=None):
        self.mapw.set_position(lat, lon)
        if zoom is not None:
            self.mapw.set_zoom(zoom)

    def add_marker(self, lat, lon, text=None, icon=None):
        return self.mapw.set_marker(lat, lon, text=text, icon=icon)

    def draw_path(self, path_list):
        return self.mapw.set_path(path_list)

    def update_serial_btn(self, connected, port, baud):
        if connected:
            self.serial_btn.configure(text="Disconnect Serial", fg_color="#E74C3C", hover_color="#D62C1A")
            self.vars['serial_status_var'].set(f"Connected: {port} @ {baud}")
        else:
            self.serial_btn.configure(text="Connect Serial", fg_color="#3498DB", hover_color="#2980B9")
            self.vars['serial_status_var'].set("Status: Disconnected")

    def set_serial_error(self, msg):
        self.vars['serial_status_var'].set(f"Error: {msg}")
