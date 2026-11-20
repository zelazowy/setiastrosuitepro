import pytest
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


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
    assert bar.preview_pane is not None

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
            dialog._pop_out_panel(restore_geometry=False)
            QTest.qWait(30)
            QTest.keySequence(dialog.curve_panel, QKeySequence('Ctrl++'))
            assert bar._scale() == pytest.approx(1.25, abs=.01)
            QTest.keySequence(dialog.curve_panel, QKeySequence('Ctrl+-'))
            assert bar._scale() == pytest.approx(1, abs=.01)
            dialog._pop_in_panel()

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
        if module_name == 'curve_editor_pro':
            # A fit above 100% still needs detail; reuse the calculated result.
            cached = dialog._full_cache
            dialog.resize(2600, 1000)
            QTest.qWait(50)
            press('Ctrl+0')
            assert dialog._detail_preview
            assert dialog._full_cache is cached
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
        if module_name == 'curve_editor_pro':
            # Native window minimums differ; explicitly exercise Fit below 100%.
            dialog.scroll.setFixedWidth(700)
            QTest.qWait(50)
            press('Ctrl+0')
            assert bar._scale() < 1
            assert not dialog._detail_preview
            assert dialog._full_cache is None
            dialog.btn_preview.setChecked(False)
            press('Ctrl+1')
            assert dialog._pix.width() == image.shape[1]
            dialog.btn_preview.setChecked(True)
            for _ in range(500):
                if dialog._full_cache is not None:
                    break
                QTest.qWait(20)
            assert dialog._full_cache is not None
            assert not dialog._reduced_preview()
        assert doc.image is image
        np.testing.assert_array_equal(doc.image, expected)
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()


@pytest.mark.parametrize('module_name,class_name', [
    ('curve_editor_pro', 'CurvesDialogPro'),
    ('clahe', 'CLAHEDialogPro'),
    ('stat_stretch', 'StatisticalStretchDialog'),
    ('backgroundneutral', 'BackgroundNeutralizationDialog'),
    ('abe', 'ABEDialog'),
    ('pixelmath', 'PixelMathDialogPro'),
    ('ghs_dialog_pro', 'GhsDialogPro'),
    ('histogram_transform_pro', 'HistogramTransformDialogPro'),
])
def test_zoom_steps_after_fitting_tiny_image(
        qapp, tmp_path, monkeypatch, module_name, class_name):
    import importlib
    import numpy as np
    from PyQt6.QtCore import QSettings
    from setiastro.saspro.doc_manager import ImageDocument

    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(
            module, 'QSettings', lambda *args, **kwargs: QSettings(
                str(tmp_path / 'tiny.ini'), QSettings.Format.IniFormat,
            ),
        )
    image = np.full((8, 8, 3), .2, dtype=np.float32)
    doc = ImageDocument(image)
    main = QMainWindow()
    dialog = getattr(module, class_name)(main, doc)
    if module_name == 'pixelmath':
        dialog._set_preview_image(image)
    dialog.show()
    dialog.activateWindow()
    dialog.setFocus()
    QTest.qWait(200)
    try:
        bar = dialog.zoom_bar
        assert bar.preview_pane is not None
        bar.actions_by_name['fit'].trigger()
        QTest.qWait(50)
        fitted = bar._scale()
        assert fitted > 0
        bar.actions_by_name['in'].trigger()
        QTest.qWait(50)
        enlarged = bar._scale()
        assert enlarged >= fitted * .999
        bar.actions_by_name['out'].trigger()
        QTest.qWait(50)
        assert bar._scale() == pytest.approx(enlarged / 1.25, rel=.02)
        np.testing.assert_array_equal(image, np.full_like(image, .2))
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()
