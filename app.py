import calendar
import csv
import html
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

from lunar_python import Solar


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "diary.db"
TABLE_DIR = APP_DIR / "data"
ENSCRIPT_PATH = Path(r"D:\softs1\印象笔记\ENScript.exe")
EVERNOTE_NOTEBOOK = "B1-日记"
SINGLE_INSTANCE_PORT = 48765
THEME = {"bg": "#D8E2EE", "panel": "#FFFFFF", "accent": "#3B6EA8"}

TEXT_MAIN = "#212529"
TEXT_SECONDARY = "#495057"
TEXT_COLOR = TEXT_MAIN
RIGHT_PANEL_BG = "#F2F5F9"
RIGHT_TITLE_COLOR = TEXT_MAIN
RIGHT_AUX_COLOR = TEXT_SECONDARY
RIGHT_ACCENT_COLOR = "#D35400"
RIGHT_INFO_BG = "#FFFFFF"
RIGHT_EDITOR_BG = "#FFFFFF"
BORDER_COLOR = "#CED4DA"
STEM_WUXING_COLORS = {
    "甲": "#3B8F5A",
    "乙": "#3B8F5A",
    "丙": "#D85B5B",
    "丁": "#D85B5B",
    "戊": "#B8862B",
    "己": "#B8862B",
    "庚": "#D4A017",
    "辛": "#D4A017",
    "壬": "#397DB8",
    "癸": "#397DB8",
}
BRANCH_WUXING_COLORS = {
    "子": "#397DB8",
    "丑": "#B8862B",
    "寅": "#3B8F5A",
    "卯": "#3B8F5A",
    "辰": "#B8862B",
    "巳": "#D85B5B",
    "午": "#D85B5B",
    "未": "#B8862B",
    "申": "#D4A017",
    "酉": "#D4A017",
    "戌": "#B8862B",
    "亥": "#397DB8",
}


