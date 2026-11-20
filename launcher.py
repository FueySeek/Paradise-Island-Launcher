import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import uuid
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

import app as core

FONT = "Segoe UI"
MONO = "Consolas"

LANG_NAMES = [
    ("zh-CN", "简体中文"), ("zh-TW", "繁體中文"), ("en", "English"), ("ja", "日本語"), ("ko", "한국어"),
    ("ru", "Русский"), ("es", "Español"), ("fr", "Français"), ("de", "Deutsch"), ("pt-BR", "Português"),
]

DARK = dict(bg="#17191c", sidebar="#121417", panel="#1e2126", panel2="#23262c", border="#2b2f36",
            text="#dcdfe4", muted="#8b929c", accent="#c98a3f", accent_hover="#d99a4f", accent_text="#15171a",
            danger="#b4544c", danger_hover="#c4655c", input="#1a1d21", sel="#2a2e35", shadow="#101214")

LIGHT = dict(bg="#f2f3f5", sidebar="#e9ebee", panel="#ffffff", panel2="#f0f2f4", border="#d5d9de",
             text="#1c1f24", muted="#5f6773", accent="#a96f2a", accent_hover="#93601f", accent_text="#ffffff",
             danger="#a94a43", danger_hover="#963f39", input="#ffffff", sel="#e6e9ed", shadow="#dfe2e6")

with open(os.path.join(core.STATIC_DIR, "i18n.json"), encoding="utf-8") as f:
    I18N = json.load(f)


def human_size(value):
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%d %s" % (value, unit)) if unit == "B" else ("%.1f %s" % (value, unit))
        value /= 1024


def human_time(ts, lang):
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return ""


def read_tail(path, limit=60000):
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[-limit:]
    except OSError:
        return ""


class Dialog(ctk.CTkToplevel):
    def __init__(self, owner, title, width=560, height=420, modal=True):
        super().__init__(owner)
        self.owner = owner
        self.title(title)
        self.configure(fg_color=owner.c["bg"])
        self.geometry("%dx%d" % (width, height))
        self.minsize(width, height)
        self.transient(owner)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.after(30, self._place)
        if modal:
            self.grab_set()

    def _place(self):
        try:
            self.update_idletasks()
            x = self.owner.winfo_rootx() + (self.owner.winfo_width() - self.winfo_width()) // 2
            y = self.owner.winfo_rooty() + (self.owner.winfo_height() - self.winfo_height()) // 3
            self.geometry("+%d+%d" % (max(0, x), max(0, y)))
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class ConfirmDialog(Dialog):
    def __init__(self, owner, message, danger=False):
        super().__init__(owner, owner.t("common.confirm"), 440, 200)
        self.result = False
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(22, 0))
        ctk.CTkLabel(body, text=message, anchor="w", justify="left", wraplength=380,
                     text_color=owner.c["text"], font=(FONT, 12)).pack(fill="x")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=22, pady=18)
        owner.button(row, owner.t("common.cancel"), self._cancel, "normal", 92).pack(side="right")
        owner.button(row, owner.t("common.ok"), self._ok, "danger" if danger else "primary", 92).pack(side="right", padx=(0, 8))

    def _ok(self):
        self.result = True
        self.close()

    def _cancel(self):
        self.result = False
        self.close()


