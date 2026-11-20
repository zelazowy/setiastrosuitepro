"""Shared image-preview presentation and temporary before/after comparison."""
import weakref
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox,
    QGraphicsProxyWidget, QGraphicsTextItem, QGraphicsView, QGroupBox,
    QLabel, QLineEdit, QPlainTextEdit, QScrollArea,
    QSplitter, QTextEdit,
    QToolBar, QVBoxLayout, QWidget,
)

PREVIEW_BACKGROUND = '#181818'


def _style_surface(viewport):
    color = QColor(PREVIEW_BACKGROUND)
    palette = viewport.palette()
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.Base, color)
    viewport.setPalette(palette)
    viewport.setAutoFillBackground(True)
    viewport.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    viewport.setObjectName('sasImagePreviewViewport')
    if not viewport.property('sasPreviewStyled'):
        previous = viewport.styleSheet()
        declarations = 'background-color: ' + PREVIEW_BACKGROUND + ';'
        if previous.strip() and '{' not in previous:
            declarations = previous + '; ' + declarations
            previous = ''
        viewport.setStyleSheet(
            previous + '\nQWidget#sasImagePreviewViewport { '
            + declarations + ' }'
        )
        viewport.setProperty('sasPreviewStyled', True)


def style_preview(viewport):
    """Give image margins an opaque, neutral background in either app theme."""
    _style_surface(viewport)
    color = QColor(PREVIEW_BACKGROUND)
    view = viewport.parentWidget()
    if isinstance(view, QGraphicsView) and view.viewport() is viewport:
        view.setBackgroundBrush(QBrush(color))
    elif isinstance(view, QScrollArea) and isinstance(view.widget(), QLabel):
        _style_surface(view.widget())


def _remove_from_layout(layout, widget):
    if layout is None:
        return
    layout.removeWidget(widget)
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.layout() is not None:
            _remove_from_layout(item.layout(), widget)


class PreviewPane(QWidget):
    """Keep an existing image renderer directly above its shared zoom bar."""

    @classmethod
    def mount(cls, viewport, bar, content=None):
        """Wrap a laid-out view, preserving grid/splitter position and sizing.

        Explicit ``content`` can group linked views under one control bar.
        The caller retains its original view and viewport references.
        """
        if sip.isdeleted(viewport) or sip.isdeleted(bar):
            return None
        style_preview(viewport)
        view = content or viewport
        parent = viewport.parentWidget()
        if content is None and isinstance(parent, QAbstractScrollArea):
            if parent.viewport() is viewport:
                view = parent
        # Some painting tools put their graphics view inside an outer scroll
        # area. Keep that scrolling arrangement intact and wrap the outer view.
        while view.parentWidget() is not None:
            outer = view.parentWidget().parentWidget()
            if isinstance(outer, QScrollArea) and outer.widget() is view:
                view = outer
            else:
                break
        if isinstance(view.parentWidget(), cls):
            return view.parentWidget()
        parent = view.parentWidget()
        if parent is None:
            return None
        # Splitters insert children on parenting. Keep the replacement
        # unparented until replaceWidget preserves the original slot.
        pane = cls() if isinstance(parent, QSplitter) else cls(parent)
        pane.setSizePolicy(view.sizePolicy())
        body = QVBoxLayout(pane)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        if isinstance(parent, QSplitter):
            sizes = parent.sizes()
            index = parent.indexOf(view)
            replaced = parent.replaceWidget(index, pane)
            if replaced is None:
                pane.deleteLater()
                return None
            parent.setSizes(sizes)
        else:
            layout = parent.layout()
            item = (layout.replaceWidget(view, pane)
                    if layout is not None else None)
            if item is None:
                pane.deleteLater()
                return None
            layout.setAlignment(pane, item.alignment())
        old_parent = bar.parentWidget()
        if isinstance(old_parent, QToolBar):
            for action in old_parent.actions():
                if old_parent.widgetForAction(action) is bar:
                    old_parent.removeAction(action)
                    break
        elif old_parent is not None:
            _remove_from_layout(old_parent.layout(), bar)
            if isinstance(old_parent, QGroupBox) and not any(
                    old_parent.layout().itemAt(i).widget() is not None
                    for i in range(old_parent.layout().count())):
                old_parent.hide()
        body.addWidget(view, 1)
        body.addWidget(bar, 0)
        pane.content = view
        pane.zoom_bar = bar
        pane.show()
        bar.show()
        return pane


