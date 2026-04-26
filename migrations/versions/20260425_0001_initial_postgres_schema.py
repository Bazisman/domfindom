"""Initial PostgreSQL schema.

Revision ID: 20260425_0001
Revises:
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260425_0001"
down_revision = None
branch_labels = None
depends_on = None


AUTH = "auth"
FINANCE = "finance"
FAMILY = "family"
SECURITY = "security"
MIGRATION = "migration"


def now():
    return sa.text("now()")


def id_column():
    return sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True)


def timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
    )


def create_schemas():
    for schema in (AUTH, FINANCE, FAMILY, SECURITY, MIGRATION):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def drop_schemas():
    for schema in (MIGRATION, SECURITY, FAMILY, FINANCE, AUTH):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def create_auth_tables():
    op.create_table(
        "users",
        id_column(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("legacy_sqlite_user_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("legacy_sqlite_user_id", name="uq_users_legacy_sqlite_user_id"),
        schema=AUTH,
    )

    op.create_table(
        "sessions",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema=AUTH,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema=AUTH)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], schema=AUTH)

    op.create_table(
        "login_attempts",
        id_column(),
        sa.Column("rate_key", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        schema=AUTH,
    )
    op.create_index("ix_login_attempts_rate_key_time", "login_attempts", ["rate_key", "attempted_at"], schema=AUTH)

    op.create_table(
        "auth_events",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        schema=AUTH,
    )
    op.create_index("ix_auth_events_created_at", "auth_events", ["created_at"], schema=AUTH)

    for table_name in ("password_reset_tokens", "email_verification_tokens", "account_deletion_tokens"):
        op.create_table(
            table_name,
            id_column(),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
            sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("token_hash", name=f"uq_{table_name}_token_hash"),
            schema=AUTH,
        )
        op.create_index(f"ix_{table_name}_user_id", table_name, ["user_id"], schema=AUTH)
        op.create_index(f"ix_{table_name}_expires_at", table_name, ["expires_at"], schema=AUTH)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("theme_mode", sa.Text(), nullable=False, server_default=sa.text("'system'")),
        sa.Column("workspace_mode", sa.Text(), nullable=False, server_default=sa.text("'personal'")),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.CheckConstraint("theme_mode IN ('light', 'dark', 'system')", name="ck_user_preferences_theme_mode"),
        sa.CheckConstraint("workspace_mode IN ('personal', 'family')", name="ck_user_preferences_workspace_mode"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        schema=AUTH,
    )

    op.create_table(
        "user_backup_slot",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("backup_blob", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        schema=AUTH,
    )


def create_family_tables():
    op.create_table(
        "families",
        id_column(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        *timestamps(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], [f"{AUTH}.users.id"], ondelete="RESTRICT"),
        schema=FAMILY,
    )
    op.create_index("ix_families_owner_user_id", "families", ["owner_user_id"], schema=FAMILY)

    op.create_table(
        "memberships",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("invited_by_user_id", sa.BigInteger(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("role IN ('owner', 'member', 'viewer')", name="ck_memberships_role"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'removed')", name="ck_memberships_status"),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("family_id", "user_id", name="uq_memberships_family_user"),
        schema=FAMILY,
    )
    op.create_index("ix_memberships_family_status", "memberships", ["family_id", "status"], schema=FAMILY)
    op.create_index("ix_memberships_user_status", "memberships", ["user_id", "status"], schema=FAMILY)

    op.create_table(
        "invites",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.CheckConstraint("role IN ('owner', 'member', 'viewer')", name="ck_invites_role"),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], [f"{AUTH}.users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
        schema=FAMILY,
    )
    op.create_index("ix_invites_family_id", "invites", ["family_id"], schema=FAMILY)
    op.create_index("ix_invites_email", "invites", ["email"], schema=FAMILY)
    op.create_index("ix_invites_expires_at", "invites", ["expires_at"], schema=FAMILY)


def create_finance_tables():
    op.create_table(
        "accounts",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("money_source", sa.Text(), nullable=True),
        sa.Column("balance_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
        sa.CheckConstraint("money_source IS NULL OR money_source IN ('cashless', 'cash')", name="ck_accounts_money_source"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_accounts_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"], schema=FINANCE)
    op.create_index("ix_accounts_user_money_source", "accounts", ["user_id", "money_source"], schema=FINANCE)

    op.create_table(
        "categories",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("semantic_key", sa.Text(), nullable=True),
        sa.Column("category_uid", sa.Uuid(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'personal'")),
        sa.Column("sync_status", sa.Text(), nullable=False, server_default=sa.text("'unlinked'")),
        sa.Column("original_name", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("type IN ('income', 'expense', 'both')", name="ck_categories_type"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_categories_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_categories_user_type", "categories", ["user_id", "type"], schema=FINANCE)
    op.create_index("ix_categories_user_semantic_key", "categories", ["user_id", "semantic_key"], schema=FINANCE)

    op.create_table(
        "transactions",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("semantic_key", sa.Text(), nullable=True),
        sa.Column("original_category_name", sa.Text(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("money_source", sa.Text(), nullable=False, server_default=sa.text("'cashless'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'actual'")),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.CheckConstraint("type IN ('income', 'expense')", name="ck_transactions_type"),
        sa.CheckConstraint("money_source IN ('cashless', 'cash')", name="ck_transactions_money_source"),
        sa.CheckConstraint("status IN ('actual', 'planned')", name="ck_transactions_status"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], [f"{FINANCE}.categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_transactions_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "date"], schema=FINANCE)
    op.create_index("ix_transactions_user_status_date", "transactions", ["user_id", "status", "date"], schema=FINANCE)
    op.create_index("ix_transactions_user_type_date", "transactions", ["user_id", "type", "date"], schema=FINANCE)
    op.create_index("ix_transactions_user_category", "transactions", ["user_id", "category_id"], schema=FINANCE)

    op.create_table(
        "budgets",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.CheckConstraint("period IN ('daily', 'weekly', 'monthly', 'yearly')", name="ck_budgets_period"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], [f"{FINANCE}.categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_budgets_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_budgets_user_category", "budgets", ["user_id", "category_id"], schema=FINANCE)

    op.create_table(
        "capital_accounts",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("balance_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_capital_accounts_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_capital_accounts_user_active", "capital_accounts", ["user_id", "is_active"], schema=FINANCE)

    op.create_table(
        "transfers",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("legacy_from_account_id", sa.Integer(), nullable=False),
        sa.Column("legacy_to_account_id", sa.Integer(), nullable=False),
        sa.Column("from_account_kind", sa.Text(), nullable=False),
        sa.Column("to_account_kind", sa.Text(), nullable=False),
        sa.Column("from_daily_account_id", sa.BigInteger(), nullable=True),
        sa.Column("to_daily_account_id", sa.BigInteger(), nullable=True),
        sa.Column("from_capital_account_id", sa.BigInteger(), nullable=True),
        sa.Column("to_capital_account_id", sa.BigInteger(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.CheckConstraint("from_account_kind IN ('daily', 'capital')", name="ck_transfers_from_account_kind"),
        sa.CheckConstraint("to_account_kind IN ('daily', 'capital')", name="ck_transfers_to_account_kind"),
        sa.CheckConstraint(
            """
            (
                from_account_kind = 'daily'
                AND from_daily_account_id IS NOT NULL
                AND from_capital_account_id IS NULL
            )
            OR (
                from_account_kind = 'capital'
                AND from_daily_account_id IS NULL
                AND from_capital_account_id IS NOT NULL
            )
            """,
            name="ck_transfers_from_account_ref",
        ),
        sa.CheckConstraint(
            """
            (
                to_account_kind = 'daily'
                AND to_daily_account_id IS NOT NULL
                AND to_capital_account_id IS NULL
            )
            OR (
                to_account_kind = 'capital'
                AND to_daily_account_id IS NULL
                AND to_capital_account_id IS NOT NULL
            )
            """,
            name="ck_transfers_to_account_ref",
        ),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_daily_account_id"], [f"{FINANCE}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_daily_account_id"], [f"{FINANCE}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_capital_account_id"], [f"{FINANCE}.capital_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_capital_account_id"], [f"{FINANCE}.capital_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], [f"{FINANCE}.transactions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_transfers_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_transfers_user_date", "transfers", ["user_id", "date"], schema=FINANCE)

    op.create_table(
        "recurring_templates",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("comment_template", sa.Text(), nullable=True),
        sa.Column("money_source", sa.Text(), nullable=False, server_default=sa.text("'cashless'")),
        sa.Column("months_ahead", sa.Integer(), nullable=False, server_default=sa.text("12")),
        sa.Column("working_days_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
        sa.CheckConstraint("type IN ('income', 'expense')", name="ck_recurring_templates_type"),
        sa.CheckConstraint("money_source IN ('cashless', 'cash')", name="ck_recurring_templates_money_source"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], [f"{FINANCE}.categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_recurring_templates_user_legacy_local_id"),
        schema=FINANCE,
    )
    op.create_index("ix_recurring_templates_user_active", "recurring_templates", ["user_id", "is_active"], schema=FINANCE)

    op.create_table(
        "reconciliation_sources",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("balance_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_reconciliation_sources_user_legacy_local_id"),
        schema=FINANCE,
    )

    op.create_table(
        "reconciliations",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_local_id", sa.Integer(), nullable=False),
        sa.Column("real_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("program_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("difference_minor", sa.BigInteger(), nullable=False),
        sa.Column("adjustment_transaction_id", sa.BigInteger(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["adjustment_transaction_id"], [f"{FINANCE}.transactions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "legacy_local_id", name="uq_reconciliations_user_legacy_local_id"),
        schema=FINANCE,
    )

    op.create_table(
        "app_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "key"),
        schema=FINANCE,
    )


def create_family_finance_tables():
    op.create_table(
        "capital_accounts",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("capital_account_id", sa.BigInteger(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_default_target", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *timestamps(),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["capital_account_id"], [f"{FINANCE}.capital_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("family_id", "owner_user_id", "capital_account_id", name="uq_family_capital_accounts_target"),
        schema=FAMILY,
    )
    op.create_index("ix_family_capital_accounts_family_visible", "capital_accounts", ["family_id", "is_visible"], schema=FAMILY)

    op.create_table(
        "capital_member_settings",
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("target_capital_account_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_owner_user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_capital_account_id"], [f"{FINANCE}.capital_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("family_id", "user_id"),
        schema=FAMILY,
    )

    op.create_table(
        "capital_contributions",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("source_user_id", sa.BigInteger(), nullable=False),
        sa.Column("legacy_source_transaction_id", sa.Integer(), nullable=False),
        sa.Column("source_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("target_owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_capital_account_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_transaction_id"], [f"{FINANCE}.transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_owner_user_id"], [f"{AUTH}.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_capital_account_id"], [f"{FINANCE}.capital_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_user_id", "legacy_source_transaction_id", name="uq_capital_contributions_legacy_source_tx"),
        schema=FAMILY,
    )
    op.create_index("ix_capital_contributions_family_reversed", "capital_contributions", ["family_id", "reversed_at"], schema=FAMILY)

    op.create_table(
        "categories",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("semantic_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False, server_default=sa.text("'both'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("type IN ('income', 'expense', 'both')", name="ck_family_categories_type"),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("family_id", "semantic_key", name="uq_family_categories_semantic_key"),
        schema=FAMILY,
    )

    op.create_table(
        "category_bindings",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("family_category_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("local_category_id", sa.BigInteger(), nullable=False),
        sa.Column("local_category_name", sa.Text(), nullable=False),
        sa.Column("local_category_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column("confirmed_by_user_id", sa.BigInteger(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["family_category_id"], [f"{FAMILY}.categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["local_category_id"], [f"{FINANCE}.categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("family_id", "user_id", "local_category_id", name="uq_category_bindings_family_user_category"),
        schema=FAMILY,
    )
    op.create_index("ix_category_bindings_family_status", "category_bindings", ["family_id", "status"], schema=FAMILY)

    op.create_table(
        "category_audit_resolutions",
        id_column(),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("category_names_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["family_id"], [f"{FAMILY}.families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], [f"{AUTH}.users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("family_id", "code", "group_key", "action", name="uq_category_audit_resolutions_item"),
        schema=FAMILY,
    )


def create_security_tables():
    op.create_table(
        "user_data_keys",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_method", sa.Text(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=True),
        sa.Column("kdf_params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "key_version", name="uq_user_data_keys_user_version"),
        schema=SECURITY,
    )

    op.create_table(
        "support_access_grants",
        id_column(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("support_public_key_id", sa.Text(), nullable=False),
        sa.Column("encrypted_grant", sa.LargeBinary(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], [f"{AUTH}.users.id"], ondelete="CASCADE"),
        schema=SECURITY,
    )

    op.create_table(
        "support_access_audit",
        id_column(),
        sa.Column("grant_id", sa.BigInteger(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.ForeignKeyConstraint(["grant_id"], [f"{SECURITY}.support_access_grants.id"], ondelete="CASCADE"),
        schema=SECURITY,
    )


def create_migration_tables():
    op.create_table(
        "id_map",
        id_column(),
        sa.Column("source_db_path", sa.Text(), nullable=False),
        sa.Column("source_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_local_id", sa.BigInteger(), nullable=False),
        sa.Column("target_schema", sa.Text(), nullable=False),
        sa.Column("target_table", sa.Text(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.UniqueConstraint(
            "source_db_path",
            "source_user_id",
            "source_table",
            "source_local_id",
            name="uq_id_map_source",
        ),
        schema=MIGRATION,
    )

    op.create_table(
        "etl_runs",
        id_column(),
        sa.Column("source_root", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        schema=MIGRATION,
    )


def upgrade():
    create_schemas()
    create_auth_tables()
    create_family_tables()
    create_finance_tables()
    create_family_finance_tables()
    create_security_tables()
    create_migration_tables()


def downgrade():
    drop_schemas()
