# inkfish

A single-document desktop text editor whose **primary navigation model is
pinch-zoom and pan** rather than scroll bars. Built on Python 3.12 + PyQt6
around a `QGraphicsView` whose transform is driven uniformly by touch, trackpad
and mouse input.

## Install

```sh
uv sync                # development
# or
pip install .          # end-user
```

## Run

```sh
uv run inkfish [path]              # development
inkfish path/to/file.md            # after pip install .
```

## Supported formats

`.txt`, `.md`, `.html` — read/write. The editor is intentionally not a viewer.

## Hotkeys

| Key                | Action                                  |
|--------------------|-----------------------------------------|
| Ctrl+O             | Open file                               |
| Ctrl+S             | Save                                    |
| Ctrl+Shift+S       | Save As                                 |
| Ctrl+Q             | Quit                                    |
| Ctrl+E             | Toggle source / rendered (`.md`/`.html`)|
| Ctrl+.             | Toggle fold at cursor                   |
| Ctrl+Wheel         | Zoom (mouse fallback)                   |
| Middle-drag        | Pan (mouse fallback)                    |
| Pinch / two-finger | Zoom / pan (touch + trackpad)           |

## Testing

```sh
uv run pytest
```

Tests run against the offscreen Qt platform; no display required:

```sh
QT_QPA_PLATFORM=offscreen uv run pytest
```
