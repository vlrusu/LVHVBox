"""Parse tracked Python sources offline; never import applications or use hardware."""
import ast
from pathlib import Path
import subprocess
import tokenize
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PythonSyntax(unittest.TestCase):
    def test_tracked_python_sources(self):
        tracked = subprocess.check_output(
            ['git', '-C', str(ROOT), 'ls-files', '-z', '--', '*.py'])
        paths = [name.decode() for name in tracked.split(b'\0') if name]
        self.assertTrue(paths, 'No tracked Python sources found')
        for relative in paths:
            with self.subTest(path=relative):
                # Honor Python encoding declarations without importing the file.
                with tokenize.open(ROOT / relative) as source:
                    ast.parse(source.read(), filename=relative)


if __name__ == '__main__':
    unittest.main()
