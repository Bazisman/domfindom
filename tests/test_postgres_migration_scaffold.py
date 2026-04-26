import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "20260425_0001_initial_postgres_schema.py"


class PostgresMigrationScaffoldTestCase(unittest.TestCase):
    def setUp(self):
        self.migration_text = MIGRATION.read_text(encoding="utf-8")
        self.migration_ast = ast.parse(self.migration_text)

    def test_initial_migration_declares_expected_revision(self):
        assignments = {
            node.targets[0].id: node.value.value
            for node in self.migration_ast.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        self.assertEqual(assignments["revision"], "20260425_0001")
        self.assertIsNone(assignments["down_revision"])

    def test_initial_migration_creates_expected_schemas(self):
        assignments = {
            node.targets[0].id: node.value.value
            for node in self.migration_ast.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        for schema in ("auth", "finance", "family", "security", "migration"):
            self.assertIn(schema, assignments.values())
        self.assertIn("CREATE SCHEMA IF NOT EXISTS", self.migration_text)

    def test_finance_money_fields_use_minor_units(self):
        forbidden_columns = (
            '"amount"',
            '"balance"',
            '"real_balance"',
            '"program_balance"',
            '"difference"',
        )
        for forbidden in forbidden_columns:
            self.assertNotIn(f"sa.Column({forbidden}, sa.BigInteger()", self.migration_text)
            self.assertNotIn(f"sa.Column({forbidden}, sa.Numeric", self.migration_text)
            self.assertNotIn(f"sa.Column({forbidden}, sa.Float", self.migration_text)

        for required in (
            "amount_minor",
            "balance_minor",
            "real_balance_minor",
            "program_balance_minor",
            "difference_minor",
        ):
            self.assertIn(required, self.migration_text)

    def test_transfers_distinguish_daily_and_capital_accounts(self):
        for required in (
            "from_account_kind",
            "to_account_kind",
            "from_daily_account_id",
            "to_daily_account_id",
            "from_capital_account_id",
            "to_capital_account_id",
            "legacy_from_account_id",
            "legacy_to_account_id",
        ):
            self.assertIn(required, self.migration_text)

    def test_backend_startup_does_not_import_alembic(self):
        for relative_path in ("backend/main.py", "backend/site_app.py", "passenger_wsgi.py"):
            content = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("alembic", content.lower(), relative_path)
            self.assertNotIn("run_migrations", content, relative_path)


if __name__ == "__main__":
    unittest.main()
