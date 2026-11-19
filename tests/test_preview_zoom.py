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


@pytest.mark.parametrize('module_name,class_name', [
    ('curve_editor_pro', 'CurvesDialogPro'),
    ('clahe', 'CLAHEDialogPro'),
    ('stat_stretch', 'StatisticalStretchDialog'),
    ('backgroundneutral', 'BackgroundNeutralizationDialog'),
    ('abe', 'ABEDialog'),
])
def test_tool_zoom_is_source_scaled_and_non_destructive(
        qapp, tmp_path, monkeypatch, module_name, class_name):
    import importlib
    import numpy as np
    from PyQt6.QtCore import QSettings
    from setiastro.saspro.doc_manager import ImageDocument

    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(module, 'QSettings', lambda: QSettings(
            str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat,
        ))
    image = np.tile(np.linspace(.02, .6, 1600, dtype=np.float32), (160, 1))
    expected = image.copy()
    doc = ImageDocument(image)
    main = QMainWindow()
    main.show()
    dialog = getattr(module, class_name)(main, doc)
    dialog.resize(1200, 700)
    dialog.show()
    dialog.activateWindow()
    QTest.qWait(200)
    bar = dialog.zoom_bar

    def press(keys):
        dialog.activateWindow()
        dialog.setFocus()
        qapp.processEvents()
        QTest.keySequence(dialog, QKeySequence(keys))
        QTest.qWait(50)

    try:
        press('Ctrl+1')
        assert bar._scale() == pytest.approx(1, abs=.01)
        if module_name == 'curve_editor_pro':
            for _ in range(500):
                if not dialog._reduced_preview():
                    break
                QTest.qWait(20)
            assert not dialog._reduced_preview()
            assert dialog._pix.width() == image.shape[1]
            assert not dialog.chk_full_bg.isChecked()

        def source_center():
            if module_name in ('clahe', 'backgroundneutral'):
                view = (dialog.view if module_name == 'clahe'
                        else dialog.graphics_view)
                point = view.mapToScene(view.viewport().rect().center())
                return point.x()
            scroll = (dialog.scroll if module_name == 'curve_editor_pro'
                      else dialog.preview_scroll)
            label = (dialog.label if module_name == 'curve_editor_pro'
                     else dialog.preview_label)
            offset = max(0, (label.width() - label.pixmap().width()) / 2)
            center = (scroll.horizontalScrollBar().value()
                      + scroll.viewport().width() / 2 - offset)
            return center / bar._scale()

        if module_name in ('clahe', 'backgroundneutral'):
            view = (dialog.view if module_name == 'clahe'
                    else dialog.graphics_view)
            view.centerOn(500, 80)
        else:
            scroll = (dialog.scroll if module_name == 'curve_editor_pro'
                      else dialog.preview_scroll)
            scroll.horizontalScrollBar().setValue(100)
        before = source_center()
        press('Ctrl++')
        assert source_center() == pytest.approx(before, abs=3)
        assert bar._scale() == pytest.approx(1.25, abs=.01)
        press('Ctrl+-')
        assert bar._scale() == pytest.approx(1, abs=.01)
        if module_name == 'stat_stretch':
            # Fast and full-res renders must retain the same source zoom.
            dialog._set_preview_pixmap(image[::4, ::4])
            assert dialog._reduced_preview()
            assert dialog._source_zoom() == pytest.approx(1)
            dialog._set_preview_pixmap(image)
            assert not dialog._reduced_preview()
            assert dialog._source_zoom() == pytest.approx(1)
        press('Ctrl+0')
        dialog.resize(1320, 780)
        QTest.qWait(100)
        assert bar._fit_mode
        viewport = bar._viewport
        assert bar._scale() <= min(
            viewport.width() / image.shape[1],
            viewport.height() / image.shape[0],
        ) + .005
        press('Ctrl+1')
        dialog.resize(1250, 730)
        QTest.qWait(100)
        assert bar._scale() == pytest.approx(1, abs=.01)
        assert doc.image is image
        np.testing.assert_array_equal(doc.image, expected)
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()