class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        self.cfg = core.load_config()
        self.lang = self.cfg.get("language", "zh-CN")
        if self.lang not in I18N:
            self.lang = "en"
        self.theme = self.cfg.get("theme", "dark")
        self.c = DARK if self.effective_theme() == "dark" else LIGHT
        self.page = os.environ.get("PIL_PAGE", "home")
        if self.page not in ("home", "versions", "accounts", "java", "settings"):
            self.page = "home"
        self.selected = self.cfg.get("last_version", "")
        self.install_version = ""
        self.versions = []
        self.versions_loaded = False
        self.instances = []
        self.java_list = []
        self.progress_job = None
        self.progress_kind = None
        self.status_text = self.t("home.ready")

        self.title(core.APP_NAME)
        self.geometry("1180x760")
        self.minsize(1000, 660)
        self.configure(fg_color=self.c["bg"])
        try:
            self.iconbitmap(os.path.join(core.IMAGES_DIR, "icon.ico"))
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.center_window()
        self.refresh_instances()
        self.build()
        self.load_java_async()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        x = max(0, (w - 1180) // 2)
        y = max(0, (h - 760) // 2)
        self.geometry("1180x760+%d+%d" % (x, y))

    def effective_theme(self):
        if self.theme == "system":
            try:
                import darkdetect
                return "light" if darkdetect.theme() == "Light" else "dark"
            except Exception:
                return "dark"
        return "light" if self.theme == "light" else "dark"

    def t(self, key, **kwargs):
        text = (I18N.get(self.lang) or {}).get(key)
        if not text:
            text = (I18N.get("en") or {}).get(key, key)
        for name, value in kwargs.items():
            text = text.replace("{" + name + "}", str(value))
        return text

    def status(self, text):
        self.status_text = text
        if getattr(self, "status_label", None) is not None:
            self.status_label.configure(text=text)

    def image(self, path, size):
        key = (path, size)
        if not hasattr(self, "_images"):
            self._images = {}
        if key not in self._images:
            try:
                img = Image.open(path).convert("RGB")
                self._images[key] = ctk.CTkImage(light_image=img, dark_image=img, size=size)
            except Exception:
                return None
        return self._images[key]

    def label(self, parent, text, size=12, bold=False, color=None, anchor="w", wrap=0, **kwargs):
        return ctk.CTkLabel(parent, text=text, anchor=anchor, justify="left", wraplength=wrap,
                            text_color=color or self.c["text"], font=(FONT, size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, kind="normal", width=0, height=32, anchor="center", **kwargs):
        colors = {
            "normal": dict(fg_color=self.c["panel2"], hover_color=self.c["sel"], text_color=self.c["text"], border_width=1, border_color=self.c["border"]),
            "primary": dict(fg_color=self.c["accent"], hover_color=self.c["accent_hover"], text_color=self.c["accent_text"], border_width=0),
            "danger": dict(fg_color="transparent", hover_color=self.c["panel2"], text_color=self.c["danger"], border_width=1, border_color=self.c["border"]),
            "ghost": dict(fg_color="transparent", hover_color=self.c["panel2"], text_color=self.c["muted"], border_width=0),
        }[kind]
        opts = dict(text=text, command=command, corner_radius=4, height=height, font=(FONT, 12),
                    anchor=anchor, **colors)
        if width:
            opts["width"] = width
        opts.update(kwargs)
        return ctk.CTkButton(parent, **opts)

    def card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=self.c["panel"], corner_radius=6,
                            border_width=1, border_color=self.c["border"], **kwargs)

    def build(self):
        for child in self.winfo_children():
            child.destroy()
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(self, width=196, corner_radius=0, fg_color=self.c["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(18, 22))
        icon = self.image(os.path.join(core.IMAGES_DIR, "icon.png"), (30, 30))
        if icon:
            ctk.CTkLabel(brand, text="", image=icon).pack(side="left")
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(titles, text="Paradise Island", text_color=self.c["text"],
                     font=(FONT, 12, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text="LAUNCHER", text_color=self.c["muted"],
                     font=(FONT, 9), anchor="w").pack(anchor="w")

        navs = [("home", "nav.home"), ("versions", "nav.instances"), ("accounts", "nav.accounts"),
                ("java", "nav.java"), ("settings", "nav.settings")]
        for key, text_key in navs:
            self.nav_item(sidebar, key, self.t(text_key))

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=(10, 10))
        self.button(bottom, self.t("theme." + self.theme), self.cycle_theme, "ghost", height=28, anchor="w").pack(fill="x")
        self.button(bottom, dict(LANG_NAMES).get(self.lang, "English"), self.open_language, "ghost", height=28, anchor="w").pack(fill="x")
        ctk.CTkLabel(bottom, text="v" + core.APP_VERSION, text_color=self.c["muted"],
                     font=(FONT, 9), anchor="w").pack(fill="x", padx=8, pady=(4, 0))

        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color=self.c["bg"])
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.main, fg_color="transparent", height=64)
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(18, 0))
        header.grid_columnconfigure(0, weight=1)
        self.header_title = ctk.CTkLabel(header, text="", text_color=self.c["text"],
                                         font=(FONT, 19, "bold"), anchor="w")
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_actions = ctk.CTkFrame(header, fg_color="transparent")
        self.header_actions.grid(row=0, column=1, sticky="e")

        self.body = ctk.CTkFrame(self.main, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=26, pady=(14, 12))

        status = ctk.CTkFrame(self, height=26, corner_radius=0, fg_color=self.c["sidebar"])
        status.grid(row=1, column=0, columnspan=2, sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status, text=self.status_text, text_color=self.c["muted"],
                                         font=(FONT, 10), anchor="w")
        self.status_label.grid(row=0, column=0, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(status, text=".minecraft", text_color=self.c["muted"], font=(FONT, 10), anchor="e").grid(
            row=0, column=1, sticky="e", padx=12, pady=4)

        self.render_page()

    def nav_item(self, parent, key, text):
        holder = ctk.CTkFrame(parent, fg_color="transparent", height=38)
        holder.pack(fill="x", padx=8, pady=1)
        active = self.page == key
        bar = ctk.CTkFrame(holder, width=3, height=36, corner_radius=0,
                           fg_color=self.c["accent"] if active else self.c["sidebar"])
        bar.pack(side="left", fill="y")
        btn = ctk.CTkButton(holder, text=text, anchor="w", corner_radius=3, height=36,
                            fg_color=self.c["panel2"] if active else "transparent",
                            hover_color=self.c["sel"],
                            text_color=self.c["text"] if active else self.c["muted"],
                            font=(FONT, 12, "bold" if active else "normal"),
                            command=lambda: self.show_page(key))
        btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

    def show_page(self, key):
        self.page = key
        self.build()

    def render_page(self):
        titles = {"home": "nav.home", "versions": "nav.instances", "accounts": "nav.accounts",
                  "java": "nav.java", "settings": "nav.settings"}
        self.header_title.configure(text=self.t(titles.get(self.page, "nav.home")))
        for child in self.header_actions.winfo_children():
            child.destroy()
        if self.page == "home":
            self.button(self.header_actions, self.t("common.refresh"), self.refresh_home, "ghost", 90).pack(side="left")
        elif self.page == "versions":
            self.button(self.header_actions, self.t("common.refresh"), self.refresh_versions, "ghost", 90).pack(side="left", padx=(0, 8))
            self.button(self.header_actions, self.t("instances.install"), self.install_dialog, "primary", 120).pack(side="left")
        elif self.page == "accounts":
            self.button(self.header_actions, self.t("common.refresh"), self.refresh_accounts, "ghost", 90).pack(side="left")
        elif self.page == "java":
            self.button(self.header_actions, self.t("common.refresh"), self.refresh_java, "ghost", 90).pack(side="left")
        for child in self.body.winfo_children():
            child.destroy()
        getattr(self, "page_" + self.page)()

    def empty_state(self, parent, text_key, hint_key=None):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(expand=True, fill="both", pady=60)
        ctk.CTkLabel(box, text=self.t(text_key), text_color=self.c["muted"], font=(FONT, 13)).pack()
        if hint_key:
            ctk.CTkLabel(box, text=self.t(hint_key), text_color=self.c["muted"], font=(FONT, 11)).pack(pady=(6, 0))
        return box

    def page_home(self):
        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        left = self.card(self.body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        left.configure(width=286)
        left.grid_propagate(False)
        ctk.CTkLabel(left, text=self.t("ui.instances"), text_color=self.c["muted"], font=(FONT, 10, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6))
        listing = ctk.CTkScrollableFrame(left, fg_color="transparent", corner_radius=0,
                                         scrollbar_button_color=self.c["border"],
                                         scrollbar_button_hover_color=self.c["muted"])
        listing.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        if not self.instances:
            self.empty_state(listing, "instances.empty", "instances.emptyHint")
        for inst in self.instances:
            self.instance_item(listing, inst)

        right = ctk.CTkFrame(self.body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        banner = self.card(right)
        banner.grid(row=0, column=0, sticky="ew")
        bg_path = self.background_path()
        img = self.image(bg_path, (760, 132)) if bg_path else None
        if img:
            ctk.CTkLabel(banner, text="", image=img, height=132).pack(fill="x")
        else:
            ctk.CTkFrame(banner, height=132, fg_color=self.c["panel2"]).pack(fill="x")

        detail = self.card(right)
        detail.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        inst = self.current_instance()
        if not inst:
            self.empty_state(detail, "home.noVersions", "home.noVersionsHint")
            return
        top = ctk.CTkFrame(detail, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(top, text=inst.get("display_name") or inst["id"], text_color=self.c["text"],
                     font=(FONT, 24, "bold"), anchor="w").pack(side="left")
        ctk.CTkButton(top, text="", width=1, height=1, fg_color="transparent", hover_color=self.c["panel"]).pack(side="left")
        ctk.CTkLabel(top, text=inst["id"], text_color=self.c["muted"], font=(FONT, 11), anchor="w").pack(
            side="left", padx=(10, 0), pady=(8, 0))

        meta = ctk.CTkFrame(detail, fg_color="transparent")
        meta.pack(fill="x", padx=20, pady=(8, 4))
        rows = [
            (self.t("common.version"), inst["id"]),
            (self.t("instances.loader"), self.t("loader." + (inst.get("loader") or "vanilla"))),
            (self.t("instances.memory"), "%s MB" % (inst.get("max_memory") or self.cfg.get("max_memory", 4096))),
            (self.t("home.mods"), str(inst.get("mod_count", 0))),
            (self.t("home.lastPlayed"), human_time(inst.get("last_launched"), self.lang) or self.t("home.never")),
        ]
        for i, (name, value) in enumerate(rows):
            ctk.CTkLabel(meta, text=name, text_color=self.c["muted"], font=(FONT, 11), anchor="w").grid(
                row=i // 3, column=(i % 3) * 2, sticky="w", padx=(0, 6), pady=3)
            ctk.CTkLabel(meta, text=value, text_color=self.c["text"], font=(FONT, 11), anchor="w").grid(
                row=i // 3, column=(i % 3) * 2 + 1, sticky="w", padx=(0, 26), pady=3)

        actions = ctk.CTkFrame(detail, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(12, 6))
        self.button(actions, self.t("home.launch"), lambda: self.launch(inst["id"]), "primary", 168, 38).pack(side="left")
        for text_key, cmd in (("home.folder", lambda: self.open_folder(inst["id"])),
                              ("ctx.log", lambda: self.open_log("instance", inst["id"])),
                              ("ctx.mods", lambda: self.open_mods(inst["id"])),
                              ("ctx.settings", lambda: self.open_instance_settings(inst))):
            self.button(actions, self.t(text_key), cmd, "normal", 92).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(detail, text=self.t("ui.recentLog"), text_color=self.c["muted"], font=(FONT, 10, "bold")).pack(
            anchor="w", padx=20, pady=(12, 4))
        box = ctk.CTkTextbox(detail, fg_color=self.c["input"], border_width=1, border_color=self.c["border"],
                             corner_radius=4, text_color=self.c["muted"], font=(MONO, 10), height=120)
        box.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        box.insert("1.0", self.instance_log_tail(inst["id"]) or self.t("log.empty"))
        box.configure(state="disabled")

    def instance_item(self, parent, inst):
        active = self.current_instance() and inst["id"] == self.current_instance()["id"]
        row = ctk.CTkFrame(parent, fg_color=self.c["panel2"] if active else "transparent",
                           corner_radius=4, height=52, cursor="hand2")
        row.pack(fill="x", pady=1)
        icon = self.image(os.path.join(core.IMAGES_DIR, "icon.png"), (26, 26))
        if icon:
            ctk.CTkLabel(row, text="", image=icon).pack(side="left", padx=(8, 8), pady=8)
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text, text=inst.get("display_name") or inst["id"], text_color=self.c["text"],
                     font=(FONT, 12, "bold"), anchor="w").pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(text, text="%s  ·  %s" % (inst["id"], self.t("loader." + (inst.get("loader") or "vanilla"))),
                     text_color=self.c["muted"], font=(FONT, 10), anchor="w").pack(anchor="w", pady=(0, 8))
        self.bind_click(row, inst["id"])

    def bind_click(self, widget, vid):
        widget.bind("<Button-1>", lambda e, i=vid: self.select_instance(i))
        for child in widget.winfo_children():
            self.bind_click(child, vid)

    def select_instance(self, vid):
        self.cfg["last_version"] = vid
        core.save_config(self.cfg)
        self.selected = vid
        self.show_page("home")

    def current_instance(self):
        for inst in self.instances:
            if inst["id"] == self.selected and inst.get("installed"):
                return inst
        for inst in self.instances:
            if inst.get("installed"):
                return inst
        return None

    def background_path(self):
        custom = self.cfg.get("custom_background") or ""
        if custom and os.path.isfile(custom):
            return custom
        idx = int(self.cfg.get("current_background") or 0)
        path = os.path.join(core.IMAGES_DIR, "background_%d.png" % (idx if 0 <= idx <= 3 else 0))
        return path if os.path.isfile(path) else os.path.join(core.IMAGES_DIR, "background_0.png")

    def instance_log_tail(self, vid):
        gdir = core.game_dir_for(vid)
        candidates = [os.path.join(gdir, "logs", "latest.log"), os.path.join(core.MC_DIR, "launcher.log")]
        for path in candidates:
            if os.path.isfile(path):
                return read_tail(path, 4000)
        return ""

    def refresh_instances(self):
        try:
            self.instances = core.list_instances()
        except Exception:
            self.instances = []
        if not self.current_instance() and self.instances:
            self.selected = self.instances[0]["id"]

    def page_versions(self):
        self.load_manifest_async(self.on_manifest_loaded)
        wrap = ctk.CTkScrollableFrame(self.body, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=self.c["border"],
                                      scrollbar_button_hover_color=self.c["muted"])
        wrap.pack(fill="both", expand=True)

        install = self.card(wrap)
        install.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(install, text=self.t("instances.install"), text_color=self.c["text"],
                     font=(FONT, 13, "bold")).pack(anchor="w", padx=16, pady=(14, 10))
        line = ctk.CTkFrame(install, fg_color="transparent")
        line.pack(fill="x", padx=16, pady=(0, 14))
        self.version_button = self.button(line, self.install_version or self.t("ui.noSelection"),
                                          self.pick_install_version, "normal", 260, 34, anchor="w")
        self.version_button.pack(side="left")
        self.loader_menu = ctk.CTkOptionMenu(line, values=[self.t("loader.vanilla"), "Forge", "NeoForge", "Fabric", "Quilt"],
                                             width=150, height=34, corner_radius=4,
                                             fg_color=self.c["panel2"], button_color=self.c["panel2"],
                                             button_hover_color=self.c["sel"], dropdown_fg_color=self.c["panel"],
                                             dropdown_hover_color=self.c["sel"], text_color=self.c["text"],
                                             dropdown_text_color=self.c["text"], font=(FONT, 12))
        self.loader_menu.pack(side="left", padx=10)
        self.button(line, self.t("instances.installBtn"), self.start_install, "primary", 130, 34).pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(install, height=6, corner_radius=3,
                                               progress_color=self.c["accent"], fg_color=self.c["panel2"])
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(install, text=self.t("home.ready"), text_color=self.c["muted"], font=(FONT, 10), anchor="w")
        self.progress_label.pack(anchor="w", padx=16, pady=(0, 12))

        table = self.card(wrap)
        table.pack(fill="x", pady=(0, 14))
        head = ctk.CTkFrame(table, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 8))
        for key, width in zip(("common.version", "instances.gameVersion", "instances.loader", "home.mods"),
                              (190, 120, 100, 60)):
            ctk.CTkLabel(head, text=self.t(key), text_color=self.c["muted"], font=(FONT, 10, "bold"),
                         width=width, anchor="w").pack(side="left", padx=(6, 12))
        if not self.instances:
            self.empty_state(table, "instances.empty", "instances.emptyHint")
        for inst in self.instances:
            self.version_table_row(table, inst)

    def version_table_row(self, parent, inst):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=48, cursor="hand2")
        row.pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(row, text=inst.get("display_name") or inst["id"], text_color=self.c["text"],
                     font=(FONT, 12, "bold"), anchor="w", width=190).pack(side="left", padx=(6, 12), pady=10)
        ctk.CTkLabel(row, text=inst["id"], text_color=self.c["muted"], font=(FONT, 11), anchor="w", width=120).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row, text=self.t("loader." + (inst.get("loader") or "vanilla")), text_color=self.c["muted"],
                     font=(FONT, 11), anchor="w", width=100).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row, text=str(inst.get("mod_count", 0)), text_color=self.c["muted"], font=(FONT, 11),
                     anchor="w", width=60).pack(side="left")
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=(0, 6))
        self.button(actions, self.t("home.launch"), lambda: self.launch(inst["id"]), "primary", 70, 28).pack(side="left", padx=(0, 6))
        self.button(actions, self.t("ctx.settings"), lambda: self.open_instance_settings(inst), "normal", 76, 28).pack(side="left", padx=(0, 6))
        self.button(actions, self.t("common.delete"), lambda: self.delete_instance(inst), "danger", 64, 28).pack(side="left")

    def page_accounts(self):
        wrap = ctk.CTkScrollableFrame(self.body, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=self.c["border"],
                                      scrollbar_button_hover_color=self.c["muted"])
        wrap.pack(fill="both", expand=True)

        current = self.active_account()
        name = current["name"] if current else (self.cfg.get("last_username") or "Steve")
        card = self.card(wrap)
        card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(card, text=self.t("accounts.current"), text_color=self.c["muted"],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.pack(fill="x", padx=16, pady=(0, 16))
        avatar = self.image(os.path.join(core.IMAGES_DIR, "avatar.png"), (56, 56))
        if avatar:
            ctk.CTkLabel(line, text="", image=avatar).pack(side="left")
        info = ctk.CTkFrame(line, fg_color="transparent")
        info.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(info, text=name, text_color=self.c["text"], font=(FONT, 18, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=self.t("accounts.microsoftType" if current and current.get("type") == "microsoft" else "accounts.offline"),
                     text_color=self.c["muted"], font=(FONT, 11), anchor="w").pack(anchor="w", pady=(2, 0))

        listing = self.card(wrap)
        listing.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(listing, text=self.t("accounts.list"), text_color=self.c["muted"],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        if not self.cfg.get("accounts"):
            ctk.CTkLabel(listing, text=self.t("accounts.empty"), text_color=self.c["muted"],
                         font=(FONT, 11)).pack(anchor="w", padx=16, pady=(0, 14))
        for account in self.cfg.get("accounts", []):
            self.account_row(listing, account)

        add = self.card(wrap)
        add.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(add, text=self.t("accounts.addOffline"), text_color=self.c["muted"],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        line = ctk.CTkFrame(add, fg_color="transparent")
        line.pack(fill="x", padx=16, pady=(0, 16))
        self.offline_entry = ctk.CTkEntry(line, width=260, height=34, corner_radius=4,
                                          fg_color=self.c["input"], border_color=self.c["border"],
                                          text_color=self.c["text"], font=(FONT, 12),
                                          placeholder_text=self.t("accounts.namePlaceholder"))
        self.offline_entry.pack(side="left")
        self.button(line, self.t("accounts.add"), self.add_offline, "primary", 90, 34).pack(side="left", padx=10)

    def account_row(self, parent, account):
        active = account["uuid"] == self.cfg.get("active_account")
        row = ctk.CTkFrame(parent, fg_color=self.c["panel2"] if active else "transparent", corner_radius=4)
        row.pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(row, text=account.get("name", ""), text_color=self.c["text"], font=(FONT, 12, "bold"),
                     anchor="w").pack(side="left", padx=12, pady=10)
        ctk.CTkLabel(row, text=self.t("accounts.microsoftType" if account.get("type") == "microsoft" else "accounts.offline"),
                     text_color=self.c["muted"], font=(FONT, 10), anchor="w").pack(side="left", padx=(0, 12))
        self.button(row, self.t("accounts.logout"), lambda: self.remove_account(account), "danger", 70, 26).pack(
            side="right", padx=(0, 8))
        if not active:
            self.button(row, self.t("accounts.switch"), lambda: self.use_account(account), "normal", 70, 26).pack(
                side="right", padx=(0, 6))

    def page_java(self):
        wrap = ctk.CTkScrollableFrame(self.body, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=self.c["border"],
                                      scrollbar_button_hover_color=self.c["muted"])
        wrap.pack(fill="both", expand=True)

        listing = self.card(wrap)
        listing.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(listing, text=self.t("java.installed"), text_color=self.c["muted"],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        if not self.java_list:
            ctk.CTkLabel(listing, text=self.t("java.none"), text_color=self.c["muted"], font=(FONT, 11)).pack(
                anchor="w", padx=16, pady=(0, 14))
        for item in self.java_list:
            self.java_row(listing, item)

        install = self.card(wrap)
        install.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(install, text=self.t("java.install"), text_color=self.c["muted"],
                     font=(FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        line = ctk.CTkFrame(install, fg_color="transparent")
        line.pack(fill="x", padx=16, pady=(0, 8))
        self.java_menu = ctk.CTkOptionMenu(line, values=["Java 8", "Java 11", "Java 16", "Java 17", "Java 21"],
                                           width=140, height=34, corner_radius=4,
                                           fg_color=self.c["panel2"], button_color=self.c["panel2"],
                                           button_hover_color=self.c["sel"], dropdown_fg_color=self.c["panel"],
                                           dropdown_hover_color=self.c["sel"], text_color=self.c["text"],
                                           dropdown_text_color=self.c["text"], font=(FONT, 12))
        self.java_menu.set("Java 17")
        self.java_menu.pack(side="left")
        self.button(line, self.t("java.install"), self.start_java_install, "primary", 120, 34).pack(side="left", padx=10)
        ctk.CTkLabel(install, text=self.t("java.installHint"), text_color=self.c["muted"], font=(FONT, 10)).pack(
            anchor="w", padx=16, pady=(0, 6))
        self.java_progress = ctk.CTkProgressBar(install, height=6, corner_radius=3,
                                                progress_color=self.c["accent"], fg_color=self.c["panel2"])
        self.java_progress.pack(fill="x", padx=16, pady=(0, 4))
        self.java_progress.set(0)
        self.java_progress_label = ctk.CTkLabel(install, text=self.t("home.ready"), text_color=self.c["muted"], font=(FONT, 10), anchor="w")
        self.java_progress_label.pack(anchor="w", padx=16, pady=(0, 12))

    def java_row(self, parent, item):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=52)
        row.pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(row, text="%s %s" % (self.t("nav.java"), item.get("version") or ""),
                     text_color=self.c["text"], font=(FONT, 12, "bold"), anchor="w", width=140).pack(side="left", padx=(12, 12), pady=10)
        ctk.CTkLabel(row, text=item.get("path", ""), text_color=self.c["muted"], font=(MONO, 9), anchor="w").pack(
            side="left", fill="x", expand=True)
        current = item.get("path") == self.cfg.get("java_path")
        if current:
            ctk.CTkLabel(row, text=self.t("java.using"), text_color=self.c["accent"], font=(FONT, 10, "bold")).pack(
                side="right", padx=12)
        else:
            self.button(row, self.t("java.use"), lambda: self.use_java(item), "normal", 90, 26).pack(side="right", padx=12)

    def page_settings(self):
        wrap = ctk.CTkScrollableFrame(self.body, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=self.c["border"],
                                      scrollbar_button_hover_color=self.c["muted"])
        wrap.pack(fill="both", expand=True)

        appearance = self.card(wrap)
        appearance.pack(fill="x", pady=(0, 14))
        self.section_title(appearance, "settings.appearance")
        theme_row = ctk.CTkFrame(appearance, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(theme_row, text=self.t("settings.theme"), text_color=self.c["text"], font=(FONT, 12),
                     anchor="w", width=160).pack(side="left")
        theme_values = [self.t("theme.dark"), self.t("theme.light"), self.t("theme.system")]
        current_theme = {"dark": theme_values[0], "light": theme_values[1], "system": theme_values[2]}.get(self.theme, theme_values[0])
        theme_menu = ctk.CTkOptionMenu(theme_row, values=theme_values, width=200, height=32, corner_radius=4,
                                       command=self.set_theme, fg_color=self.c["panel2"], button_color=self.c["panel2"],
                                       button_hover_color=self.c["sel"], dropdown_fg_color=self.c["panel"],
                                       dropdown_hover_color=self.c["sel"], text_color=self.c["text"],
                                       dropdown_text_color=self.c["text"], font=(FONT, 12))
        theme_menu.set(current_theme)
        theme_menu.pack(side="left")

        row = ctk.CTkFrame(appearance, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 10))
        ctk.CTkLabel(row, text=self.t("settings.language"), text_color=self.c["text"], font=(FONT, 12), anchor="w",
                     width=160).pack(side="left")
        self.language_menu = ctk.CTkOptionMenu(row, values=[name for _, name in LANG_NAMES], width=200, height=32,
                                               corner_radius=4, command=self.set_language,
                                               fg_color=self.c["panel2"], button_color=self.c["panel2"],
                                               button_hover_color=self.c["sel"], dropdown_fg_color=self.c["panel"],
                                               dropdown_hover_color=self.c["sel"], text_color=self.c["text"],
                                               dropdown_text_color=self.c["text"], font=(FONT, 12))
        current_name = dict(LANG_NAMES).get(self.lang, "English")
        self.language_menu.set(current_name)
        self.language_menu.pack(side="left")

        ctk.CTkLabel(appearance, text=self.t("settings.background"), text_color=self.c["text"], font=(FONT, 12),
                     anchor="w").pack(anchor="w", padx=16, pady=(4, 6))
        thumbs = ctk.CTkFrame(appearance, fg_color="transparent")
        thumbs.pack(fill="x", padx=16, pady=(0, 10))
        for i in range(4):
            path = os.path.join(core.IMAGES_DIR, "background_%d.png" % i)
            img = self.image(path, (150, 84))
            if not img:
                continue
            holder = ctk.CTkFrame(thumbs, fg_color=self.c["accent"] if int(self.cfg.get("current_background") or 0) == i else self.c["border"],
                                  corner_radius=3, width=156, height=90)
            holder.pack(side="left", padx=(0, 10))
            holder.pack_propagate(False)
            btn = ctk.CTkButton(holder, text="", image=img, width=150, height=84, corner_radius=2,
                                fg_color=self.c["panel2"], hover_color=self.c["sel"],
                                command=lambda idx=i: self.set_background(idx))
            btn.pack(padx=3, pady=3)
        self.button(thumbs, self.t("settings.upload"), self.upload_background, "normal", 110, 34).pack(side="left", padx=(16, 8))
        self.button(thumbs, self.t("settings.resetBg"), self.reset_background, "ghost", 100, 34).pack(side="left")

        game = self.card(wrap)
        game.pack(fill="x", pady=(0, 14))
        self.section_title(game, "settings.game")
        self.source_menu = self.simple_menu(game, "settings.source", ["BMCLAPI", "Official"],
                                            "BMCLAPI" if self.cfg.get("download_source", "bmclapi") == "bmclapi" else "Official",
                                            command=self.set_source)
        self.isolation_switch = self.switch_row(game, "settings.isolation", bool(self.cfg.get("version_isolation", True)))
        self.max_entry = self.entry_row(game, "settings.maxMemory", str(self.cfg.get("max_memory", 4096)))
        self.min_entry = self.entry_row(game, "settings.minMemory", str(self.cfg.get("min_memory", 512)))
        self.jvm_entry = self.entry_row(game, "settings.jvmArgs", self.cfg.get("jvm_args", ""))
        java_row = ctk.CTkFrame(game, fg_color="transparent")
        java_row.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(java_row, text=self.t("settings.javaPath"), text_color=self.c["text"], font=(FONT, 12),
                     anchor="w", width=220).pack(side="left")
        self.java_entry = ctk.CTkEntry(java_row, height=32, corner_radius=4, fg_color=self.c["input"],
                                       border_color=self.c["border"], text_color=self.c["text"], font=(FONT, 11))
        self.java_entry.pack(side="left", fill="x", expand=True)
        self.java_entry.insert(0, self.cfg.get("java_path", ""))
        self.button(java_row, self.t("ui.browse"), self.browse_java, "normal", 76, 32).pack(side="left", padx=(8, 0))

        microsoft = self.card(wrap)
        microsoft.pack(fill="x", pady=(0, 14))
        self.section_title(microsoft, "settings.microsoft")
        self.client_entry = self.entry_row(microsoft, "settings.clientId", self.cfg.get("microsoft_client_id", ""))
        ctk.CTkLabel(microsoft, text="http://127.0.0.1:10131/api/auth/microsoft/callback",
                     text_color=self.c["muted"], font=(MONO, 9), anchor="w").pack(anchor="w", padx=16, pady=(0, 12))

        about = self.card(wrap)
        about.pack(fill="x", pady=(0, 14))
        self.section_title(about, "settings.about")
        info = ctk.CTkFrame(about, fg_color="transparent")
        info.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(info, text=self.t("settings.version") + "  v" + core.APP_VERSION, text_color=self.c["muted"],
                     font=(FONT, 11), anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=core.MC_DIR, text_color=self.c["muted"], font=(MONO, 9), anchor="w").pack(anchor="w", pady=(4, 0))
        line = ctk.CTkFrame(about, fg_color="transparent")
        line.pack(fill="x", padx=16, pady=(4, 14))
        self.button(line, self.t("settings.openFolder"), lambda: os.startfile(core.MC_DIR), "normal", 110).pack(side="left")
        self.button(line, self.t("settings.viewLog"), lambda: self.open_log("launcher", ""), "normal", 130).pack(side="left", padx=8)
        self.button(line, self.t("settings.quit"), self.destroy, "danger", 110).pack(side="right")

        save = ctk.CTkFrame(wrap, fg_color="transparent")
        save.pack(fill="x", pady=(0, 10))
        self.button(save, self.t("common.save"), self.save_settings, "primary", 130, 36).pack(side="right")

    def section_title(self, parent, key):
        ctk.CTkLabel(parent, text=self.t(key), text_color=self.c["text"], font=(FONT, 13, "bold")).pack(
            anchor="w", padx=16, pady=(14, 10))

    def setting_row(self, parent, key, widget=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(row, text=self.t(key), text_color=self.c["text"], font=(FONT, 12), anchor="w",
                     width=160).pack(side="left")
        return row

    def simple_menu(self, parent, label_key, values, value, command=None):
        row = self.setting_row(parent, label_key)
        menu = ctk.CTkOptionMenu(row, values=values, width=200, height=32, corner_radius=4,
                                 command=command,
                                 fg_color=self.c["panel2"], button_color=self.c["panel2"],
                                 button_hover_color=self.c["sel"], dropdown_fg_color=self.c["panel"],
                                 dropdown_hover_color=self.c["sel"], text_color=self.c["text"],
                                 dropdown_text_color=self.c["text"], font=(FONT, 12))
        menu.set(value)
        menu.pack(side="left")
        return menu

    def switch_row(self, parent, key, value):
        row = self.setting_row(parent, key)
        switch = ctk.CTkSwitch(row, text="", width=44, switch_width=40, switch_height=20,
                               progress_color=self.c["accent"], button_color=self.c["text"],
                               fg_color=self.c["border"], font=(FONT, 11))
        if value:
            switch.select()
        switch.pack(side="left")
        return switch

    def entry_row(self, parent, key, value, width=280):
        row = self.setting_row(parent, key)
        entry = ctk.CTkEntry(row, width=width, height=32, corner_radius=4, fg_color=self.c["input"],
                             border_color=self.c["border"], text_color=self.c["text"], font=(FONT, 12))
        entry.pack(side="left")
        entry.insert(0, value or "")
        return entry

    def refresh_home(self):
        self.refresh_instances()
        self.show_page("home")

    def refresh_accounts(self):
        self.cfg = core.load_config()
        self.show_page("accounts")

    def refresh_versions(self):
        self.refresh_instances()
        self.show_page("versions")
        self.load_manifest_async()

    def load_manifest_async(self, callback=None):
        if self.versions_loaded:
            if callback:
                callback()
            return
        def worker():
            try:
                data = core.fetch_manifest()
                self.versions = data.get("versions", [])
                self.versions_loaded = True
            except Exception as exc:
                self.after(0, lambda: self.status(str(exc)))
            self.after(0, lambda: callback() if callback else None)
        threading.Thread(target=worker, daemon=True).start()

    def on_manifest_loaded(self):
        if not self.install_version and self.versions:
            releases = [item for item in self.versions if item.get("type") == "release"]
            self.install_version = (releases[0] if releases else self.versions[0]).get("id", "")
        if self.page == "versions" and getattr(self, "version_button", None) is not None:
            self.version_button.configure(text=self.install_version or self.t("ui.noSelection"))

    def pick_install_version(self):
        if not self.versions_loaded:
            self.load_manifest_async()
            self.status(self.t("common.loading"))
        VersionPicker(self, False, self.set_install_version)

    def set_install_version(self, vid):
        self.install_version = vid
        if getattr(self, "version_button", None) is not None:
            self.version_button.configure(text=vid)

    def install_dialog(self):
        self.show_page("versions")
        self.pick_install_version()

    def start_install(self):
        if not self.install_version:
            self.pick_install_version()
            return
        loader_label = self.loader_menu.get() if getattr(self, "loader_menu", None) else self.t("loader.vanilla")
        loaders = {self.t("loader.vanilla"): "vanilla", "Forge": "forge", "NeoForge": "neoforge",
                   "Fabric": "fabric", "Quilt": "quilt"}
        loader = loaders.get(loader_label, "vanilla")
        if core.get_progress().get("status") == "running":
            self.status(self.t("instances.installing"))
            return
        self.status(self.t("toast.installStarted"))
        threading.Thread(target=core.do_install, args=(self.install_version, loader), daemon=True).start()
        self.track_progress("install")

    def track_progress(self, kind):
        self.progress_kind = kind
        if self.progress_job:
            try:
                self.after_cancel(self.progress_job)
            except Exception:
                pass
        self.poll_progress()

    def poll_progress(self):
        progress = core.get_progress()
        status = progress.get("status")
        percent = max(0.0, min(1.0, (progress.get("percent") or 0) / 100.0))
        text = self.progress_text(progress)
        if self.progress_kind == "install" and getattr(self, "progress_bar", None) is not None:
            try:
                self.progress_bar.set(percent)
                self.progress_label.configure(text=text)
            except Exception:
                pass
        elif self.progress_kind == "java" and getattr(self, "java_progress", None) is not None:
            try:
                self.java_progress.set(percent)
                self.java_progress_label.configure(text=text)
            except Exception:
                pass
        if status == "running":
            self.progress_job = self.after(400, self.poll_progress)
            return
        self.progress_job = None
        if self.progress_kind == "install":
            if status == "done":
                self.status(self.t("toast.installDone"))
                self.refresh_instances()
                self.show_page("versions")
            elif status == "error":
                self.status(progress.get("message") or self.t("instances.installFailed"))
        elif self.progress_kind == "java":
            if status == "done":
                self.status(self.t("java.done"))
                self.load_java_async()
            elif status == "error":
                self.status(self.t("java.failed"))
        self.progress_kind = None

    def progress_text(self, progress):
        stage = progress.get("stage") or "prepare"
        label = self.t("stage." + stage)
        message = progress.get("message") or ""
        if progress.get("status") == "error":
            return self.t("stage.error") + (": " + message if message else "")
        if stage == "loader" and message:
            return label + "  " + message
        if stage in ("libraries", "assets") and message:
            return label + "  " + message
        if stage == "done" and message.startswith("warn:"):
            return self.t("instances.installDone") + " (" + message[5:] + ")"
        return label

    def launch(self, vid):
        self.status(self.t("home.launching"))
        threading.Thread(target=self.launch_worker, args=(vid,), daemon=True).start()

    def launch_worker(self, vid):
        try:
            cmd, gdir = core.build_command(vid)
            core.game_dir_for(vid)
            log_path = os.path.join(core.MC_DIR, "launcher.log")
            log_file = open(log_path, "w", encoding="utf-8", errors="replace")
            flags = subprocess.CREATE_NO_WINDOW if core.OS_NAME == "windows" else 0
            proc = subprocess.Popen(cmd, cwd=gdir, stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags)
            cfg = core.load_config()
            cfg["last_version"] = vid
            core.save_config(cfg)
            try:
                core.write_instance_cfg(vid, {"last_launched": int(time.time())})
            except Exception:
                pass
            time.sleep(2.5)
            code = proc.poll()
            if code is not None:
                self.after(0, lambda: self.launch_failed(read_tail(log_path, 4000)))
            else:
                self.after(0, lambda: self.status(self.t("toast.launched", pid=proc.pid)))
                self.after(0, self.refresh_home)
        except Exception as exc:
            self.after(0, lambda: self.launch_failed(str(exc)))

    def launch_failed(self, detail):
        self.status(self.t("toast.launchFailed"))
        LogDialog(self, self.t("toast.launchFailed"), "launcher", None, detail)

    def open_folder(self, vid):
        try:
            os.startfile(core.game_dir_for(vid))
        except Exception as exc:
            self.status(str(exc))

    def open_log(self, source, vid):
        LogDialog(self, self.t("log.title"), source, vid)

    def open_mods(self, vid):
        ModsDialog(self, vid)

    def open_instance_settings(self, inst):
        InstanceDialog(self, inst)

    def delete_instance(self, inst):
        if not ConfirmDialog(self, self.t("instances.confirmDelete") + "\n" + inst["id"], True).result:
            return
        try:
            shutil.rmtree(core.VERSIONS_DIR + os.sep + inst["id"])
        except Exception as exc:
            self.status(str(exc))
            return
        self.status(self.t("toast.deleted"))
        self.refresh_instances()
        self.show_page("versions")

    def active_account(self):
        active = self.cfg.get("active_account")
        for account in self.cfg.get("accounts", []):
            if account.get("uuid") == active:
                return account
        return None

    def add_offline(self):
        name = self.offline_entry.get().strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name or ""):
            self.status(self.t("accounts.invalidName"))
            return
        uid = str(uuid.UUID(hashlib.md5(name.encode()).hexdigest()))
        accounts = [account for account in self.cfg.get("accounts", []) if account.get("uuid") != uid]
        accounts.append({"uuid": uid, "name": name, "type": "offline"})
        self.cfg["accounts"] = accounts
        self.cfg["active_account"] = uid
        self.cfg["last_username"] = name
        core.save_config(self.cfg)
        self.status(self.t("toast.added"))
        self.show_page("accounts")

    def use_account(self, account):
        self.cfg["active_account"] = account["uuid"]
        self.cfg["last_username"] = account["name"]
        core.save_config(self.cfg)
        self.status(self.t("toast.switched"))
        self.show_page("accounts")

    def remove_account(self, account):
        self.cfg["accounts"] = [item for item in self.cfg.get("accounts", []) if item.get("uuid") != account["uuid"]]
        if self.cfg.get("active_account") == account["uuid"]:
            self.cfg["active_account"] = self.cfg["accounts"][0]["uuid"] if self.cfg["accounts"] else ""
        core.save_config(self.cfg)
        self.status(self.t("toast.logout"))
        self.show_page("accounts")

    def refresh_java(self):
        self.load_java_async()

    def load_java_async(self):
        def worker():
            try:
                items = core.scan_installed_javas()
            except Exception:
                items = []
            self.java_list = items
            self.after(0, lambda: self.show_page("java") if self.page == "java" else None)
        threading.Thread(target=worker, daemon=True).start()

    def use_java(self, item):
        self.cfg["java_path"] = item.get("path", "")
        core.save_config(self.cfg)
        self.status(self.t("toast.javaSet"))
        self.show_page("java")

    def start_java_install(self):
        if core.get_progress().get("status") == "running":
            self.status(self.t("instances.installing"))
            return
        label = self.java_menu.get()
        try:
            major = int(label.split()[-1])
        except Exception:
            major = 17
        self.status(self.t("java.downloading"))
        threading.Thread(target=core.ensure_java, args=(major,), daemon=True).start()
        self.track_progress("java")

    def browse_java(self):
        path = filedialog.askopenfilename(filetypes=[("Java", "java.exe"), ("All", "*.*")])
        if path:
            self.java_entry.delete(0, "end")
            self.java_entry.insert(0, path)

    def cycle_theme(self):
        order = ["dark", "light", "system"]
        self.set_theme(self.t("theme." + order[(order.index(self.theme) + 1) % 3]))

    def set_theme(self, label):
        mapping = {self.t("theme.dark"): "dark", self.t("theme.light"): "light", self.t("theme.system"): "system"}
        self.theme = mapping.get(label, "dark")
        self.cfg["theme"] = self.theme
        core.save_config(self.cfg)
        self.c = DARK if self.effective_theme() == "dark" else LIGHT
        self.build()

    def open_language(self):
        self.show_page("settings")

    def set_language(self, name):
        mapping = {label: code for code, label in LANG_NAMES}
        lang = mapping.get(name, "en")
        self.lang = lang
        self.cfg["language"] = lang
        core.save_config(self.cfg)
        self.build()

    def set_background(self, idx):
        self.cfg["current_background"] = idx
        core.save_config(self.cfg)
        self.show_page("settings")

    def upload_background(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")])
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        dest = os.path.join(core.BG_DIR, "custom" + ext)
        try:
            shutil.copyfile(path, dest)
        except Exception as exc:
            self.status(str(exc))
            return
        self.cfg["custom_background"] = dest
        self.cfg["current_background"] = 0
        core.save_config(self.cfg)
        self.status(self.t("toast.bgUpdated"))
        self.show_page("settings")

    def reset_background(self):
        old = self.cfg.get("custom_background")
        if old and os.path.isfile(old):
            try:
                os.remove(old)
            except Exception:
                pass
        self.cfg["custom_background"] = ""
        self.cfg["current_background"] = 0
        core.save_config(self.cfg)
        self.status(self.t("toast.bgUpdated"))
        self.show_page("settings")

    def set_source(self, label):
        self.cfg["download_source"] = "bmclapi" if label == "BMCLAPI" else "official"
        core.save_config(self.cfg)

    def save_settings(self):
        self.cfg["download_source"] = "bmclapi" if self.source_menu.get() == "BMCLAPI" else "official"
        self.cfg["version_isolation"] = bool(self.isolation_switch.get())
        try:
            self.cfg["max_memory"] = int(self.max_entry.get())
        except Exception:
            pass
        try:
            self.cfg["min_memory"] = int(self.min_entry.get())
        except Exception:
            pass
        self.cfg["jvm_args"] = self.jvm_entry.get().strip()
        self.cfg["java_path"] = self.java_entry.get().strip()
        self.cfg["microsoft_client_id"] = self.client_entry.get().strip()
        core.save_config(self.cfg)
        self.status(self.t("settings.saved"))


class VersionPicker(Dialog):
    def __init__(self, owner, installed_only, on_pick):
        super().__init__(owner, owner.t("instances.gameVersion"), 560, 620)
        self.owner = owner
        self.on_pick = on_pick
        self.installed_only = installed_only
        self.search = ctk.CTkEntry(self, height=34, corner_radius=4, fg_color=owner.c["input"],
                                   border_color=owner.c["border"], text_color=owner.c["text"],
                                   placeholder_text=owner.t("instances.searchVersion"))
        self.search.pack(fill="x", padx=16, pady=(16, 8))
        self.search.bind("<KeyRelease>", lambda e: self.render())
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=owner.c["border"],
                                           scrollbar_button_hover_color=owner.c["muted"])
        self.list.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        if not installed_only:
            owner.load_manifest_async(self.safe_render)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 12))
        owner.button(footer, owner.t("common.close"), self.close, "normal", 90).pack(side="right")
        self.render()

    def safe_render(self):
        try:
            if self.winfo_exists():
                self.render()
        except Exception:
            pass

    def render(self):
        for child in self.list.winfo_children():
            child.destroy()
        text = self.search.get().strip().lower()
        if self.installed_only:
            items = [inst["id"] for inst in self.owner.instances if inst.get("installed")]
            items = [{"id": vid, "type": ""} for vid in items]
        else:
            items = self.owner.versions
        shown = 0
        for item in items:
            vid = item.get("id", "")
            if text and text not in vid.lower():
                continue
            if shown >= 300:
                break
            shown += 1
            selected = vid == (self.owner.selected if self.installed_only else self.owner.install_version)
            row = ctk.CTkFrame(self.list, fg_color=self.owner.c["panel2"] if selected else "transparent",
                               corner_radius=3, cursor="hand2")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=vid, text_color=self.owner.c["text"], font=(FONT, 12), anchor="w").pack(
                side="left", padx=10, pady=7)
            kind = item.get("type") or ""
            if kind:
                label = {"release": "filter.release", "snapshot": "filter.snapshot"}.get(kind, "filter.old")
                ctk.CTkLabel(row, text=self.owner.t(label), text_color=self.owner.c["muted"],
                             font=(FONT, 9)).pack(side="left", padx=8)
            if not self.installed_only and any(inst["id"] == vid and inst.get("installed") for inst in self.owner.instances):
                ctk.CTkLabel(row, text=self.owner.t("instances.installed"), text_color=self.owner.c["accent"],
                             font=(FONT, 9)).pack(side="right", padx=10)
            if not selected:
                row.bind("<Enter>", lambda e, r=row: r.configure(fg_color=self.owner.c["sel"]))
                row.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))
            row.bind("<Button-1>", lambda e, v=vid: self.pick(v))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, v=vid: self.pick(v))

    def pick(self, vid):
        self.on_pick(vid)
        self.close()


class LogDialog(Dialog):
    def __init__(self, owner, title, source, vid=None, initial=None):
        super().__init__(owner, title, 820, 560)
        self.owner = owner
        self.source = source
        self.vid = vid
        self.text = ctk.CTkTextbox(self, fg_color="#0f1114" if owner.effective_theme() == "dark" else "#fbfbfc",
                                   text_color=owner.c["text"], font=(MONO, 10), corner_radius=4)
        self.text.pack(fill="both", expand=True, padx=14, pady=(14, 6))
        line = ctk.CTkFrame(self, fg_color="transparent")
        line.pack(fill="x", padx=14, pady=(0, 12))
        owner.button(line, owner.t("common.refresh"), self.load, "normal", 90).pack(side="left")
        owner.button(line, owner.t("common.copy"), self.copy, "normal", 90).pack(side="left", padx=8)
        owner.button(line, owner.t("common.close"), self.close, "primary", 90).pack(side="right")
        if initial is not None:
            self.set_text(initial)
        else:
            self.load()

    def set_text(self, value):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if value:
            self.text.insert("1.0", value)
        else:
            self.text.insert("1.0", self.owner.t("log.empty"))
        self.text.see("end")
        self.text.configure(state="disabled")

    def load(self):
        if self.source == "instance":
            gdir = core.game_dir_for(self.vid)
            paths = [os.path.join(gdir, "logs", "latest.log"), os.path.join(core.MC_DIR, "launcher.log")]
            content = ""
            for path in paths:
                if os.path.isfile(path):
                    content = read_tail(path, 120000)
                    break
            self.set_text(content)
        else:
            self.set_text(read_tail(os.path.join(core.MC_DIR, "launcher.log"), 120000))

    def copy(self):
        value = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(value)
        self.owner.status(self.owner.t("toast.copied"))


class ModsDialog(Dialog):
    def __init__(self, owner, vid):
        super().__init__(owner, owner.t("mods.title") + " · " + vid, 720, 560)
        self.owner = owner
        self.vid = vid
        self.mods_dir = os.path.join(core.game_dir_for(vid), "mods")
        os.makedirs(self.mods_dir, exist_ok=True)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(head, text=owner.t("mods.hint"), text_color=owner.c["muted"], font=(FONT, 10)).pack(side="left")
        owner.button(head, owner.t("mods.import"), self.import_mods, "primary", 110).pack(side="right")
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=owner.c["border"],
                                           scrollbar_button_hover_color=owner.c["muted"])
        self.list.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 12))
        owner.button(footer, owner.t("common.close"), self.close, "normal", 90).pack(side="right")
        self.render()

    def render(self):
        for child in self.list.winfo_children():
            child.destroy()
        files = []
        for name in sorted(os.listdir(self.mods_dir), key=str.lower):
            low = name.lower()
            if low.endswith(".jar") or low.endswith(".jar.disabled"):
                files.append(name)
        if not files:
            box = ctk.CTkFrame(self.list, fg_color="transparent")
            box.pack(fill="both", expand=True, pady=60)
            ctk.CTkLabel(box, text=self.owner.t("mods.empty"), text_color=self.owner.c["muted"],
                         font=(FONT, 11)).pack()
            return
        for name in files:
            path = os.path.join(self.mods_dir, name)
            enabled = name.lower().endswith(".jar")
            row = ctk.CTkFrame(self.list, fg_color="transparent", height=46)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=name, text_color=self.owner.c["text"] if enabled else self.owner.c["muted"],
                         font=(FONT, 11), anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(row, text=human_size(os.path.getsize(path)), text_color=self.owner.c["muted"],
                         font=(FONT, 9), width=70).pack(side="left")
            self.owner.button(row, self.owner.t("mods.disable" if enabled else "mods.enable"),
                              lambda n=name: self.toggle(n), "normal", 76, 26).pack(side="right", padx=(6, 10))
            self.owner.button(row, self.owner.t("mods.delete"), lambda n=name: self.remove(n), "danger", 64, 26).pack(
                side="right")

    def toggle(self, name):
        path = os.path.join(self.mods_dir, name)
        target = path[:-9] if name.lower().endswith(".jar.disabled") else path + ".disabled"
        try:
            os.replace(path, target)
        except Exception as exc:
            self.owner.status(str(exc))
            return
        self.render()

    def remove(self, name):
        if not ConfirmDialog(self.owner, self.owner.t("mods.confirmDelete") + "\n" + name, True).result:
            return
        try:
            os.remove(os.path.join(self.mods_dir, name))
        except Exception as exc:
            self.owner.status(str(exc))
            return
        self.owner.status(self.owner.t("mods.deleted"))
        self.render()

    def import_mods(self):
        paths = filedialog.askopenfilenames(filetypes=[("Mods", "*.jar")])
        saved = 0
        for path in paths:
            try:
                shutil.copyfile(path, os.path.join(self.mods_dir, os.path.basename(path)))
                saved += 1
            except Exception:
                pass
        if saved:
            self.owner.status(self.owner.t("mods.imported", n=saved))
        self.render()


