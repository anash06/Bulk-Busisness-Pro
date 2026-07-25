"""
CustomTkinter graphical user interface for Bulk Business Search & Export Pro.
Includes dashboard, advanced filters, pagination, sortable treeview, settings,
and background search execution tracking.
"""

import os
import queue
import threading
import time
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

import webbrowser
from logger import logger
from config import APP_NAME, APP_VERSION, PLACE_TYPES, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, DEFAULT_WEB_PORT
# Database imports removed
from settings import AppSettings
from search_engine import SearchEngine
from exporter import Exporter

class BusinessSearchGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Load user configuration
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1200x750")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        
        # Apply theme settings
        ctk.set_appearance_mode(AppSettings.get_theme())
        ctk.set_default_color_theme(AppSettings.get_color_theme())
        
        # Search Engine integration
        self.progress_queue = queue.Queue()
        self.search_engine = SearchEngine(self.progress_queue)
        
        # Internal states
        self.raw_data: List[Dict[str, Any]] = []
        self.filtered_data: List[Dict[str, Any]] = []
        self.current_page = 1
        self.page_size = 50
        self.sort_column = "Business Name"
        self.sort_reverse = False
        
        self._current_responsive_mode = None
        self._active_frame = None
        self.mobile_menu_open = False
        self.web_server_thread = None
        
        # Setup UI layout
        self._create_layout()
        
        # Bind resize event for responsive window adaptation
        self.bind("<Configure>", self._on_window_resize)
        
        # Start periodic GUI queue poller
        self._poll_progress_queue()
        
        # Load initial database records
        self._load_database_records()
        self.update_dashboard()

    def _create_layout(self):
        # Grid layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Sidebar (Desktop & Tablet) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Bulk Business Pro", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=25)

        self.btn_dashboard = ctk.CTkButton(
            self.sidebar_frame, text="Dashboard", command=self._show_dashboard_tab, anchor="w"
        )
        self.btn_dashboard.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.btn_search = ctk.CTkButton(
            self.sidebar_frame, text="Search & Extract", command=self._show_search_tab, anchor="w"
        )
        self.btn_search.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.btn_settings = ctk.CTkButton(
            self.sidebar_frame, text="Settings", command=self._show_settings_tab, anchor="w"
        )
        self.btn_settings.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.btn_web_app = ctk.CTkButton(
            self.sidebar_frame, text="Mobile Web App 🌐", fg_color="#16a085", hover_color="#117a65", command=self._launch_web_app, anchor="w"
        )
        self.btn_web_app.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.version_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text=f"Version {APP_VERSION}", 
            font=ctk.CTkFont(size=10, slant="italic")
        )
        self.version_label.grid(row=6, column=0, padx=20, pady=15, sticky="s")

        # --- Mobile Header Bar (< 650px) ---
        self.mobile_header_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.mobile_header_frame.grid_columnconfigure(0, weight=1)

        self.mobile_logo_label = ctk.CTkLabel(
            self.mobile_header_frame, 
            text="Bulk Business Pro", 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.mobile_logo_label.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.btn_mobile_menu = ctk.CTkButton(
            self.mobile_header_frame,
            text="☰ Menu",
            width=70,
            command=self._toggle_mobile_menu
        )
        self.btn_mobile_menu.grid(row=0, column=1, padx=15, pady=10, sticky="e")

        # --- Mobile Nav Dropdown Frame ---
        self.mobile_nav_dropdown = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "gray20"))
        
        btn_m_dash = ctk.CTkButton(self.mobile_nav_dropdown, text="Dashboard", command=lambda: [self._show_dashboard_tab(), self._toggle_mobile_menu()])
        btn_m_dash.pack(fill="x", padx=15, pady=5)

        btn_m_search = ctk.CTkButton(self.mobile_nav_dropdown, text="Search & Extract", command=lambda: [self._show_search_tab(), self._toggle_mobile_menu()])
        btn_m_search.pack(fill="x", padx=15, pady=5)

        btn_m_settings = ctk.CTkButton(self.mobile_nav_dropdown, text="Settings", command=lambda: [self._show_settings_tab(), self._toggle_mobile_menu()])
        btn_m_settings.pack(fill="x", padx=15, pady=5)

        btn_m_web = ctk.CTkButton(self.mobile_nav_dropdown, text="Mobile Web App 🌐", fg_color="#16a085", hover_color="#117a65", command=lambda: [self._launch_web_app(), self._toggle_mobile_menu()])
        btn_m_web.pack(fill="x", padx=15, pady=5)

        # --- Main View Panels ---
        self.dashboard_frame = ctk.CTkFrame(self, corner_radius=0)
        self.search_frame = ctk.CTkFrame(self, corner_radius=0)
        self.settings_frame = ctk.CTkFrame(self, corner_radius=0)

        # Setup subviews
        self._setup_dashboard_tab()
        self._setup_search_tab()
        self._setup_settings_tab()

        # Display dashboard by default
        self._show_dashboard_tab()

    def _on_window_resize(self, event):
        if event.widget != self:
            return
        width = event.width
        if width < 650:
            new_mode = "mobile"
        elif width < 900:
            new_mode = "tablet"
        else:
            new_mode = "desktop"

        if new_mode != self._current_responsive_mode:
            self._current_responsive_mode = new_mode
            self._apply_responsive_layout(new_mode)

    def _apply_responsive_layout(self, mode: str):
        if mode == "mobile":
            self.sidebar_frame.grid_forget()
            self.mobile_header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)

            if self._active_frame:
                self._active_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

            # Reflow dashboard cards to 1 column
            self.card_total.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
            self.card_rating.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
            self.card_websites.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
            self.card_phones.grid(row=4, column=0, padx=5, pady=5, sticky="ew")
            self.db_status_frame.grid(row=5, column=0, columnspan=1, padx=5, pady=10, sticky="nsew")
            self.dashboard_frame.grid_columnconfigure((0, 1, 2, 3), weight=0)
            self.dashboard_frame.grid_columnconfigure(0, weight=1)

            # Reflow search form to 1 column
            self.form_frame.grid_columnconfigure((0, 1, 2), weight=0)
            self.form_frame.grid_columnconfigure(0, weight=1)
            self.ent_keywords.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
            self.ent_locations.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="ew")
            self.actions_frame.grid(row=4, column=0, columnspan=1, padx=10, pady=10, sticky="ew")

        elif mode == "tablet":
            if self.mobile_menu_open:
                self._toggle_mobile_menu()
            self.mobile_header_frame.grid_forget()
            self.sidebar_frame.configure(width=160)
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)
            self.grid_columnconfigure(0, weight=0)
            self.grid_columnconfigure(1, weight=1)

            if self._active_frame:
                self._active_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

            # Reflow dashboard cards to 2x2
            self.dashboard_frame.grid_columnconfigure((0, 1), weight=1)
            self.dashboard_frame.grid_columnconfigure((2, 3), weight=0)
            self.card_total.grid(row=1, column=0, padx=8, pady=8, sticky="ew")
            self.card_rating.grid(row=1, column=1, padx=8, pady=8, sticky="ew")
            self.card_websites.grid(row=2, column=0, padx=8, pady=8, sticky="ew")
            self.card_phones.grid(row=2, column=1, padx=8, pady=8, sticky="ew")
            self.db_status_frame.grid(row=3, column=0, columnspan=2, padx=8, pady=10, sticky="nsew")

            # Reflow search form
            self.form_frame.grid_columnconfigure((0, 1), weight=1)
            self.actions_frame.grid(row=0, column=2, rowspan=2, padx=10, pady=10, sticky="ew")

        else: # desktop
            if self.mobile_menu_open:
                self._toggle_mobile_menu()
            self.mobile_header_frame.grid_forget()
            self.sidebar_frame.configure(width=200)
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)
            self.grid_columnconfigure(0, weight=0)
            self.grid_columnconfigure(1, weight=1)

            if self._active_frame:
                self._active_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

            # Reflow dashboard cards to 1x4
            self.dashboard_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
            self.card_total.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
            self.card_rating.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
            self.card_websites.grid(row=1, column=2, padx=10, pady=10, sticky="ew")
            self.card_phones.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
            self.db_status_frame.grid(row=2, column=0, columnspan=4, padx=10, pady=15, sticky="nsew")

            # Reflow search form
            self.form_frame.grid_columnconfigure((0, 1, 2), weight=1)
            self.actions_frame.grid(row=0, column=2, rowspan=2, padx=10, pady=10, sticky="ew")

    def _toggle_mobile_menu(self):
        if self.mobile_menu_open:
            self.mobile_nav_dropdown.grid_forget()
            self.mobile_menu_open = False
        else:
            self.mobile_nav_dropdown.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
            self.mobile_menu_open = True

    def _launch_web_app(self):
        """Launches the companion Mobile Web App server and opens browser."""
        if not self.web_server_thread:
            try:
                from web_app import run_web_server
                self.web_server_thread = threading.Thread(target=run_web_server, daemon=True)
                self.web_server_thread.start()
                logger.info("Mobile Web App server thread started.")
            except Exception as e:
                logger.error(f"Error starting web server thread: {e}")

        url = f"http://localhost:{DEFAULT_WEB_PORT}"
        webbrowser.open(url)
        messagebox.showinfo("Mobile Web App", f"Mobile Web App server is running!\nOpened in browser: {url}\n\nAccess on mobile devices connected to your Wi-Fi network!")

    def _show_tab(self, frame_to_show):
        self.dashboard_frame.grid_forget()
        self.search_frame.grid_forget()
        self.settings_frame.grid_forget()
        self._active_frame = frame_to_show
        
        if self._current_responsive_mode == "mobile":
            frame_to_show.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        else:
            frame_to_show.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

    def _show_dashboard_tab(self):
        self._show_tab(self.dashboard_frame)
        self.update_dashboard()

    def _show_search_tab(self):
        self._show_tab(self.search_frame)

    def _show_settings_tab(self):
        self._show_tab(self.settings_frame)
        self._load_settings_fields()

    # ==========================================
    # 1. DASHBOARD TAB
    # ==========================================
    def _setup_dashboard_tab(self):
        self.dashboard_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.dashboard_frame.grid_rowconfigure(2, weight=1)

        # Tab Title
        lbl_title = ctk.CTkLabel(
            self.dashboard_frame, 
            text="System Analytics Dashboard", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        lbl_title.grid(row=0, column=0, columnspan=4, padx=20, pady=15, sticky="w")

        # --- Cards Row 1 ---
        self.card_total = ctk.CTkFrame(self.dashboard_frame, height=100)
        self.card_total.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.lbl_card_total_title = ctk.CTkLabel(self.card_total, text="Total Businesses Found", font=ctk.CTkFont(size=12))
        self.lbl_card_total_title.pack(pady=(15, 5))
        self.lbl_card_total_val = ctk.CTkLabel(self.card_total, text="0", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_card_total_val.pack(pady=(0, 15))

        self.card_rating = ctk.CTkFrame(self.dashboard_frame, height=100)
        self.card_rating.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.lbl_card_rating_title = ctk.CTkLabel(self.card_rating, text="Average Rating", font=ctk.CTkFont(size=12))
        self.lbl_card_rating_title.pack(pady=(15, 5))
        self.lbl_card_rating_val = ctk.CTkLabel(self.card_rating, text="0.00", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_card_rating_val.pack(pady=(0, 15))

        self.card_websites = ctk.CTkFrame(self.dashboard_frame, height=100)
        self.card_websites.grid(row=1, column=2, padx=10, pady=10, sticky="ew")
        self.lbl_card_websites_title = ctk.CTkLabel(self.card_websites, text="With Website Link", font=ctk.CTkFont(size=12))
        self.lbl_card_websites_title.pack(pady=(15, 5))
        self.lbl_card_websites_val = ctk.CTkLabel(self.card_websites, text="0", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_card_websites_val.pack(pady=(0, 15))

        self.card_phones = ctk.CTkFrame(self.dashboard_frame, height=100)
        self.card_phones.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
        self.lbl_card_phones_title = ctk.CTkLabel(self.card_phones, text="With Phone Number", font=ctk.CTkFont(size=12))
        self.lbl_card_phones_title.pack(pady=(15, 5))
        self.lbl_card_phones_val = ctk.CTkLabel(self.card_phones, text="0", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_card_phones_val.pack(pady=(0, 15))

        # Bottom section: Recent System Logs & Status Info
        self.db_status_frame = ctk.CTkFrame(self.dashboard_frame)
        self.db_status_frame.grid(row=2, column=0, columnspan=4, padx=10, pady=15, sticky="nsew")
        self.db_status_frame.grid_columnconfigure(0, weight=1)
        self.db_status_frame.grid_rowconfigure(1, weight=1)

        self.lbl_recent_exports = ctk.CTkLabel(self.db_status_frame, text="Recent System Logs & Status Info", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_recent_exports.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        # System info textbox
        self.txt_sys_info = ctk.CTkTextbox(self.db_status_frame, height=150)
        self.txt_sys_info.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.txt_sys_info.configure(state="disabled")

    def update_dashboard(self):
        total_biz = len(self.raw_data)
        ratings = [b["rating"] for b in self.raw_data if b.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        with_website = sum(1 for b in self.raw_data if b.get("website"))
        with_phone = sum(1 for b in self.raw_data if b.get("phone_number"))
        top_rated = sum(1 for b in self.raw_data if b.get("rating") and b["rating"] >= 4.5)

        self.lbl_card_total_val.configure(text=f"{total_biz}")
        self.lbl_card_rating_val.configure(text=f"{avg_rating:.2f}")
        self.lbl_card_websites_val.configure(text=f"{with_website}")
        self.lbl_card_phones_val.configure(text=f"{with_phone}")

        # System info output
        self.txt_sys_info.configure(state="normal")
        self.txt_sys_info.delete("1.0", tk.END)
        self.txt_sys_info.insert(tk.END, "System Statistics:\n")
        self.txt_sys_info.insert(tk.END, f"- Cache: Disallowed (In-Memory Only)\n")
        self.txt_sys_info.insert(tk.END, f"- Multi-threading state: Ready\n")
        self.txt_sys_info.insert(tk.END, f"- Top Rated Businesses (rating >= 4.5): {top_rated}\n")
        self.txt_sys_info.insert(tk.END, f"- Current Export folder: {AppSettings.get_export_folder()}\n")
        self.txt_sys_info.configure(state="disabled")

    # ==========================================
    # 2. SEARCH & EXTRACT TAB
    # ==========================================
    def _setup_search_tab(self):
        self.search_frame.grid_columnconfigure(0, weight=1) # Search Panel occupies full width
        self.search_frame.grid_rowconfigure(2, weight=1)    # Results table

        # --- TOP CONTROLS & FORM ---
        self.form_frame = ctk.CTkFrame(self.search_frame)
        self.form_frame.grid(row=0, column=0, columnspan=1, padx=10, pady=10, sticky="ew")
        self.form_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Keyword
        ctk.CTkLabel(self.form_frame, text="Keywords (e.g. restaurant, hospital):", anchor="w").grid(row=0, column=0, padx=10, pady=(10, 2), sticky="w")
        self.ent_keywords = ctk.CTkEntry(self.form_frame, placeholder_text="gym, dentist, spa")
        self.ent_keywords.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.btn_import_keywords = ctk.CTkButton(self.form_frame, text="Import", width=60, command=self._import_keywords)
        self.btn_import_keywords.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="e")

        # Location/City
        ctk.CTkLabel(self.form_frame, text="Cities / States / Countries:", anchor="w").grid(row=0, column=1, padx=10, pady=(10, 2), sticky="w")
        self.ent_locations = ctk.CTkEntry(self.form_frame, placeholder_text="New York, Paris")
        self.ent_locations.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")
        self.btn_import_locations = ctk.CTkButton(self.form_frame, text="Import", width=60, command=self._import_locations)
        self.btn_import_locations.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="e")

        # Actions Panel (Start, Pause, Resume, Stop)
        self.actions_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.actions_frame.grid(row=0, column=2, rowspan=2, padx=10, pady=10, sticky="ew")
        
        self.btn_start = ctk.CTkButton(self.actions_frame, text="Start Search", fg_color="green", hover_color="dark green", command=self._start_search)
        self.btn_start.pack(fill="x", pady=2)
        
        # --- PROGRESS BAR FRAME ---
        self.progress_frame = ctk.CTkFrame(self.search_frame)
        self.progress_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.progress_frame.grid_columnconfigure(1, weight=1)

        self.lbl_progress_status = ctk.CTkLabel(self.progress_frame, text="Status: Ready", font=ctk.CTkFont(weight="bold"))
        self.lbl_progress_status.grid(row=0, column=0, padx=15, pady=5, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=15, pady=5, sticky="ew")

        self.lbl_progress_stats = ctk.CTkLabel(self.progress_frame, text="Grid: 0/0 | Found: 0 | Remaining Time: N/A")
        self.lbl_progress_stats.grid(row=0, column=2, padx=15, pady=5, sticky="e")

        # --- LEFT: SEARCH RESULTS TABLE PANEL ---
        self.table_panel = ctk.CTkFrame(self.search_frame)
        self.table_panel.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.table_panel.grid_rowconfigure(2, weight=1)
        self.table_panel.grid_columnconfigure(0, weight=1)

        # Table controls (Search, Page limit, Export)
        self.table_ctrls = ctk.CTkFrame(self.table_panel, fg_color="transparent")
        self.table_ctrls.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.ent_table_search = ctk.CTkEntry(self.table_ctrls, placeholder_text="Filter in-table search...", width=200)
        self.ent_table_search.pack(side="left", padx=5, pady=5)
        self.ent_table_search.bind("<KeyRelease>", lambda e: self._on_filter_changed())

        # Page Size
        self.lbl_page_size = ctk.CTkLabel(self.table_ctrls, text="Page Size:")
        self.lbl_page_size.pack(side="left", padx=(15, 5))
        self.opt_page_size = ctk.CTkOptionMenu(
            self.table_ctrls, values=["25", "50", "100", "200"], width=80, command=self._on_page_size_changed
        )
        self.opt_page_size.set("50")
        self.opt_page_size.pack(side="left", padx=5)

        # Export Actions Dropdown/Buttons
        self.btn_export_xls = ctk.CTkButton(self.table_ctrls, text="Export Excel", fg_color="dark green", hover_color="#0e6251", command=self._export_excel)
        self.btn_export_xls.pack(side="right", padx=5)

        self.btn_export_csv = ctk.CTkButton(self.table_ctrls, text="Export CSV", fg_color="#34495e", hover_color="#2c3e50", command=self._export_csv)
        self.btn_export_csv.pack(side="right", padx=5)

        self.btn_export_json = ctk.CTkButton(self.table_ctrls, text="Export JSON", fg_color="#2e4053", hover_color="#283747", command=self._export_json)
        self.btn_export_json.pack(side="right", padx=5)

        self.btn_clear_results = ctk.CTkButton(self.table_ctrls, text="Clear Results", fg_color="#c0392b", hover_color="#962d22", command=self._clear_results)
        self.btn_clear_results.pack(side="right", padx=5)

        # --- MIDDLE FILTER CONTROLS BAR (Row 1) ---
        self.filter_bar = ctk.CTkFrame(self.table_panel, fg_color="transparent")
        self.filter_bar.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.lbl_filters = ctk.CTkLabel(self.filter_bar, text="Filters:", font=ctk.CTkFont(weight="bold"))
        self.lbl_filters.pack(side="left", padx=5)

        # City Filter
        self.lbl_filter_city = ctk.CTkLabel(self.filter_bar, text="City:")
        self.lbl_filter_city.pack(side="left", padx=(10, 2))
        self.ent_filter_city = ctk.CTkEntry(self.filter_bar, placeholder_text="e.g. Chennai", width=120)
        self.ent_filter_city.pack(side="left", padx=5)
        self.ent_filter_city.bind("<KeyRelease>", lambda e: self._on_filter_changed())

        # Type/Category Filter
        self.lbl_filter_type = ctk.CTkLabel(self.filter_bar, text="Type:")
        self.lbl_filter_type.pack(side="left", padx=(10, 2))
        self.ent_filter_type = ctk.CTkEntry(self.filter_bar, placeholder_text="e.g. Hospital", width=120)
        self.ent_filter_type.pack(side="left", padx=5)
        self.ent_filter_type.bind("<KeyRelease>", lambda e: self._on_filter_changed())

        # Status Filter
        self.lbl_filter_status = ctk.CTkLabel(self.filter_bar, text="Status:")
        self.lbl_filter_status.pack(side="left", padx=(10, 2))
        self.opt_filter_status = ctk.CTkOptionMenu(
            self.filter_bar, values=["All Statuses", "Active", "Temporarily Closed", "Permanently Closed"], width=130, command=lambda e: self._on_filter_changed()
        )
        self.opt_filter_status.set("All Statuses")
        self.opt_filter_status.pack(side="left", padx=5)

        # Has Phone Filter
        self.var_filter_phone = tk.BooleanVar(value=False)
        self.chk_filter_phone = ctk.CTkCheckBox(
            self.filter_bar, text="Has Phone Only", variable=self.var_filter_phone, command=self._on_filter_changed
        )
        self.chk_filter_phone.pack(side="left", padx=(15, 5))

        # Has Website Filter
        self.var_filter_website = tk.BooleanVar(value=False)
        self.chk_filter_website = ctk.CTkCheckBox(
            self.filter_bar, text="Has Website Only", variable=self.var_filter_website, command=self._on_filter_changed
        )
        self.chk_filter_website.pack(side="left", padx=(15, 5))

        # Styled Tkinter Treeview inside CustomTkinter Frame (Row 2)
        self.tree_frame = ttk.Frame(self.table_panel)
        self.tree_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")

        # Treeview Scrollbars
        self.tree_scroll_y = ttk.Scrollbar(self.tree_frame, orient="vertical")
        self.tree_scroll_x = ttk.Scrollbar(self.tree_frame, orient="horizontal")

        # Configure Style for Treeview to make it fit CustomTkinter Dark/Light themes
        self.tree_style = ttk.Style()
        self.tree_style.theme_use("clam")
        
        # Configure standard Treeview colors
        self._apply_treeview_styles()

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("SNo", "Name", "Type", "Status", "Phone", "Website", "Rating", "Reviews", "City", "State"),
            show="headings",
            yscrollcommand=self.tree_scroll_y.set,
            xscrollcommand=self.tree_scroll_x.set
        )

        self.tree_scroll_y.config(command=self.tree.yview)
        self.tree_scroll_y.pack(side="right", fill="y")
        self.tree_scroll_x.config(command=self.tree.xview)
        self.tree_scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        # Columns configuration & header click sorting binding
        cols = {
            "SNo": ("S.No", 50),
            "Name": ("Business Name", 200),
            "Type": ("Type", 120),
            "Status": ("Status", 100),
            "Phone": ("Phone", 120),
            "Website": ("Website", 150),
            "Rating": ("Rating", 60),
            "Reviews": ("Reviews", 70),
            "City": ("City", 120),
            "State": ("State", 100)
        }

        for col_id, (header, width) in cols.items():
            self.tree.heading(col_id, text=header, command=lambda c=col_id: self._sort_treeview(c))
            self.tree.column(col_id, width=width, minwidth=50, stretch=True, anchor="w" if col_id not in ["Rating", "Reviews", "Status", "SNo"] else "center")

        # Table Footer Pagination panel
        self.footer_panel = ctk.CTkFrame(self.table_panel, fg_color="transparent")
        self.footer_panel.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        self.lbl_table_stats = ctk.CTkLabel(self.footer_panel, text="Showing 0 of 0 businesses")
        self.lbl_table_stats.pack(side="left", padx=5)

        self.pagination_frame = ctk.CTkFrame(self.footer_panel, fg_color="transparent")
        self.pagination_frame.pack(side="right", padx=5)

        self.btn_prev_page = ctk.CTkButton(self.pagination_frame, text="◀ Prev", width=60, command=self._prev_page)
        self.btn_prev_page.pack(side="left", padx=2)

        self.lbl_page_num = ctk.CTkLabel(self.pagination_frame, text="Page 1 of 1")
        self.lbl_page_num.pack(side="left", padx=10)

        self.btn_next_page = ctk.CTkButton(self.pagination_frame, text="Next ▶", width=60, command=self._next_page)
        self.btn_next_page.pack(side="left", padx=2)



    def _apply_treeview_styles(self):
        # Configure colors dynamically depending on theme
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg_color = "#2b2b2b"
            fg_color = "#ffffff"
            selected_color = "#1f538d"
            header_bg = "#212121"
            header_fg = "#ffffff"
        else:
            bg_color = "#ffffff"
            fg_color = "#000000"
            selected_color = "#3a7ebf"
            header_bg = "#e0e0e0"
            header_fg = "#000000"

        self.tree_style.configure(
            "Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            rowheight=25,
            font=("Segoe UI", 10)
        )
        self.tree_style.map("Treeview", background=[("selected", selected_color)])

        self.tree_style.configure(
            "Heading",
            background=header_bg,
            foreground=header_fg,
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )

    def _on_radius_slider(self, val):
        self.lbl_radius_val.configure(text=f"{int(val)} m")



    # ==========================================
    # 3. HISTORY & DATABASE TAB
    # ==========================================
    # History tab methods removed

    # ==========================================
    # 4. SETTINGS TAB
    # ==========================================
    def _setup_settings_tab(self):
        self.settings_frame.grid_columnconfigure(0, weight=1)
        self.settings_frame.grid_rowconfigure(1, weight=1)

        # Tab Title
        lbl_title = ctk.CTkLabel(
            self.settings_frame, 
            text="Preferences & API Credentials", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        lbl_title.grid(row=0, column=0, padx=20, pady=15, sticky="w")

        # Scrollable Settings Container
        self.settings_scroll = ctk.CTkScrollableFrame(self.settings_frame)
        self.settings_scroll.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.settings_scroll.grid_columnconfigure(1, weight=1)

        # API Key
        ctk.CTkLabel(self.settings_scroll, text="Google Places API Key (Optional):", anchor="w").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.ent_api_key = ctk.CTkEntry(self.settings_scroll, show="*", width=350)
        self.ent_api_key.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.btn_show_key = ctk.CTkButton(self.settings_scroll, text="Show", width=60, command=self._toggle_api_key_visibility)
        self.btn_show_key.grid(row=0, column=1, padx=10, pady=10, sticky="e")

        # Export Folder
        ctk.CTkLabel(self.settings_scroll, text="Default Export Path:", anchor="w").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.ent_export_path = ctk.CTkEntry(self.settings_scroll, width=350)
        self.ent_export_path.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        self.btn_browse_path = ctk.CTkButton(self.settings_scroll, text="Browse", width=60, command=self._browse_export_path)
        self.btn_browse_path.grid(row=1, column=1, padx=10, pady=10, sticky="e")

        # Default Radius
        ctk.CTkLabel(self.settings_scroll, text="Default Search Radius (m):", anchor="w").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.ent_def_radius = ctk.CTkEntry(self.settings_scroll, width=150)
        self.ent_def_radius.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        # Delay
        ctk.CTkLabel(self.settings_scroll, text="Request Delay (sec):", anchor="w").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.ent_def_delay = ctk.CTkEntry(self.settings_scroll, width=150)
        self.ent_def_delay.grid(row=3, column=1, padx=10, pady=10, sticky="w")

        # Theme
        ctk.CTkLabel(self.settings_scroll, text="Interface Theme Mode:", anchor="w").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.opt_theme_mode = ctk.CTkOptionMenu(self.settings_scroll, values=["System", "Dark", "Light"])
        self.opt_theme_mode.grid(row=4, column=1, padx=10, pady=10, sticky="w")

        # Color Theme
        ctk.CTkLabel(self.settings_scroll, text="Theme Color Scheme:", anchor="w").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.opt_theme_color = ctk.CTkOptionMenu(self.settings_scroll, values=["blue", "green", "dark-blue"])
        self.opt_theme_color.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        # Browser Visibility Mode
        ctk.CTkLabel(self.settings_scroll, text="Browser Scraper Visibility:", anchor="w").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.opt_browser_mode = ctk.CTkOptionMenu(self.settings_scroll, values=["Hidden (Headless)", "Visible (Headful)"])
        self.opt_browser_mode.grid(row=6, column=1, padx=10, pady=10, sticky="w")

        # Save Button
        self.btn_save_settings = ctk.CTkButton(
            self.settings_scroll, 
            text="Save Preferences", 
            fg_color="green", 
            hover_color="dark green", 
            command=self._save_settings_fields
        )
        self.btn_save_settings.grid(row=7, column=0, columnspan=2, padx=10, pady=25, sticky="ew")

    def _toggle_api_key_visibility(self):
        if self.ent_api_key.cget("show") == "*":
            self.ent_api_key.configure(show="")
            self.btn_show_key.configure(text="Hide")
        else:
            self.ent_api_key.configure(show="*")
            self.btn_show_key.configure(text="Show")

    def _browse_export_path(self):
        folder = filedialog.askdirectory(initialdir=self.ent_export_path.get())
        if folder:
            self.ent_export_path.delete(0, tk.END)
            self.ent_export_path.insert(0, folder)

    def _load_settings_fields(self):
        self.ent_api_key.delete(0, tk.END)
        self.ent_api_key.insert(0, AppSettings.get_api_key())
        
        self.ent_export_path.delete(0, tk.END)
        self.ent_export_path.insert(0, AppSettings.get_export_folder())
        
        self.ent_def_radius.delete(0, tk.END)
        self.ent_def_radius.insert(0, str(AppSettings.get_search_radius()))
        
        self.ent_def_delay.delete(0, tk.END)
        self.ent_def_delay.insert(0, f"{AppSettings.get_request_delay():.2f}")
        
        self.opt_theme_mode.set(AppSettings.get_theme())
        self.opt_theme_color.set(AppSettings.get_color_theme())
        
        # Load browser mode
        is_headless = AppSettings.get_headless()
        self.opt_browser_mode.set("Hidden (Headless)" if is_headless else "Visible (Headful)")

    def _save_settings_fields(self):
        try:
            # Validate input values
            api_key = self.ent_api_key.get().strip()
            export_path = self.ent_export_path.get().strip()
            
            radius = int(self.ent_def_radius.get())
            delay = float(self.ent_def_delay.get())
            
            theme = self.opt_theme_mode.get()
            color = self.opt_theme_color.get()
            browser_mode = self.opt_browser_mode.get()
            is_headless = browser_mode == "Hidden (Headless)"

            if not os.path.exists(export_path):
                messagebox.showerror("Error", f"Default export folder path does not exist:\n{export_path}")
                return

            AppSettings.set_api_key(api_key)
            AppSettings.set_export_folder(export_path)
            AppSettings.set_search_radius(radius)
            AppSettings.set_request_delay(delay)
            AppSettings.set_theme(theme)
            AppSettings.set_color_theme(color)
            AppSettings.set_headless(is_headless)

            # Apply UI theme redrawing
            ctk.set_appearance_mode(theme)
            ctk.set_default_color_theme(color)
            
            # Apply color adjustments to Treeview
            self._apply_treeview_styles()

            messagebox.showinfo("Preferences Saved", "Your application settings have been updated successfully.")
            self.update_dashboard()
        except ValueError:
            messagebox.showerror("Invalid Values", "Please check radius (integer) and delay (float) formatting.")

    # ==========================================
    # 5. DATA LOGIC & EVENTS HANDLING
    # ==========================================
    def _load_database_records(self):
        """No-op because SQLite database is removed."""
        self.raw_data = []
        self._on_filter_changed()

    def _on_filter_changed(self):
        """Filters the dataset using all criteria and updates pagination."""
        # Start with all raw data
        self.filtered_data = list(self.raw_data)

        # 1. Global in-table search filter
        table_search_val = self.ent_table_search.get().strip().lower()
        if table_search_val:
            self.filtered_data = [
                biz for biz in self.filtered_data if
                table_search_val in (biz.get("name") or "").lower() or
                table_search_val in (biz.get("full_address") or "").lower() or
                table_search_val in (biz.get("phone_number") or "").lower()
            ]

        # 2. City filter
        city_filter = self.ent_filter_city.get().strip().lower()
        if city_filter:
            self.filtered_data = [
                biz for biz in self.filtered_data
                if city_filter in (biz.get("city") or "").lower()
            ]

        # 4. Type/Category filter
        type_filter = self.ent_filter_type.get().strip().lower()
        if type_filter:
            self.filtered_data = [
                biz for biz in self.filtered_data
                if any(type_filter in str(t).lower() for t in (biz.get("business_types") or []))
                or type_filter in str(biz.get("business_types") or "").lower()
            ]

        # 5. Status filter (Active, Temporarily Closed, Permanently Closed)
        status_sel = self.opt_filter_status.get()
        if status_sel != "All Statuses":
            status_map = {
                "Active": "OPERATIONAL",
                "Temporarily Closed": "CLOSED_TEMPORARILY",
                "Permanently Closed": "CLOSED_PERMANENTLY"
            }
            target_status = status_map.get(status_sel)
            self.filtered_data = [
                biz for biz in self.filtered_data
                if (biz.get("business_status") or "OPERATIONAL") == target_status
            ]

        # 6. Has Phone filter
        if self.var_filter_phone.get():
            self.filtered_data = [
                biz for biz in self.filtered_data
                if biz.get("phone_number") and biz.get("phone_number") != "N/A"
            ]

        # 7. Has Website filter
        if self.var_filter_website.get():
            self.filtered_data = [
                biz for biz in self.filtered_data
                if biz.get("website") and biz.get("website") != "N/A"
            ]

        # Reset pagination and refresh view
        self.current_page = 1
        self._sort_and_paginate()

    def _sort_and_paginate(self):
        """Sorts the filtered dataset and displays the current page in Treeview."""
        # 1. Sorting
        def get_sort_key(item: dict):
            val = item.get(self._get_raw_column_name(self.sort_column))
            if val is None:
                return "" if isinstance(self.sort_column, str) else 0.0
            if isinstance(val, str):
                return val.lower().strip()
            return val

        self.filtered_data.sort(key=get_sort_key, reverse=self.sort_reverse)

        # 2. Pagination
        total_items = len(self.filtered_data)
        total_pages = max(1, math.ceil(total_items / self.page_size))
        
        if self.current_page > total_pages:
            self.current_page = total_pages

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)
        page_items = self.filtered_data[start_idx:end_idx]

        # 3. Populate Treeview
        # Clear treeview items
        for child in self.tree.get_children():
            self.tree.delete(child)

        for idx, biz in enumerate(page_items):
            s_no = start_idx + idx + 1
            rating = biz.get("rating")
            rating_str = f"{rating:.1f}" if rating is not None and rating > 0 else "N/A"
            
            reviews = biz.get("total_reviews")
            reviews_str = f"{int(reviews):,}" if reviews is not None else "0"

            # Format Type
            biz_types = biz.get("business_types", [])
            type_str = ", ".join([t.title() for t in biz_types]) if isinstance(biz_types, list) else str(biz_types).title()
            if not type_str:
                type_str = "N/A"

            # Format Active Status
            status_raw = biz.get("business_status") or "OPERATIONAL"
            status_mapping = {
                "OPERATIONAL": "Active",
                "CLOSED_TEMPORARILY": "Temporarily Closed",
                "CLOSED_PERMANENTLY": "Permanently Closed"
            }
            status_str = status_mapping.get(status_raw, status_raw.title().replace("_", " "))

            self.tree.insert(
                "",
                tk.END,
                values=(
                    s_no,
                    biz.get("name", "N/A"),
                    type_str,
                    status_str,
                    biz.get("phone_number") or "N/A",
                    biz.get("website") or "N/A",
                    rating_str,
                    reviews_str,
                    biz.get("city") or "N/A",
                    biz.get("state") or "N/A"
                )
            )

        # 4. Updates labels
        if total_items == 0:
            self.lbl_table_stats.configure(text="Showing 0 of 0 businesses")
        else:
            self.lbl_table_stats.configure(text=f"Showing {start_idx + 1}-{end_idx} of {total_items} businesses")
        self.lbl_page_num.configure(text=f"Page {self.current_page} of {total_pages}")

    def _get_raw_column_name(self, ui_col: str) -> str:
        mapping = {
            "S.No": "name", # Sort by name if S.No is clicked
            "Business Name": "name",
            "Type": "business_types",
            "Status": "business_status",
            "Phone": "phone_number",
            "Website": "website",
            "Rating": "rating",
            "Reviews": "total_reviews",
            "City": "city",
            "State": "state"
        }
        return mapping.get(ui_col, "name")

    def _sort_treeview(self, col_id: str):
        col_name_mapping = {
            "SNo": "S.No",
            "Name": "Business Name",
            "Type": "Type",
            "Status": "Status",
            "Phone": "Phone",
            "Website": "Website",
            "Rating": "Rating",
            "Reviews": "Reviews",
            "City": "City",
            "State": "State"
        }
        col_ui_name = col_name_mapping.get(col_id, "Business Name")
        
        if self.sort_column == col_ui_name:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col_ui_name
            self.sort_reverse = False

        self._sort_and_paginate()

    def _on_page_size_changed(self, size_str):
        self.page_size = int(size_str)
        self.current_page = 1
        self._sort_and_paginate()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._sort_and_paginate()

    def _next_page(self):
        total_items = len(self.filtered_data)
        total_pages = max(1, math.ceil(total_items / self.page_size))
        if self.current_page < total_pages:
            self.current_page += 1
            self._sort_and_paginate()

    # --- Excel and File imports ---
    def _import_locations(self):
        """Loads city strings from text/Excel/CSV files."""
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel Files", "*.xlsx;*.xls"), ("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            cities = []
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path)
                # Try to search common header names, else take first col
                target_col = None
                for col in df.columns:
                    if col.lower() in ["city", "location", "cities", "search location"]:
                        target_col = col
                        break
                if target_col is None:
                    target_col = df.columns[0]
                cities = df[target_col].dropna().astype(str).tolist()
            elif ext == ".csv":
                with open(file_path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    first_row = next(reader, None)
                    if first_row:
                        # Simple heuristics: take column 0
                        cities.append(first_row[0])
                        for row in reader:
                            if row:
                                cities.append(row[0])
            else: # txt
                with open(file_path, "r", encoding="utf-8") as f:
                    cities = [line.strip() for line in f if line.strip()]

            # Format to comma separated and set to Entry
            formatted = ", ".join(cities)
            self.ent_locations.delete(0, tk.END)
            self.ent_locations.insert(0, formatted)
            messagebox.showinfo("Import Successful", f"Successfully loaded {len(cities)} location search inputs.")
        except Exception as e:
            logger.error(f"Failed to import location list file: {e}")
            messagebox.showerror("Import Error", f"Failed to parse file: {e}")

    def _import_keywords(self):
        """Loads keyword strings from files."""
        file_path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("CSV Files", "*.csv"), ("Excel Files", "*.xlsx;*.xls"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            keywords = []
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path)
                target_col = df.columns[0]
                keywords = df[target_col].dropna().astype(str).tolist()
            elif ext == ".csv":
                with open(file_path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row:
                            keywords.append(row[0])
            else: # txt
                with open(file_path, "r", encoding="utf-8") as f:
                    keywords = [line.strip() for line in f if line.strip()]

            formatted = ", ".join(keywords)
            self.ent_keywords.delete(0, tk.END)
            self.ent_keywords.insert(0, formatted)
            messagebox.showinfo("Import Successful", f"Successfully loaded {len(keywords)} search keywords.")
        except Exception as e:
            logger.error(f"Failed to import keywords list: {e}")
            messagebox.showerror("Import Error", f"Failed to parse file: {e}")

    # --- Search Engine controller triggers ---
    def _start_search(self):
        """Prepares parameters and triggers background search thread execution."""
        api_key = AppSettings.get_api_key()
        if not api_key:
            logger.info("No API Key configured. Launching search in Keyless Scraper Mode.")

        cities_str = self.ent_locations.get().strip()
        keywords_str = self.ent_keywords.get().strip()

        if not cities_str or not keywords_str:
            messagebox.showwarning("Missing Fields", "Please supply at least one location and search keyword/category.")
            return

        # Split and clean
        cities = [c.strip() for c in cities_str.split(",") if c.strip()]
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        # No radius filter — collect all businesses in the location
        radius = 0

        # Toggle GUI states
        self.btn_start.configure(state="disabled")

        # Clear previous in-memory results
        self.raw_data = []
        self._on_filter_changed()
        self.update_dashboard()

        # Fire search engine thread
        self.search_engine.start_bulk_search(cities, keywords, radius)

    # --- Queue poller ---
    def _poll_progress_queue(self):
        """Executes on Tkinter main loop to catch search engine events and update GUI elements."""
        try:
            while True:
                data = self.progress_queue.get_nowait()
                status = data.get("status")
                msg = data.get("message")
                
                # Update status text
                self.lbl_progress_status.configure(text=f"Status: {status.capitalize()} - {msg}")
                
                # Progress calculation
                grid_total = data.get("grid_total", 0)
                grid_proc = data.get("grid_processed", 0)
                found = data.get("found", 0)
                proc = data.get("processed", 0)

                # Set progress bar
                if status == "details" and found > 0:
                    pct = proc / found
                    self.progress_bar.set(pct)
                    self.lbl_progress_stats.configure(
                        text=f"Retrieving Details: {proc}/{found} ({int(pct*100)}%)"
                    )
                elif grid_total > 0:
                    pct = grid_proc / grid_total
                    self.progress_bar.set(pct)
                    self.lbl_progress_stats.configure(
                        text=f"Grid: {grid_proc}/{grid_total} ({int(pct*100)}%) | Found: {found}"
                    )
                else:
                    self.progress_bar.set(0)
                    self.lbl_progress_stats.configure(text="Grid: 0/0 | Found: 0")

                # Handle dynamic live updates
                if status == "business_found":
                    biz = data.get("data")
                    if biz:
                        # Prevent duplicate entries in memory by checking place_id
                        existing_ids = {item.get("place_id") for item in self.raw_data}
                        if biz.get("place_id") not in existing_ids:
                            self.raw_data.append(biz)
                            logger.info(f"GUI: Added '{biz.get('name')}' to display table. Total: {len(self.raw_data)}")
                            self._on_filter_changed()
                            self.update_dashboard()

                # Handle finishes
                elif status in ["finished", "stopped"]:
                    self.btn_start.configure(state="normal")
                    self.update_dashboard()
                    
                    if status == "finished":
                        messagebox.showinfo("Completed", "Bulk search process completed successfully!")
                
                elif status == "error":
                    # We just log errors but continue. If it's a critical crash, it's flagged.
                    logger.warning(f"Engine background warning: {msg}")

                self.progress_queue.task_done()
        except queue.Empty:
            pass

        # Loop again in 100ms
        self.after(100, self._poll_progress_queue)

    # --- Export options triggers ---
    def _get_export_filepath(self, file_ext: str) -> str:
        """Determines export path name."""
        def_folder = AppSettings.get_export_folder()
        time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Business_Search_Export_{time_str}{file_ext}"
        
        path = filedialog.asksaveasfilename(
            initialdir=def_folder,
            initialfile=filename,
            filetypes=[(f"{file_ext[1:].upper()} File", f"*{file_ext}")]
        )
        return path

    def _export_excel(self):
        if not self.filtered_data:
            messagebox.showwarning("Empty Dataset", "There are no business rows to export.")
            return

        file_path = self._get_export_filepath(".xlsx")
        if file_path:
            success = Exporter.export_to_excel(self.filtered_data, file_path)
            if success:
                messagebox.showinfo("Export Successful", f"Excel workbook successfully saved:\n{file_path}")
                self.update_dashboard()
            else:
                messagebox.showerror("Export Error", "An error occurred while compiling the Excel file.")

    def _export_csv(self):
        if not self.filtered_data:
            messagebox.showwarning("Empty Dataset", "There are no business rows to export.")
            return

        file_path = self._get_export_filepath(".csv")
        if file_path:
            success = Exporter.export_to_csv(self.filtered_data, file_path)
            if success:
                messagebox.showinfo("Export Successful", f"CSV file successfully saved:\n{file_path}")
                self.update_dashboard()
            else:
                messagebox.showerror("Export Error", "An error occurred while writing the CSV file.")

    def _export_json(self):
        if not self.filtered_data:
            messagebox.showwarning("Empty Dataset", "There are no business rows to export.")
            return

        file_path = self._get_export_filepath(".json")
        if file_path:
            success = Exporter.export_to_json(self.filtered_data, file_path)
            if success:
                messagebox.showinfo("Export Successful", f"JSON file successfully saved:\n{file_path}")
                self.update_dashboard()
            else:
                messagebox.showerror("Export Error", "An error occurred while writing the JSON file.")

    def _clear_results(self):
        if messagebox.askyesno("Clear Results", "Are you sure you want to permanently clear all search results?"):
            self.raw_data = []
            self._on_filter_changed()
            self.update_dashboard()
            messagebox.showinfo("Results Cleared", "All businesses have been cleared from memory.")
