import ast
from pathlib import Path
import unittest


class MySqlRuntimeBoundaryTestCase(unittest.TestCase):
    def test_api_routes_do_not_import_legacy_core_directly(self):
        routes_dir = Path("backend/api/routes")
        offenders = []
        for path in routes_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name == "core" or alias.name.startswith("core.") for alias in node.names):
                        offenders.append(str(path))
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "core" or (node.module and node.module.startswith("core.")):
                        offenders.append(str(path))
        self.assertEqual(sorted(set(offenders)), [])


if __name__ == "__main__":
    unittest.main()
