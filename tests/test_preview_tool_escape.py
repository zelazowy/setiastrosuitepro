"""Window-local Escape, including popup priority and normal close cleanup."""
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeyEvent, QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLabel, QLineEdit, QMainWindow, QMenu, QVBoxLayout,
)

from setiastro.saspro.widgets.tool_escape import ToolEscapeFilter
from setiastro.saspro.widgets.preview_zoom import PreviewZoomBar


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def windows(qapp):
    main = QMainWindow()
    main.escape_filter = ToolEscapeFilter(main)
    main.show()
    tool = QDialog(main)
    tool.setWindowFlag(Qt.WindowType.Tool, True)
    layout = QVBoxLayout(tool)
    edit = QLineEdit(tool)
    layout.addWidget(edit)
    tool.show()
    tool.activateWindow()
    edit.setFocus()
    qapp.processEvents()
    yield main, tool, edit
    tool.close()
    main.close()
    qapp.processEvents()


def test_escape_closes_only_the_focused_tool(windows):
    main, tool, edit = windows
    other = QDialog(main)
    other.show()
    tool.activateWindow()
    edit.setFocus()
    QTest.keyClick(edit, Qt.Key.Key_Escape)
    assert not tool.isVisible()
    assert main.isVisible()
    assert other.isVisible()
    other.close()


def test_independent_main_window_is_not_a_tool(windows):
    main, _, _ = windows

    class AnotherMain(QMainWindow):
        pass

    AnotherMain.__module__ = 'setiastro.saspro.gui.main_window'
    other = AnotherMain()
    other.show()
    QTest.keyClick(other, Qt.Key.Key_Escape)
    assert other.isVisible()
    assert main.isVisible()
    other.close()


def test_unparented_sas_preview_closes_normally(windows):
    class AuxiliaryPreview(QDialog):
        pass

    AuxiliaryPreview.__module__ = 'setiastro.saspro.widgets.preview_dialogs'
    tool = AuxiliaryPreview()
    tool.show()
    calls = []
    tool.finished.connect(calls.append)
    QTest.keyClick(tool, Qt.Key.Key_Escape)
    assert not tool.isVisible()
    assert calls == [QDialog.DialogCode.Rejected]


def test_main_workspace_escape_keeps_its_existing_action(windows, qapp):
    main, tool, _ = windows
    tool.hide()
    calls = []
    action = QAction(main)
    action.setShortcut(QKeySequence('Escape'))
    action.triggered.connect(lambda: calls.append(True))
    main.addAction(action)
    main.activateWindow()
    qapp.setActiveWindow(main)
    QTest.keyClick(main, Qt.Key.Key_Escape)
    assert calls == [True]
    assert main.isVisible()


def test_escape_dismisses_popup_before_tool(windows, qapp):
    _, tool, edit = windows
    menu = QMenu(tool)
    menu.addAction('Example command')
    menu.popup(edit.mapToGlobal(edit.rect().bottomLeft()))
    qapp.processEvents()
    assert qapp.activePopupWidget() is menu
    QTest.keyClick(menu, Qt.Key.Key_Escape)
    assert not menu.isVisible()
    assert tool.isVisible()
    QTest.keyClick(edit, Qt.Key.Key_Escape)
    assert not tool.isVisible()


def test_modal_cancel_does_not_close_its_parent(windows, qapp):
    _, tool, _ = windows
    prompt = QDialog(tool)
    prompt.setModal(True)
    prompt.show()
    qapp.processEvents()
    assert qapp.activeModalWidget() is prompt
    QTest.keyClick(prompt, Qt.Key.Key_Escape)
    assert not prompt.isVisible()
    assert tool.isVisible()


def test_close_handler_can_veto_escape(windows):
    main, _, _ = windows
    calls = []

    class ProtectedTool(QDialog):
        def closeEvent(self, event: QCloseEvent):
            calls.append('close')
            event.ignore()

        def reject(self):
            calls.append('reject')
            super().reject()

    tool = ProtectedTool(main)
    tool.show()
    QTest.keyClick(tool, Qt.Key.Key_Escape)
    assert tool.isVisible()
    assert calls == ['close']
    tool.hide()


def test_auto_repeat_and_modified_escape_do_not_close_tool(windows, qapp):
    _, tool, edit = windows
    repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.NoModifier, '', True)
    qapp.sendEvent(edit, repeat)
    assert tool.isVisible()
    QTest.keyClick(edit, Qt.Key.Key_Escape, Qt.KeyboardModifier.ControlModifier)
    assert tool.isVisible()


def test_escape_releases_held_comparison_without_applying(windows):
    _, tool, _ = windows
    image = QLabel('Preview', tool)
    tool.layout().addWidget(image)
    bar = PreviewZoomBar(tool, image, zoom_in=lambda: None, zoom_out=lambda: None,
                         actual=lambda: None, fit=lambda: None, scale=lambda: 1)
    tool.layout().addWidget(bar)
    changes = []
    bar.enable_comparison(changes.append)
    QTest.qWait(20)
    QTest.keyPress(image, Qt.Key.Key_Space)
    assert changes == [True]
    QTest.keyClick(image, Qt.Key.Key_Escape)
    assert changes == [True, False]
    assert not tool.isVisible()
