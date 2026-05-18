"""Splash screen shown on startup."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

_ART = r"""
          *    *    *    *    *    *    *    *    *
        *    .                               .    *
      *    .    .  .  .  .  .  .  .  .  .    .    *
    *    .    .                               .    .    *
   *    .    .    . - - - - - - - - - - - .    .    .   *
  *    .    .   /                           \    .    .  *
  *   .    .   /    ~  ~  ~  ~  ~  ~  ~  ~   \   .    . *
 *    .    .  |                               |    .    . *
 *    .    .  |    (( O ))         (( O ))    |    .    . *
 *    .    .  |                               |    .    . *
 *    .    .  |          > > > > > > >        |    .    . *
 *    .    .  |                               |    .    . *
 *    .    .  |    ~  ~  ~  ~  ~  ~  ~  ~    |    .    . *
 *    .    .  |                               |    .    . *
  *   .    .   \                             /   .    .  *
  *    .    .   \  .  .  .  .  .  .  .  .  /    .    .  *
   *    .    .    ' - - - - - - - - - - - '    .    .   *
    *    .    .                               .    .    *
      *    .    .  .  .  .  .  .  .  .  .    .    *
        *    .                               .    *
          *    *    *    *    *    *    *    *    *
"""

_TITLE    = "SquidPad"
_SUBTITLE = "pinch · zoom · edit"
_HINT     = "press any key or esc to continue"


class SplashScreen(QDialog):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.setSpacing(0)

        def _mono(size: int, bold: bool = False) -> QFont:
            f = QFont("Courier New")
            f.setStyleHint(QFont.StyleHint.Monospace)
            f.setPointSize(size)
            f.setBold(bold)
            return f

        title = QLabel(_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(_mono(30, bold=True))
        title.setStyleSheet("color: #f0e68c;")
        layout.addWidget(title)

        subtitle = QLabel(_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(_mono(10))
        subtitle.setStyleSheet("color: #87ceeb; letter-spacing: 2px;")
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        art = QLabel(_ART.strip("\n"))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setFont(_mono(9))
        art.setStyleSheet("color: #7fffd4;")
        layout.addWidget(art)

        layout.addSpacing(14)

        hint = QLabel(_HINT)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFont(_mono(8))
        hint.setStyleSheet("color: #445566;")
        layout.addWidget(hint)

        self.setStyleSheet("QDialog { background-color: #0d1117; }")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.accept)
        self._timer.start(5000)

        self.adjustSize()
        if screen := QApplication.primaryScreen():
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._timer.stop()
        self.accept()

    def mousePressEvent(self, event) -> None:
        self._timer.stop()
        self.accept()
