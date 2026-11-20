"""Shared preview zoom controls and window-local keyboard shortcuts."""
import itertools
import weakref

from PyQt6 import sip
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

    _instances = weakref.WeakSet()
    _sequence = itertools.count()

    def __init__(self, host, viewport, *, zoom_in, zoom_out, actual, fit,
                 scale, reduced=None, ctrl_wheel=False, buttons=None):
        super().__init__(host)
        self._instances.add(self)
        self._order = next(self._sequence)
        self._host = host
        self._viewport = viewport
        self._viewports = [viewport]
        self._fit = fit
        self._scale = scale
        self._reduced = reduced
        self._ctrl_wheel = ctrl_wheel
        self._fit_mode = True
        self._fit_pending = False
        self.actions_by_name = {}
        self.buttons_by_name = {}
        buttons = buttons or {}
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
            button = buttons.get(name)
            if button is None:
                button = QToolButton(self)
                button.setDefaultAction(action)
            else:
                # Keep the tool's connections and enabled state when adopting
                # existing controls, including linked previews and busy states.
                button.setParent(self)
                button.setText(text)
                button.setIcon(action.icon())
                button.setToolTip(action.toolTip())
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
                button.clicked.connect(
                    lambda checked=False, fitting=(name == 'fit'):
                    self._adopted_clicked(fitting)
                )
            if isinstance(button, QToolButton):
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                )
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(button)
            self.actions_by_name[name] = action
            self.buttons_by_name[name] = button
        self.label = QLabel(self)
        row.addWidget(self.label)
        row.addStretch(1)
        self._ready = True
        viewport.installEventFilter(self)
        QApplication.instance().installEventFilter(self)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    @classmethod
    def replace(cls, host, viewport, *, buttons, scale, actual=None,
                reduced=None, ctrl_wheel=False, zoom_in=None, zoom_out=None,
                fit=None):
        """Replace a legacy zoom row, retaining its buttons and signal wiring.

        ``buttons`` maps action names to existing QAbstractButtons.
        An explicit ``actual`` callback replaces the legacy 100% connection.
        All buttons must already belong to layouts inside ``host``.
        """
        def find_layout(widget):
            def walk(layout):
                if layout is None:
                    return None
                if layout.indexOf(widget) >= 0:
                    return layout
                for index in range(layout.count()):
                    item = layout.itemAt(index)
                    nested = item.layout()
                    if nested is None and item.widget() is not None:
                        nested = item.widget().layout()
                    found = walk(nested)
                    if found is not None:
                        return found
                return None
            parent = widget.parentWidget()
            layout = parent.layout() if parent is not None else host.layout()
            return walk(layout)

        first = next(iter(buttons.values()))
        target = find_layout(first)
        if target is None:
            raise ValueError('Preview zoom buttons must be in a layout')
        index = min(target.indexOf(button) for button in buttons.values()
                    if target.indexOf(button) >= 0)
        for button in buttons.values():
            layout = find_layout(button)
            if layout is not None:
                layout.removeWidget(button)
        if actual is not None and 'actual' in buttons:
            buttons['actual'].clicked.disconnect()
            buttons['actual'].clicked.connect(actual)
        callbacks = {name: button.click for name, button in buttons.items()}
        for name, callback in (('actual', actual), ('in', zoom_in),
                               ('out', zoom_out), ('fit', fit)):
            if name not in callbacks:
                if callback is None:
                    raise ValueError(f'A preview needs a {name} callback')
                callbacks[name] = callback
        bar = cls(host, viewport, zoom_in=callbacks['in'],
                  zoom_out=callbacks['out'], actual=callbacks['actual'],
                  fit=callbacks['fit'], scale=scale, reduced=reduced,
                  ctrl_wheel=ctrl_wheel, buttons=buttons)
        # Zoom rows are box layouts; keep unrelated controls in the same row.
        target.insertWidget(index, bar)
        return bar

    def watch_viewport(self, viewport):
        """Keep fit mode in sync with an additional linked preview."""
        self._viewports.append(viewport)
        viewport.installEventFilter(self)

    def _activate(self):
        self._host.window()._active_preview_zoom_bar = weakref.ref(self)

    def _adopted_clicked(self, fitting):
        self._activate()
        self._fit_mode = fitting
        self.refresh()

    def _run(self, callback, fitting):
        self._activate()
        self._fit_mode = fitting
        callback()
        self.refresh()

    def refresh(self):
        for name, button in self.buttons_by_name.items():
            if (isinstance(button, QToolButton)
                    and button.defaultAction() is not None):
                continue
            self.actions_by_name[name].setEnabled(button.isEnabled())
        if not self.isVisible():
            return
        scale = self._scale()
        text = f'{scale * 100:.1f}%'
        if self._reduced is not None and self._reduced():
            text += ' · ' + self.tr('Reduced preview')
        self.label.setText(text)

    def _refit(self):
        self._fit_pending = False
        if self._fit_mode and self._viewport.isVisible():
            self._fit()
            self.refresh()

    def _handles_keys(self, obj):
        # Embedded tools and multiple independent previews share a window.
        # Prefer the closest host, then the preview last used in that window.
        if not isinstance(obj, QWidget):
            return False
        candidates = []
        for bar in list(self._instances):
            if (sip.isdeleted(bar) or not getattr(bar, "_ready", False)
                    or sip.isdeleted(bar._host)):
                continue
            if (sip.isdeleted(bar._viewport) or not bar._viewport.isVisible()
                    or bar._host.window() is not obj.window()):
                continue
            depth, parent = 0, obj
            while parent is not None and parent is not bar._host:
                depth += 1
                parent = parent.parentWidget()
            if parent is bar._host:
                candidates.append((depth, bar._order, bar))
        if not candidates:
            return False
        nearest = min(item[0] for item in candidates)
        candidates = [item for item in candidates if item[0] == nearest]
        focused = [bar for _, _, bar in candidates
                   if any(obj is viewport or viewport.isAncestorOf(obj)
                          or obj is viewport.parentWidget()
                          for viewport in bar._viewports
                          if not sip.isdeleted(viewport))]
        if len(focused) == 1:
            return focused[0] is self
        active = getattr(obj.window(), '_active_preview_zoom_bar', None)
        active = active() if active is not None else None
        chosen = next((bar for _, _, bar in candidates if bar is active), None)
        return (chosen or min(candidates, key=lambda item: item[1])[2]) is self

    def eventFilter(self, obj, event):
        if not getattr(self, "_ready", False) or sip.isdeleted(self._viewport):
            return False
        # Qt Tool windows inherit their parent's WindowShortcuts. Reserve
        # preview keys before shortcut resolution to avoid ambiguous matches
        # with the main image window. Route only events inside this tool.
        key_events = (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
        if (event.type() in key_events
                and self._handles_keys(obj)):
            sequence = QKeySequence(event.keyCombination())
            self.refresh()
            for action in self.actions_by_name.values():
                if any(sequence.matches(key)
                       == QKeySequence.SequenceMatch.ExactMatch
                       for key in action.shortcuts()):
                    event.accept()
                    if event.type() == QEvent.Type.KeyPress:
                        if action.isEnabled():
                            action.trigger()
                    return True
        inside = (isinstance(obj, QWidget)
                  and any(not sip.isdeleted(viewport)
                          and (obj is viewport or viewport.isAncestorOf(obj))
                          for viewport in self._viewports))
        if inside and event.type() in (QEvent.Type.MouseButtonPress,
                                       QEvent.Type.FocusIn):
            self._activate()
        if inside:
            if event.type() == QEvent.Type.Wheel:
                if (not self._ctrl_wheel or event.modifiers()
                        & Qt.KeyboardModifier.ControlModifier):
                    self._fit_mode = False
            elif obj in self._viewports and event.type() == QEvent.Type.Resize:
                if self._fit_mode and not self._fit_pending:
                    self._fit_pending = True
                    QTimer.singleShot(0, self._refit)
        return False


def preview_ratio(preview, source):
    """Return preview pixels per source pixel for an array or base pixmap."""
    if preview is None or source is None:
        return 1.0
    width = (preview.shape[1] if hasattr(preview, 'shape')
             else preview.width())
    if width <= 0 or source.shape[1] <= 0:
        return 1.0
    return width / source.shape[1]
