"""Comparison on actual processing dialogs, with distinct cached pixel data."""
import importlib

import numpy as np
import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('module_name,class_name', [
    ('curve_editor_pro', 'CurvesDialogPro'),
    ('clahe', 'CLAHEDialogPro'),
    ('stat_stretch', 'StatisticalStretchDialog'),
    ('abe', 'ABEDialog'),
    ('backgroundneutral', 'BackgroundNeutralizationDialog'),
    ('morphology', 'MorphologyDialogPro'),
    ('wavescalede', 'WaveScaleDarkEnhancerDialogPro'),
    ('wavescale_hdr', 'WaveScaleHDRDialogPro'),
    ('halobgon', 'HaloBGonDialogPro'),
    ('texture_clarity', 'TextureClarityDialog'),
    ('fx_module', 'FXDialog'),
    ('pedestal', 'RemovePedestalDialog'),
    ('star_stretch', 'StarStretchDialog'),
    ('histogram_transform_pro', 'HistogramTransformDialogPro'),
    ('ghs_dialog_pro', 'GhsDialogPro'),
    ('pixelmath', 'PixelMathDialogPro'),
    ('selective_color', 'SelectiveColorCorrection'),
    ('selective_luma', 'SelectiveLuminanceCorrection'),
    ('star_spikes', 'StarSpikesDialogPro'),
])
def test_hold_uses_real_original_and_restores_result_without_editing(
        qapp, tmp_path, monkeypatch, module_name, class_name):
    from setiastro.saspro.doc_manager import ImageDocument
    from setiastro.saspro.widgets.preview import source_preview_image

    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(
            module, 'QSettings', lambda *args, **kwargs: QSettings(
                str(tmp_path / 'comparison.ini'), QSettings.Format.IniFormat,
            ),
        )
    mono = np.tile(np.linspace(.04, .6, 1600, dtype=np.float32), (160, 1))
    source = np.stack([mono, mono * .7, mono * .45], axis=-1)
    original = source.copy()
    doc = ImageDocument(source)
    main = QMainWindow()
    cls = getattr(module, class_name)
    if module_name.startswith('selective_'):
        dialog = cls(None, doc, main)
    elif module_name == 'star_spikes':
        dialog = cls(main, None, doc)
    else:
        dialog = cls(main, doc)
    dialog.show()
    dialog.activateWindow()
    dialog.setFocus()
    QTest.qWait(300)
    bar = dialog.zoom_bar
    result = np.empty_like(source)
    result[:] = [.8, .05, .75]
    result_pm = QPixmap.fromImage(source_preview_image(result))
    processing_calls = []
    try:
        assert bar.preview_pane is not None
        if module_name == 'curve_editor_pro':
            dialog._detail_preview = False
            dialog._preview_proc = result
            dialog._show_proc = True
            dialog._update_preview_pix(result)
            get_pixmap = dialog.label.pixmap
        elif module_name == 'clahe':
            dialog._preview = result
            dialog.chk_stretch.setChecked(False)
            dialog._rebuild_pixmaps()
            dialog._compose_and_show()
            get_pixmap = dialog.pix.pixmap
        elif module_name in ('stat_stretch', 'abe'):
            if module_name == 'abe':
                dialog._autostretch_on = False
                dialog.btn_autostr.setChecked(False)
            dialog._set_preview_pixmap(result)
            get_pixmap = dialog.preview_label.pixmap
        elif module_name == 'backgroundneutral':
            dialog.auto_stretch = False
            dialog._load_image()
            dialog.seed_from_preset({
                'mode': 'rect', 'rect_norm': [0, 0, .2, .2],
            })
            get_pixmap = dialog.pixmap_item.pixmap
        elif module_name in ('morphology', 'wavescalede',
                             'wavescale_hdr', 'halobgon'):
            dialog._set_pix(result)
            get_pixmap = dialog.pix.pixmap
        elif module_name in ('texture_clarity', 'fx_module'):
            dialog._pix_processed = result_pm
            dialog._show_pixmap(result_pm)
            get_pixmap = dialog.preview_lbl.pixmap
        elif module_name in ('pedestal', 'star_stretch'):
            if hasattr(dialog, 'chk_autostretch'):
                dialog.chk_autostretch.setChecked(False)
            dialog._update_preview_pix(result)
            get_pixmap = dialog.label.pixmap
        elif module_name == 'histogram_transform_pro':
            dialog._base_pm = result_pm
            dialog._apply_zoom()
            get_pixmap = dialog.lbl_preview.pixmap
        elif module_name == 'ghs_dialog_pro':
            dialog.chk_display_stretch.setChecked(False)
            dialog._cached_processed_pix = result_pm
            dialog._pix = result_pm
            dialog._apply_zoom()
            get_pixmap = dialog.label.pixmap
        elif module_name.startswith('selective_'):
            def adjusted(base, *args, **kwargs):
                color = np.array([.8, .05, .75], dtype=np.float32)
                return np.broadcast_to(color, base.shape).copy()
            monkeypatch.setattr(
                module, '_apply_selective_adjustments', adjusted,
            )
            dialog.cb_live.setChecked(True)
            dialog.cb_show_mask.setChecked(False)
            dialog._update_preview_pixmap()
            for name in ('_adj_timer', '_mask_timer'):
                timer = getattr(dialog, name, None)
                if timer is not None:
                    timer.stop()

            def counted_adjustment(*args, **kwargs):
                processing_calls.append(True)
                return adjusted(*args, **kwargs)
            monkeypatch.setattr(
                module, '_apply_selective_adjustments', counted_adjustment,
            )
            get_pixmap = dialog.lbl_preview.pixmap
        elif module_name == 'star_spikes':
            dialog._update_preview(result)
            get_pixmap = dialog.pix.pixmap
        else:
            dialog._set_preview_image(result)
            get_pixmap = dialog._preview_item.pixmap

        # Manual zoom must survive comparison, including reduced/full rasters.
        bar.actions_by_name['out'].trigger()
        scale = bar._scale()
        processing_calls.clear()
        after = get_pixmap().toImage().copy()
        QTest.keyPress(bar._viewport, Qt.Key.Key_Space)
        assert bar.comparison.showing_before
        before = get_pixmap().toImage()
        assert before != after, module_name
        assert bar._scale() == pytest.approx(scale, rel=.01)
        QTest.keyRelease(bar._viewport, Qt.Key.Key_Space)
        assert not bar.comparison.showing_before
        assert processing_calls == []
        restored = get_pixmap().toImage()
        assert restored == after, module_name
        assert bar._scale() == pytest.approx(scale, rel=.01)
        assert doc.image is source
        np.testing.assert_array_equal(source, original)
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()


