import sys
import os
import glob
import time
import datetime
import multiprocessing
import threading
import math
import subprocess
import shutil
import customtkinter as ctk
from tkinter import messagebox, filedialog, Canvas
from PIL import Image, ImageTk

import IDF_Verifier
import sim_runner

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
    
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_BG = "#1A1A1A"
CARD_BG = "#242424"
TEXT_MAIN = "#EAEAEA"
TEXT_MUTED = "#888888"
ACCENT_BLUE = "#2980B9"
ACCENT_GREEN = "#27AE60"
ACCENT_RED = "#C0392B"
ACCENT_ORANGE = "#E67E22"

is_spinning = False
gear_angle = 0
base_gear_img = None
sim_start_time = 0

selected_idf = ""
weather_dir = os.path.join(os.getcwd(), "Weather_Files")
total_base_sims = 0

is_verified = False
are_inputs_valid = True
pause_event = None

active_cities = set()
city_hitboxes = {}

TIME_MAP = {
    "12:00 AM": 0, "1:00 AM": 1, "2:00 AM": 2, "3:00 AM": 3, 
    "4:00 AM": 4, "5:00 AM": 5, "6:00 AM": 6, "7:00 AM": 7, 
    "8:00 AM": 8, "9:00 AM": 9, "10:00 AM": 10, "11:00 AM": 11, 
    "12:00 PM": 12, "1:00 PM": 13, "2:00 PM": 14, "3:00 PM": 15, 
    "4:00 PM": 16, "5:00 PM": 17, "6:00 PM": 18, "7:00 PM": 19, 
    "8:00 PM": 20, "9:00 PM": 21, "10:00 PM": 22, "11:00 PM": 23, 
    "11:59 PM": 24
}

CITIES = {
    "resolute": (0.573, 0.146), "whitehorse": (0.303, 0.269),
    "edmonton": (0.411, 0.404), "calgary": (0.405, 0.446),
    "winnipeg": (0.551, 0.495), "seattle": (0.307, 0.492),
    "minneapolis": (0.591, 0.569), "chicago": (0.649, 0.61),
    "denver": (0.454, 0.634), "angeles": (0.295, 0.691),
    "phoenix": (0.368, 0.711), "houston": (0.566, 0.775),
    "miami": (0.768, 0.819),
}

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(tw, text=self.text, fg_color="#333333", corner_radius=6, padx=10, pady=5, text_color="white", font=ctk.CTkFont(size=12))
        label.pack()

    def leave(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

def calculate_eta(current, total):
    if current == 0:
        return "Calculating...", ""
    elapsed = time.time() - sim_start_time
    time_per_sim = elapsed / current
    remaining_sec = time_per_sim * (total - current)
    td = datetime.timedelta(seconds=int(remaining_sec))
    eta_time = (datetime.datetime.now() + td).strftime('%H:%M')
    return str(td), eta_time

def update_progress(current, total):
    def update_ui():
        progress_val = current / total
        progress_bar.set(progress_val)
        rem_str, eta_str = calculate_eta(current, total)
        lbl_status.configure(text=f"Status: Running... ({current}/{total})", text_color=ACCENT_BLUE)
        if current > 0:
            lbl_time.configure(text=f"Time Remaining: {rem_str}  |  ETA: {eta_str}")
    root.after(0, update_ui)

def spin_gear():
    global gear_angle, is_spinning, base_gear_img
    if is_spinning and base_gear_img:
        gear_angle = (gear_angle - 10) % 360
        rotated_img = base_gear_img.rotate(gear_angle)
        gear_ctk_img = ctk.CTkImage(light_image=rotated_img, dark_image=rotated_img, size=(30, 30))
        lbl_gear.configure(image=gear_ctk_img)
        lbl_gear.image = gear_ctk_img
        root.after(50, spin_gear)

def render_map():
    global city_hitboxes
    map_canvas.delete("all")
    city_hitboxes.clear()
    
    try:
        original_img = Image.open(resource_path("na_map.jpg"))
        img_w, img_h = original_img.size
        ratio = min(240 / img_w, 180 / img_h)
        draw_w, draw_h = int(img_w * ratio), int(img_h * ratio)
        bg_image = original_img.resize((draw_w, draw_h), Image.Resampling.LANCZOS)
        map_canvas.image = ImageTk.PhotoImage(bg_image)
        offset_x = (240 - draw_w) // 2
        offset_y = (180 - draw_h) // 2
        map_canvas.create_image(offset_x, offset_y, anchor="nw", image=map_canvas.image)
        
        for city, (rel_x, rel_y) in CITIES.items():
            x = int(rel_x * draw_w) + offset_x
            y = int(rel_y * draw_h) + offset_y
            r = 5 
            city_hitboxes[city] = (x, y)
            
            if city in active_cities:
                color = "#E74C3C" 
                outline = "#FFFFFF"
            else:
                color = "#555555" 
                outline = "#333333"
            map_canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline=outline, width=1)
    except Exception:
        map_canvas.create_rectangle(0, 0, 240, 180, fill="#1E1E1E", outline="#1E1E1E")
        map_canvas.create_text(120, 90, text="Map not found", fill=TEXT_MUTED)

