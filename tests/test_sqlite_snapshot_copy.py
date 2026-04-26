import unittest
from pathlib import Path

from tools.sqlite_snapshot_copy import target_path_for


class SqliteSnapshotCopyTestCase(unittest.TestCase):
    def test_target_path_preserves_relative_layout(self):
        source_root = Path("project").resolve()
        target_root = Path("snapshot").resolve()
        source_file = source_root / "data" / "users" / "12" / "finance.db"

        result = target_path_for(source_root, target_root, source_file)

        self.assertEqual(result, target_root / "data" / "users" / "12" / "finance.db")


if __name__ == "__main__":
    unittest.main()