def test_clahe_side_by_side_hold_preserves_scene_geometry(
        qapp, tmp_path, monkeypatch):
    from setiastro.saspro import clahe
    from setiastro.saspro.doc_manager import ImageDocument

    monkeypatch.setattr(clahe, 'QSettings', lambda: QSettings(
        str(tmp_path / 'side-by-side.ini'), QSettings.Format.IniFormat,
    ))
    source = np.full((160, 1600, 3), .3, dtype=np.float32)
    main = QMainWindow()
    dialog = clahe.CLAHEDialogPro(main, ImageDocument(source))
    dialog.show()
    QTest.qWait(300)
    try:
        dialog.grp_mode.button(clahe._MODE_SBS).setChecked(True)
        dialog._on_mode_changed(clahe._MODE_SBS)
        geometry = dialog.scene.sceneRect()
        scale = dialog.zoom_bar._scale()
        after = dialog.pix.pixmap().toImage()
        QTest.keyPress(dialog.view.viewport(), Qt.Key.Key_Space)
        assert dialog.scene.sceneRect() == geometry
        assert dialog.zoom_bar._scale() == scale
        QTest.keyRelease(dialog.view.viewport(), Qt.Key.Key_Space)
        assert dialog.scene.sceneRect() == geometry
        assert dialog.pix.pixmap().toImage() == after
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()


def test_retained_stretch_frame_survives_a_new_result(
        qapp, tmp_path, monkeypatch):
    import gc
    from setiastro.saspro import stat_stretch
    from setiastro.saspro.doc_manager import ImageDocument

    monkeypatch.setattr(stat_stretch, 'QSettings', lambda: QSettings(
        str(tmp_path / 'retained-frame.ini'), QSettings.Format.IniFormat,
    ))
    source = np.full((32, 640, 3), .4, dtype=np.float32)
    main = QMainWindow()
    dialog = stat_stretch.StatisticalStretchDialog(main, ImageDocument(source))
    try:
        dialog._set_preview_pixmap(source)
        retained = dialog._preview_qimg
        expected = retained.copy()
        dialog._set_preview_pixmap(source * .5)
        gc.collect()
        assert retained == expected
        assert retained != dialog._preview_qimg
    finally:
        dialog.close()
        QTest.qWait(100)
        main.close()
