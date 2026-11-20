"""Integration coverage for shared controls on legacy preview renderers."""
import importlib

import numpy as np
import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('module_name,class_name', [
    ('morphology', 'MorphologyDialogPro'),
    ('wavescalede', 'WaveScaleDarkEnhancerDialogPro'),
    ('wavescale_hdr', 'WaveScaleHDRDialogPro'),
    ('pedestal', 'RemovePedestalDialog'),
    ('star_stretch', 'StarStretchDialog'),
    ('ghs_dialog_pro', 'GhsDialogPro'),
    ('histogram_transform_pro', 'HistogramTransformDialogPro'),
    ('crop_dialog_pro', 'CropDialogPro'),
    ('blemish_blaster', 'BlemishBlasterDialogPro'),
    ('clone_stamp', 'CloneStampDialogPro'),
    ('halobgon', 'HaloBGonDialogPro'),
    ('texture_clarity', 'TextureClarityDialog'),
    ('fx_module', 'FXDialog'),
])
def test_migrated_image_tools(
        qapp, tmp_path, monkeypatch, module_name, class_name):
    from setiastro.saspro.doc_manager import ImageDocument

    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(
            module, 'QSettings',
            lambda *args, **kwargs: QSettings(
                str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat),
        )
    image = np.tile(np.linspace(.03, .7, 3000, dtype=np.float32), (64, 1))
    image = np.repeat(image[..., None], 3, axis=2)
    original = image.copy()
    doc = ImageDocument(image)
    main = QMainWindow()
    main.show()
    dialog = getattr(module, class_name)(main, doc)
    dialog.show()
    QTest.qWait(200)
    bar = dialog.zoom_bar

    def press(sequence):
        dialog.activateWindow()
        dialog.setFocus()
        QTest.keySequence(dialog, QKeySequence(sequence))
        QTest.qWait(30)

    try:
        press('Ctrl+1')
        assert bar._scale() == pytest.approx(1, abs=.01)
        press('Ctrl++')
        assert bar._scale() > 1
        press('Ctrl+-')
        assert bar._scale() == pytest.approx(1, abs=.01)
        press('Ctrl+0')
        fitted = bar._scale()
        assert 0 < fitted < 1
        # A step after Fit must start at the fitted size, without jumping.
        press('Ctrl++')
        assert fitted < bar._scale() < fitted * 1.3
        press('Ctrl+1')
        dialog.resize(dialog.width() + 80, dialog.height() + 40)
        QTest.qWait(50)
        assert bar._scale() == pytest.approx(1, abs=.01)
        assert doc.image is image
        np.testing.assert_array_equal(image, original)
    finally:
        dialog.close()
        QTest.qWait(200)
        main.close()


@pytest.mark.parametrize('module_name,class_name,kind', [
    ('mask_creation', 'LivePreviewDialog', 'array'),
    ('mask_creation', 'MaskPreviewDialog', 'array'),
    ('mask_creation', 'MaskCreationDialog', 'array'),
    ('mosaic_master', 'MosaicPreviewWindow', 'array'),
    ('widgets.preview_dialogs', 'ImagePreviewDialog', 'array'),
    ('planetprojection', 'PlanetDiskAdjustDialog', 'disk'),
    ('satchroma_tool', 'SatChromaTool', 'color'),
    ('planetprojection', 'PlanetProjectionPreviewDialog', 'projection'),
    ('ser_stacker_dialog', 'APEditorDialog', 'ap'),
    ('stacking_suite', 'FlatStrengthPreviewDialog', 'flat'),
    ('layers_dock', 'LayersPreviewWindow', 'layers'),
])
def test_special_preview_renderers(
        qapp, tmp_path, monkeypatch, module_name, class_name, kind):
    from setiastro.saspro.doc_manager import ImageDocument

    module = importlib.import_module('setiastro.saspro.' + module_name)
    if hasattr(module, 'QSettings'):
        monkeypatch.setattr(
            module, 'QSettings',
            lambda *args, **kwargs: QSettings(
                str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat),
        )
    image = np.tile(np.linspace(.03, .7, 1600, dtype=np.float32), (120, 1))
    rgb = np.repeat(image[..., None], 3, axis=2)
    doc = ImageDocument(rgb)
    main = QMainWindow()
    cls = getattr(module, class_name)
    if kind == 'array':
        dialog = cls(image if class_name == "MaskPreviewDialog" else rgb)
    elif kind == 'disk':
        dialog = cls(main, rgb, 800, 60, 40)
    elif kind == 'color':
        dialog = cls(document=doc, parent=main)
    elif kind == 'projection':
        dialog = cls(main)
        dialog.set_frame_u8((rgb * 255).astype(np.uint8))
    elif kind == 'ap':
        dialog = cls(main, ref_img01=image, ap_size=32,
                     ap_spacing=64, ap_min_mean=.03)
    elif kind == 'flat':
        dialog = cls(main, 'Synthetic flat', rgb, np.ones_like(rgb),
                     False, lambda array: array)
    else:
        dialog = cls(main)
        dialog.update_composite(rgb, rgb)
    dialog.show()
    QTest.qWait(100)
    bar = dialog.zoom_bar

    def press(sequence):
        dialog.activateWindow()
        dialog.setFocus()
        QTest.keySequence(dialog, QKeySequence(sequence))
        QTest.qWait(30)

    try:
        press('Ctrl+1')
        assert bar._scale() == pytest.approx(1, abs=.01)
        press('Ctrl++')
        assert bar._scale() > 1
        press('Ctrl+-')
        assert bar._scale() == pytest.approx(1, abs=.01)
        dialog.resize(dialog.width() + 100, dialog.height() + 60)
        QTest.qWait(50)
        assert bar._scale() == pytest.approx(1, abs=.01)
        press('Ctrl+0')
        fitted = bar._scale()
        press('Ctrl++')
        assert fitted < bar._scale() < fitted * 1.3
    finally:
        dialog.close()
        QTest.qWait(100)
        main.close()


