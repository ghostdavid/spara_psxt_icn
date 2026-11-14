import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main


class IconTests(unittest.TestCase):
    def test_assets(self):
        svg = ET.parse(ROOT / 'assets/app_icon.svg').getroot()
        self.assertEqual(svg.attrib['viewBox'], '0 0 256 256')
        with Image.open(ROOT / 'assets/app_icon.png') as image:
            self.assertEqual(image.size, (256, 256))
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0, 0))[3], 0)
        with Image.open(ROOT / 'assets/app_icon.ico') as image:
            self.assertEqual(image.ico.sizes(), {(s, s) for s in (16, 24, 32, 48, 64, 128, 256)})

    def test_entry_and_child_icon(self):
        def exercise(root):
            root.update()
            extension = 'ico' if sys.platform == 'win32' else 'png'
            expected = ROOT / 'assets' / f'app_icon.{extension}'
            self.assertTrue(expected.is_file())
            child = main.ttk.Toplevel(root)
            child.update()
            if sys.platform == 'win32':
                import ctypes
                user32 = ctypes.windll.user32
                user32.SendMessageW.restype = ctypes.c_void_p
                user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
                user32.GetAncestor.restype = ctypes.c_void_p
                user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
                user32.GetClassLongPtrW.restype = ctypes.c_void_p
                user32.GetClassLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int)
                icons = []
                for window in (root, child):
                    hwnd = user32.GetAncestor(window.winfo_id(), 2)
                    icon = (user32.SendMessageW(hwnd, 0x007F, 1, 0)
                            or user32.GetClassLongPtrW(hwnd, -14))
                    self.assertTrue(icon)
                    icons.append(icon)
                self.assertEqual(*icons)
            child.destroy()
            root.destroy()

        previous = Path.cwd()
        try:
            os.chdir(ROOT / 'tests')
            with patch.object(main, 'SParamPowerSumApp', side_effect=exercise):
                self.assertEqual(main.main([]), 0)
        finally:
            os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
