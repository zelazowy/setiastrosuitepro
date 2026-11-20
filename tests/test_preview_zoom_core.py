import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QDialog, QGraphicsScene, QLineEdit, QMainWindow,
    QScrollArea, QVBoxLayout,
)

from setiastro.saspro.widgets.graphics_views import ZoomableGraphicsView
from setiastro.saspro.widgets.preview_zoom import PreviewZoomBar


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def test_shortcuts_stay_in_tool_and_leave_plain_text_alone(qapp):
    main = QMainWindow()
    main_calls = []
    main_action = QAction('Main zoom', main)
    main_action.setShortcut(QKeySequence('Ctrl+0'))
    main_action.triggered.connect(lambda: main_calls.append(True))
    main.addAction(main_action)
    main.show()
    tool = QDialog(main)
    tool.setWindowFlag(Qt.WindowType.Tool, True)
    layout = QVBoxLayout(tool)
    edit = QLineEdit(tool)
    layout.addWidget(edit)
    preview = QScrollArea(tool)
    layout.addWidget(preview)
    state = {'scale': .5, 'fit_calls': 0}

    def set_scale(scale):
        state['scale'] = scale

    def fit():
        state['fit_calls'] += 1
        set_scale(.5)

    bar = PreviewZoomBar(
        tool, preview.viewport(),
        zoom_in=lambda: set_scale(state['scale'] * 1.25),
        zoom_out=lambda: set_scale(state['scale'] / 1.25),
        actual=lambda: set_scale(1), fit=fit,
        scale=lambda: state['scale'],
    )
    layout.addWidget(bar)
    tool.show()
    tool.activateWindow()
    edit.setFocus()
    qapp.processEvents()
    for key, expected in (
        ('Ctrl+1', 1), ('Ctrl++', 1.25), ('Ctrl+-', 1),
        ('Ctrl+=', 1.25), ('Ctrl+-', 1),
        ('Ctrl+Shift+=', 1.25), ('Ctrl+0', .5),
    ):
        QTest.keySequence(edit, QKeySequence(key))
        qapp.processEvents()
        assert state['scale'] == pytest.approx(expected), key
    assert main_calls == []
    QTest.keyClicks(edit, '10+-')
    assert edit.text() == '10+-'
    assert state['scale'] == .5
    initial_calls = state['fit_calls']
    tool.resize(tool.width() + 100, tool.height() + 80)
    qapp.processEvents()
    qapp.processEvents()
    assert state['fit_calls'] > initial_calls
    QTest.keySequence(edit, QKeySequence('Ctrl+1'))
    initial_calls = state['fit_calls']
    tool.resize(tool.width() + 100, tool.height() + 80)
    qapp.processEvents()
    assert state['scale'] == 1
    assert state['fit_calls'] == initial_calls
    main.activateWindow()
    main.setFocus()
    qapp.processEvents()
    # QTest dispatches synthetic keys; establish their Qt shortcut scope even
    # when another desktop application currently owns native macOS focus.
    qapp.setActiveWindow(main)
    QTest.keySequence(main, QKeySequence('Ctrl+0'))
    qapp.processEvents()
    assert main_calls == [True]
    assert state['scale'] == 1
    tool.close()
    main.close()


def test_graphics_zoom_uses_actual_transform_after_fit(qapp):
    scene = QGraphicsScene()
    item = scene.addPixmap(QPixmap(2000, 1000))
    view = ZoomableGraphicsView(scene)
    view.resize(500, 300)
    view.show()
    qapp.processEvents()
    view.fit_to_item(item)
    scale = view.transform().m11()
    assert view.zoom_level == pytest.approx(scale)
    view.zoom_in()
    assert view.transform().m11() == pytest.approx(scale * 1.25)
    view.resetTransform()  # existing callers also reset directly
    view.zoom_out()
    assert view.transform().m11() == pytest.approx(.8)
    large_item = scene.addRect(0, 0, 100000, 1000)
    view.fit_to_item(large_item)
    scale = view.transform().m11()
    assert scale < .05
    view.zoom_in()
    assert view.transform().m11() == pytest.approx(scale * 1.25)
    view.zoom_out()
    assert view.transform().m11() == pytest.approx(scale)
    view.close()


