"""Shared preview zoom controls and window-local keyboard shortcuts."""
from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QToolButton, QWidget,
)


class PreviewZoomBar(QWidget):
    """Adapt existing preview renderers without changing their image pipeline.

    Callbacks operate on the tool's own preview. Scale is measured in logical
    viewport pixels per source image pixel, as in the main image view.
    """

    def __init__(self, host, viewport, *, zoom_in, zoom_out, actual, fit,
                 scale, reduced=None, ctrl_wheel=False):
        super().__init__(host)
        self._host = host
        self._viewport = viewport
        self._fit = fit
        self._scale = scale
        self._reduced = reduced
        self._ctrl_wheel = ctrl_wheel
        self._fit_mode = True
        self._fit_pending = False
        self.actions_by_name = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for name, text, tip, icon, keys, callback in (
            ('out', '−', self.tr('Zoom Out'), 'zoom-out',
             ('Ctrl+-',), zoom_out),
            ('in', '+', self.tr('Zoom In'), 'zoom-in',
             ('Ctrl++', 'Ctrl+=', 'Ctrl+Shift+=', 'Ctrl+Shift++'), zoom_in),
            ('actual', '100%', self.tr('Actual Size'), 'zoom-original',
             ('Ctrl+1',), actual),
            ('fit', self.tr('Fit'), self.tr('Fit to Preview'), 'zoom-fit-best',
             ('Ctrl+0',), fit),
        ):
            action = QAction(QIcon.fromTheme(icon), text, host)
            action.setShortcuts([QKeySequence(key) for key in keys])
            action.setShortcutContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            shortcut = action.shortcuts()[0].toString(
                QKeySequence.SequenceFormat.NativeText
            )
            action.setToolTip(f'{tip} ({shortcut})')
            action.triggered.connect(
                lambda checked=False, cb=callback, fitting=(name == 'fit'):
                self._run(cb, fitting)
            )
            host.addAction(action)
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(button)
            self.actions_by_name[name] = action
        self.label = QLabel(self)
        row.addWidget(self.label)
        row.addStretch(1)
        viewport.installEventFilter(self)
        QApplication.instance().installEventFilter(self)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _run(self, callback, fitting):
        self._fit_mode = fitting
        callback()
        self.refresh()

    def refresh(self):
        if not self.isVisible():
            return
        scale = self._scale()
        text = f'{scale * 100:.1f}%'
        if self._reduced is not None and self._reduced():
            text += ' · ' + self.tr('Reduced preview')
        self.label.setText(text)

    def _refit(self):
        self._fit_pending = False
        if self._fit_mode and self.isVisible():
            self._fit()
            self.refresh()

    def eventFilter(self, obj, event):
        # Qt Tool windows inherit their parent's WindowShortcuts. Reserve
        # preview keys before shortcut resolution to avoid ambiguous matches
        # with the main image window. Route only events inside this tool.
        key_events = (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
        if (event.type() in key_events
                and isinstance(obj, QWidget) and obj.window() is self._host
                and self._host.isVisible()):
            sequence = QKeySequence(event.keyCombination())
            for action in self.actions_by_name.values():
                if any(sequence.matches(key)
                       == QKeySequence.SequenceMatch.ExactMatch
                       for key in action.shortcuts()):
                    event.accept()
                    if event.type() == QEvent.Type.KeyPress:
                        action.trigger()
                    return True
        if obj is self._viewport:
            if event.type() == QEvent.Type.Wheel:
                if (not self._ctrl_wheel or event.modifiers()
                        & Qt.KeyboardModifier.ControlModifier):
                    self._fit_mode = False
            elif event.type() == QEvent.Type.Resize:
                if self._fit_mode and not self._fit_pending:
                    self._fit_pending = True
                    QTimer.singleShot(0, self._refit)
        return False
