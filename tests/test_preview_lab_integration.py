"""Integration with upstream's asynchronous preview delivery paths."""
import importlib

import numpy as np
import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow

from setiastro.saspro.doc_manager import ImageDocument
from setiastro.saspro.widgets.image_utils import numpy_to_qimage


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('module_name,class_name', [
    ('morphology', 'MorphologyDialogPro'),
    ('halobgon', 'HaloBGonDialogPro'),
    ('wavescale_hdr', 'WaveScaleHDRDialogPro'),
    ('wavescalede', 'WaveScaleDarkEnhancerDialogPro'),
])
def test_worker_delivery_preserves_hold_and_restores_latest_result(
        qapp, tmp_path, monkeypatch, module_name, class_name):
    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(module, 'QSettings', lambda: QSettings(
            str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat,
        ))
    source = np.full((48, 96, 3), .2, dtype=np.float32)
    main = QMainWindow()
    dialog = getattr(module, class_name)(main, ImageDocument(source))
    dialog.show()
    QTest.qWait(300)
    bar = dialog.zoom_bar
    result = np.full_like(source, [.8, .1, .6])
    dialog._set_pix(result)
    QTest.keyPress(bar._viewport, Qt.Key.Key_Space)
    try:
        before = dialog.pix.pixmap().toImage().copy()
        latest = np.full_like(source, [.1, .7, .9])
        qimg = numpy_to_qimage(latest)
        if module_name in ('wavescale_hdr', 'wavescalede'):
            dialog._show_pixmap(QPixmap.fromImage(qimg))
        elif module_name == 'morphology':
            dialog._pv_fit = False
            dialog._on_preview_ready({
                'orig': dialog.orig, 'base_u8': np.zeros_like(source, dtype=np.uint8),
                'key': ('erosion', 3, 1), 'out_u8': np.zeros_like(source, dtype=np.uint8),
                'qimg': qimg,
            })
        else:
            dialog._on_preview_ready({
                'orig': dialog.orig, 'linear': False, 'prep': None, 'level': 0,
                'u8': np.zeros_like(source, dtype=np.uint8), 'qimg': qimg,
            })
        assert dialog.pix.pixmap().toImage() == before
        QTest.keyRelease(bar._viewport, Qt.Key.Key_Space)
        assert dialog.pix.pixmap().toImage() == QPixmap.fromImage(qimg).toImage()
        assert np.array_equal(source, np.full_like(source, .2))
    finally:
        QTest.keyRelease(bar._viewport, Qt.Key.Key_Space)
        dialog.close()
        main.close()
        QTest.qWait(200)