def on_map_click(event):
    global active_cities
    for city, (cx, cy) in city_hitboxes.items():
        if math.hypot(event.x - cx, event.y - cy) < 10:
            if city in active_cities:
                active_cities.remove(city)
            else:
                active_cities.add(city)
            render_map()
            validate_inputs()
            update_button_state()
            break

def on_map_hover(event):
    map_canvas.delete("tooltip")
    map_canvas.delete("tooltip_bg")
    for city, (cx, cy) in city_hitboxes.items():
        if math.hypot(event.x - cx, event.y - cy) < 10:
            txt = city.title()
            bg_id = map_canvas.create_rectangle(event.x + 10, event.y - 20, event.x + 15 + len(txt)*8, event.y - 4, fill="#333333", outline="", tags="tooltip_bg")
            map_canvas.create_text(event.x + 15, event.y - 12, text=txt, fill="white", anchor="w", tags="tooltip", font=("Arial", 10, "bold"))
            break

def validate_inputs(*args):
    global are_inputs_valid
    are_inputs_valid = True
    
    def check_float_list(var, entry_widget):
        global are_inputs_valid
        try:
            items = [x for x in var.get().split(',') if x.strip()]
            if not items:
                raise ValueError
            for x in items:
                float(x.strip())
            entry_widget.configure(border_color="#1E1E1E") 
            return len(items)
        except ValueError:
            entry_widget.configure(border_color=ACCENT_RED)
            are_inputs_valid = False
            return 0

    def check_int(var, entry_widget):
        global are_inputs_valid
        try:
            val = int(var.get().strip())
            if val <= 0: raise ValueError
            entry_widget.configure(border_color="#1E1E1E")
        except ValueError:
            entry_widget.configure(border_color=ACCENT_RED)
            are_inputs_valid = False

    w = check_float_list(var_wall, entry_wall)
    r = check_float_list(var_roof, entry_roof)
    win = check_float_list(var_window, entry_window)
    i = check_float_list(var_infil, entry_infil)
    check_int(var_timesteps, entry_timesteps)
    check_int(var_warmup, entry_warmup)
    
    if are_inputs_valid:
        epw_count = len(active_cities) if active_cities else 1
            
        hvac_count = 34
        if 'hvac_vars' in globals() and hvac_vars:
            hvac_count = sum(1 for var in hvac_vars.values() if var.get())
            if hvac_count == 0: hvac_count = 1
            
        geom_layouts = sum([var_geom_1.get(), var_geom_2.get(), var_geom_3.get(), var_geom_4.get()])
        if geom_layouts == 0:
            are_inputs_valid = False
        
        total = total_base_sims * epw_count * geom_layouts * hvac_count * w * r * win * i
        lbl_sim_count.configure(text=f"{total:,}")
    else:
        lbl_sim_count.configure(text="ERR")

    update_button_state()

