"""Review shared previews with isolated preferences and a synthetic image.

Run with PYTHONPATH=src python tools/review_previews.py.
"""
import importlib
import os
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QPushButton, QVBoxLayout,
)


def main():
    state = Path(tempfile.mkdtemp(prefix='sas-preview-review-'))
    os.environ['MPLCONFIGDIR'] = str(state / 'mpl')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(state),
    )
    app = QApplication([])
    app.setOrganizationName('SASPreviewReview')
    app.setApplicationName('SAS Preview Review')
    from setiastro.saspro.gui.main_window import AstroSuiteProMainWindow

    main = AstroSuiteProMainWindow(
        version='1.24.6 unified preview review',
    )
    main.show()
    main.setWindowOpacity(1)
    image = np.tile(np.linspace(.02, .6, 1600, dtype=np.float32), (900, 1))
    image[420:430, 750:760] = 1
    rgb = np.repeat(image[..., None], 3, axis=2)
    path = state / 'synthetic-preview-review.fits'
    fits.writeto(path, rgb.transpose(2, 0, 1))
    main.docman.open_path(str(path))
    selector = QDialog(main)
    selector.setWindowTitle('Unified preview review')
    layout = QVBoxLayout(selector)
    choices = QComboBox(selector)
    items = [
        ('Curves', 'curve_editor_pro', 'CurvesDialogPro'),
        ('CLAHE', 'clahe', 'CLAHEDialogPro'),
        ('Statistical Stretch', 'stat_stretch', 'StatisticalStretchDialog'),
        ('Background Neutralization', 'backgroundneutral',
         'BackgroundNeutralizationDialog'),
        ('ADBE', 'abe', 'ABEDialog'),
        ('Morphology', 'morphology', 'MorphologyDialogPro'),
        ('GHS', 'ghs_dialog_pro', 'GhsDialogPro'),
        ('Histogram Transform', 'histogram_transform_pro',
         'HistogramTransformDialogPro'),
        ('Texture and Clarity', 'texture_clarity', 'TextureClarityDialog'),
        ('FX', 'fx_module', 'FXDialog'),
        ('Clone Stamp', 'clone_stamp', 'CloneStampDialogPro'),
        ('HaloBGon', 'halobgon', 'HaloBGonDialogPro'),
        ('Signature Insert', 'signature_insert', 'SignatureInsertDialogPro'),
        ('WaveScale HDR', 'wavescale_hdr', 'WaveScaleHDRDialogPro'),
        ('WaveScale Dark Enhancer', 'wavescalede',
         'WaveScaleDarkEnhancerDialogPro'),
    ]
    choices.addItems([entry[0] for entry in items])
    layout.addWidget(choices)
    button = QPushButton('Open selected tool', selector)
    layout.addWidget(button)
    opened = []
    choices.setCurrentIndex(1)

    def open_tool():
        for previous in opened:
            try:
                previous.close()
            except RuntimeError:
                pass
        opened.clear()
        _, module, name = items[choices.currentIndex()]
        tool_module = importlib.import_module('setiastro.saspro.' + module)
        cls = getattr(tool_module, name)
        dialog = cls(main, main.docman.get_active_document())
        dialog.show()
        dialog.raise_()
        opened.append(dialog)

    button.clicked.connect(open_tool)
    selector.show()
    QTimer.singleShot(800, open_tool)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