class _HoldDispatcher(QObject):
    """Keep native application filters independent of short-lived dialogs."""

    def __init__(self, app):
        super().__init__(app)
        self.controllers = weakref.WeakSet()
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        for controller in list(self.controllers):
            if (not sip.isdeleted(controller)
                    and controller.eventFilter(obj, event)):
                return True
        return False


class HoldPreview(QObject):
    """Hold Space to display an existing original render.

    ``show_before(bool)`` changes presentation; the tool owns processing/Apply.
    Text entry, modified Space and other windows keep their existing behavior.
    Loss of focus always releases a held comparison.
    """

    def __init__(self, bar, show_before):
        super().__init__(bar)
        self.bar = bar
        self._show_before = show_before
        self._keyboard = False
        self._before = False
        self.hint = QLabel(self.tr('Hold Space to compare'), bar)
        self.destroyed.connect(self.hint.deleteLater)
        self.hint.setEnabled(False)
        self.hint.ensurePolished()
        self.hint.setFixedWidth(max(
            self.hint.sizeHint().width(),
            self.hint.fontMetrics().horizontalAdvance(self.tr('Before')),
        ))
        self.hint.setToolTip(self.tr(
            'Hold Space to show Before; release to restore the preview',
        ))
        self.hint.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Insert before the trailing stretch in the common zoom row.
        bar.layout().insertWidget(bar.layout().count() - 1, self.hint)
        app = QApplication.instance()
        dispatcher = getattr(app, '_sas_preview_hold_dispatcher', None)
        if dispatcher is None:
            dispatcher = _HoldDispatcher(app)
            app._sas_preview_hold_dispatcher = dispatcher
        dispatcher.controllers.add(self)

    @property
    def showing_before(self):
        return self._before

    def _update(self):
        before = self._keyboard
        if before == self._before:
            return
        self._before = before
        self.hint.setText(self.tr('Before') if before
                          else self.tr('Hold Space to compare'))
        self._show_before(before)

    def release(self):
        self._keyboard = False
        self._update()

    def _text_entry(self, widget):
        while isinstance(widget, QWidget):
            if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit,
                                   QAbstractSpinBox)):
                return True
            if isinstance(widget, QComboBox) and widget.isEditable():
                return True
            if (isinstance(widget, QGraphicsView)
                    and widget.scene() is not None):
                item = widget.scene().focusItem()
                if (isinstance(item, QGraphicsTextItem)
                        and item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditable):
                    return True
                if isinstance(item, QGraphicsProxyWidget):
                    embedded = item.widget()
                    if embedded is not None:
                        return self._text_entry(
                            embedded.focusWidget() or embedded,
                        )
            widget = widget.parentWidget()
        return False

    def eventFilter(self, obj, event):
        bar = getattr(self, 'bar', None)
        host = getattr(bar, '_host', None)
        if (bar is None or host is None or sip.isdeleted(bar)
                or sip.isdeleted(host)):
            return False
        kind = event.type()
        if (kind == QEvent.Type.FocusOut and self._keyboard
                and self.bar._handles_keys(obj)):
            self._keyboard = False
            self._update()
        if kind in (QEvent.Type.ApplicationDeactivate,
                    QEvent.Type.WindowDeactivate):
            if kind == QEvent.Type.ApplicationDeactivate or (
                    isinstance(obj, QWidget) and any(
                        not sip.isdeleted(scope) and obj is scope.window()
                        for scope in self.bar._control_scopes)):
                self.release()
        elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
            if obj is self.bar or obj is self.bar._host:
                self.release()
        if kind not in (QEvent.Type.ShortcutOverride,
                        QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if event.key() != Qt.Key.Key_Space:
            return False
        # Release even if focus or modifiers changed after the initial press.
        if kind == QEvent.Type.KeyRelease and self._keyboard:
            if not event.isAutoRepeat():
                self._keyboard = False
                self._update()
            event.accept()
            return True
        if kind == QEvent.Type.KeyRelease:
            return False
        if (event.modifiers() != Qt.KeyboardModifier.NoModifier
                or not self.bar._has_visible_viewport()
                or not self.bar._handles_keys(obj) or self._text_entry(obj)):
            return False
        event.accept()
        if kind == QEvent.Type.KeyPress and not event.isAutoRepeat():
            self._keyboard = True
            self._update()
        return True


class CachedImageComparison(QObject):
    """Select a cached original QImage without replacing the renderer's result.

    Renderers call ``image(result)`` at display time. New worker results remain
    available while Before is held and become visible immediately on release.
    """

    def __init__(self, bar, before_image, redraw, source_key=None):
        super().__init__(bar)
        self._before_image = before_image
        self._redraw = redraw
        self._source_key = source_key or (lambda: None)
        self._cache_across_holds = source_key is not None
        self._original = None
        self._scaled_original = None
        self._key = None
        self.result = None
        self.hold = bar.enable_comparison(self._changed)

    def _changed(self, before):
        if not self._cache_across_holds:
            self._original = self._scaled_original = None
        self._redraw()

    def set_before(self, image):
        """Seed a rendered original for the current stable source key."""
        if not self._cache_across_holds:
            raise ValueError('Seeding an original requires a source_key')
        self._original = image
        self._scaled_original = None
        self._key = self._source_key()

    def image(self, result):
        self.result = result
        if not self.hold.showing_before or result is None or result.isNull():
            return result
        key = self._source_key()
        if self._original is None or key != self._key:
            self._original = self._before_image()
            self._scaled_original = None
            self._key = key
        if self._original is None or self._original.isNull():
            return result
        if isinstance(result, QPixmap) and isinstance(self._original, QImage):
            self._original = QPixmap.fromImage(self._original)
        elif (isinstance(result, QImage)
              and isinstance(self._original, QPixmap)):
            self._original = self._original.toImage()
        if self._original.size() == result.size():
            return self._original
        if (self._scaled_original is None
                or self._scaled_original.size() != result.size()
                or type(self._scaled_original) is not type(result)):
            self._scaled_original = self._original.scaled(
                result.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return self._scaled_original


class SceneOverlayComparison(QObject):
    """Hide overlays temporarily, retaining their previous visibility."""

    def __init__(self, bar, scene, base_item):
        super().__init__(bar)
        self._scene = scene
        self._base_item = base_item
        self._hidden = {}
        self.hold = bar.enable_comparison(self._changed)
        scene.changed.connect(self._hide_new_overlays)

    def _hide_new_overlays(self, *_):
        if not self.hold.showing_before:
            return
        base = self._base_item()
        for item in self._scene.items():
            if (item is not base and item.parentItem() is None
                    and item.isVisible() and item not in self._hidden):
                self._hidden[item] = True
                item.setVisible(False)

    def _changed(self, before):
        if before:
            self._hide_new_overlays()
        else:
            hidden, self._hidden = self._hidden, {}
            for item, visible in hidden.items():
                if not sip.isdeleted(item):
                    item.setVisible(visible)


def source_preview_image(source):
    """Convert a source array without mutating it or truncating uint16 data."""
    import numpy as np
    from .image_utils import numpy_to_qimage
    if source is None:
        return QImage()
    array = np.asarray(source)
    if array.size == 0:
        return QImage()
    if array.dtype.kind in 'ui' and array.dtype != np.uint8:
        array = array.astype(np.float32) / np.iinfo(array.dtype).max
    return numpy_to_qimage(array)
