"""Vim modal editing engine — pure state machine, no Qt imports.

The engine processes raw key events and returns lists of Action objects.
DocumentItem applies those actions using QTextCursor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

# ---- Qt key code constants (mirrored from Qt.Key without importing Qt) -------
_ESC       = 0x01000000
_RETURN    = 0x01000004
_BACKSPACE = 0x01000003
_LEFT      = 0x01000012
_UP        = 0x01000013
_RIGHT     = 0x01000014
_DOWN      = 0x01000015
_HOME      = 0x01000010
_END       = 0x01000011
_PGUP      = 0x01000016
_PGDOWN    = 0x01000017

_CTRL  = 0x04000000
_SHIFT = 0x02000000


# ---- Modes -------------------------------------------------------------------

class VimMode(Enum):
    NORMAL      = auto()
    INSERT      = auto()
    VISUAL      = auto()
    VISUAL_LINE = auto()
    COMMAND     = auto()


# ---- Actions (applied by DocumentItem) --------------------------------------

@dataclass
class ChangeMode:
    mode: VimMode

@dataclass
class MoveCursor:
    motion: str
    count: int = 1
    keep_anchor: bool = False

@dataclass
class DeleteMotion:
    motion: str | FindChar
    count: int = 1

@dataclass
class YankMotion:
    motion: str | FindChar
    count: int = 1

@dataclass
class ChangeMotion:
    motion: str | FindChar
    count: int = 1

@dataclass
class PasteAfter:
    pass

@dataclass
class PasteBefore:
    pass

@dataclass
class Undo:
    pass

@dataclass
class Redo:
    pass

@dataclass
class OpenLine:
    above: bool = False

@dataclass
class ReplaceChar:
    char: str

@dataclass
class DeleteChar:
    before: bool = False
    count: int = 1

@dataclass
class ToggleCase:
    pass

@dataclass
class JoinLines:
    count: int = 1

@dataclass
class FindChar:
    char: str
    forward: bool = True
    till: bool = False

@dataclass
class ScrollHalfPage:
    down: bool = True

@dataclass
class ScrollPage:
    down: bool = True

@dataclass
class SearchForward:
    pattern: str

@dataclass
class SearchNext:
    reverse: bool = False

@dataclass
class ExCommand:
    command: str

@dataclass
class UpdateCommandBuf:
    buf: str

@dataclass
class SetMark:
    name: str

@dataclass
class JumpToMark:
    name: str


# ---- State ------------------------------------------------------------------

@dataclass
class VimState:
    mode: VimMode = VimMode.NORMAL
    count_str: str = ""
    operator: str = ""        # pending operator: d / y / c
    register: str = ""        # unnamed register (yank / delete buffer)
    search_pattern: str = ""
    command_buf: str = ""
    last_actions: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)
    # single-character await flags
    _await_r: bool = False
    _await_f: str = ""        # one of f F t T
    _await_mark_set: bool = False
    _await_mark_jump: bool = False
    _await_g: bool = False

    @property
    def count(self) -> int:
        return max(1, int(self.count_str)) if self.count_str else 1

    def reset_pending(self) -> None:
        self.count_str = ""
        self.operator = ""
        self._await_r = False
        self._await_f = ""
        self._await_mark_set = False
        self._await_mark_jump = False
        self._await_g = False


# ---- Engine -----------------------------------------------------------------

class VimEngine:
    def __init__(self) -> None:
        self.state = VimState()

    @property
    def mode(self) -> VimMode:
        return self.state.mode

    @property
    def command_buf(self) -> str:
        return self.state.command_buf

    def process_key(self, key: int, modifiers: int, text: str) -> list:
        ctrl = bool(modifiers & _CTRL)
        match self.state.mode:
            case VimMode.NORMAL:
                return self._normal(key, modifiers, text, ctrl)
            case VimMode.INSERT:
                return self._insert(key, modifiers, text, ctrl)
            case VimMode.VISUAL:
                return self._visual(key, modifiers, text, ctrl, line=False)
            case VimMode.VISUAL_LINE:
                return self._visual(key, modifiers, text, ctrl, line=True)
            case VimMode.COMMAND:
                return self._command_mode(key, modifiers, text)
        return []

    def _set_mode(self, mode: VimMode) -> list:
        self.state.mode = mode
        self.state.reset_pending()
        return [ChangeMode(mode)]

    # ---- Normal mode --------------------------------------------------------

    def _normal(self, key: int, modifiers: int, text: str, ctrl: bool) -> list:
        s = self.state

        # --- single-char awaits (checked before operator dispatch) ---

        if s._await_r:
            s._await_r = False
            if text:
                acts = [ReplaceChar(text)]
                s.last_actions = acts[:]
                s.reset_pending()
                return acts
            return []

        if s._await_f:
            variant = s._await_f
            s._await_f = ""
            if not text:
                s.reset_pending()
                return []
            forward = variant in "ft"
            till = variant in "tT"
            fc = FindChar(text, forward=forward, till=till)
            if s.operator:
                op = s.operator
                count = s.count
                s.reset_pending()
                return self._operator_action(op, fc, count)
            acts = [fc]
            s.reset_pending()
            return acts

        if s._await_mark_set:
            s._await_mark_set = False
            if text and text.isalpha():
                s.reset_pending()
                return [SetMark(text)]
            s.reset_pending()
            return []

        if s._await_mark_jump:
            s._await_mark_jump = False
            if text and text.isalpha():
                s.reset_pending()
                return [JumpToMark(text)]
            s.reset_pending()
            return []

        if s._await_g:
            s._await_g = False
            if text == "g":
                if s.operator:
                    op = s.operator
                    count = s.count
                    s.reset_pending()
                    return self._operator_action(op, "start", count)
                count = s.count
                s.reset_pending()
                return [MoveCursor("start", count)]
            s.reset_pending()
            return []

        # --- count digits ---
        if text.isdigit() and (text != "0" or s.count_str):
            s.count_str += text
            return []

        # --- escape clears pending ---
        if key == _ESC or (ctrl and key == 0x5B):
            s.reset_pending()
            return []

        # --- operator + motion dispatch ---
        if s.operator:
            return self._apply_operator(key, text, ctrl)

        count = s.count

        # --- movement ---
        if   text == "h" or key == _LEFT:  s.reset_pending(); return [MoveCursor("left",  count)]
        if   text == "l" or key == _RIGHT: s.reset_pending(); return [MoveCursor("right", count)]
        if   text == "j" or key == _DOWN:  s.reset_pending(); return [MoveCursor("down",  count)]
        if   text == "k" or key == _UP:    s.reset_pending(); return [MoveCursor("up",    count)]
        if   text == "w":                  s.reset_pending(); return [MoveCursor("word_next",  count)]
        if   text == "W":                  s.reset_pending(); return [MoveCursor("WORD_next",  count)]
        if   text == "b":                  s.reset_pending(); return [MoveCursor("word_prev",  count)]
        if   text == "B":                  s.reset_pending(); return [MoveCursor("WORD_prev",  count)]
        if   text == "e":                  s.reset_pending(); return [MoveCursor("word_end",   count)]
        if   text == "E":                  s.reset_pending(); return [MoveCursor("WORD_end",   count)]
        if   text == "0" or key == _HOME:  s.reset_pending(); return [MoveCursor("line_start", 1)]
        if   text == "^":                  s.reset_pending(); return [MoveCursor("line_start_nonws", 1)]
        if   text == "$" or key == _END:   s.reset_pending(); return [MoveCursor("line_end", 1)]
        if   text == "{":                  s.reset_pending(); return [MoveCursor("para_prev", count)]
        if   text == "}":                  s.reset_pending(); return [MoveCursor("para_next", count)]
        if text == "G":
            s.reset_pending()
            return [MoveCursor("line_n", count) if s.count_str else MoveCursor("end", 1)]
        if text == "g":
            s._await_g = True
            return []
        if ctrl and text == "d": s.reset_pending(); return [ScrollHalfPage(down=True)]
        if ctrl and text == "u": s.reset_pending(); return [ScrollHalfPage(down=False)]
        if ctrl and text == "f": s.reset_pending(); return [ScrollPage(down=True)]
        if ctrl and text == "b": s.reset_pending(); return [ScrollPage(down=False)]
        if key == _PGDOWN:       s.reset_pending(); return [ScrollPage(down=True)]
        if key == _PGUP:         s.reset_pending(); return [ScrollPage(down=False)]

        # --- enter insert mode ---
        if text == "i":
            return self._set_mode(VimMode.INSERT)
        if text == "I":
            return [MoveCursor("line_start_nonws", 1)] + self._set_mode(VimMode.INSERT)
        if text == "a":
            return [MoveCursor("right", 1)] + self._set_mode(VimMode.INSERT)
        if text == "A":
            return [MoveCursor("line_end", 1)] + self._set_mode(VimMode.INSERT)
        if text == "o":
            return self._set_mode(VimMode.INSERT) + [OpenLine(above=False)]
        if text == "O":
            return self._set_mode(VimMode.INSERT) + [OpenLine(above=True)]
        if text == "s":
            return [DeleteChar(before=False, count=count)] + self._set_mode(VimMode.INSERT)
        if text == "S":
            return [DeleteMotion("line", 1)] + self._set_mode(VimMode.INSERT)
        if text == "C":
            return [DeleteMotion("to_line_end", 1)] + self._set_mode(VimMode.INSERT)
        if text == "R":
            return self._set_mode(VimMode.INSERT)

        # --- operators ---
        if text in "dyc":
            s.operator = text
            return []

        # --- standalone edits ---
        if text == "x":
            acts = [DeleteChar(before=False, count=count)]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == "X":
            acts = [DeleteChar(before=True, count=count)]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == "D":
            acts = [DeleteMotion("to_line_end", 1)]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == "Y":
            acts = [YankMotion("line", count)]
            s.reset_pending(); return acts
        if text == "p":
            acts = [PasteAfter()]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == "P":
            s.reset_pending(); return [PasteBefore()]
        if text == "u":
            s.reset_pending(); return [Undo()]
        if ctrl and text == "r":
            s.reset_pending(); return [Redo()]
        if text == "r":
            s._await_r = True
            return []
        if text == "~":
            acts = [ToggleCase()]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == "J":
            acts = [JoinLines(count)]
            s.last_actions = acts[:]; s.reset_pending(); return acts
        if text == ".":
            if s.last_actions:
                acts = list(s.last_actions)
                s.reset_pending()
                return acts
            return []

        # --- visual ---
        if text == "v":
            return self._set_mode(VimMode.VISUAL)
        if text == "V":
            return self._set_mode(VimMode.VISUAL_LINE)

        # --- search ---
        if text == "/":
            s.reset_pending()
            return [SearchForward("")]
        if text == "n":
            s.reset_pending(); return [SearchNext(reverse=False)]
        if text == "N":
            s.reset_pending(); return [SearchNext(reverse=True)]
        if text == "*":
            s.reset_pending(); return [SearchForward("__word_under_cursor__")]

        # --- find char ---
        if text in "fFtT":
            s._await_f = text
            return []

        # --- marks ---
        if text == "m":
            s._await_mark_set = True
            return []
        if text in "`'":
            s._await_mark_jump = True
            return []

        # --- command mode ---
        if text == ":":
            self.state.mode = VimMode.COMMAND
            self.state.command_buf = ":"
            self.state.reset_pending()
            return [ChangeMode(VimMode.COMMAND), UpdateCommandBuf(":")]

        return []

    def _operator_action(self, op: str, motion: str | FindChar, count: int) -> list:
        if op == "d":
            acts = [DeleteMotion(motion, count)]
        elif op == "y":
            acts = [YankMotion(motion, count)]
        elif op == "c":
            if isinstance(motion, str) and motion == "line":
                acts = [DeleteMotion(motion, count)] + self._set_mode(VimMode.INSERT)
            else:
                acts = [DeleteMotion(motion, count)] + self._set_mode(VimMode.INSERT)
        else:
            acts = []
        self.state.last_actions = acts[:]
        return acts

    def _apply_operator(self, key: int, text: str, ctrl: bool) -> list:
        s = self.state
        op = s.operator
        count = s.count

        # doubled operator = line
        if text == op:
            motion = "line"
        elif text == "h" or key == _LEFT:   motion = "left"
        elif text == "l" or key == _RIGHT:  motion = "right"
        elif text == "j" or key == _DOWN:   motion = "down"
        elif text == "k" or key == _UP:     motion = "up"
        elif text == "w":                   motion = "word_next"
        elif text == "W":                   motion = "WORD_next"
        elif text == "b":                   motion = "word_prev"
        elif text == "B":                   motion = "WORD_prev"
        elif text == "e":                   motion = "word_end"
        elif text == "E":                   motion = "WORD_end"
        elif text == "0" or key == _HOME:   motion = "line_start"
        elif text == "$" or key == _END:    motion = "line_end"
        elif text == "G":                   motion = "end"
        elif text == "{":                   motion = "para_prev"
        elif text == "}":                   motion = "para_next"
        elif text == "g":
            # wait for second g
            s._await_g = True
            return []
        elif text in "fFtT":
            s._await_f = text
            return []
        else:
            s.reset_pending()
            return []

        acts = self._operator_action(op, motion, count)
        s.reset_pending()
        return acts

    # ---- Insert mode --------------------------------------------------------

    def _insert(self, key: int, modifiers: int, text: str, ctrl: bool) -> list:
        if key == _ESC or (ctrl and key == 0x5B):
            acts = [MoveCursor("left", 1)] + self._set_mode(VimMode.NORMAL)
            return acts
        return []

    # ---- Visual modes -------------------------------------------------------

    def _visual(self, key: int, modifiers: int, text: str, ctrl: bool, *, line: bool) -> list:
        s = self.state
        count = s.count

        if text.isdigit() and (text != "0" or s.count_str):
            s.count_str += text
            return []

        if key == _ESC or (ctrl and key == 0x5B):
            return self._set_mode(VimMode.NORMAL)

        _MOVE = {
            "h": "left",  "l": "right",  "j": "down",  "k": "up",
            "w": "word_next", "b": "word_prev", "e": "word_end",
            "W": "WORD_next", "B": "WORD_prev", "E": "WORD_end",
            "0": "line_start", "$": "line_end", "^": "line_start_nonws",
            "G": "end", "{": "para_prev", "}": "para_next",
        }
        if text in _MOVE:
            s.reset_pending()
            return [MoveCursor(_MOVE[text], count, keep_anchor=True)]
        if text in "dx":
            acts = [DeleteMotion("selection", 1)] + self._set_mode(VimMode.NORMAL)
            s.last_actions = acts[:]
            return acts
        if text == "y":
            return [YankMotion("selection", 1)] + self._set_mode(VimMode.NORMAL)
        if text == "c":
            return [DeleteMotion("selection", 1)] + self._set_mode(VimMode.INSERT)
        if text == "~":
            acts = [ToggleCase()] + self._set_mode(VimMode.NORMAL)
            return acts
        if text == "p":
            return [PasteAfter()] + self._set_mode(VimMode.NORMAL)
        if text == "o":
            return [MoveCursor("selection_other_end", 1)]
        if text == "V":
            return self._set_mode(VimMode.NORMAL) if line else self._set_mode(VimMode.VISUAL_LINE)
        if text == "v":
            return self._set_mode(VimMode.NORMAL) if not line else self._set_mode(VimMode.VISUAL)
        if text == ":":
            self.state.mode = VimMode.COMMAND
            self.state.command_buf = ":'<,'>"
            return [ChangeMode(VimMode.COMMAND), UpdateCommandBuf(":'<,'>")]

        s.reset_pending()
        return []

    # ---- Command mode -------------------------------------------------------

    def _command_mode(self, key: int, modifiers: int, text: str) -> list:
        s = self.state
        if key == _ESC:
            s.command_buf = ""
            return self._set_mode(VimMode.NORMAL)
        if key == _RETURN:
            cmd = s.command_buf.lstrip(":")
            s.command_buf = ""
            acts = self._set_mode(VimMode.NORMAL)
            return acts + [ExCommand(cmd)]
        if key == _BACKSPACE:
            if len(s.command_buf) > 1:
                s.command_buf = s.command_buf[:-1]
                return [UpdateCommandBuf(s.command_buf)]
            else:
                s.command_buf = ""
                return self._set_mode(VimMode.NORMAL)
        if text and text.isprintable():
            s.command_buf += text
            return [UpdateCommandBuf(s.command_buf)]
        return []
