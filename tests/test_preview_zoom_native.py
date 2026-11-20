"""Native Windows keyboard translation, beyond synthetic Qt key events."""
import sys

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QVBoxLayout

from setiastro.saspro.widgets.preview_zoom import PreviewZoomBar


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('layout', ['00000409', '00000415'])
def test_windows_native_zoom_keys(qapp, layout):
    if sys.platform != 'win32' or qapp.platformName() != 'windows':
        pytest.skip('Requires the native Windows Qt platform plugin')
    import ctypes
    from ctypes import wintypes

    class KeyboardInput(ctypes.Structure):
        _fields_ = [
            ('vk', wintypes.WORD), ('scan', wintypes.WORD),
            ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
            ('extra', ctypes.c_size_t),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ('x', wintypes.LONG), ('y', wintypes.LONG),
            ('data', wintypes.DWORD), ('flags', wintypes.DWORD),
            ('time', wintypes.DWORD), ('extra', ctypes.c_size_t),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [('msg', wintypes.DWORD), ('low', wintypes.WORD),
                    ('high', wintypes.WORD)]

    class InputData(ctypes.Union):
        _fields_ = [('keyboard', KeyboardInput), ('mouse', MouseInput),
                    ('hardware', HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [('kind', wintypes.DWORD), ('data', InputData)]

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SendInput.argtypes = [
        wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    user32.GetKeyboardLayout.restype = wintypes.HANDLE
    user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
    user32.LoadKeyboardLayoutW.restype = wintypes.HANDLE
    user32.ActivateKeyboardLayout.argtypes = [wintypes.HANDLE, wintypes.UINT]
    user32.ActivateKeyboardLayout.restype = wintypes.HANDLE
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    previous_layout = user32.GetKeyboardLayout(0)
    keyboard_layout = user32.LoadKeyboardLayoutW(layout, 0)
    assert keyboard_layout, 'Windows keyboard layout unavailable'
    window = QDialog()
    row = QVBoxLayout(window)
    edit = QLineEdit(window)
    row.addWidget(edit)
    calls = []
    bar = PreviewZoomBar(
        window, edit, zoom_in=lambda: calls.append('in'),
        zoom_out=lambda: calls.append('out'),
        actual=lambda: calls.append('actual'), fit=lambda: calls.append('fit'),
        scale=lambda: 1,
    )
    row.addWidget(bar)
    window.show()
    window.activateWindow()
    edit.setFocus()
    hwnd = int(window.winId())
    user32.SetForegroundWindow(hwnd)
    QTest.qWait(100)
    calls.clear()

    def press(virtual_keys):
        assert user32.GetForegroundWindow() == hwnd, 'Test window lost focus'
        inputs = []
        for key in virtual_keys:
            flags = 1 if key == 0x6F else 0  # extended VK_DIVIDE
            inputs.append(Input(1, InputData(
                keyboard=KeyboardInput(key, 0, flags, 0, 0))))
        for key in reversed(virtual_keys):
            flags = 3 if key == 0x6F else 2  # KEYEVENTF_KEYUP
            inputs.append(Input(1, InputData(
                keyboard=KeyboardInput(key, 0, flags, 0, 0))))
        packet = (Input * len(inputs))(*inputs)
        assert user32.SendInput(len(inputs), packet, ctypes.sizeof(Input)) == (
            len(inputs))
        QTest.qWait(100)

    try:
        assert user32.ActivateKeyboardLayout(keyboard_layout, 0)
        for keys, expected in (
            ([0x11, 0x30], 'fit'),        # Ctrl+0
            ([0x11, 0x31], 'actual'),     # Ctrl+1
            ([0x11, 0xBB], 'in'),         # Ctrl+=
            ([0x11, 0x10, 0xBB], 'in'),   # Ctrl+Shift+= (plus)
            ([0x11, 0xBD], 'out'),        # Ctrl+minus
            ([0x11, 0x6B], 'in'),         # Ctrl+keypad plus
            ([0x11, 0x6D], 'out'),        # Ctrl+keypad minus
        ):
            calls.clear()
            press(keys)
            assert calls == [expected], (keys, calls)
    finally:
        user32.ActivateKeyboardLayout(previous_layout, 0)
        window.close()
