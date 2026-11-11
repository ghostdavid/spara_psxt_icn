"""署名资源回归：python -B tests/test_branding.py。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app


class BrandingTests(unittest.TestCase):
    def test_resources(self):
        version = f'v{app.APP_VERSION}'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            resource = folder / 'branding.private.json'
            with patch.object(app, '__file__', str(folder / 'app.py')), \
                 patch.object(sys, 'frozen', True, create=True):
                self.assertEqual(app._version_author_text(), version)
                for payload in ['{', '[]', '{}', '{"author": null}',
                                '{"author": 12}', '{"author": " "}']:
                    resource.write_text(payload, encoding='utf-8')
                    self.assertEqual(app._version_author_text(), version)
                resource.write_bytes(b'\xff')
                self.assertEqual(app._version_author_text(), version)
                resource.write_text(json.dumps({'author': ' 示例作者 '}), encoding='utf-8-sig')
                previous = Path.cwd()
                try:
                    os.chdir(folder.parent)
                    self.assertEqual(app._version_author_text(), version + ' | 作者：示例作者')
                finally:
                    os.chdir(previous)
                with patch.object(sys, 'frozen', False):
                    self.assertEqual(app._version_author_text(), version)


if __name__ == '__main__':
    unittest.main()