def update_button_state():
    if is_verified and are_inputs_valid and len(active_cities) > 0 and selected_idf:
        btn_run.configure(state="normal", fg_color=ACCENT_GREEN, hover_color="#219653", text_color="white", border_width=0)
        lbl_status.configure(text="Status: Ready to Run (Auto-resumes if files exist)", text_color=ACCENT_GREEN)
    else:
        btn_run.configure(state="disabled", fg_color="transparent", border_width=2, border_color="#444444", text_color="#666666")
        if not selected_idf:
            lbl_status.configure(text="Status: Waiting for IDF selection...", text_color=TEXT_MUTED)
        elif not is_verified:
            lbl_status.configure(text="Status: Waiting for verification...", text_color=TEXT_MUTED)
        elif len(active_cities) == 0:
            lbl_status.configure(text="Status: Select at least one weather location on the map...", text_color=ACCENT_ORANGE)
        else:
            lbl_status.configure(text="Status: Fix configuration errors...", text_color=ACCENT_RED)

def select_idf_file():
    global selected_idf, total_base_sims
    base_dir = os.path.join(os.getcwd(), "IDF Storage")
    
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        
    f = filedialog.askopenfilename(title="Select IDF File for Simulation", initialdir=base_dir, filetypes=[("IDF Files", "*.idf")])
    if f:
        selected_idf = f
        total_base_sims = 1
        lbl_proj_dir.configure(text=f"...{os.path.basename(f)}")
        validate_inputs()
        reset_verification()

def verify_files():
    global is_verified
    if not selected_idf:
        messagebox.showwarning("Warning", "Please select an IDF file first.")
        return
        
    is_valid, msg = IDF_Verifier.verify_idf_parameters(selected_idf)
    if is_valid:
        is_verified = True
        update_button_state()
        messagebox.showinfo("Verification Success", msg)
    else:
        reset_verification()
        messagebox.showerror("Verification Failed", msg)

def reset_verification():
    global is_verified
    is_verified = False
    update_button_state()

def toggle_kill_mode():
    if var_kill.get():
        slider_threads.set(multiprocessing.cpu_count())
        slider_threads.configure(state="disabled", progress_color=ACCENT_RED) 
        opt_start.set("12:00 AM"); opt_start.configure(state="disabled")
        opt_end.set("11:59 PM"); opt_end.configure(state="disabled")
        update_thread_label(multiprocessing.cpu_count())
    else:
        slider_threads.configure(state="normal", progress_color=ACCENT_BLUE) 
        opt_start.configure(state="normal")
        opt_end.configure(state="normal")

def start_simulations_thread():
    global is_spinning, sim_start_time, pause_event
    
    btn_run.configure(state="disabled", fg_color="transparent", border_width=2, border_color="#444444", text_color="#666666")
    btn_pause.configure(state="normal", fg_color=ACCENT_ORANGE, text_color="white", hover_color="#D35400", border_width=0)
    
    lbl_status.configure(text="Status: Preparing / Cleaning workers...", text_color=ACCENT_BLUE)
    lbl_time.configure(text="Time Remaining: Calculating...")
    progress_bar.set(0)
    
    is_spinning = True
    sim_start_time = time.time()
    spin_gear()

    manager = multiprocessing.Manager()
    pause_event = manager.Event()

    try:
        timesteps_str = str(int(var_timesteps.get()))
        warmup_str = str(int(var_warmup.get()))
        wall_list = [float(x.strip()) for x in var_wall.get().split(',')]
        roof_list = [float(x.strip()) for x in var_roof.get().split(',')]
        win_list = [float(x.strip()) for x in var_window.get().split(',')]
        inf_list = [float(x.strip()) for x in var_infil.get().split(',')]
        threads = int(slider_threads.get())
        start_hr = TIME_MAP[opt_start.get()]
        end_hr = TIME_MAP[opt_end.get()]

        selected_hvac = [sys_id for sys_id, var in hvac_vars.items() if var.get()]
        
        base_path = os.getcwd()
        main_dir = os.path.join(base_path, "Main Dir")
        report_dir = os.path.join(base_path, "Simulations Report")
        
        if os.path.exists(main_dir):
            shutil.rmtree(main_dir)
        
        os.makedirs(main_dir, exist_ok=True)
        os.makedirs(report_dir, exist_ok=True)
        
        selected_geoms = []
        if var_geom_1.get(): selected_geoms.append(1)
        if var_geom_2.get(): selected_geoms.append(2)
        if var_geom_3.get(): selected_geoms.append(3)
        if var_geom_4.get(): selected_geoms.append(4)
        
        sim_runner.start_batch_simulation(
            idf_file=selected_idf, 
            weather_dir=weather_dir,
            selected_cities=list(active_cities),
            eplus_dir="C:\\EnergyPlusV25-2-0",
            num_threads=threads,
            wall_mults=wall_list, 
            roof_mults=roof_list, 
            win_mults=win_list, 
            inf_vals=inf_list,
            hvac_list=selected_hvac,
            main_dir=main_dir,
            report_dir=report_dir,
            progress_callback=update_progress,
            geom_list=selected_geoms
        )
        
        is_spinning = False
        if pause_event.is_set():
            lbl_status.configure(text="Status: PAUSED by user.", text_color=ACCENT_ORANGE)
            messagebox.showinfo("Paused", "Simulations paused. Remaining runs have been halted.\nYou can click 'START BATCH' to resume.")
        else:
            progress_bar.set(1.0)
            lbl_status.configure(text="Status: BATCH COMPLETE!", text_color=ACCENT_GREEN)
            lbl_time.configure(text="Time Remaining: 00:00:00  |  ETA: --:--")
            messagebox.showinfo("Success", "All simulations have finished and Summary generated!")
            
    except Exception as e:
        is_spinning = False
        lbl_status.configure(text="Status: ERROR!", text_color=ACCENT_RED)
        messagebox.showerror("Simulation Error", f"An error occurred:\n{str(e)}")
    finally:
        btn_pause.configure(state="disabled", fg_color="transparent", border_width=2, border_color="#444444", text_color="#666666")
        update_button_state()

