"""Shared preview zoom controls and window-local keyboard shortcuts."""
import itertools
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QKeyCombination, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractButton, QApplication, QBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QWidget,
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
        self._control_scopes = weakref.WeakSet([host])
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
        self.visible_buttons_by_name = {}
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
            # The host registers shortcuts, but the bar owns their lifetime.
            action = QAction(QIcon.fromTheme(icon), text, self)
            action.setShortcuts([QKeySequence(key) for key in keys])
            action.setShortcutContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            action.setAutoRepeat(name in ('in', 'out'))
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
                visible_button = button
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
                # Keep legacy references/signals for renderer busy states,
                # and present the same toolbar buttons in every preview.
                button.hide()
                visible_button = QToolButton(self)
                visible_button.setDefaultAction(action)
            visible_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            visible_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(visible_button)
            self.actions_by_name[name] = action
            self.buttons_by_name[name] = button
            self.visible_buttons_by_name[name] = visible_button
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
        self.preview_pane = None
        self.preview_content = None
        self.refresh()
        QTimer.singleShot(0, self._mount_preview)

    def _mount_preview(self):
        from .preview import PreviewPane, style_preview
        if sip.isdeleted(self) or sip.isdeleted(self._host):
            return
        self.preview_pane = PreviewPane.mount(
            self._viewport, self, self.preview_content,
        )
        for viewport in self._viewports:
            if not sip.isdeleted(viewport):
                style_preview(viewport)

    def enable_comparison(self, show_before):
        """Attach shared Space/button hold behavior to a cached renderer."""
        from .preview import HoldPreview
        self.comparison = HoldPreview(self, show_before)
        return self.comparison

    def enable_image_comparison(self, before_image, redraw, source_key=None):
        """Compare cached QImages without changing processing/zoom state."""
        from .preview import CachedImageComparison
        return CachedImageComparison(self, before_image, redraw, source_key)

    def enable_pixmap_comparison(self, before_image, item, source_key=None):
        """Compare a graphics pixmap without changing its transform."""
        comparison = self.enable_image_comparison(
            before_image,
            lambda: item.setPixmap(comparison.image(comparison.result)),
            source_key,
        )
        comparison.result = item.pixmap()
        return comparison

    def enable_canvas_comparison(self, canvas):
        """Let a custom painter display its cached original in place."""
        def show_before(before):
            canvas.setProperty('sasShowBefore', before)
            canvas.update()
        return self.enable_comparison(show_before)

    def enable_overlay_comparison(self, scene, base_item):
        """Temporarily hide compositing overlays above a source image."""
        from .preview import SceneOverlayComparison
        return SceneOverlayComparison(self, scene, base_item)

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

        names = {'in', 'out', 'actual', 'fit'}
        if not buttons or not set(buttons) <= names:
            raise ValueError('Provide named preview zoom buttons')
        if any(not isinstance(button, QAbstractButton)
               for button in buttons.values()):
            raise TypeError('Preview zoom controls must be QAbstractButtons')
        callbacks = {name: button.click for name, button in buttons.items()}
        for name, callback in (('actual', actual), ('in', zoom_in),
                               ('out', zoom_out), ('fit', fit)):
            if name not in callbacks:
                if not callable(callback):
                    raise ValueError(f'A preview needs a {name} callback')
                callbacks[name] = callback
        first = next(iter(buttons.values()))
        target = find_layout(first)
        layouts = [find_layout(button) for button in buttons.values()]
        if not isinstance(target, QBoxLayout) or any(
                layout is None for layout in layouts):
            raise ValueError('Preview zoom buttons must be in box layouts')
        index = min(target.indexOf(button) for button in buttons.values()
                    if target.indexOf(button) >= 0)
        for button, layout in zip(buttons.values(), layouts):
            layout.removeWidget(button)
        if actual is not None and 'actual' in buttons:
            try:
                buttons['actual'].clicked.disconnect()
            except TypeError:
                pass  # A legacy button may not have a connection yet.
            buttons['actual'].clicked.connect(actual)
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

    def watch_controls(self, widget):
        """Route shortcuts from an explicitly linked detached editor window."""
        self._control_scopes.add(widget)
        for action in self.actions_by_name.values():
            widget.addAction(action)

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
        if sip.isdeleted(self) or sip.isdeleted(self._host):
            return
        for name, button in self.buttons_by_name.items():
            if (isinstance(button, QToolButton)
                    and button.defaultAction() is self.actions_by_name[name]):
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
        if (not sip.isdeleted(self) and not sip.isdeleted(self._host)
                and self._fit_mode and self._has_visible_viewport()):
            self._fit()
            self.refresh()

    def _has_visible_viewport(self):
        return any(not sip.isdeleted(viewport) and viewport.isVisible()
                   for viewport in self._viewports)

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
            if not bar._has_visible_viewport():
                continue
            for scope in list(bar._control_scopes):
                if sip.isdeleted(scope) or scope.window() is not obj.window():
                    continue
                depth, parent = 0, obj
                while parent is not None and parent is not scope:
                    depth += 1
                    parent = parent.parentWidget()
                if parent is scope:
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
        if (not getattr(self, "_ready", False)
                or sip.isdeleted(self._host)):
            return False
        # Qt Tool windows inherit their parent's WindowShortcuts. Reserve
        # preview keys before shortcut resolution to avoid ambiguous matches
        # with the main image window. Route only events inside this tool.
        key_events = (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
        if (event.type() in key_events
                and self._has_visible_viewport() and self._handles_keys(obj)):
            # Numeric-pad keys are the same zoom commands. Native backends
            # differ in whether shortcut matching removes KeypadModifier.
            combination = event.keyCombination().toCombined()
            combination &= ~Qt.KeyboardModifier.KeypadModifier.value
            sequence = QKeySequence(QKeyCombination.fromCombined(combination))
            self.refresh()
            for action in self.actions_by_name.values():
                if any(sequence.matches(key)
                       == QKeySequence.SequenceMatch.ExactMatch
                       for key in action.shortcuts()):
                    event.accept()
                    if event.type() == QEvent.Type.KeyPress:
                        if (action.isEnabled()
                                and (not event.isAutoRepeat()
                                     or action.autoRepeat())):
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
                moved = not (event.angleDelta().isNull()
                             and event.pixelDelta().isNull())
                if moved and (not self._ctrl_wheel or event.modifiers()
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