class DiaryStore:
    def __init__(self, db_path=DB_PATH, table_dir=None):
        db_path = Path(db_path)
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.table_dir = Path(table_dir) if table_dir else db_path.parent
        self.backup_dir = self.table_dir / "data_bak"
        self.connection = sqlite3.connect(db_path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diaries (
                diary_date TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                todo_date TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()
        self.export_table()
        self.export_todos()

    def get(self, diary_date):
        row = self.connection.execute(
            "SELECT content FROM diaries WHERE diary_date = ?", (diary_date,)
        ).fetchone()
        return row[0] if row else ""

    def backup_data(self):
        files = [self.db_path, *self.table_dir.glob("*.csv")]
        files = [path for path in files if path.exists() and path.stat().st_size > 0]
        if not files:
            return None

        backup_path = self.backup_dir / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path.mkdir(parents=True, exist_ok=True)
        for path in files:
            shutil.copy2(path, backup_path / path.name)
        self.prune_backups()
        return backup_path

    def prune_backups(self, keep=5):
        if not self.backup_dir.exists():
            return
        backups = sorted(
            [path for path in self.backup_dir.iterdir() if path.is_dir()],
            key=lambda path: path.name,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            shutil.rmtree(old_backup)

    def merge_stale_content(self, current_content, content, expected_content):
        if expected_content is None or current_content == expected_content:
            return content
        if not content.strip():
            return current_content
        if not current_content.strip():
            return content

        new_content = content
        if expected_content and content.startswith(expected_content):
            new_content = content[len(expected_content) :].lstrip("\r\n")
        elif expected_content:
            return current_content
        if not new_content.strip() or new_content.strip() in current_content:
            return current_content
        return f"{current_content.rstrip()}\n{new_content.rstrip()}"

    def save(self, diary_date, content, expected_content=None):
        content = content.rstrip()
        current_content = self.get(diary_date)
        if (
            expected_content is not None
            and current_content != expected_content
            and not content.strip()
        ):
            return False
        if (
            expected_content
            and current_content != expected_content
            and content.strip()
            and not content.startswith(expected_content)
        ):
            return False
        content = self.merge_stale_content(current_content, content, expected_content)
        if content:
            self.backup_data()
            self.connection.execute(
                """
                INSERT INTO diaries (diary_date, content, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(diary_date) DO UPDATE SET
                    content = excluded.content,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (diary_date, content),
            )
        else:
            if expected_content is not None and current_content != expected_content:
                return False
            self.backup_data()
            self.connection.execute(
                "DELETE FROM diaries WHERE diary_date = ?", (diary_date,)
            )
        self.connection.commit()
        self.export_table()
        return True

    def get_todo(self, todo_date):
        row = self.connection.execute(
            "SELECT content FROM todos WHERE todo_date = ?", (todo_date,)
        ).fetchone()
        return row[0] if row else ""

    def save_todo(self, todo_date, content, expected_content=None):
        content = content.rstrip()
        current_content = self.get_todo(todo_date)
        if (
            expected_content is not None
            and current_content != expected_content
            and not content.strip()
        ):
            return False
        if (
            expected_content
            and current_content != expected_content
            and content.strip()
            and not content.startswith(expected_content)
        ):
            return False
        content = self.merge_stale_content(current_content, content, expected_content)
        if content:
            self.backup_data()
            self.connection.execute(
                """
                INSERT INTO todos (todo_date, content, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(todo_date) DO UPDATE SET
                    content = excluded.content,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (todo_date, content),
            )
        else:
            if expected_content is not None and current_content != expected_content:
                return False
            self.backup_data()
            self.connection.execute("DELETE FROM todos WHERE todo_date = ?", (todo_date,))
        self.connection.commit()
        self.export_todos()
        return True

    def export_todos(self):
        rows = self.connection.execute(
            "SELECT todo_date, content FROM todos ORDER BY todo_date"
        ).fetchall()
        self.table_dir.mkdir(parents=True, exist_ok=True)
        with self.todo_table_path().open("w", encoding="utf-8-sig", newline="") as table:
            writer = csv.writer(table)
            writer.writerow(("时间", "农历", "年月日干支", "待办内容"))
            for todo_date, content in rows:
                selected_date = datetime.strptime(todo_date, "%Y-%m-%d").date()
                lunar_date, ganzhi, _wuxing = get_date_info(selected_date)
                writer.writerow((todo_date, lunar_date, ganzhi, content))

    def todo_table_path(self):
        return self.table_dir / "待办事项.csv"

    def export_table(self):
        rows = self.connection.execute(
            "SELECT diary_date, content FROM diaries ORDER BY diary_date"
        ).fetchall()
        self.table_dir.mkdir(parents=True, exist_ok=True)
        rows_by_year = {}
        for diary_date, content in rows:
            selected_date = datetime.strptime(diary_date, "%Y-%m-%d").date()
            rows_by_year.setdefault(selected_date.year, []).append(
                (selected_date.timetuple().tm_yday, diary_date, content)
            )

        for year, year_rows in rows_by_year.items():
            table_path = self.year_table_path(year)
            with table_path.open("w", encoding="utf-8-sig", newline="") as table:
                writer = csv.writer(table)
                writer.writerow(("id", "时间", "日志"))
                writer.writerows(year_rows)

    def year_table_path(self, year):
        return self.table_dir / f"{year}年的日记.csv"

    def year_rows(self, year):
        rows = self.connection.execute(
            """
            SELECT diary_date, content
            FROM diaries
            WHERE diary_date LIKE ?
            ORDER BY diary_date
            """,
            (f"{year:04d}-%",),
        ).fetchall()
        result = []
        for diary_date, content in rows:
            selected_date = datetime.strptime(diary_date, "%Y-%m-%d").date()
            result.append((selected_date.timetuple().tm_yday, diary_date, content))
        return result

    def dates_in_month(self, year, month):
        prefix = f"{year:04d}-{month:02d}-%"
        rows = self.connection.execute(
            "SELECT diary_date FROM diaries WHERE diary_date LIKE ?", (prefix,)
        ).fetchall()
        return {row[0] for row in rows}

    def todo_dates_in_month(self, year, month):
        prefix = f"{year:04d}-{month:02d}-%"
        rows = self.connection.execute(
            "SELECT todo_date FROM todos WHERE todo_date LIKE ?", (prefix,)
        ).fetchall()
        return {row[0] for row in rows}

    def get_setting(self, key, default=""):
        row = self.connection.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        self.connection.execute(
            """
            INSERT INTO settings (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
            """,
            (key, value),
        )
        self.connection.commit()

    def close(self):
        self.export_table()
        self.export_todos()
        self.connection.close()


def get_date_info(selected_date):
    lunar = Solar.fromYmd(
        selected_date.year, selected_date.month, selected_date.day
    ).getLunar()
    lunar_date = (
        f"{lunar.getYearInChinese()}年"
        f"{lunar.getMonthInChinese()}月"
        f"{lunar.getDayInChinese()}"
    )
    ganzhi = (
        f"{lunar.getYearInGanZhi()}年  "
        f"{lunar.getMonthInGanZhi()}月  "
        f"{lunar.getDayInGanZhi()}日"
    )
    wuxing = (
        f"年：{lunar.getYearNaYin()}  "
        f"月：{lunar.getMonthNaYin()}  "
        f"日：{lunar.getDayNaYin()}"
    )
    return lunar_date, ganzhi, wuxing


def get_diary_header(selected_date):
    lunar_date, ganzhi, _wuxing = get_date_info(selected_date)
    return f"农历：{lunar_date}　干支：{ganzhi}"


def get_day_ganzhi(selected_date):
    lunar = Solar.fromYmd(
        selected_date.year, selected_date.month, selected_date.day
    ).getLunar()
    ganzhi = lunar.getDayInGanZhi()
    return (
        ganzhi,
        STEM_WUXING_COLORS[ganzhi[0]],
        BRANCH_WUXING_COLORS[ganzhi[1]],
    )


def build_evernote_enex(year, rows):
    def cell(value):
        return html.escape(str(value)).replace("\n", "<br/>")

    table_rows = [
        "<tr>"
        '<th style="width:6%;padding:8px;border:1px solid #bbb;background:#f3f3f3;">id</th>'
        '<th style="width:16%;padding:8px;border:1px solid #bbb;background:#f3f3f3;">时间</th>'
        '<th style="width:78%;padding:8px;border:1px solid #bbb;background:#f3f3f3;">日记内容</th>'
        "</tr>"
    ]
    for day_id, diary_date, content in rows:
        table_rows.append(
            "<tr>"
            f'<td style="width:6%;padding:8px;border:1px solid #bbb;text-align:center;">{day_id}</td>'
            f'<td style="width:16%;padding:8px;border:1px solid #bbb;white-space:nowrap;">{cell(diary_date)}</td>'
            f'<td style="width:78%;padding:8px;border:1px solid #bbb;white-space:normal;">{cell(content)}</td>'
            "</tr>"
        )
    enml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        "<en-note>"
        '<table style="border-collapse:collapse;width:100%;">'
        + "".join(table_rows)
        + "</table></en-note>"
    )
    export_date = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export4.dtd">\n'
        f'<en-export export-date="{export_date}" application="本地日记" version="1.0">\n'
        "<note>\n"
        f"<title>{year}年的日记</title>\n"
        f"<content><![CDATA[{enml}]]></content>\n"
        "<tag>本地日记</tag>\n"
        "</note>\n"
        "</en-export>\n"
    )


def get_ganzhi_parts(selected_date):
    lunar = Solar.fromYmd(
        selected_date.year, selected_date.month, selected_date.day
    ).getLunar()
    return (
        ("年", lunar.getYearInGanZhi()),
        ("月", lunar.getMonthInGanZhi()),
        ("日", lunar.getDayInGanZhi()),
    )


def acquire_single_instance_lock():
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        lock_socket.listen(1)
        return lock_socket
    except OSError:
        lock_socket.close()
        return None


class DiaryApp:
    def __init__(self, root):
        self.root = root
        self.store = DiaryStore()
        self.selected_date = date.today()
        self.display_year = self.selected_date.year
        self.display_month = self.selected_date.month
        self.date_buttons = []
        self.theme = THEME
        self.is_pinned = False
        self.drag_x = 0
        self.drag_y = 0
        self.loaded_diary_content = ""
        self.loaded_todo_content = ""

        self.root.title("本地日记")
        self.root.geometry("980x640+80+80")
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 1.0)
        self.root.configure(bg=self.theme["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_ui()
        self.render_calendar()
        self.load_selected_date()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        self.configure_styles(style)

        self.header = tk.Frame(self.root, bg=self.theme["bg"], height=46)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.drag_window)

        self.app_title = tk.Label(
            self.header,
            text="本地日记",
            bg=self.theme["bg"],
            fg=TEXT_COLOR,
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.app_title.pack(side="left", padx=(16, 12))
        self.app_title.bind("<ButtonPress-1>", self.start_drag)
        self.app_title.bind("<B1-Motion>", self.drag_window)

        self.close_button = tk.Button(
            self.header, text="×", command=self.on_close, cursor="hand2"
        )
        self.close_button.pack(side="right", padx=(4, 12), pady=8)
        self.pin_button = tk.Button(
            self.header, text="置顶", command=self.toggle_pin, cursor="hand2"
        )
        self.pin_button.pack(side="right", padx=4, pady=8)

        container = ttk.Frame(self.root, padding=(18, 6, 18, 18), style="App.TFrame")
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        calendar_panel = ttk.Frame(
            container, padding=(0, 0, 18, 0), style="App.TFrame"
        )
        calendar_panel.grid(row=0, column=0, sticky="nsew")
        calendar_panel.columnconfigure(0, weight=1)
        calendar_panel.rowconfigure(5, weight=1)

        nav = ttk.Frame(calendar_panel, style="App.TFrame")
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(nav, text="‹", width=4, command=lambda: self.change_month(-1)).pack(
            side="left"
        )
        self.year_filter = ttk.Combobox(
            nav,
            width=8,
            state="readonly",
            values=[
                f"{year} 年"
                for year in range(date.today().year - 30, date.today().year + 31)
            ],
            style="DateFilter.TCombobox",
        )
        self.year_filter.set(f"{self.display_year} 年")
        self.year_filter.pack(side="left", padx=(8, 3))
        self.year_filter.bind("<<ComboboxSelected>>", self.select_calendar_period)
        self.month_filter = ttk.Combobox(
            nav,
            width=5,
            state="readonly",
            values=[f"{month} 月" for month in range(1, 13)],
            style="DateFilter.TCombobox",
        )
        self.month_filter.set(f"{self.display_month} 月")
        self.month_filter.pack(side="left", padx=(3, 8))
        self.month_filter.bind("<<ComboboxSelected>>", self.select_calendar_period)
        ttk.Button(nav, text="›", width=4, command=lambda: self.change_month(1)).pack(
            side="right"
        )

        weekdays = ttk.Frame(calendar_panel, style="App.TFrame")
        weekdays.grid(row=1, column=0, sticky="ew")
        for index, name in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            ttk.Label(
                weekdays, text=name, width=6, anchor="center", style="Weekday.TLabel"
            ).grid(
                row=0, column=index
            )

        self.calendar_grid = ttk.Frame(calendar_panel, style="App.TFrame")
        self.calendar_grid.grid(row=2, column=0)

        ttk.Button(calendar_panel, text="回到今天", command=self.go_today).grid(
            row=3, column=0, sticky="ew", pady=(14, 0)
        )

        ttk.Label(calendar_panel, text="待办事项", style="Info.TLabel").grid(
            row=4, column=0, sticky="w", pady=(16, 4)
        )
        self.todo_editor = tk.Text(
            calendar_panel,
            wrap="word",
            undo=True,
            height=9,
            width=34,
            font=("Microsoft YaHei UI", 11),
            padx=10,
            pady=8,
            bg=self.theme["panel"],
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["accent"],
        )
        self.todo_editor.grid(row=5, column=0, sticky="nsew")
        ttk.Frame(calendar_panel, height=38, style="App.TFrame").grid(
            row=6, column=0, sticky="ew"
        )

        editor_panel = ttk.Frame(container, style="Right.TFrame", padding=(10, 8))
        editor_panel.grid(row=0, column=1, sticky="nsew")
        editor_panel.columnconfigure(0, weight=1)
        editor_panel.rowconfigure(1, weight=1)

        info_card = ttk.Frame(editor_panel, style="RightInfo.TFrame", padding=(12, 10))
        info_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        info_card.columnconfigure(0, weight=1)

        self.solar_label = ttk.Label(info_card, style="RightTitle.TLabel")
        self.solar_label.grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.lunar_label = ttk.Label(info_card, style="RightAux.TLabel")
        self.lunar_label.grid(row=1, column=0, sticky="w", pady=3)
        self.ganzhi_frame = tk.Frame(info_card, bg=RIGHT_INFO_BG)
        self.ganzhi_frame.grid(row=2, column=0, sticky="w", pady=3)
        self.wuxing_label = ttk.Label(info_card, style="RightAux.TLabel")
        self.wuxing_label.grid(row=3, column=0, sticky="w", pady=3)

        self.editor = tk.Text(
            editor_panel,
            wrap="word",
            undo=True,
            font=("Microsoft YaHei UI", 11),
            padx=14,
            pady=14,
            bg=RIGHT_EDITOR_BG,
            fg=RIGHT_TITLE_COLOR,
            insertbackground=RIGHT_TITLE_COLOR,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        self.editor.grid(row=1, column=0, sticky="nsew")

        bottom = ttk.Frame(editor_panel, style="Right.TFrame")
        bottom.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.status_label = ttk.Label(bottom, text="", style="RightStatus.TLabel")
        self.status_label.pack(side="left")
        ttk.Button(bottom, text="保存日记", command=self.save_current).pack(side="right")
        ttk.Button(
            bottom, text="同步印象笔记", command=self.sync_evernote
        ).pack(side="right", padx=(0, 8))
        ttk.Button(
            bottom, text="打开日志文件夹", command=self.open_log_folder
        ).pack(side="right", padx=(0, 8))

        self.root.bind("<Control-s>", lambda _event: self.save_current())
        self.root.bind("<Escape>", lambda _event: self.on_close())

    def configure_styles(self, style):
        style.configure("App.TFrame", background=self.theme["bg"])
        style.configure("Right.TFrame", background=RIGHT_PANEL_BG)
        style.configure("RightInfo.TFrame", background=RIGHT_INFO_BG)
        style.configure(
            "TLabel",
            background=self.theme["bg"],
            foreground=TEXT_COLOR,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Title.TLabel",
            background=self.theme["bg"],
            foreground=TEXT_COLOR,
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        style.configure(
            "Info.TLabel",
            background=self.theme["bg"],
            foreground=TEXT_COLOR,
            font=("Microsoft YaHei UI", 11),
        )
        style.configure(
            "Weekday.TLabel",
            background=self.theme["bg"],
            foreground=RIGHT_AUX_COLOR,
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "RightTitle.TLabel",
            background=RIGHT_INFO_BG,
            foreground=RIGHT_TITLE_COLOR,
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        style.configure(
            "RightAux.TLabel",
            background=RIGHT_INFO_BG,
            foreground=RIGHT_AUX_COLOR,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "RightStatus.TLabel",
            background=RIGHT_PANEL_BG,
            foreground=RIGHT_AUX_COLOR,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "RightAccent.TLabel",
            background=RIGHT_PANEL_BG,
            foreground=RIGHT_ACCENT_COLOR,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "TButton",
            background=self.theme["panel"],
            foreground=TEXT_COLOR,
            borderwidth=0,
            font=("Microsoft YaHei UI", 10),
        )
        style.map("TButton", background=[("active", self.theme["accent"])])
        style.configure("TSeparator", background=self.theme["accent"])
        style.configure("Right.TSeparator", background=BORDER_COLOR)
        style.configure(
            "DateFilter.TCombobox",
            fieldbackground=self.theme["panel"],
            background=self.theme["panel"],
            foreground=TEXT_COLOR,
            arrowcolor=self.theme["accent"],
            bordercolor=self.theme["accent"],
            lightcolor=self.theme["accent"],
            darkcolor=self.theme["accent"],
            padding=5,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "DateFilter.TCombobox",
            fieldbackground=[("readonly", self.theme["panel"])],
            selectbackground=[("readonly", self.theme["panel"])],
            selectforeground=[("readonly", TEXT_COLOR)],
        )

    def style_window_button(self, button):
        button.configure(
            bg=self.theme["panel"],
            fg=TEXT_COLOR,
            activebackground=self.theme["accent"],
            activeforeground=TEXT_COLOR,
            relief="flat",
            bd=0,
        )

    def start_drag(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def drag_window(self, event):
        self.root.geometry(
            f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}"
        )

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.root.attributes("-topmost", self.is_pinned)
        self.pin_button.configure(text="已置顶" if self.is_pinned else "置顶")

    def render_calendar(self):
        for widget in self.calendar_grid.winfo_children():
            widget.destroy()
        self.date_buttons.clear()
        self.year_filter.set(f"{self.display_year} 年")
        self.month_filter.set(f"{self.display_month} 月")
        diary_dates = self.store.dates_in_month(self.display_year, self.display_month)
        todo_dates = self.store.todo_dates_in_month(self.display_year, self.display_month)

        month_days = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.display_year, self.display_month
        )
        while len(month_days) < 6:
            month_days.append([0] * 7)

        for row, week in enumerate(month_days):
            for column, day in enumerate(week):
                if day == 0:
                    ttk.Label(self.calendar_grid, text="", width=6).grid(
                        row=row, column=column, padx=2, pady=2
                    )
                    continue
                day_date = date(self.display_year, self.display_month, day)
                key = day_date.isoformat()
                markers = ("●" if key in diary_dates else "") + (
                    "✓" if key in todo_dates else ""
                )
                cell_bg = (
                    self.theme["accent"]
                    if day_date == self.selected_date
                    else self.theme["panel"]
                )
                ganzhi, stem_color, branch_color = get_day_ganzhi(day_date)
                cell = tk.Frame(
                    self.calendar_grid,
                    width=48,
                    height=54,
                    bg=cell_bg,
                    bd=1,
                    relief="sunken" if day_date == self.selected_date else "flat",
                )
                cell.grid(row=row, column=column, padx=2, pady=2)
                cell.grid_propagate(False)
                day_label = tk.Label(
                    cell,
                    text=str(day),
                    bg=cell_bg,
                    fg=RIGHT_TITLE_COLOR,
                    font=("Consolas", 11, "bold"),
                )
                day_label.place(x=6, y=4)
                marker_label = tk.Label(
                    cell,
                    text=markers,
                    bg=cell_bg,
                    fg=RIGHT_ACCENT_COLOR,
                    font=("Microsoft YaHei UI", 8),
                )
                marker_label.place(relx=1.0, x=-4, y=4, anchor="ne")
                stem_label = tk.Label(
                    cell,
                    text=ganzhi[0],
                    bg=cell_bg,
                    fg=stem_color,
                    font=("Microsoft YaHei UI", 8),
                )
                stem_label.place(x=5, rely=1.0, y=-4, anchor="sw")
                branch_label = tk.Label(
                    cell,
                    text=ganzhi[1],
                    bg=cell_bg,
                    fg=branch_color,
                    font=("Microsoft YaHei UI", 8),
                )
                branch_label.place(x=18, rely=1.0, y=-4, anchor="sw")
                for widget in (cell, day_label, marker_label, stem_label, branch_label):
                    widget.bind(
                        "<Button-1>",
                        lambda _event, chosen=day_date: self.select_date(chosen),
                    )
                self.date_buttons.append((day_date, cell))

    def select_date(self, chosen_date):
        if chosen_date == self.selected_date:
            return
        self.save_current(show_status=False)
        self.selected_date = chosen_date
        self.load_selected_date()
        self.render_calendar()

    def select_calendar_period(self, _event=None):
        selected_year = int(self.year_filter.get().split()[0])
        selected_month = int(self.month_filter.get().split()[0])
        self.save_current(show_status=False)
        self.display_year = selected_year
        self.display_month = selected_month
        self.render_calendar()

    def load_selected_date(self):
        lunar_date, ganzhi, wuxing = get_date_info(self.selected_date)
        diary_header = get_diary_header(self.selected_date)
        weekday = "一二三四五六日"[self.selected_date.weekday()]
        self.solar_label.config(
            text=f"{self.selected_date:%Y 年 %m 月 %d 日}  星期{weekday}"
        )
        self.lunar_label.config(text=f"农历：{lunar_date}")
        self.render_ganzhi_info()
        self.wuxing_label.config(text=f"五行纳音：{wuxing}")
        self.editor.delete("1.0", "end")
        content = self.store.get(self.selected_date.isoformat())
        self.loaded_diary_content = content
        if content and not content.startswith(diary_header):
            content = f"{diary_header}\n{content}"
        self.editor.insert("1.0", content or f"{diary_header}\n")
        self.todo_editor.delete("1.0", "end")
        todo_content = self.store.get_todo(self.selected_date.isoformat())
        self.loaded_todo_content = todo_content
        self.todo_editor.insert("1.0", todo_content)
        self.status_label.config(text="")
        self.editor.focus_set()

    def render_ganzhi_info(self):
        for widget in self.ganzhi_frame.winfo_children():
            widget.destroy()
        tk.Label(
            self.ganzhi_frame,
            text="干支：",
            bg=RIGHT_INFO_BG,
            fg=RIGHT_AUX_COLOR,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left")
        for period, ganzhi in get_ganzhi_parts(self.selected_date):
            is_day = period == "日"
            font = ("Microsoft YaHei UI", 10, "bold" if is_day else "normal")
            tk.Label(
                self.ganzhi_frame,
                text=ganzhi[0],
                bg=RIGHT_INFO_BG,
                fg=STEM_WUXING_COLORS[ganzhi[0]],
                font=font,
            ).pack(side="left")
            tk.Label(
                self.ganzhi_frame,
                text=ganzhi[1],
                bg=RIGHT_INFO_BG,
                fg=BRANCH_WUXING_COLORS[ganzhi[1]],
                font=font,
            ).pack(side="left")
            tk.Label(
                self.ganzhi_frame,
                text=f"{period}  ",
                bg=RIGHT_INFO_BG,
                fg=RIGHT_AUX_COLOR,
                font=("Microsoft YaHei UI", 10),
            ).pack(side="left")

    def save_current(self, show_status=True):
        content = self.editor.get("1.0", "end-1c")
        if content.strip() == get_diary_header(self.selected_date):
            content = ""
        diary_saved = self.store.save(
            self.selected_date.isoformat(),
            content,
            expected_content=self.loaded_diary_content,
        )
        todo_content = self.todo_editor.get("1.0", "end-1c")
        todo_saved = self.store.save_todo(
            self.selected_date.isoformat(),
            todo_content,
            expected_content=self.loaded_todo_content,
        )
        if diary_saved:
            self.loaded_diary_content = content.rstrip()
        if todo_saved:
            self.loaded_todo_content = todo_content.rstrip()
        self.render_calendar()
        if show_status:
            if diary_saved and todo_saved:
                self.status_label.config(text="已保存到本地")
            else:
                self.status_label.config(text="已有较新/更多内容，已跳过覆盖")

    def sync_evernote(self):
        self.save_current(show_status=False)
        year = self.selected_date.year
        rows = self.store.year_rows(year)
        if not rows:
            messagebox.showinfo("没有日记", f"{year}年还没有可同步的日记。")
            return
        if not ENSCRIPT_PATH.exists():
            messagebox.showerror("同步失败", f"找不到印象笔记工具：{ENSCRIPT_PATH}")
            return

        note_title = f"{year}年的日记"
        note_body_path = self.store.table_dir / f"{note_title}.enex"
        note_body_path.write_text(
            build_evernote_enex(year, rows), encoding="utf-8-sig"
        )

        result = subprocess.run(
            [
                str(ENSCRIPT_PATH),
                "importNotes",
                "/s",
                str(note_body_path),
                "/n",
                EVERNOTE_NOTEBOOK,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            messagebox.showerror("同步失败", result.stderr.strip() or result.stdout.strip())
            return

        subprocess.Popen(
            [
                str(ENSCRIPT_PATH),
                "showNotes",
                "/q",
                f'notebook:"{EVERNOTE_NOTEBOOK}" intitle:"{note_title}"',
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.status_label.config(text=f"已同步到印象笔记：{note_title}")
        messagebox.showinfo(
            "同步完成",
            f"已在“{EVERNOTE_NOTEBOOK}”创建表格笔记“{note_title}”。\n"
            "印象笔记已打开同名笔记列表，请删除旧版本。",
        )

    def open_log_folder(self):
        self.store.table_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.store.table_dir)
        self.status_label.config(text="已打开日志文件夹")

    def change_month(self, offset):
        self.save_current(show_status=False)
        month_index = self.display_year * 12 + self.display_month - 1 + offset
        self.display_year, month_zero_based = divmod(month_index, 12)
        self.display_month = month_zero_based + 1
        self.render_calendar()

    def go_today(self):
        today = date.today()
        self.display_year = today.year
        self.display_month = today.month
        self.select_date(today)
        self.render_calendar()

    def on_close(self):
        try:
            self.save_current(show_status=False)
            self.store.close()
        except sqlite3.Error as error:
            messagebox.showerror("保存失败", str(error))
        self.root.destroy()


if __name__ == "__main__":
    instance_lock = acquire_single_instance_lock()
    if instance_lock is None:
        sys.exit(0)
    root = tk.Tk()
    app = DiaryApp(root)
    app.style_window_button(app.pin_button)
    app.style_window_button(app.close_button)
    root.mainloop()