def run_button_clicked():
    threading.Thread(target=start_simulations_thread, daemon=True).start()

def pause_button_clicked():
    if pause_event:
        pause_event.set()
        lbl_status.configure(text="Status: Finishing active sims, halting...", text_color=ACCENT_ORANGE)
        btn_pause.configure(state="disabled")

def update_thread_label(val):
    lbl_threads_val.configure(text=f"Allocated Threads: {int(val)}")

def start_move(event):
    root.x = event.x
    root.y = event.y

def stop_move(event):
    root.x = None
    root.y = None

def do_move(event):
    deltax = event.x - root.x
    deltay = event.y - root.y
    x = root.winfo_x() + deltax
    y = root.winfo_y() + deltay
    root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    multiprocessing.freeze_support()

    root = ctk.CTk()
    root.geometry("1150x820") 
    root.configure(fg_color=APP_BG)
    root.overrideredirect(True)

    try:
        root.iconbitmap(resource_path("gear.ico"))
    except Exception:
        pass
    
    title_bar = ctk.CTkFrame(root, height=35, corner_radius=0, fg_color="#111111")
    title_bar.grid(row=0, column=0, columnspan=3, sticky="ew")
    title_bar.grid_columnconfigure(0, weight=1)
    
    title_bar.bind("<ButtonPress-1>", start_move)
    title_bar.bind("<ButtonRelease-1>", stop_move)
    title_bar.bind("<B1-Motion>", do_move)
    
    title_label = ctk.CTkLabel(title_bar, text="EnergyPlus Batch Simulator", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
    title_label.grid(row=0, column=0, pady=5)
    title_label.bind("<ButtonPress-1>", start_move)
    title_label.bind("<B1-Motion>", do_move)

    btn_close = ctk.CTkButton(title_bar, text="✕", width=40, height=35, corner_radius=0, 
                              fg_color="transparent", hover_color=ACCENT_RED, command=root.destroy)
    btn_close.grid(row=0, column=1, sticky="e")
    
    root.grid_columnconfigure(0, weight=1) 
    root.grid_columnconfigure(1, weight=1) 
    root.grid_columnconfigure(2, weight=1) 
    root.grid_rowconfigure(2, weight=1)

    var_timesteps = ctk.StringVar(value="6")
    var_warmup = ctk.StringVar(value="25")
    var_wall = ctk.StringVar(value="3.1783, 4.3812, 10.8411")
    var_roof = ctk.StringVar(value="5.00000, 8.26446, 16.66667")
    var_window = ctk.StringVar(value="1.0, 1.73, 2.8")
    var_infil = ctk.StringVar(value="0.0001, 0.0005, 0.0015")
    var_geom_1 = ctk.BooleanVar(value=True)
    var_geom_2 = ctk.BooleanVar(value=True)
    var_geom_3 = ctk.BooleanVar(value=True)
    var_geom_4 = ctk.BooleanVar(value=True)
    var_kill = ctk.BooleanVar(value=False)
    
    var_timesteps.trace_add("write", validate_inputs)
    var_warmup.trace_add("write", validate_inputs)
    var_wall.trace_add("write", validate_inputs)
    var_roof.trace_add("write", validate_inputs)
    var_window.trace_add("write", validate_inputs)
    var_infil.trace_add("write", validate_inputs)

    header_frame = ctk.CTkFrame(root, fg_color="transparent")
    header_frame.grid(row=1, column=0, columnspan=3, pady=(25, 15), sticky="ew")
    
    logo_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
    logo_frame.pack()
    
    try:
        logo_img = Image.open(resource_path("Engg_Logo.png"))
        logo_ctk = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(40, 40))
        ctk.CTkLabel(logo_frame, image=logo_ctk, text="").pack(side="left", padx=(0, 10))
    except Exception:
        pass

    ctk.CTkLabel(logo_frame, text="UofA ", font=ctk.CTkFont(family="Helvetica", size=32, weight="normal"), text_color=ACCENT_BLUE).pack(side="left")
    ctk.CTkLabel(logo_frame, text="SimRunner", font=ctk.CTkFont(family="Helvetica", size=32, weight="bold"), text_color=TEXT_MAIN).pack(side="left")

    frame_setup = ctk.CTkFrame(root, corner_radius=12, fg_color=CARD_BG)
    frame_setup.grid(row=2, column=0, sticky="nsew", padx=(30, 15), pady=(0, 30))
    
    ctk.CTkLabel(frame_setup, text="Environment Setup", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_MAIN).pack(pady=(20, 15))
    
    btn_proj_dir = ctk.CTkButton(frame_setup, text="Select IDF File", command=select_idf_file, width=220, height=35, fg_color="#333333", hover_color="#444444", text_color=TEXT_MAIN)
    btn_proj_dir.pack(pady=(5, 2))
    lbl_proj_dir = ctk.CTkLabel(frame_setup, text="No file selected", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
    lbl_proj_dir.pack(pady=(0, 20))

    ctk.CTkLabel(frame_setup, text="Select Weather Locations (Map):", text_color=TEXT_MAIN, font=ctk.CTkFont(size=12)).pack(pady=(5, 5))

    map_container = ctk.CTkFrame(frame_setup, width=240, height=180, corner_radius=8, fg_color="#1E1E1E")
    map_container.pack(pady=(0, 30))
    map_container.pack_propagate(False)
    
    map_canvas = Canvas(map_container, width=240, height=180, bg="#1E1E1E", highlightthickness=0)
    map_canvas.place(relx=0.5, rely=0.5, anchor="center")
    
    map_canvas.bind("<Button-1>", on_map_click)
    map_canvas.bind("<Motion>", on_map_hover)
    render_map()

    btn_verify = ctk.CTkButton(frame_setup, text="Verify Input File", fg_color="transparent", border_width=1, border_color=TEXT_MUTED, hover_color="#333333", text_color=TEXT_MAIN, command=verify_files, width=220, height=40, font=ctk.CTkFont(weight="bold"))
    btn_verify.pack(pady=(5, 20))

    col2_container = ctk.CTkFrame(root, fg_color="transparent")
    col2_container.grid(row=2, column=1, sticky="nsew", padx=15, pady=(0, 30))
    col2_container.grid_rowconfigure(0, weight=1)
    col2_container.grid_rowconfigure(1, weight=1) 
    col2_container.grid_columnconfigure(0, weight=1)

    frame_config = ctk.CTkScrollableFrame(col2_container, corner_radius=12, fg_color=CARD_BG)
    frame_config.grid(row=0, column=0, sticky="nsew")
    frame_config.grid_columnconfigure(0, weight=1)
    frame_config.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(frame_config, text="Simulation Parameters", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=0, columnspan=2, pady=(20, 20))

    pad_x = 25
    
    ctk.CTkLabel(frame_config, text="Timesteps / Hr:", text_color=TEXT_MAIN).grid(row=1, column=0, sticky="w", padx=pad_x, pady=3)
    entry_timesteps = ctk.CTkEntry(frame_config, textvariable=var_timesteps, width=150, border_width=1, fg_color="#1E1E1E")
    entry_timesteps.grid(row=1, column=1, sticky="e", padx=pad_x, pady=8)

    ctk.CTkLabel(frame_config, text="Max Warmup Days:", text_color=TEXT_MAIN).grid(row=2, column=0, sticky="w", padx=pad_x, pady=8)
    entry_warmup = ctk.CTkEntry(frame_config, textvariable=var_warmup, width=150, border_width=1, fg_color="#1E1E1E")
    entry_warmup.grid(row=2, column=1, sticky="e", padx=pad_x, pady=8)

    divider = ctk.CTkFrame(frame_config, height=1, fg_color="#444444")
    divider.grid(row=3, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=15)

    ctk.CTkLabel(frame_config, text="Wall U-Value(s):", text_color=TEXT_MAIN).grid(row=4, column=0, sticky="w", padx=pad_x, pady=8)
    entry_wall = ctk.CTkEntry(frame_config, textvariable=var_wall, width=150, border_width=1, fg_color="#1E1E1E")
    entry_wall.grid(row=4, column=1, sticky="e", padx=pad_x, pady=8)
    ToolTip(entry_wall, "Enter comma-separated values (e.g. 1.5, 2.0, 3.5)")

    ctk.CTkLabel(frame_config, text="Roof U-Value(s):", text_color=TEXT_MAIN).grid(row=5, column=0, sticky="w", padx=pad_x, pady=8)
    entry_roof = ctk.CTkEntry(frame_config, textvariable=var_roof, width=150, border_width=1, fg_color="#1E1E1E")
    entry_roof.grid(row=5, column=1, sticky="e", padx=pad_x, pady=8)

    ctk.CTkLabel(frame_config, text="Window U-Value(s):", text_color=TEXT_MAIN).grid(row=6, column=0, sticky="w", padx=pad_x, pady=8)
    entry_window = ctk.CTkEntry(frame_config, textvariable=var_window, width=150, border_width=1, fg_color="#1E1E1E")
    entry_window.grid(row=6, column=1, sticky="e", padx=pad_x, pady=8)

    ctk.CTkLabel(frame_config, text="Infiltration(s):", text_color=TEXT_MAIN).grid(row=7, column=0, sticky="w", padx=pad_x, pady=8)
    entry_infil = ctk.CTkEntry(frame_config, textvariable=var_infil, width=150, border_width=1, fg_color="#1E1E1E")
    entry_infil.grid(row=7, column=1, sticky="e", padx=pad_x, pady=8)
    
    divider2 = ctk.CTkFrame(frame_config, height=1, fg_color="#444444")
    divider2.grid(row=8, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=15)

    ctk.CTkLabel(frame_config, text="Geometries:", text_color=TEXT_MAIN).grid(row=9, column=0, sticky="nw", padx=pad_x, pady=8)
    
    geom_frame = ctk.CTkFrame(frame_config, fg_color="transparent")
    geom_frame.grid(row=9, column=1, sticky="w", padx=pad_x, pady=8)
    
    ctk.CTkCheckBox(geom_frame, text="1. Nominal", variable=var_geom_1, command=validate_inputs, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=2)
    ctk.CTkCheckBox(geom_frame, text="2. Pancake", variable=var_geom_2, command=validate_inputs, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=2)
    ctk.CTkCheckBox(geom_frame, text="3. Tower", variable=var_geom_3, command=validate_inputs, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=2)
    ctk.CTkCheckBox(geom_frame, text="4. Reduced WWR", variable=var_geom_4, command=validate_inputs, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=2)

    frame_hvac = ctk.CTkFrame(col2_container, corner_radius=12, fg_color=CARD_BG)
    frame_hvac.grid(row=1, column=0, sticky="nsew", pady=(15, 0))
    frame_hvac.grid_columnconfigure(0, weight=1)
    frame_hvac.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(frame_hvac, text="HVAC Components Generation", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=0, columnspan=2, pady=(15, 10))
    ctk.CTkLabel(frame_hvac, text="Select HVAC Systems to Run:", text_color=TEXT_MAIN).grid(row=1, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(8, 0))

    hvac_scroll = ctk.CTkScrollableFrame(frame_hvac, height=200, width=250, fg_color="#1E1E1E")
    hvac_scroll.grid(row=2, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=8)

    global hvac_vars
    hvac_vars = {}
    
    HVAC_SYSTEM_NAMES = {
        1: "Boiler + PTAC", 2: "Furnace + AC", 3: "Furnace", 4: "Electric AHU",
        5: "PTHP + Electric Backup", 6: "PHTP + Boiler", 7: "SZHP + Electric Backup", 8: "WSHP System",
        9: "ASHP VRF", 10: "Gas Unit Heater", 11: "Gas Unit Heater + PTAC", 12: "Gas Unit Heater + Exhaust Only",
        13: "Gas Furnace + DX + SZ VAV", 14: "Gas AHU + Air-Chiller + SZ CV",
        15: "Gas AHU + Electric Reheat + Air-Chiller + VAV", 16: "Gas Boiler + HW Reheat + Air-Chiller + CV",
        17: "Gas Boiler + HW Reheat + Air-Chiller + VAV", 18: "Gas FCU + Chilled-Water-FCU",
        19: "Gas Boiler HW FPB + Air-Chiller + FPB", 20: "Gas FCU + DOAS HW Tempering",
        21: "Electric BB + PTAC/DX", 22: "Electric BB + PTAC/DX + Exhaust Only",
        23: "Electric BB + PTAC/DX + CV", 24: "District HW Reheat + District CHW + CV",
        25: "District HW BB + District CHW + VAV", 26: "District HW FCUs + District CHW FCUs",
        27: "District HW TPBs + District CHW + FPB", 28: "District HW AHU + District CHW AHU + CV",
        29: "District HW AHU + District CHW AHU + VAV", 30: "PSZHP + Electric Backup + PSZHP/DX + SZ CV",
        31: "PTHP + PTHP/DX + CV", 32: "WSHP + Gas Boiler Loop + Cooling Tower + DOAS",
        33: "VRF ASHP + Electric DOAS Tempering + VRF ASHP", 34: "VRF WSHP + Electric Backup + VRF WSHP"
    }
    
    num_hvac_systems = 34
    for i in range(1, num_hvac_systems + 1):
        var = ctk.BooleanVar(value=True) 
        sys_name = HVAC_SYSTEM_NAMES.get(i, f"System {i}")
        chk = ctk.CTkCheckBox(hvac_scroll, text=f"{i}: {sys_name}", variable=var, text_color=TEXT_MAIN, fg_color=ACCENT_BLUE, command=validate_inputs, font=ctk.CTkFont(size=11))
        chk.pack(anchor="w", pady=2, padx=5)
        hvac_vars[i] = var

    def select_all_systems():
        for var in hvac_vars.values():
            var.set(True)

    btn_select_all = ctk.CTkButton(frame_hvac, text="Select All Systems", fg_color="#333333", hover_color="#555555", text_color=TEXT_MAIN, command=select_all_systems)
    btn_select_all.grid(row=3, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=(8, 15))

    frame_control = ctk.CTkFrame(root, corner_radius=12, fg_color=CARD_BG)
    frame_control.grid(row=2, column=2, sticky="nsew", padx=(15, 30), pady=(0, 30))
    frame_control.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(frame_control, text="Launch Controls", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_MAIN).grid(row=0, column=0, pady=(20, 15))

    run_frame = ctk.CTkFrame(frame_control, fg_color="transparent")
    run_frame.grid(row=1, column=0, pady=5)
    ctk.CTkLabel(run_frame, text="Active Window:", text_color=TEXT_MUTED).grid(row=0, column=0, padx=(0, 10))
    
    time_list = list(TIME_MAP.keys())
    opt_start = ctk.CTkOptionMenu(run_frame, values=time_list, width=90, fg_color="#333333", button_color="#444444", font=ctk.CTkFont(size=12))
    opt_start.set("12:00 AM")
    opt_start.grid(row=0, column=1, padx=2)
    
    ctk.CTkLabel(run_frame, text="to", text_color=TEXT_MUTED).grid(row=0, column=2, padx=5)
    
    opt_end = ctk.CTkOptionMenu(run_frame, values=time_list, width=90, fg_color="#333333", button_color="#444444", font=ctk.CTkFont(size=12))
    opt_end.set("11:59 PM")
    opt_end.grid(row=0, column=3, padx=2)

    max_cores = multiprocessing.cpu_count()
    lbl_threads_val = ctk.CTkLabel(frame_control, text=f"Allocated Threads: {max_cores // 2}", font=ctk.CTkFont(weight="bold"), text_color=TEXT_MAIN)
    lbl_threads_val.grid(row=2, column=0, pady=(15, 0))
    
    slider_threads = ctk.CTkSlider(frame_control, from_=1, to=max_cores, command=update_thread_label, button_color=ACCENT_BLUE, progress_color=ACCENT_BLUE)
    slider_threads.set(max_cores // 2)
    slider_threads.grid(row=3, column=0, pady=(10, 10), padx=40)

    chk_kill = ctk.CTkCheckBox(frame_control, text="Unrestricted Resource Mode", variable=var_kill, command=toggle_kill_mode, 
                               fg_color=ACCENT_RED, hover_color="#A93226", text_color=TEXT_MUTED)
    chk_kill.grid(row=4, column=0, pady=(5, 10))
    ToolTip(chk_kill, "Warning: Overrides thread slider to 100% and bypasses Active Window settings. System may become unresponsive.") 

    count_frame = ctk.CTkFrame(frame_control, fg_color="transparent")
    count_frame.grid(row=5, column=0, pady=(5, 10))
    ctk.CTkLabel(count_frame, text="Total Simulations:", text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(side="left", padx=5)
    lbl_sim_count = ctk.CTkLabel(count_frame, text="0", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_BLUE)
    lbl_sim_count.pack(side="left")

    btn_run = ctk.CTkButton(frame_control, text="START BATCH", corner_radius=6, width=240, height=45, 
                            font=ctk.CTkFont(size=16, weight="bold"), 
                            command=run_button_clicked, state="disabled", fg_color="transparent", border_width=2, border_color="#444444", text_color="#666666")
    btn_run.grid(row=6, column=0, pady=(5, 10)) 

    btn_pause = ctk.CTkButton(frame_control, text="PAUSE RUN", corner_radius=6, width=240, height=35,
                              font=ctk.CTkFont(size=14, weight="bold"),
                              command=pause_button_clicked, state="disabled", fg_color="transparent", border_width=2, border_color="#444444", text_color="#666666")
    btn_pause.grid(row=7, column=0, pady=(0, 10))

    progress_bar = ctk.CTkProgressBar(frame_control, width=250, height=8, progress_color=ACCENT_BLUE)
    progress_bar.grid(row=8, column=0, pady=(5, 10))
    progress_bar.set(0) 
    
    lbl_status = ctk.CTkLabel(frame_control, text="Status: Waiting for IDF selection...", text_color=TEXT_MUTED, font=ctk.CTkFont(size=13, weight="bold"))
    lbl_status.grid(row=9, column=0, pady=(0, 0))
    
    lbl_time = ctk.CTkLabel(frame_control, text="Time Remaining: --  |  ETA: --", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
    lbl_time.grid(row=10, column=0, pady=(0, 5))

    lbl_gear = ctk.CTkLabel(frame_control, text="")
    lbl_gear.grid(row=11, column=0, pady=(0, 15))

    try:
        base_gear_img = Image.open(resource_path("gear.png"))
        initial_gear = ctk.CTkImage(light_image=base_gear_img, dark_image=base_gear_img, size=(20, 20))
        lbl_gear.configure(image=initial_gear)
    except Exception:
        lbl_gear.configure(text="", text_color="transparent") 

    validate_inputs()
    root.mainloop()