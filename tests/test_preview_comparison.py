"""Focus-safe comparison and common layout without processing engines."""
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)
from setiastro.saspro.widgets.preview import PREVIEW_BACKGROUND, PreviewPane
from setiastro.saspro.widgets.preview_zoom import PreviewZoomBar


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def preview(qapp):
    host = QDialog()
    row = QVBoxLayout(host)
    edit = QLineEdit(host)
    row.addWidget(edit)
    scroll = QScrollArea(host)
    label = QLabel('Image', scroll)
    scroll.setWidget(label)
    row.addWidget(scroll)
    calls = []
    bar = PreviewZoomBar(
        host, scroll.viewport(), zoom_in=lambda: None,
        zoom_out=lambda: None, actual=lambda: None, fit=lambda: None,
        scale=lambda: 1,
    )
    row.addWidget(bar)
    comparison = bar.enable_comparison(calls.append)
    host.show()
    host.activateWindow()
    scroll.setFocus()
    qapp.processEvents()
    scroll.setFocus()
    qapp.processEvents()
    yield host, scroll, edit, bar, comparison, calls
    if not sip.isdeleted(host):
        host.close()
        host.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_common_frame_keeps_controls_below_image(preview):
    _, scroll, _, bar, _, _ = preview
    pane = bar.preview_pane
    assert isinstance(pane, PreviewPane)
    assert pane.content is scroll
    assert pane.layout().itemAt(0).widget() is scroll
    assert pane.layout().itemAt(1).widget() is bar
    assert bar.mapToGlobal(QPoint()).y() >= scroll.mapToGlobal(
        QPoint(0, scroll.height())).y()
    for widget in (scroll.viewport(), scroll.widget()):
        assert widget.autoFillBackground()
        assert widget.palette().color(QPalette.ColorRole.Window).name() == (
            PREVIEW_BACKGROUND)


def test_hold_and_release_do_not_repeat(preview):
    _, scroll, _, _, comparison, calls = preview
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    assert comparison.showing_before
    assert calls == [True]
    repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                       Qt.KeyboardModifier.NoModifier, ' ', True, 1)
    QApplication.sendEvent(scroll.viewport(), repeat)
    assert calls == [True]
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space)
    assert not comparison.showing_before
    assert calls == [True, False]


def test_text_entry_keeps_spaces_and_does_not_compare(preview):
    _, _, edit, _, comparison, calls = preview
    edit.setFocus()
    QTest.keyClicks(edit, 'a b c')
    assert edit.text() == 'a b c'
    assert not comparison.showing_before
    assert calls == []


@pytest.mark.parametrize('modifier', [
    Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier,
    Qt.KeyboardModifier.AltModifier,
])
def test_modified_space_keeps_existing_behavior(preview, modifier):
    _, scroll, _, _, _, calls = preview
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space, modifier)
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space, modifier)
    assert calls == []


@pytest.mark.parametrize('event_type', [
    QEvent.Type.WindowDeactivate, QEvent.Type.Hide, QEvent.Type.Close,
])
def test_lost_release_restores_after(preview, event_type):
    host, scroll, _, _, comparison, calls = preview
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    QApplication.sendEvent(host, QEvent(event_type))
    assert not comparison.showing_before
    assert calls == [True, False]


def test_changing_focus_restores_after(preview, qapp):
    _, scroll, edit, _, comparison, calls = preview
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    edit.setFocus()
    qapp.processEvents()
    assert not comparison.showing_before
    assert calls == [True, False]


def test_mouse_hold_and_keyboard_hold_share_state(preview):
    _, scroll, _, _, comparison, calls = preview
    QTest.mousePress(comparison.button, Qt.MouseButton.LeftButton)
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    QTest.mouseRelease(comparison.button, Qt.MouseButton.LeftButton)
    assert comparison.showing_before
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space)
    assert calls == [True, False]


def test_worker_result_and_source_changes_during_hold(preview):
    _, scroll, _, bar, old_comparison, _ = preview
    old_comparison.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    source = [QImage(20, 10, QImage.Format.Format_RGB32)]
    source[0].fill(QColor('red'))
    result = QImage(10, 5, QImage.Format.Format_RGB32)
    result.fill(QColor('green'))
    painted = []
    comparison = bar.enable_image_comparison(
        lambda: source[0], lambda: painted.append(comparison.image(result)),
        source_key=lambda: id(source[0]),
    )
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    assert painted[-1].size() == result.size()
    assert painted[-1].pixelColor(0, 0) == QColor('red')
    # A finished worker must stay hidden until release.
    result.fill(QColor('blue'))
    assert comparison.image(result).pixelColor(0, 0) == QColor('red')
    source[0] = QImage(source[0])
    source[0].fill(QColor('yellow'))
    assert comparison.image(result).pixelColor(0, 0) == QColor('yellow')
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space)
    assert painted[-1].pixelColor(0, 0) == QColor('blue')


