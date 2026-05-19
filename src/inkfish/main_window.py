"""Top-level QMainWindow: MDI shell hosting EditorSubWindows."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent
from PyQt6.QtWidgets import (
    QFileDialog, QLabel, QMainWindow, QMdiArea, QMdiSubWindow, QMenu,
)

from .editor_pane import EditorPane
from .editor_subwindow import EditorSubWindow
from .hotkeys import register_shortcuts
from .io import file_dialog_filter
from . import layouts, settings


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SquidPad")
        self.resize(1280, 800)

        self._mdi = QMdiArea()
        self._mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(self._mdi)

        self._active_pane: EditorPane | None = None
        self._mdi_mode: str = "subwindow"

        self._build_menus()
        self._build_status_bar()
        register_shortcuts(self)

        self._mdi.subWindowActivated.connect(self._on_subwindow_activated)
        self._update_zoom_label(1.0)

        prefs = settings.load()
        self._mdi_mode = prefs.get("mdi_view_mode", "subwindow")
        self._apply_mdi_view_mode()
        self._act_pan_clamp.setChecked(bool(prefs.get("pan_clamp", False)))
        self._restore_session(prefs)

    # ---- menus / status bar ---------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self._act_open = QAction("&Open…", self)
        self._act_open.triggered.connect(self.open_file_dialog)
        file_menu.addAction(self._act_open)

        self._recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self._recent_menu)
        self._refresh_recent_menu()

        self._act_save = QAction("&Save", self)
        self._act_save.triggered.connect(self.save)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction("Save &As…", self)
        self._act_save_as.triggered.connect(self.save_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        self._act_quit = QAction("&Quit", self)
        self._act_quit.triggered.connect(self.close)
        file_menu.addAction(self._act_quit)

        edit_menu = self.menuBar().addMenu("&Edit")

        self._act_find = QAction("&Find…", self)
        self._act_find.triggered.connect(self.open_find)
        edit_menu.addAction(self._act_find)

        self._act_find_replace = QAction("Find && &Replace…", self)
        self._act_find_replace.triggered.connect(self.open_find_replace)
        edit_menu.addAction(self._act_find_replace)

        view_menu = self.menuBar().addMenu("&View")

        self._act_toggle_mode = QAction("Toggle &Rendered/Source", self)
        self._act_toggle_mode.triggered.connect(self.toggle_mode)
        view_menu.addAction(self._act_toggle_mode)

        self._act_toggle_fold = QAction("Toggle &Fold at Cursor", self)
        self._act_toggle_fold.triggered.connect(self.toggle_fold_at_cursor)
        view_menu.addAction(self._act_toggle_fold)

        self._act_reset_view = QAction("&Reset Zoom && Pan", self)
        self._act_reset_view.triggered.connect(self.reset_view)
        view_menu.addAction(self._act_reset_view)

        self._act_center_on_cursor = QAction("&Centre on Cursor", self)
        self._act_center_on_cursor.triggered.connect(self.center_on_cursor)
        view_menu.addAction(self._act_center_on_cursor)

        self._act_fit_page = QAction("Fit &Page", self)
        self._act_fit_page.triggered.connect(self.fit_page)
        view_menu.addAction(self._act_fit_page)

        view_menu.addSeparator()

        self._act_line_numbers = QAction("Show &Line Numbers", self)
        self._act_line_numbers.setCheckable(True)
        self._act_line_numbers.triggered.connect(self.toggle_line_numbers)
        view_menu.addAction(self._act_line_numbers)

        self._act_pan_clamp = QAction("Constrain &Pan", self)
        self._act_pan_clamp.setCheckable(True)
        self._act_pan_clamp.triggered.connect(self.toggle_pan_clamp)
        view_menu.addAction(self._act_pan_clamp)

        self._act_vim_mode = QAction("&Vim Mode", self)
        self._act_vim_mode.setCheckable(True)
        self._act_vim_mode.triggered.connect(self.toggle_vim)
        view_menu.addAction(self._act_vim_mode)

        # ---- Window menu ----
        win_menu = self.menuBar().addMenu("&Window")

        mode_group = QActionGroup(self)

        self._act_subwindow_mode = QAction("&Sub-window Mode", self)
        self._act_subwindow_mode.setCheckable(True)
        self._act_subwindow_mode.setChecked(True)
        self._act_subwindow_mode.triggered.connect(
            lambda: self._set_mdi_mode("subwindow")
        )
        mode_group.addAction(self._act_subwindow_mode)
        win_menu.addAction(self._act_subwindow_mode)

        self._act_tabbed_mode = QAction("&Tabbed Mode", self)
        self._act_tabbed_mode.setCheckable(True)
        self._act_tabbed_mode.triggered.connect(
            lambda: self._set_mdi_mode("tabbed")
        )
        mode_group.addAction(self._act_tabbed_mode)
        win_menu.addAction(self._act_tabbed_mode)

        win_menu.addSeparator()

        self._act_tile = QAction("&Tile Windows", self)
        self._act_tile.triggered.connect(self._mdi.tileSubWindows)
        win_menu.addAction(self._act_tile)

        self._act_cascade = QAction("&Cascade Windows", self)
        self._act_cascade.triggered.connect(self._mdi.cascadeSubWindows)
        win_menu.addAction(self._act_cascade)

        win_menu.addSeparator()

        self._act_new_editor = QAction("&New Editor", self)
        self._act_new_editor.triggered.connect(self.new_editor)
        win_menu.addAction(self._act_new_editor)

        self._act_close_editor = QAction("&Close Editor", self)
        self._act_close_editor.triggered.connect(self.close_active_editor)
        win_menu.addAction(self._act_close_editor)

        self._act_toggle_mdi_mode = QAction("Toggle Sub-window/Tabbed", self)
        self._act_toggle_mdi_mode.triggered.connect(self._toggle_mdi_mode)
        self.addAction(self._act_toggle_mdi_mode)  # shortcut only, not in menu

    def _build_status_bar(self) -> None:
        self._vim_label = QLabel("")
        self._vim_label.setVisible(False)
        self.statusBar().addWidget(self._vim_label)

        self._zoom_label = QLabel("100%")
        self._mode_label = QLabel("")
        self.statusBar().addPermanentWidget(self._mode_label)
        self.statusBar().addPermanentWidget(self._zoom_label)

    # ---- active pane accessor -------------------------------------------------

    def active_pane(self) -> EditorPane | None:
        sw = self._mdi.activeSubWindow()
        return sw.widget() if sw is not None else None

    # ---- editor window management ---------------------------------------------

    def new_editor(self) -> EditorSubWindow:
        pane = EditorPane()
        prefs = settings.load()
        if prefs.get("vim_mode"):
            pane.set_vim_enabled(True)
        if prefs.get("line_numbers"):
            pane.set_line_numbers_visible(True)
        if prefs.get("pan_clamp"):
            pane.set_pan_clamp(True)
        sw = EditorSubWindow(pane)
        self._mdi.addSubWindow(sw)
        sw.show()
        self._mdi.setActiveSubWindow(sw)
        return sw

    def open_path(self, path: Path) -> None:
        path = path.resolve()
        for sw in self._mdi.subWindowList():
            if sw.widget().current_path == path:
                self._mdi.setActiveSubWindow(sw)
                return
        sw = self.new_editor()
        pane = sw.pane
        pane.open_path(path)
        self._push_recent(path)
        saved = layouts.get_layout(path)
        if saved:
            pane.apply_layout(
                saved.get("zoom", 1.0),
                saved.get("scroll_x", 0),
                saved.get("scroll_y", 0),
            )
            if "geometry" in saved:
                g = saved["geometry"]
                sw.setGeometry(g[0], g[1], g[2], g[3])

    def open_file_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open file", "", file_dialog_filter()
        )
        if path_str:
            self.open_path(Path(path_str))

    # ---- recent files ---------------------------------------------------------

    _MAX_RECENT = 10

    def _push_recent(self, path: Path) -> None:
        key = str(path.resolve())
        prefs = settings.load()
        recent: list[str] = prefs.get("recent_files", [])
        recent = [p for p in recent if p != key]
        recent.insert(0, key)
        settings.save({**prefs, "recent_files": recent[: self._MAX_RECENT]})
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent: list[str] = settings.load().get("recent_files", [])
        existing = [p for p in recent if Path(p).exists()]
        if not existing:
            placeholder = QAction("No recent files", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
        else:
            for path_str in existing:
                p = Path(path_str)
                act = QAction(p.name, self)
                act.setToolTip(path_str)
                act.setStatusTip(path_str)
                act.triggered.connect(lambda _checked, p=p: self.open_path(p))
                self._recent_menu.addAction(act)
            self._recent_menu.addSeparator()
            clear_act = QAction("Clear Recent Files", self)
            clear_act.triggered.connect(self._clear_recent)
            self._recent_menu.addAction(clear_act)

    def _clear_recent(self) -> None:
        settings.save({**settings.load(), "recent_files": []})
        self._refresh_recent_menu()

    def close_active_editor(self) -> None:
        sw = self._mdi.activeSubWindow()
        if sw is not None:
            sw.close()

    # ---- menu action delegates ------------------------------------------------

    def save(self) -> bool:
        p = self.active_pane()
        return p.save() if p is not None else False

    def save_as(self) -> bool:
        p = self.active_pane()
        return p.save_as() if p is not None else False

    def toggle_mode(self) -> None:
        if p := self.active_pane():
            p.toggle_mode()

    def toggle_fold_at_cursor(self) -> None:
        if p := self.active_pane():
            p.toggle_fold_at_cursor()

    def reset_view(self) -> None:
        if p := self.active_pane():
            p.reset_view()

    def center_on_cursor(self) -> None:
        if p := self.active_pane():
            p.center_on_cursor()

    def fit_page(self) -> None:
        if p := self.active_pane():
            p.fit_page()

    def toggle_pan_clamp(self) -> None:
        on = self._act_pan_clamp.isChecked()
        for sw in self._mdi.subWindowList():
            sw.widget().set_pan_clamp(on)
        settings.save({**settings.load(), "pan_clamp": on})

    def open_find(self) -> None:
        if p := self.active_pane():
            p.open_find()

    def open_find_replace(self) -> None:
        if p := self.active_pane():
            p.open_find_replace()

    def toggle_line_numbers(self) -> None:
        if p := self.active_pane():
            p.toggle_line_numbers()
            settings.save({**settings.load(), "line_numbers": p.line_numbers_visible()})

    def toggle_vim(self) -> None:
        if p := self.active_pane():
            p.toggle_vim()
            on = p.vim_enabled()
            settings.save({**settings.load(), "vim_mode": on})

    # ---- MDI view mode --------------------------------------------------------

    def _set_mdi_mode(self, mode: str) -> None:
        self._mdi_mode = mode
        self._apply_mdi_view_mode()
        settings.save({**settings.load(), "mdi_view_mode": mode})

    def _toggle_mdi_mode(self) -> None:
        self._set_mdi_mode(
            "tabbed" if self._mdi_mode == "subwindow" else "subwindow"
        )

    def _apply_mdi_view_mode(self) -> None:
        if self._mdi_mode == "tabbed":
            self._mdi.setViewMode(QMdiArea.ViewMode.TabbedView)
            self._act_tabbed_mode.setChecked(True)
            self._act_tile.setEnabled(False)
            self._act_cascade.setEnabled(False)
        else:
            self._mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
            self._act_subwindow_mode.setChecked(True)
            self._act_tile.setEnabled(True)
            self._act_cascade.setEnabled(True)

    # ---- signal wiring for active pane ----------------------------------------

    def _connect_pane(self, pane: EditorPane) -> None:
        pane.title_changed.connect(self._on_pane_title_changed)
        pane.zoom_changed.connect(self._update_zoom_label)
        pane.vim_mode_changed.connect(self._on_vim_mode_changed)
        pane.command_buf_changed.connect(self._on_command_buf_changed)
        pane.mode_label_changed.connect(self._mode_label.setText)
        pane.vim_toggled.connect(self._on_vim_toggled)
        pane.line_numbers_toggled.connect(self._act_line_numbers.setChecked)

    def _disconnect_pane(self, pane: EditorPane) -> None:
        try:
            pane.title_changed.disconnect(self._on_pane_title_changed)
            pane.zoom_changed.disconnect(self._update_zoom_label)
            pane.vim_mode_changed.disconnect(self._on_vim_mode_changed)
            pane.command_buf_changed.disconnect(self._on_command_buf_changed)
            pane.mode_label_changed.disconnect(self._mode_label.setText)
            pane.vim_toggled.disconnect(self._on_vim_toggled)
            pane.line_numbers_toggled.disconnect(self._act_line_numbers.setChecked)
        except (TypeError, RuntimeError):
            pass

    def _on_subwindow_activated(self, subwindow: QMdiSubWindow | None) -> None:
        if self._active_pane is not None:
            self._disconnect_pane(self._active_pane)
            self._active_pane = None

        if subwindow is not None:
            pane = subwindow.widget()
            self._active_pane = pane
            self._connect_pane(pane)
            self._update_zoom_label(pane.view.current_scale())
            self._mode_label.setText(pane.mode_label())
            self._act_vim_mode.setChecked(pane.vim_enabled())
            self._act_line_numbers.setChecked(pane.line_numbers_visible())
            if pane.vim_enabled():
                self._vim_label.setText("-- NORMAL --")
                self._vim_label.setVisible(True)
            else:
                self._vim_label.setVisible(False)
            self.setWindowTitle(f"SquidPad — {pane.display_name()}")
        else:
            self._update_zoom_label(1.0)
            self._mode_label.setText("")
            self._vim_label.setVisible(False)
            self._act_vim_mode.setChecked(False)
            self.setWindowTitle("SquidPad")

    # ---- status bar update slots ----------------------------------------------

    def _update_zoom_label(self, factor: float) -> None:
        self._zoom_label.setText(f"{int(round(factor * 100))}%")

    def _on_pane_title_changed(self, name: str) -> None:
        self.setWindowTitle(f"SquidPad — {name}")

    def _on_vim_mode_changed(self, mode_name: str) -> None:
        labels = {
            "NORMAL":      "-- NORMAL --",
            "INSERT":      "-- INSERT --",
            "VISUAL":      "-- VISUAL --",
            "VISUAL_LINE": "-- VISUAL LINE --",
            "COMMAND":     "",
        }
        self._vim_label.setText(labels.get(mode_name, f"-- {mode_name} --"))

    def _on_command_buf_changed(self, buf: str) -> None:
        self._vim_label.setText(buf)

    def _on_vim_toggled(self, on: bool) -> None:
        self._act_vim_mode.setChecked(on)
        if on:
            self._vim_label.setText("-- NORMAL --")
            self._vim_label.setVisible(True)
        else:
            self._vim_label.setVisible(False)

    # ---- session save / restore -----------------------------------------------

    def _restore_session(self, prefs: dict) -> None:
        session = prefs.get("session", [])
        active_path: str | None = None
        for entry in session:
            path_str = entry.get("path")
            if path_str and Path(path_str).exists():
                self.open_path(Path(path_str))
                if entry.get("active"):
                    active_path = path_str
        # Activate the previously active window
        if active_path:
            for sw in self._mdi.subWindowList():
                p = sw.widget().current_path
                if p is not None and str(p) == active_path:
                    self._mdi.setActiveSubWindow(sw)
                    break

    def _save_session(self) -> None:
        active_sw = self._mdi.activeSubWindow()
        session = []
        for sw in self._mdi.subWindowList():
            path = sw.widget().current_path
            if path is not None:
                session.append({
                    "path": str(path),
                    "active": sw is active_sw,
                })
        settings.save({**settings.load(), "session": session})

    # ---- close ----------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        for sw in list(self._mdi.subWindowList()):
            if not sw.widget().confirm_discard():
                event.ignore()
                return
        self._save_session()
        event.accept()