def test_adopted_controls_preserve_wiring_and_busy_state(qapp):
    from PyQt6.QtWidgets import QHBoxLayout, QPushButton

    host = QDialog()
    layout = QVBoxLayout(host)
    viewport = QLineEdit(host)
    layout.addWidget(viewport)
    row = QHBoxLayout()
    layout.addLayout(row)
    calls = []
    buttons = {}
    for name in ('in', 'out', 'actual', 'fit'):
        button = QPushButton(name)
        button.clicked.connect(lambda checked=False, n=name: calls.append(n))
        row.addWidget(button)
        buttons[name] = button
    bar = PreviewZoomBar.replace(
        host, viewport, buttons=buttons, scale=lambda: 1,
    )
    host.show()
    qapp.processEvents()
    calls.clear()  # Ignore the initial fit when the viewport appears.
    QTest.keySequence(viewport, QKeySequence('Ctrl++'))
    assert calls == ['in']
    buttons['out'].click()
    assert calls == ['in', 'out']
    buttons['in'].setEnabled(False)
    QTest.keySequence(viewport, QKeySequence('Ctrl++'))
    assert calls == ['in', 'out']
    buttons['in'].setEnabled(True)
    QTest.keySequence(viewport, QKeySequence('Ctrl++'))
    assert calls == ['in', 'out', 'in']
    assert bar.buttons_by_name == buttons
    assert buttons['actual'].text() == '100%'
    assert row.count() == 0
    assert bar.preview_pane.zoom_bar is bar
    bar.hide()  # Collapsed settings must leave viewport shortcuts available.
    QTest.keySequence(viewport, QKeySequence('Ctrl++'))
    assert calls == ['in', 'out', 'in', 'in']
    host.close()


def test_embedded_previews_route_keys_to_last_used_pane(qapp):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QWidget

    host = QDialog()
    layout = QVBoxLayout(host)
    values = [0, 0]
    bars = []
    previews = []
    for index in range(2):
        pane = QWidget(host)
        inner = QVBoxLayout(pane)
        preview = QLineEdit(pane)
        inner.addWidget(preview)
        bar = PreviewZoomBar(
            pane, preview,
            zoom_in=lambda i=index: values.__setitem__(i, values[i] + 1),
            zoom_out=lambda: None, actual=lambda: None, fit=lambda: None,
            scale=lambda: 1,
        )
        inner.addWidget(bar)
        layout.addWidget(pane)
        previews.append(preview)
        bars.append(bar)
    host.show()
    qapp.processEvents()
    for index in (0, 1, 0):
        QTest.keySequence(previews[index], QKeySequence('Ctrl++'))
    assert values == [2, 1]
    # A deferred-delete wrapper must not break other windows' key events.
    other = QDialog()
    other_layout = QVBoxLayout(other)
    edit = QLineEdit(other)
    other_layout.addWidget(edit)
    removed = PreviewZoomBar(
        other, edit, zoom_in=lambda: None, zoom_out=lambda: None,
        actual=lambda: None, fit=lambda: None, scale=lambda: 1,
    )
    other_layout.addWidget(removed)
    other.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.keySequence(previews[1], QKeySequence('Ctrl++'))
    assert values == [2, 2]
    host.close()


def test_preview_ratio_uses_unscaled_source_dimensions():
    import numpy as np
    from setiastro.saspro.widgets.preview_zoom import preview_ratio

    source = np.zeros((20, 5000), dtype=np.float32)
    preview = source[:, ::4]
    assert preview_ratio(preview, source) == .25
    assert preview_ratio(None, source) == 1



@pytest.fixture
def simple_bar(qapp):
    host = QDialog()
    layout = QVBoxLayout(host)
    preview = QLineEdit(host)
    layout.addWidget(preview)
    calls = []
    bar = PreviewZoomBar(
        host, preview, zoom_in=lambda: calls.append('in'),
        zoom_out=lambda: calls.append('out'),
        actual=lambda: calls.append('actual'), fit=lambda: calls.append('fit'),
        scale=lambda: 1,
    )
    layout.addWidget(bar)
    host.show()
    host.activateWindow()
    preview.setFocus()
    qapp.processEvents()
    calls.clear()
    yield host, preview, bar, calls
    from PyQt6 import sip
    if not sip.isdeleted(host):
        host.close()


def test_deleting_bar_removes_host_shortcuts(simple_bar):
    from PyQt6 import sip
    from PyQt6.QtCore import QEvent

    host, _, bar, _ = simple_bar
    actions = list(bar.actions_by_name.values())
    bar.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(bar)
    assert all(sip.isdeleted(action) for action in actions)
    assert not host.actions()