class InstanceDialog(Dialog):
    def __init__(self, owner, inst):
        super().__init__(owner, owner.t("inst.title") + " · " + inst["id"], 520, 520)
        self.owner = owner
        self.inst = inst
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(16, 0))
        self.name_entry = self.field(body, "inst.name", inst.get("display_name") or inst["id"])
        self.memory_entry = self.field(body, "inst.memory", str(inst.get("max_memory") or ""))
        self.jvm_entry = self.field(body, "inst.jvm", inst.get("jvm_args") or "")
        self.java_entry = self.field(body, "inst.java", inst.get("java_path") or "")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(row, text=owner.t("inst.isolation"), text_color=owner.c["text"], font=(FONT, 12),
                     anchor="w", width=150).pack(side="left")
        self.iso = ctk.CTkSwitch(row, text="", switch_width=40, switch_height=20,
                                 progress_color=owner.c["accent"], button_color=owner.c["text"],
                                 fg_color=owner.c["border"])
        if inst.get("isolated"):
            self.iso.select()
        self.iso.pack(side="left")
        icon_row = ctk.CTkFrame(body, fg_color="transparent")
        icon_row.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(icon_row, text=owner.t("inst.icon"), text_color=owner.c["text"], font=(FONT, 12),
                     anchor="w", width=150).pack(side="left")
        owner.button(icon_row, owner.t("settings.upload"), self.set_icon, "normal", 100).pack(side="left")
        owner.button(icon_row, owner.t("settings.resetBg"), self.reset_icon, "ghost", 100).pack(side="left", padx=8)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=18, pady=14)
        owner.button(footer, owner.t("common.cancel"), self.close, "normal", 90).pack(side="right")
        owner.button(footer, owner.t("common.save"), self.save, "primary", 90).pack(side="right", padx=8)

    def field(self, parent, key, value):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(row, text=self.owner.t(key), text_color=self.owner.c["text"], font=(FONT, 12),
                     anchor="w", width=150).pack(side="left")
        entry = ctk.CTkEntry(row, height=32, corner_radius=4, fg_color=self.owner.c["input"],
                             border_color=self.owner.c["border"], text_color=self.owner.c["text"], font=(FONT, 11))
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, value or "")
        return entry

    def save(self):
        data = {
            "display_name": self.name_entry.get().strip() or self.inst["id"],
            "max_memory": int(self.memory_entry.get()) if self.memory_entry.get().strip().isdigit() else None,
            "jvm_args": self.jvm_entry.get().strip(),
            "java_path": self.java_entry.get().strip() or None,
            "version_isolation": bool(self.iso.get()),
        }
        core.write_instance_cfg(self.inst["id"], data)
        self.owner.status(self.owner.t("inst.saved"))
        self.owner.refresh_instances()
        self.close()
        self.owner.show_page(self.owner.page)

    def set_icon(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not path:
            return
        try:
            target = os.path.join(core.game_dir_for(self.inst["id"]), "icon.png")
            Image.open(path).convert("RGBA").resize((128, 128), Image.LANCZOS).save(target)
            self.owner.status(self.owner.t("toast.bgUpdated"))
        except Exception as exc:
            self.owner.status(str(exc))

    def reset_icon(self):
        target = os.path.join(core.game_dir_for(self.inst["id"]), "icon.png")
        if os.path.isfile(target):
            try:
                os.remove(target)
            except Exception:
                pass


def write_error(detail):
    try:
        path = os.path.join(core.BASE_DIR, "launcher-error.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write(detail)
    except Exception:
        pass


def main():
    app = Launcher()
    app.report_callback_exception = lambda exc_type, exc, tb: write_error(
        "".join(__import__("traceback").format_exception(exc_type, exc, tb))
    )
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        write_error(traceback.format_exc())
