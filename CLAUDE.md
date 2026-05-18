# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project

**inkfish / SquidPad** is a standalone desktop text editor whose distinguishing feature is **pinch-zoom and pan as the primary navigation model** — users move around a document the way they would on a touchscreen. Supports multiple documents open simultaneously in an MDI (Multiple Document Interface) layout.

The app presents itself to users as **SquidPad** (splash screen and window title).

## Stack

- Python 3.11+
- PyQt6 ≥ 6.6
- uv (env management and packaging)
- pytest + pytest-qt (tests)

## Run commands

```
uv sync                   # install / sync dependencies
uv run inkfish [path]     # launch editor (path optional)
uv run pytest             # run test suite
```

On Windows without uv on PATH: `.venv\Scripts\python -m pytest`

---

## Architecture

### Top-level structure

```
MainWindow  (QMainWindow)
  └─ QMdiArea  (central widget)
       ├─ EditorSubWindow  (QMdiSubWindow)
       │    └─ EditorPane  (QWidget)
       │         └─ InkfishView  (QGraphicsView)
       │              └─ DocumentItem  (QGraphicsTextItem)
       └─ EditorSubWindow ...
```

`MainWindow` is a thin shell. All per-document state and logic lives in `EditorPane`. `MainWindow` dispatches menu actions to `active_pane()` and rewires status-bar signals whenever `QMdiArea.subWindowActivated` fires.

### Module map

| Module | Responsibility |
|--------|---------------|
| `app.py` | Entry point — shows `SplashScreen`, creates `QApplication` + `MainWindow`, handles `--version` and optional file path arg |
| `splash.py` | `SplashScreen` — frameless dark dialog with ASCII puffer fish art; auto-closes after 5 s or any key/click |
| `main_window.py` | MDI shell — `QMdiArea`, menus, status bar, signal rewiring on active-window change, session save/restore |
| `editor_pane.py` | `EditorPane(QWidget)` — owns `_current_path`, `_raw_text`, `_mode`, `_vim_engine`; all file/view/vim/fold methods; emits `title_changed`, `zoom_changed`, `vim_mode_changed`, `mode_label_changed`, `vim_toggled`, `close_requested` |
| `editor_subwindow.py` | `EditorSubWindow(QMdiSubWindow)` — wraps `EditorPane`; saves layout to `layouts.py` on close; forwards close confirmation |
| `canvas.py` | `InkfishView(QGraphicsView)` — zoom, pan, gesture dispatch, scroll bars, `reset_view()`, `scroll_to_document_origin()` |
| `document_item.py` | `DocumentItem(QGraphicsTextItem)` — text display/edit, fold apply/unapply, Vim key intercept, Vim action application |
| `vim.py` | `VimEngine` — pure state machine (no Qt); `process_key(key, modifiers, text) → list[Action]` |
| `gestures.py` | `PinchHandler`, `PanHandler` — translate `QGestureEvent` into `zoom_to` / `pan_by` calls |
| `modes.py` | `Mode` enum (SOURCE / RENDERED), `apply_mode()`, `is_toggleable()` |
| `folding.py` | `find_fold_regions()` — bracket-based (code), heading-based (.md), tag-based (.html) |
| `io.py` | `load_file()`, `save_file()`, `file_dialog_filter()` — UTF-8; unknown extensions → `.txt` |
| `settings.py` | `load()` / `save()` — JSON prefs at `~/.config/inkfish/settings.json` |
| `layouts.py` | `get_layout(path)` / `set_layout(path, data)` — per-file zoom/scroll/geometry at `~/.config/inkfish/layouts.json` |
| `hotkeys.py` | `register_shortcuts()` — single binding table for all `QAction` shortcuts |

---

## Key patterns

### Opening a file
`MainWindow.open_path(path)` checks if the file is already open (by path) and activates the existing sub-window rather than duplicating it. If new, calls `new_editor()` → creates `EditorPane` → `EditorSubWindow` → adds to MDI → restores layout from `layouts.py` → calls `_push_recent(path)` to prepend to the recent files list.

### Active pane dispatch
All View/File menu actions call `self.active_pane()` (returns `EditorPane | None`) and delegate:
```python
def save(self) -> bool:
    p = self.active_pane()
    return p.save() if p is not None else False
```

### Signal rewiring
`MainWindow._on_subwindow_activated()` disconnects the old pane's signals and connects the new pane's signals to the status bar updaters. Uses try/except on disconnect to handle already-disconnected signals gracefully.

### Layout persistence
- `EditorPane.capture_layout()` → `{"zoom", "scroll_x", "scroll_y"}`
- `EditorSubWindow.closeEvent` appends `"geometry": [x, y, w, h]` and calls `layouts.set_layout(path, data)`
- `EditorPane.apply_layout(zoom, scroll_x, scroll_y)` resets transform to identity, scales to `zoom`, defers scroll restore via `QTimer.singleShot(0, ...)`

### Session save/restore
On app close: `MainWindow._save_session()` writes open file paths + active flag to `settings["session"]`.
On startup: `MainWindow._restore_session(prefs)` re-opens each path that exists on disk, then activates the previously-active window.

