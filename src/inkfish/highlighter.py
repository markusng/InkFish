"""Syntax highlighting for code files.

Uses QSyntaxHighlighter with rule-based single-line matching plus block-state
tracking for multi-line constructs (/* */ comments, triple-quoted strings).

Block states:
  0 / -1 : normal
  1      : inside /* ... */ block comment  (C / C++ / JS)
  2      : inside triple-double-quote string  (Python)
  3      : inside triple-single-quote string  (Python)
"""
from __future__ import annotations

import re

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


# ---- colour palette (VSCode Dark+ inspired) ----------------------------------

def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


_KW       = _fmt("#569cd6", bold=True)    # keywords
_BUILTIN  = _fmt("#4ec9b0")               # built-ins / types
_STRING   = _fmt("#ce9178")               # strings
_COMMENT  = _fmt("#6a9955", italic=True)  # comments
_NUMBER   = _fmt("#b5cea8")               # numeric literals
_DECO     = _fmt("#c586c0")               # decorators / preprocessor
_FUNC     = _fmt("#dcdcaa")               # function / method names
_TAG      = _fmt("#569cd6")               # HTML/XML tags
_ATTR     = _fmt("#9cdcfe")               # HTML attributes
_HDG      = _fmt("#569cd6", bold=True)    # Markdown headings
_BOLD     = _fmt("#d4d4d4", bold=True)
_ITALIC   = _fmt("#d4d4d4", italic=True)
_CODE     = _fmt("#ce9178")               # inline code


# ---- helpers -----------------------------------------------------------------

def _kw(*words: str) -> re.Pattern:
    return re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b')


# ---- Python ------------------------------------------------------------------

_PY_KEYWORDS = (
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
    'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
    'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
    'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
    'while', 'with', 'yield',
)
_PY_BUILTINS = (
    'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'breakpoint', 'bytearray',
    'bytes', 'callable', 'chr', 'classmethod', 'compile', 'complex',
    'delattr', 'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec',
    'filter', 'float', 'format', 'frozenset', 'getattr', 'globals',
    'hasattr', 'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance',
    'issubclass', 'iter', 'len', 'list', 'locals', 'map', 'max',
    'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord', 'pow',
    'print', 'property', 'range', 'repr', 'reversed', 'round', 'set',
    'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super',
    'tuple', 'type', 'vars', 'zip',
)

_PY_SL_RULES: list[tuple[re.Pattern, QTextCharFormat]] = [
    (_kw(*_PY_KEYWORDS),                                             _KW),
    (_kw(*_PY_BUILTINS),                                             _BUILTIN),
    (re.compile(r'\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[jJ]?\b'),        _NUMBER),
    (re.compile(r'(?<!\w)@[\w.]+'),                                   _DECO),
    (re.compile(r'\bdef\s+([\w]+)', re.ASCII),                        None),   # see below
    # Single-line strings (after triple patterns handled in block logic)
    (re.compile(r'[fFrRbBuU]{0,2}"(?:[^"\\]|\\.)*"'),                _STRING),
    (re.compile(r"[fFrRbBuU]{0,2}'(?:[^'\\]|\\.)*'"),                _STRING),
    (re.compile(r'#[^\n]*'),                                          _COMMENT),
]

# Patch: function name after 'def'
_PY_DEF_RE   = re.compile(r'\bdef\s+([\w]+)')
_PY_CLASS_RE = re.compile(r'\bclass\s+([\w]+)')


class PythonHighlighter(QSyntaxHighlighter):
    _TDQ = re.compile(r'"""')
    _TSQ = re.compile(r"'''")
    _IN_TDQ, _IN_TSQ = 2, 3

    def highlightBlock(self, text: str) -> None:
        # --- single-line rules ---
        for pat, fmt in _PY_SL_RULES:
            if fmt is None:
                continue
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # function / class names
        for m in _PY_DEF_RE.finditer(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1), _FUNC)
        for m in _PY_CLASS_RE.finditer(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1), _BUILTIN)

        # --- multi-line triple strings ---
        self.setCurrentBlockState(0)
        state = self.previousBlockState()
        i = 0

        if state in (self._IN_TDQ, self._IN_TSQ):
            delim = self._TDQ if state == self._IN_TDQ else self._TSQ
            m = delim.search(text)
            if m:
                self.setFormat(0, m.end(), _STRING)
                i = m.end()
                state = 0
            else:
                self.setFormat(0, len(text), _STRING)
                self.setCurrentBlockState(state)
                return

        while i < len(text):
            dq = self._TDQ.search(text, i)
            sq = self._TSQ.search(text, i)
            # pick the one that starts first
            match, new_state, delim = None, 0, None
            if dq and (not sq or dq.start() <= sq.start()):
                match, new_state, delim = dq, self._IN_TDQ, self._TDQ
            elif sq:
                match, new_state, delim = sq, self._IN_TSQ, self._TSQ
            if match is None:
                break
            end_m = delim.search(text, match.end())
            if end_m:
                self.setFormat(match.start(), end_m.end() - match.start(), _STRING)
                i = end_m.end()
            else:
                self.setFormat(match.start(), len(text) - match.start(), _STRING)
                self.setCurrentBlockState(new_state)
                return

        self.setCurrentBlockState(state if state in (self._IN_TDQ, self._IN_TSQ) else 0)


# ---- C / C++ / JS (shared block-comment logic) -------------------------------

