"""Read the actual CLI command registry without importing/connecting the CLI."""
import ast
from collections import namedtuple
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RetiredCLICommandsTests(unittest.TestCase):
    def test_registry_removes_legacy_ramps_and_preserves_direct_dac_commands(self):
        path = ROOT / 'Client/Client.py'
        tree = ast.parse(path.read_text())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in ('Command', 'commands')
                    for target in node.targets)]
        namespace = {'namedtuple': namedtuple}
        exec(compile(ast.Module(body=assignments, type_ignores=[]), str(path), 'exec'), namespace)
        names = {command.name for command in namespace['commands']}
        self.assertNotIn('ramp_hv', names)
        self.assertNotIn('down_hv', names)
        self.assertIn('set_hv_by_dac', names)
        self.assertIn('query_hv_dac_cache', names)


if __name__ == '__main__':
    unittest.main()