def test_splitter_position_and_size_are_preserved(qapp):
    host = QDialog()
    layout = QVBoxLayout(host)
    splitter = QSplitter(host)
    first = QWidget(splitter)
    view = QScrollArea(splitter)
    last = QWidget(splitter)
    layout.addWidget(splitter)
    bar = PreviewZoomBar(
        host, view.viewport(), zoom_in=lambda: None, zoom_out=lambda: None,
        actual=lambda: None, fit=lambda: None, scale=lambda: 1,
    )
    layout.addWidget(bar)
    host.show()
    qapp.processEvents()
    assert splitter.widget(0) is first
    assert splitter.widget(1) is bar.preview_pane
    assert splitter.widget(2) is last
    assert bar.preview_pane.content is view
    assert view.parentWidget() is bar.preview_pane
    host.close()


def test_closed_comparisons_can_be_garbage_collected(
        preview, qapp, monkeypatch):
    import gc
    import sys

    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *error: errors.append(error))
    for _ in range(30):
        host = QDialog()
        layout = QVBoxLayout(host)
        image = QLabel('Temporary preview', host)
        layout.addWidget(image)
        bar = PreviewZoomBar(
            host, image, zoom_in=lambda: None, zoom_out=lambda: None,
            actual=lambda: None, fit=lambda: None, scale=lambda: 1,
        )
        layout.addWidget(bar)
        bar.enable_comparison(lambda before, window=host: window.setProperty(
            'before', before))
        host.show()
        qapp.processEvents()
        host.close()
        del host, layout, image, bar
        gc.collect()
        qapp.processEvents()
    _, scroll, _, _, comparison, calls = preview
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space)
    assert calls == [True, False]
    assert errors == []


def test_overlay_visibility_survives_updates_and_deleted_items(preview, qapp):
    from PyQt6.QtWidgets import QGraphicsScene

    host, scroll, _, bar, old, _ = preview
    old.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    scene = QGraphicsScene(host)
    base = scene.addRect(0, 0, 100, 100)
    overlay = scene.addRect(0, 0, 10, 10)
    hidden_overlay = scene.addRect(20, 20, 10, 10)
    hidden_overlay.hide()
    bar.enable_overlay_comparison(scene, lambda: base)
    QTest.keyPress(scroll.viewport(), Qt.Key.Key_Space)
    assert base.isVisible()
    assert not overlay.isVisible()
    new_overlay = scene.addRect(30, 30, 10, 10)
    qapp.processEvents()
    assert not new_overlay.isVisible()
    sip.delete(overlay)
    QTest.keyRelease(scroll.viewport(), Qt.Key.Key_Space)
    assert base.isVisible()
    assert new_overlay.isVisible()
    assert not hidden_overlay.isVisible()


def test_unclaimed_space_release_reaches_legacy_pan_handler(preview):
    _, scroll, _, _, _, calls = preview
    released = []
    old_release = scroll.keyReleaseEvent
    scroll.keyReleaseEvent = lambda event: released.append(event.key())
    try:
        QTest.keyPress(scroll, Qt.Key.Key_Space,
                       Qt.KeyboardModifier.ShiftModifier)
        QTest.keyRelease(scroll, Qt.Key.Key_Space)
        assert released == [Qt.Key.Key_Space]
        assert calls == []
    finally:
        scroll.keyReleaseEvent = old_release


@pytest.mark.parametrize('dtype', ['uint8', 'uint16', 'float32'])
def test_original_array_conversion_preserves_values_and_source(dtype):
    import numpy as np
    from setiastro.saspro.widgets.preview import source_preview_image

    maximum = 1 if dtype == 'float32' else np.iinfo(dtype).max
    source = np.array([[0, maximum / 2, maximum]], dtype=dtype)
    original = source.copy()
    image = source_preview_image(source)
    assert image.pixelColor(0, 0).red() == 0
    assert image.pixelColor(1, 0).red() == pytest.approx(127, abs=1)
    assert image.pixelColor(2, 0).red() == 255
    np.testing.assert_array_equal(source, original)
    assert source_preview_image(None).isNull()


def test_toolbar_buttons_have_one_widget_type(preview):
    from PyQt6.QtWidgets import QToolButton

    _, _, _, bar, _, _ = preview
    assert all(isinstance(button, QToolButton)
               for button in bar.visible_buttons_by_name.values())


def test_unicode_and_unknown_keys_remain_text_input(preview):
    _, _, edit, _, _, calls = preview
    edit.setFocus()
    for key, text in [(0x104, 'Ą'), (0, 'Ł')]:
        event = QKeyEvent(QEvent.Type.KeyPress, key,
                          Qt.KeyboardModifier.NoModifier, text)
        QApplication.sendEvent(edit, event)
    assert edit.text() == 'ĄŁ'
    assert calls == []