---

## Zoom / pan

- **Alt + right-click drag** — zoom; anchor locked to press point; `target_scale = start_scale × exp(Δ × 0.005)` where `Δ = Δx_right + Δy_up`. Drift-free.
- **Ctrl+wheel** — zoom anchored to mouse position
- **Middle-click drag** — pan
- **Alt + middle-click drag** — pan (middle button takes priority over zoom)
- **Trackpad pinch / pan** — via `QGestureEvent`
- Zoom bounds: `MIN_SCALE = 0.01`, `MAX_SCALE = 1000.0`; `ALT_ZOOM_SENSITIVITY = 0.005`
- On file open, view scrolls so document top-left is at viewport (0, 0)

---

## Supported file formats

`.txt` `.md` `.html` `.py` `.c` `.cpp` `.h` `.c++` `.h++` `.js`

Any other extension is opened as plain text (no error). Source/Rendered toggle is only available for `.md` and `.html`.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open file (dialog); File → Open Recent lists last 10 |
| Ctrl+S | Save active editor |
| Ctrl+Shift+S | Save As |
| Ctrl+Q | Quit |
| Ctrl+N | New editor pane |
| Ctrl+W | Close active editor |
| Ctrl+E | Toggle Rendered / Source (`.md` / `.html` only) |
| Ctrl+. | Toggle fold at cursor |
| Ctrl+R | Reset zoom & pan |
| Ctrl+G | Centre canvas on text cursor |
| Ctrl+Shift+V | Toggle Vim mode |
| Ctrl+Shift+M | Toggle sub-window / tabbed MDI mode |

---

## Vim mode

Opt-in per-pane (off by default). Global preference in `settings["vim_mode"]` sets the default for new panes. Toggle via **View → Vim Mode** or **Ctrl+Shift+V** — affects the active pane.

`vim.py` is Qt-free. Pass `event.modifiers().value` (not `int(event.modifiers())`) when calling `VimEngine.process_key`.

**Modes:** NORMAL · INSERT · VISUAL · VISUAL_LINE · COMMAND

**Normal — movement:** `h j k l` · `w b e W B E` · `0 ^ $` · `gg G` · `{ }` · `f F t T` · `Ctrl+d/u` (half page) · `Ctrl+f/b` (full page)

**Normal — enter Insert:** `i I a A o O s S C R`

**Normal — operators:** `d` `y` `c` + motion · `dd yy cc` · `D Y C` (with count prefix)

**Normal — edits:** `x X` · `r` · `~` · `J` · `u` · `Ctrl+R` (redo) · `.` (repeat)

**Normal — misc:** `p P` · `v V` · `/` `n N` `*` · `m<a>` `` `<a> `` · `:`

**Visual / Visual-Line:** movement extends selection · `d y c x ~` · `o` swaps anchor

**Insert:** `Esc`/`Ctrl+[` → Normal · `Ctrl+W` delete word · `Ctrl+U` delete to line start

**Command:** `:w` `:q` `:wq` `:x` `:e <path>` `:set vim` `:set novim`

**Status bar** shows `-- NORMAL --` / `-- INSERT --` / live `:buf`.

---

## Window / MDI

**Window menu** — Sub-window mode / Tabbed mode (radio pair), Tile, Cascade, New Editor, Close Editor.

- Sub-window mode: floating, resizable panels; tile and cascade available
- Tabbed mode: tab bar across top; tile/cascade disabled
- Toggle: `Ctrl+Shift+M` or Window menu
- Mode persisted in `settings["mdi_view_mode"]`

---

## Persistence files

| File | Contents |
|------|---------|
| `~/.config/inkfish/settings.json` | `vim_mode`, `mdi_view_mode`, `session` (open file paths), `recent_files` (last 10 opened paths) |
| `~/.config/inkfish/layouts.json` | Per-file: `zoom`, `scroll_x`, `scroll_y`, `geometry [x,y,w,h]` keyed by absolute path |

---

## Conventions

- Multiple documents via MDI — `EditorPane` is the unit of per-document state.
- `MainWindow` must stay thin: dispatch only, no document state.
- `vim.py` must remain Qt-free — all Qt interaction goes through `DocumentItem`.
- Monospace typography (Courier New, 11 pt) — no syntax highlighting.
- Touchscreen + trackpad are first-class input targets.
- No language-server dependency; folding is heuristic.
- PyQt6 quirk: `QTextLine.cursorToX()` returns `(x, pos)` — unpack with `x, _ = ...`.
- PyQt6 quirk: `event.modifiers()` → use `.value` for int conversion.

---

## Testing

```
uv run pytest                        # all tests
uv run pytest tests/test_vim.py -v   # Vim engine only (fast, no Qt)
```

Test files: `test_canvas.py` · `test_folding.py` · `test_io.py` · `test_modes.py` · `test_smoke.py` · `test_vim.py`

Vim engine tests are Qt-free (~0.25 s). Canvas/smoke tests require a display (pytest-qt).