def test_keeper_blink_zoom_tracks_fitted_frame(qapp, monkeypatch):
    from types import SimpleNamespace
    from setiastro.saspro.imageops import serloader
    from setiastro.saspro.ser_stacker_dialog import BlinkKeepersDialog

    image = np.tile(np.linspace(.03, .7, 1600, dtype=np.float32), (120, 1))
    source = SimpleNamespace(get_frame=lambda *args, **kwargs: image)
    monkeypatch.setattr(serloader, 'open_planetary_source',
                        lambda *args, **kwargs: source)
    analysis = SimpleNamespace(
        frames_total=2, order=np.arange(2), quality=np.ones(2),
        ref_image=image, dx=np.zeros(2), dy=np.zeros(2),
    )
    cfg = SimpleNamespace(source=None, roi=None, bayer_pattern=None)
    dialog = BlinkKeepersDialog(
        cfg=cfg, analysis=analysis, debayer=False, to_rgb=False, keep_k=2)
    dialog.show()
    QTest.qWait(50)
    bar = dialog.zoom_bar
    try:
        bar.actions_by_name['fit'].trigger()
        fitted = bar._scale()
        assert fitted == pytest.approx(dialog.lbl.pixmap().width() / 1600)
        bar.actions_by_name['in'].trigger()
        assert bar._scale() == pytest.approx(fitted * 1.25)
        bar.actions_by_name['actual'].trigger()
        assert bar._scale() == 1
        # Plain Space retains its frame-rejection behavior.
        dialog.setFocus()
        QTest.keyClick(dialog, Qt.Key.Key_Space)
        assert dialog.rejected[0]
    finally:
        dialog.close()


def test_generated_script_uses_shared_zoom_component():
    import ast
    from pathlib import Path
    from setiastro.saspro.ops import scripts

    tree = ast.parse(Path(scripts.__file__).read_text())
    sample = next(node.value for node in ast.walk(tree)
                  if isinstance(node, ast.Constant)
                  and isinstance(node.value, str)
                  and 'class StarPreviewDialog' in node.value)
    compile(sample, 'sample_star_preview_ui.py', 'exec')
    assert 'PreviewZoomBar.replace(' in sample


def test_frequency_previews_remain_linked(qapp):
    from setiastro.saspro.frequency_separation import FrequencySeperationTab

    image = np.zeros((300, 1600, 3), dtype=np.float32)
    dialog = FrequencySeperationTab()
    dialog.image = image
    dialog.low_freq_image = image.copy()
    dialog.high_freq_image = image.copy()
    dialog._update_previews()
    dialog.show()
    QTest.qWait(50)
    try:
        bar = dialog.zoom_bar
        bar.actions_by_name['actual'].trigger()
        bar.actions_by_name['in'].trigger()
        assert dialog.labelHF.pixmap().width() == 2000
        assert dialog.labelLF.pixmap().width() == 2000
        bar.actions_by_name['fit'].trigger()
        assert dialog.zoom_factor == pytest.approx(min(
            dialog.scrollHF.viewport().width() / 1600,
            dialog.scrollLF.viewport().width() / 1600,
            dialog.scrollHF.viewport().height() / 300,
            dialog.scrollLF.viewport().height() / 300,
        ))
    finally:
        dialog.close()