@pytest.mark.parametrize('key,name', [
    (Qt.Key.Key_Plus, 'in'), (Qt.Key.Key_Minus, 'out'),
    (Qt.Key.Key_0, 'fit'), (Qt.Key.Key_1, 'actual'),
])
def test_keypad_shortcuts(simple_bar, key, name):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    _, preview, _, calls = simple_bar
    event = QKeyEvent(
        QEvent.Type.KeyPress, key,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier,
    )
    QApplication.sendEvent(preview, event)
    assert calls == [name]


@pytest.mark.parametrize('key,expected', [
    (Qt.Key.Key_0, []), (Qt.Key.Key_1, []), (Qt.Key.Key_Minus, ['out']),
])
def test_repeat_only_steps_zoom(simple_bar, key, expected):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    _, preview, _, calls = simple_bar
    event = QKeyEvent(QEvent.Type.KeyPress, key,
                      Qt.KeyboardModifier.ControlModifier, '', True, 1)
    QApplication.sendEvent(preview, event)
    assert calls == expected


def test_linked_preview_survives_hidden_or_deleted_primary(simple_bar, qapp):
    from PyQt6.QtCore import QEvent

    host, preview, bar, calls = simple_bar
    secondary = QLineEdit(host)
    host.layout().addWidget(secondary)
    bar.watch_viewport(secondary)
    secondary.show()
    preview.hide()
    qapp.processEvents()
    calls.clear()
    QTest.keySequence(secondary, QKeySequence('Ctrl+1'))
    assert calls == ['actual']
    preview.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.keySequence(secondary, QKeySequence('Ctrl+-'))
    assert calls == ['actual', 'out']


def test_invalid_replacement_preserves_original_layout(qapp):
    from PyQt6.QtWidgets import QPushButton

    host = QDialog()
    layout = QVBoxLayout(host)
    button = QPushButton('Legacy zoom', host)
    layout.addWidget(button)
    with pytest.raises(ValueError, match='callback'):
        PreviewZoomBar.replace(host, host, buttons={'in': button}, scale=lambda: 1)
    assert layout.indexOf(button) == 0
    assert button.parentWidget() is host
    host.close()


def test_zoom_out_above_ceiling_takes_one_step(qapp):
    scene = QGraphicsScene()
    item = scene.addPixmap(QPixmap(2, 2))
    view = ZoomableGraphicsView(scene)
    view.resize(500, 300)
    view.show()
    qapp.processEvents()
    view.fit_to_item(item)
    fitted = view.zoom_level
    assert fitted > 12
    view.zoom_in()
    assert view.zoom_level == pytest.approx(fitted)
    view.zoom_out()
    assert view.zoom_level == pytest.approx(fitted / 1.25)
    view.close()


def test_detached_controls_opt_in_without_capturing_other_dialogs(simple_bar, qapp):
    host, _, bar, calls = simple_bar
    detached = QDialog(host)
    layout = QVBoxLayout(detached)
    edit = QLineEdit(detached)
    layout.addWidget(edit)
    detached.show()
    qapp.processEvents()
    QTest.keySequence(edit, QKeySequence('Ctrl+1'))
    assert calls == []
    bar.watch_controls(detached)
    QTest.keySequence(edit, QKeySequence('Ctrl+1'))
    assert calls == ['actual']
    unrelated = QDialog(host)
    unrelated.show()
    qapp.processEvents()
    QTest.keySequence(unrelated, QKeySequence('Ctrl+0'))
    assert calls == ['actual']
    unrelated.close()
    detached.close()


def test_pending_fit_after_viewport_deletion_is_safe(simple_bar, qapp):
    from PyQt6.QtCore import QEvent

    _, preview, bar, calls = simple_bar
    bar._fit_pending = True
    preview.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    bar._refit()
    assert calls == []
    assert not bar._fit_pending


def test_callback_can_delete_host(simple_bar):
    from PyQt6 import sip

    host, _, bar, _ = simple_bar
    bar._run(lambda: sip.delete(host), False)
    assert sip.isdeleted(bar)


@pytest.mark.parametrize('ctrl_only', [False, True])
def test_scroll_and_zero_delta_wheel_preserve_fit(simple_bar, ctrl_only):
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent

    _, preview, bar, _ = simple_bar
    bar._ctrl_wheel = ctrl_only
    for delta, modifiers, manual in (
        (0, Qt.KeyboardModifier.ControlModifier, False),
        (120, Qt.KeyboardModifier.NoModifier, not ctrl_only),
        (120, Qt.KeyboardModifier.ControlModifier, True),
    ):
        bar._fit_mode = True
        event = QWheelEvent(
            QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, delta),
            Qt.MouseButton.NoButton, modifiers,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        QApplication.sendEvent(preview, event)
        assert bar._fit_mode is not manual
