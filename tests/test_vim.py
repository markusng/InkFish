"""Unit tests for VimEngine — no Qt required."""
from inkfish.vim import (
    ChangeMode, DeleteChar, DeleteMotion, FindChar, JoinLines, MoveCursor,
    OpenLine, PasteAfter, PasteBefore, Redo, ReplaceChar, SearchForward,
    SearchNext, ToggleCase, Undo, VimEngine, VimMode, YankMotion,
    ExCommand, UpdateCommandBuf,
    _ESC, _BACKSPACE, _RETURN, _LEFT, _RIGHT, _UP, _DOWN, _CTRL,
)

_NO_MOD = 0


def _key(ch: str, mod: int = 0) -> tuple:
    return ord(ch.upper()), mod, ch


def _special(code: int, mod: int = 0) -> tuple:
    return code, mod, ""


def _ctrl(ch: str) -> tuple:
    return ord(ch.upper()), _CTRL, ch


def press(engine: VimEngine, *args) -> list:
    """Press a sequence of keys (each as (key, mod, text) tuple)."""
    results = []
    for key, mod, text in args:
        results = engine.process_key(key, mod, text)
    return results


# ---- Mode transitions --------------------------------------------------------

def test_starts_in_normal():
    assert VimEngine().mode == VimMode.NORMAL


def test_i_enters_insert():
    e = VimEngine()
    acts = press(e, _key("i"))
    assert e.mode == VimMode.INSERT
    assert any(isinstance(a, ChangeMode) and a.mode == VimMode.INSERT for a in acts)


def test_esc_returns_to_normal():
    e = VimEngine()
    press(e, _key("i"))
    acts = press(e, _special(_ESC))
    assert e.mode == VimMode.NORMAL
    assert any(isinstance(a, ChangeMode) and a.mode == VimMode.NORMAL for a in acts)


def test_v_enters_visual():
    e = VimEngine()
    press(e, _key("v"))
    assert e.mode == VimMode.VISUAL


def test_V_enters_visual_line():
    e = VimEngine()
    acts = press(e, (ord("V"), 0, "V"))
    assert e.mode == VimMode.VISUAL_LINE
    assert any(isinstance(a, ChangeMode) and a.mode == VimMode.VISUAL_LINE for a in acts)


def test_colon_enters_command():
    e = VimEngine()
    acts = press(e, _key(":"))
    assert e.mode == VimMode.COMMAND
    assert any(isinstance(a, UpdateCommandBuf) and a.buf == ":" for a in acts)


# ---- Movement ---------------------------------------------------------------

def test_hjkl_movement():
    e = VimEngine()
    for ch, motion in [("h", "left"), ("l", "right"), ("j", "down"), ("k", "up")]:
        acts = press(e, _key(ch))
        assert any(isinstance(a, MoveCursor) and a.motion == motion for a in acts)


def test_word_motions():
    e = VimEngine()
    for ch, motion in [("w", "word_next"), ("b", "word_prev"), ("e", "word_end")]:
        acts = press(e, _key(ch))
        assert any(isinstance(a, MoveCursor) and a.motion == motion for a in acts)


def test_line_start_end():
    e = VimEngine()
    acts = press(e, (ord("0"), 0, "0"))
    assert any(isinstance(a, MoveCursor) and a.motion == "line_start" for a in acts)
    acts = press(e, (ord("$"), 0, "$"))
    assert any(isinstance(a, MoveCursor) and a.motion == "line_end" for a in acts)


def test_G_goes_to_end():
    e = VimEngine()
    acts = press(e, (ord("G"), 0, "G"))
    assert any(isinstance(a, MoveCursor) and a.motion == "end" for a in acts)


def test_gg_goes_to_start():
    e = VimEngine()
    press(e, _key("g"))
    acts = press(e, _key("g"))
    assert any(isinstance(a, MoveCursor) and a.motion == "start" for a in acts)


# ---- Count accumulation -----------------------------------------------------

def test_count_prefix_on_move():
    e = VimEngine()
    press(e, (ord("3"), 0, "3"))
    acts = press(e, _key("j"))
    assert any(isinstance(a, MoveCursor) and a.motion == "down" and a.count == 3 for a in acts)


def test_count_cleared_after_action():
    e = VimEngine()
    press(e, (ord("5"), 0, "5"))
    press(e, _key("j"))
    assert e.state.count_str == ""


# ---- Operators + motions ----------------------------------------------------

def test_dd_deletes_line():
    e = VimEngine()
    press(e, _key("d"))
    acts = press(e, _key("d"))
    assert any(isinstance(a, DeleteMotion) and a.motion == "line" for a in acts)


def test_3dd_deletes_3_lines():
    e = VimEngine()
    press(e, (ord("3"), 0, "3"))
    press(e, _key("d"))
    acts = press(e, _key("d"))
    assert any(isinstance(a, DeleteMotion) and a.motion == "line" and a.count == 3 for a in acts)


def test_dw_deletes_word():
    e = VimEngine()
    press(e, _key("d"))
    acts = press(e, _key("w"))
    assert any(isinstance(a, DeleteMotion) and a.motion == "word_next" for a in acts)


def test_yy_yanks_line():
    e = VimEngine()
    press(e, _key("y"))
    acts = press(e, _key("y"))
    assert any(isinstance(a, YankMotion) and a.motion == "line" for a in acts)


def test_cw_changes_word():
    e = VimEngine()
    press(e, _key("c"))
    acts = press(e, _key("w"))
    assert any(isinstance(a, DeleteMotion) and a.motion == "word_next" for a in acts)
    assert any(isinstance(a, ChangeMode) and a.mode == VimMode.INSERT for a in acts)


