# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project

**inkfish / SquidPad** is a standalone desktop text editor whose distinguishing feature is **pinch-zoom and pan as the primary navigation model** — users move around a document the way they would on a touchscreen. Goal: a natural, gestural reading and editing experience for long but structured documents.

The app presents itself to users as **SquidPad** (shown on the splash screen and window title).

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

## Architecture

The editing surface is a `QGraphicsView` + `QGraphicsScene` (`InkfishView` in `canvas.py`). The document lives as a `DocumentItem` (`QGraphicsTextItem`) inside the scene. All zoom and pan route through `InkfishView.zoom_to()` and `pan_by()`, keeping transforms consistent across every input mode.

### Module map

| Module | Responsibility |
|--------|---------------|
| `app.py` | Entry point — shows `SplashScreen`, builds `QApplication`, shows `MainWindow`, handles `--version` and file path CLI arg |
| `splash.py` | `SplashScreen` — frameless dark dialog with ASCII puffer fish art; auto-closes after 5 s or on any key / click |
| `main_window.py` | Top-level `QMainWindow` — menus, status bar, file ops, mode toggle, Vim toggle, signal wiring |
| `canvas.py` | `InkfishView` — zoom, pan, gesture dispatch, scroll bars, `reset_view()`, `scroll_to_document_origin()` |
| `document_item.py` | `DocumentItem` — text display/edit, fold apply/unapply, Vim key intercept, Vim action application |
| `vim.py` | `VimEngine` — pure state machine (no Qt); processes raw key ints → `Action` dataclasses |
| `gestures.py` | `PinchHandler`, `PanHandler` — translate `QGestureEvent` into `zoom_to` / `pan_by` calls |
| `modes.py` | `Mode` enum (SOURCE / RENDERED), `apply_mode()`, `is_toggleable()` |
| `folding.py` | `find_fold_regions()` — bracket-based (.txt/.code), heading-based (.md), tag-based (.html) |
| `io.py` | `load_file()`, `save_file()`, `file_dialog_filter()` — UTF-8 I/O; unknown extensions default to `.txt` |
| `settings.py` | `load()` / `save()` — JSON prefs at `~/.config/inkfish/settings.json` |
| `hotkeys.py` | `register_shortcuts()` — single binding table for all `QAction` shortcuts |

### Zoom / pan

- **Alt + right-click drag** — zoom; anchor locked to press point; formula: `target_scale = start_scale × exp(Δ × 0.005)` where `Δ = Δx_right + Δy_up` (total pixels from press point). Drift-free: dragging back to origin restores original zoom exactly.
- **Ctrl+wheel** — zoom anchored to mouse position
- **Middle-click drag** — pan
- **Alt + middle-click drag** — pan (middle button always takes priority over zoom)
- **Trackpad pinch / pan** — via `QGestureEvent` (`PinchGesture`, `PanGesture`)
- Zoom bounds: `MIN_SCALE = 0.01`, `MAX_SCALE = 1000.0`; sensitivity constant `ALT_ZOOM_SENSITIVITY = 0.005`
- On file open, view scrolls so document top-left is at viewport (0, 0)
- Scroll bars appear when document content overflows the viewport

### Supported file formats

`.txt` `.md` `.html` `.py` `.c` `.cpp` `.h` `.c++` `.h++` `.js`

Any other extension is opened as plain text (no error). Source/Rendered toggle is only available for `.md` and `.html`.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open file |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Q | Quit |
| Ctrl+E | Toggle Rendered / Source (`.md` / `.html` only) |
| Ctrl+. | Toggle fold at cursor |
| Ctrl+R | Reset zoom & pan to 100% at document origin |
| Ctrl+G | Centre canvas on current text cursor position |
| Ctrl+Shift+V | Toggle Vim mode |

### Vim mode

Opt-in (off by default). Toggle via **View → Vim Mode** or **Ctrl+Shift+V**. Preference persisted in `settings.json`.

`vim.py` is a Qt-free state machine. `VimEngine.process_key(key, modifiers, text) → list[Action]`. `DocumentItem` applies actions via `_apply_vim_actions()`. Pass `event.modifiers().value` (not `int(event.modifiers())`) when calling from PyQt6.

**Modes:** NORMAL · INSERT · VISUAL · VISUAL_LINE · COMMAND

**Normal mode — movement:** `h j k l` · `w b e W B E` · `0 ^ $` · `gg G` · `{ }` · `f F t T` · `Ctrl+d/u` (half page) · `Ctrl+f/b` (full page)

**Normal mode — enter Insert:** `i I a A o O s S C R`

**Normal mode — operators (with count + motion):** `d` `y` `c` + any motion · `dd yy cc` · `D Y C`

**Normal mode — edits:** `x X` · `r` · `~` · `J` · `u` · `Ctrl+R` (redo) · `.` (repeat)

**Normal mode — misc:** `p P` · `v V` (visual) · `/` `n N` `*` (search) · `m<a>` `` `<a> `` (marks) · `:` (command)

**Visual / Visual-Line:** movement extends selection · `d y c x ~` operate on selection · `o` swaps anchor

**Insert:** normal typing via Qt · `Esc` / `Ctrl+[` → Normal (cursor moves left) · `Ctrl+W` delete word · `Ctrl+U` delete to line start

**Command (`:`):** `:w` `:q` `:wq` `:x` `:e <path>` `:set vim` `:set novim`

**Status bar** shows `-- NORMAL --` / `-- INSERT --` / `-- VISUAL --` / live `:command` buffer.

## Conventions

- Single-document UI: one file at a time. No tabs, no split panes.
- Monospace typography (Courier New, 11 pt) — no syntax highlighting.
- Touchscreen + trackpad are first-class input targets.
- Full read/write capability for all supported formats.
- No language-server dependency; folding is heuristic and extension-based.
- Settings are persisted as JSON; no Qt settings / registry.
- `vim.py` must remain Qt-free — all Qt interaction goes through `DocumentItem`.
- PyQt6 quirk: `QTextLine.cursorToX()` returns `(x, pos)` tuple — unpack with `x, _ = line.cursorToX(...)`.
- PyQt6 quirk: `event.modifiers()` returns `KeyboardModifier` flags — use `.value` to get an int.

## Testing

```
uv run pytest              # all tests
uv run pytest tests/test_vim.py -v   # Vim engine only (fast, no Qt)
```

Test files: `test_canvas.py` · `test_folding.py` · `test_io.py` · `test_modes.py` · `test_smoke.py` · `test_vim.py`

Vim engine tests are Qt-free and run in ~0.25 s. Canvas / smoke tests require a display (pytest-qt handles this).