_C_KEYWORDS = (
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if',
    'inline', 'int', 'long', 'register', 'restrict', 'return', 'short',
    'signed', 'sizeof', 'static', 'struct', 'switch', 'typedef', 'union',
    'unsigned', 'void', 'volatile', 'while',
    # C++ extras
    'alignas', 'alignof', 'bool', 'catch', 'class', 'constexpr', 'consteval',
    'constinit', 'co_await', 'co_return', 'co_yield', 'decltype', 'delete',
    'explicit', 'export', 'false', 'friend', 'mutable', 'namespace', 'new',
    'noexcept', 'nullptr', 'operator', 'override', 'private', 'protected',
    'public', 'static_assert', 'template', 'this', 'throw', 'true', 'try',
    'typeid', 'typename', 'using', 'virtual',
)
_JS_KEYWORDS = (
    'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue',
    'debugger', 'default', 'delete', 'do', 'else', 'export', 'extends',
    'false', 'finally', 'for', 'from', 'function', 'if', 'import', 'in',
    'instanceof', 'let', 'new', 'null', 'of', 'return', 'static', 'super',
    'switch', 'this', 'throw', 'true', 'try', 'typeof', 'undefined', 'var',
    'void', 'while', 'with', 'yield',
)

_C_SL_RULES: list[tuple[re.Pattern, QTextCharFormat]] = [
    (_kw(*_C_KEYWORDS),                                               _KW),
    (re.compile(r'\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*\b'),     _NUMBER),
    (re.compile(r'#\s*\w+'),                                           _DECO),
    (re.compile(r'"(?:[^"\\]|\\.)*"'),                                 _STRING),
    (re.compile(r"'(?:[^'\\]|\\.)*'"),                                 _STRING),
    (re.compile(r'//[^\n]*'),                                          _COMMENT),
]
_JS_SL_RULES: list[tuple[re.Pattern, QTextCharFormat]] = [
    (_kw(*_JS_KEYWORDS),                                               _KW),
    (re.compile(r'\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b'),               _NUMBER),
    (re.compile(r'"(?:[^"\\]|\\.)*"'),                                 _STRING),
    (re.compile(r"'(?:[^'\\]|\\.)*'"),                                 _STRING),
    (re.compile(r'`(?:[^`\\]|\\.)*`'),                                 _STRING),
    (re.compile(r'//[^\n]*'),                                          _COMMENT),
]

_BC_START = re.compile(r'/\*')
_BC_END   = re.compile(r'\*/')
_IN_BC    = 1


class _BlockCommentHighlighter(QSyntaxHighlighter):
    def __init__(self, document, sl_rules) -> None:
        super().__init__(document)
        self._sl = sl_rules

    def highlightBlock(self, text: str) -> None:
        for pat, fmt in self._sl:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        self.setCurrentBlockState(0)
        i = 0
        if self.previousBlockState() == _IN_BC:
            m = _BC_END.search(text)
            if m:
                self.setFormat(0, m.end(), _COMMENT)
                i = m.end()
            else:
                self.setFormat(0, len(text), _COMMENT)
                self.setCurrentBlockState(_IN_BC)
                return

        while True:
            sm = _BC_START.search(text, i)
            if not sm:
                break
            em = _BC_END.search(text, sm.end())
            if em:
                self.setFormat(sm.start(), em.end() - sm.start(), _COMMENT)
                i = em.end()
            else:
                self.setFormat(sm.start(), len(text) - sm.start(), _COMMENT)
                self.setCurrentBlockState(_IN_BC)
                break


class CppHighlighter(_BlockCommentHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document, _C_SL_RULES)


class JsHighlighter(_BlockCommentHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document, _JS_SL_RULES)


# ---- Markdown ----------------------------------------------------------------

_MD_RULES: list[tuple[re.Pattern, QTextCharFormat]] = [
    (re.compile(r'^#{1,6}\s.*$', re.MULTILINE),   _HDG),
    (re.compile(r'\*\*[^*]+\*\*'),                _BOLD),
    (re.compile(r'__[^_]+__'),                     _BOLD),
    (re.compile(r'\*[^*]+\*'),                     _ITALIC),
    (re.compile(r'_[^_]+_'),                       _ITALIC),
    (re.compile(r'`[^`]+`'),                       _CODE),
    (re.compile(r'^```.*$', re.MULTILINE),         _CODE),
    (re.compile(r'^>\s.*$', re.MULTILINE),         _COMMENT),
]


class MarkdownHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        for pat, fmt in _MD_RULES:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ---- HTML --------------------------------------------------------------------

_HTML_RULES: list[tuple[re.Pattern, QTextCharFormat]] = [
    (re.compile(r'<!--.*?-->', re.DOTALL),                 _COMMENT),
    (re.compile(r'</?[\w:.-]+'),                           _TAG),
    (re.compile(r'\b[\w:-]+='),                            _ATTR),
    (re.compile(r'"[^"]*"'),                               _STRING),
    (re.compile(r"'[^']*'"),                               _STRING),
    (re.compile(r'>'),                                     _TAG),
]


class HtmlHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        for pat, fmt in _HTML_RULES:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ---- factory -----------------------------------------------------------------

def create_highlighter(
    ext: str, document
) -> QSyntaxHighlighter | None:
    """Return an attached QSyntaxHighlighter for *ext*, or None for plain text."""
    ext = ext.lower()
    cls = {
        ".py":  PythonHighlighter,
        ".c":   CppHighlighter,
        ".cpp": CppHighlighter,
        ".h":   CppHighlighter,
        ".c++": CppHighlighter,
        ".h++": CppHighlighter,
        ".js":  JsHighlighter,
        ".md":  MarkdownHighlighter,
        ".html": HtmlHighlighter,
    }.get(ext)
    return cls(document) if cls is not None else None
