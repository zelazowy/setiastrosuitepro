"""Close the focused tool through its normal close handler on Escape."""
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget


class ToolEscapeFilter(QObject):
    """Keep popup/modal cancellation and the main workspace's keys intact."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self._main = weakref.ref(main_window)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            return False
        if (event.key() != Qt.Key.Key_Escape
                or event.modifiers() != Qt.KeyboardModifier.NoModifier
                or not isinstance(obj, QWidget)):
            return False
        main_ref = getattr(self, '_main', None)
        main = main_ref() if main_ref is not None else None
        if main is None or sip.isdeleted(main):
            return False
        app = QApplication.instance()
        if app.activePopupWidget() is not None or app.activeModalWidget() is not None:
            return False
        window = obj.window()
        if (window is main or not window.isVisible()
                or window.windowType() in (Qt.WindowType.Popup, Qt.WindowType.ToolTip,
                                          Qt.WindowType.SplashScreen)):
            return False
        owner = window.parentWidget()
        while owner is not None and owner is not main:
            owner = owner.parentWidget()
        owned = owner is main
        # Some auxiliary previews are intentionally created without a parent.
        # Never treat another independent main window as an auxiliary tool.
        if not owned and (isinstance(window, QMainWindow) or not
                          type(window).__module__.startswith('setiastro.saspro.')):
            return False
        event.accept()
        if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
            # QDialog.reject() can bypass closeEvent cleanup and vetoes.
            # close() follows the same path as the title-bar close button.
            window.close()
        return True