def test_operator_cleared_on_escape():
    e = VimEngine()
    press(e, _key("d"))
    press(e, _special(_ESC))
    assert e.state.operator == ""


# ---- Standalone edits -------------------------------------------------------

def test_x_deletes_char():
    e = VimEngine()
    acts = press(e, _key("x"))
    assert any(isinstance(a, DeleteChar) and not a.before for a in acts)


def test_X_deletes_before():
    e = VimEngine()
    acts = press(e, (ord("X"), 0, "X"))
    assert any(isinstance(a, DeleteChar) and a.before for a in acts)


def test_u_undoes():
    e = VimEngine()
    acts = press(e, _key("u"))
    assert any(isinstance(a, Undo) for a in acts)


def test_ctrl_r_redoes():
    e = VimEngine()
    acts = press(e, _ctrl("r"))
    assert any(isinstance(a, Redo) for a in acts)


def test_p_pastes_after():
    e = VimEngine()
    acts = press(e, _key("p"))
    assert any(isinstance(a, PasteAfter) for a in acts)


def test_P_pastes_before():
    e = VimEngine()
    acts = press(e, (ord("P"), 0, "P"))
    assert any(isinstance(a, PasteBefore) for a in acts)


def test_r_replaces_char():
    e = VimEngine()
    press(e, _key("r"))
    acts = press(e, _key("a"))
    assert any(isinstance(a, ReplaceChar) and a.char == "a" for a in acts)


def test_tilde_toggles_case():
    e = VimEngine()
    acts = press(e, (ord("~"), 0, "~"))
    assert any(isinstance(a, ToggleCase) for a in acts)


def test_J_joins_lines():
    e = VimEngine()
    acts = press(e, (ord("J"), 0, "J"))
    assert any(isinstance(a, JoinLines) for a in acts)


def test_dot_repeats_last():
    e = VimEngine()
    press(e, _key("x"))
    acts = press(e, (ord("."), 0, "."))
    assert any(isinstance(a, DeleteChar) for a in acts)


# ---- Find char --------------------------------------------------------------

def test_f_motion():
    e = VimEngine()
    press(e, _key("f"))
    acts = press(e, _key("a"))
    assert any(isinstance(a, FindChar) and a.char == "a" and a.forward and not a.till for a in acts)


def test_F_motion_backward():
    e = VimEngine()
    press(e, (ord("F"), 0, "F"))
    acts = press(e, _key("x"))
    assert any(isinstance(a, FindChar) and a.char == "x" and not a.forward for a in acts)


def test_t_till_motion():
    e = VimEngine()
    press(e, _key("t"))
    acts = press(e, _key("b"))
    assert any(isinstance(a, FindChar) and a.char == "b" and a.forward and a.till for a in acts)


def test_df_deletes_to_char():
    e = VimEngine()
    press(e, _key("d"))
    press(e, _key("f"))
    acts = press(e, _key("z"))
    assert any(isinstance(a, DeleteMotion) and isinstance(a.motion, FindChar) and a.motion.char == "z" for a in acts)


# ---- Visual mode ------------------------------------------------------------

def test_visual_movement_keeps_anchor():
    e = VimEngine()
    press(e, _key("v"))
    acts = press(e, _key("l"))
    assert any(isinstance(a, MoveCursor) and a.motion == "right" and a.keep_anchor for a in acts)


def test_visual_d_deletes_selection():
    e = VimEngine()
    press(e, _key("v"))
    press(e, _key("l"))
    acts = press(e, _key("d"))
    assert any(isinstance(a, DeleteMotion) and a.motion == "selection" for a in acts)
    assert e.mode == VimMode.NORMAL


def test_visual_esc_returns_normal():
    e = VimEngine()
    press(e, _key("v"))
    press(e, _special(_ESC))
    assert e.mode == VimMode.NORMAL


# ---- Command mode -----------------------------------------------------------

def test_command_accumulates_text():
    e = VimEngine()
    press(e, (ord(":"), 0, ":"))
    press(e, _key("w"))
    acts = press(e, _key("q"))
    assert any(isinstance(a, UpdateCommandBuf) and "wq" in a.buf for a in acts)


def test_command_enter_emits_ex_command():
    e = VimEngine()
    press(e, (ord(":"), 0, ":"))
    press(e, _key("w"))
    acts = press(e, _special(_RETURN))
    assert any(isinstance(a, ExCommand) and a.command.strip() == "w" for a in acts)
    assert e.mode == VimMode.NORMAL


def test_command_backspace():
    e = VimEngine()
    press(e, (ord(":"), 0, ":"))
    press(e, _key("w"))
    acts = press(e, _special(_BACKSPACE))
    assert any(isinstance(a, UpdateCommandBuf) and a.buf == ":" for a in acts)


def test_command_esc_cancels():
    e = VimEngine()
    press(e, (ord(":"), 0, ":"))
    press(e, _special(_ESC))
    assert e.mode == VimMode.NORMAL


# ---- Insert mode passthrough ------------------------------------------------

def test_insert_non_esc_returns_empty():
    e = VimEngine()
    press(e, _key("i"))
    acts = press(e, _key("a"))
    assert acts == []


def test_insert_esc_to_normal_moves_left():
    e = VimEngine()
    press(e, _key("i"))
    acts = press(e, _special(_ESC))
    assert any(isinstance(a, MoveCursor) and a.motion == "left" for a in acts)
    assert e.mode == VimMode.NORMAL
