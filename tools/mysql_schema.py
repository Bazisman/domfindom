from __future__ import annotations

import argparse
from urllib.parse import parse_qsl, unquote, urlparse


MYSQL_TABLES = [
    "migration_etl_runs",
    "migration_id_map",
    "security_support_access_audit",
    "security_support_access_grants",
    "security_user_data_keys",
    "family_category_audit_resolutions",
    "family_category_bindings",
    "family_categories",
    "family_capital_contributions",
    "family_capital_member_settings",
    "family_capital_accounts",
    "finance_app_settings",
    "finance_reconciliations",
    "finance_reconciliation_sources",
    "finance_recurring_templates",
    "finance_transfers",
    "finance_capital_accounts",
    "finance_budgets",
    "finance_transactions",
    "finance_categories",
    "finance_accounts",
    "family_invites",
    "family_memberships",
    "family_families",
    "auth_user_backup_slot",
    "auth_user_preferences",
    "auth_account_deletion_tokens",
    "auth_email_verification_tokens",
    "auth_password_reset_tokens",
    "auth_auth_events",
    "auth_login_attempts",
    "auth_sessions",
    "auth_users",
]


DDL = [
    """
    CREATE TABLE IF NOT EXISTS auth_users (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        email VARCHAR(255) NOT NULL,
        password_hash TEXT NOT NULL,
        email_verified BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        legacy_sqlite_user_id INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_auth_users_email (email),
        UNIQUE KEY uq_auth_users_legacy_sqlite_user_id (legacy_sqlite_user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at DATETIME NOT NULL,
        ip VARCHAR(255) NULL,
        user_agent TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revoked_at DATETIME NULL,
        UNIQUE KEY uq_auth_sessions_token_hash (token_hash),
        KEY ix_auth_sessions_user_id (user_id),
        KEY ix_auth_sessions_expires_at (expires_at),
        CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_login_attempts (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        rate_key VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL,
        ip VARCHAR(255) NULL,
        success BOOLEAN NOT NULL,
        attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY ix_auth_login_attempts_rate_key_time (rate_key, attempted_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_auth_events (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NULL,
        email VARCHAR(255) NULL,
        event_type VARCHAR(120) NOT NULL,
        status VARCHAR(80) NOT NULL,
        ip VARCHAR(255) NULL,
        user_agent TEXT NULL,
        detail TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY ix_auth_auth_events_created_at (created_at),
        CONSTRAINT fk_auth_events_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_password_reset_tokens (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at DATETIME NOT NULL,
        used_at DATETIME NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_password_reset_tokens_token_hash (token_hash),
        KEY ix_password_reset_tokens_user_id (user_id),
        KEY ix_password_reset_tokens_expires_at (expires_at),
        CONSTRAINT fk_password_reset_tokens_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_email_verification_tokens (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at DATETIME NOT NULL,
        used_at DATETIME NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_email_verification_tokens_token_hash (token_hash),
        KEY ix_email_verification_tokens_user_id (user_id),
        KEY ix_email_verification_tokens_expires_at (expires_at),
        CONSTRAINT fk_email_verification_tokens_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_account_deletion_tokens (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at DATETIME NOT NULL,
        used_at DATETIME NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_account_deletion_tokens_token_hash (token_hash),
        KEY ix_account_deletion_tokens_user_id (user_id),
        KEY ix_account_deletion_tokens_expires_at (expires_at),
        CONSTRAINT fk_account_deletion_tokens_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_user_preferences (
        user_id BIGINT PRIMARY KEY,
        theme_mode VARCHAR(20) NOT NULL DEFAULT 'system',
        workspace_mode VARCHAR(20) NOT NULL DEFAULT 'personal',
        display_name VARCHAR(255) NOT NULL DEFAULT '',
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_auth_user_preferences_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_user_backup_slot (
        user_id BIGINT PRIMARY KEY,
        backup_blob LONGTEXT NOT NULL,
        checksum VARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_auth_user_backup_slot_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_families (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        owner_user_id BIGINT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        archived_at DATETIME NULL,
        KEY ix_family_families_owner_user_id (owner_user_id),
        CONSTRAINT fk_family_families_owner FOREIGN KEY (owner_user_id) REFERENCES auth_users(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_memberships (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        role VARCHAR(20) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        invited_by_user_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_memberships_family_user (family_id, user_id),
        KEY ix_family_memberships_family_status (family_id, status),
        KEY ix_family_memberships_user_status (user_id, status),
        CONSTRAINT fk_family_memberships_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_memberships_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_memberships_invited_by FOREIGN KEY (invited_by_user_id) REFERENCES auth_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_invites (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        invited_by_user_id BIGINT NOT NULL,
        expires_at DATETIME NOT NULL,
        accepted_at DATETIME NULL,
        revoked_at DATETIME NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_invites_token_hash (token_hash),
        KEY ix_family_invites_family_id (family_id),
        KEY ix_family_invites_email (email),
        KEY ix_family_invites_expires_at (expires_at),
        CONSTRAINT fk_family_invites_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_invites_invited_by FOREIGN KEY (invited_by_user_id) REFERENCES auth_users(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_accounts (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(40) NOT NULL,
        money_source VARCHAR(20) NULL,
        balance_minor BIGINT NOT NULL DEFAULT 0,
        currency VARCHAR(8) NOT NULL DEFAULT 'RUB',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_accounts_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_accounts_user_id (user_id),
        KEY ix_finance_accounts_user_money_source (user_id, money_source),
        CONSTRAINT fk_finance_accounts_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_categories (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(20) NOT NULL,
        color VARCHAR(80) NULL,
        icon VARCHAR(80) NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        semantic_key VARCHAR(255) NULL,
        category_uid CHAR(36) NULL,
        scope VARCHAR(40) NOT NULL DEFAULT 'personal',
        sync_status VARCHAR(40) NOT NULL DEFAULT 'unlinked',
        original_name VARCHAR(255) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_categories_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_categories_user_type (user_id, type),
        KEY ix_finance_categories_user_semantic_key (user_id, semantic_key),
        CONSTRAINT fk_finance_categories_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_transactions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        type VARCHAR(20) NOT NULL,
        category VARCHAR(255) NOT NULL,
        category_id BIGINT NULL,
        semantic_key VARCHAR(255) NULL,
        original_category_name VARCHAR(255) NULL,
        amount_minor BIGINT NOT NULL,
        comment TEXT NULL,
        date DATE NOT NULL,
        money_source VARCHAR(20) NOT NULL DEFAULT 'cashless',
        status VARCHAR(20) NOT NULL DEFAULT 'actual',
        executed_at DATETIME NULL,
        template_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_transactions_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_transactions_user_date (user_id, date),
        KEY ix_finance_transactions_user_status_date (user_id, status, date),
        KEY ix_finance_transactions_user_type_date (user_id, type, date),
        KEY ix_finance_transactions_user_category (user_id, category_id),
        CONSTRAINT fk_finance_transactions_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_finance_transactions_category FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_budgets (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        category_id BIGINT NOT NULL,
        amount_minor BIGINT NOT NULL,
        period VARCHAR(20) NOT NULL,
        UNIQUE KEY uq_finance_budgets_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_budgets_user_category (user_id, category_id),
        CONSTRAINT fk_finance_budgets_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_finance_budgets_category FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_capital_accounts (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        balance_minor BIGINT NOT NULL DEFAULT 0,
        currency VARCHAR(8) NOT NULL DEFAULT 'RUB',
        icon VARCHAR(80) NULL,
        color VARCHAR(80) NULL,
        purpose VARCHAR(40) NOT NULL DEFAULT 'cushion',
        is_default BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_capital_accounts_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_capital_accounts_user_active (user_id, is_active),
        CONSTRAINT fk_finance_capital_accounts_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_transfers (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        legacy_from_account_id INT NOT NULL,
        legacy_to_account_id INT NOT NULL,
        from_account_kind VARCHAR(20) NOT NULL,
        to_account_kind VARCHAR(20) NOT NULL,
        from_daily_account_id BIGINT NULL,
        to_daily_account_id BIGINT NULL,
        from_capital_account_id BIGINT NULL,
        to_capital_account_id BIGINT NULL,
        amount_minor BIGINT NOT NULL,
        transaction_id BIGINT NULL,
        date DATE NOT NULL,
        comment TEXT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_transfers_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_transfers_user_date (user_id, date),
        CONSTRAINT fk_finance_transfers_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_finance_transfers_from_daily FOREIGN KEY (from_daily_account_id) REFERENCES finance_accounts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_finance_transfers_to_daily FOREIGN KEY (to_daily_account_id) REFERENCES finance_accounts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_finance_transfers_from_capital FOREIGN KEY (from_capital_account_id) REFERENCES finance_capital_accounts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_finance_transfers_to_capital FOREIGN KEY (to_capital_account_id) REFERENCES finance_capital_accounts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_finance_transfers_transaction FOREIGN KEY (transaction_id) REFERENCES finance_transactions(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_recurring_templates (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        type VARCHAR(20) NOT NULL,
        name VARCHAR(255) NOT NULL,
        amount_minor BIGINT NOT NULL,
        day_of_month INT NOT NULL,
        category_id BIGINT NULL,
        comment_template TEXT NULL,
        money_source VARCHAR(20) NOT NULL DEFAULT 'cashless',
        months_ahead INT NOT NULL DEFAULT 12,
        working_days_only BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_recurring_templates_user_legacy (user_id, legacy_local_id),
        KEY ix_finance_recurring_templates_user_active (user_id, is_active),
        CONSTRAINT fk_finance_recurring_templates_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_finance_recurring_templates_category FOREIGN KEY (category_id) REFERENCES finance_categories(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_reconciliation_sources (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        balance_minor BIGINT NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_reconciliation_sources_user_legacy (user_id, legacy_local_id),
        CONSTRAINT fk_finance_reconciliation_sources_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_reconciliations (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        legacy_local_id INT NOT NULL,
        real_balance_minor BIGINT NOT NULL,
        program_balance_minor BIGINT NOT NULL,
        difference_minor BIGINT NOT NULL,
        adjustment_transaction_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_finance_reconciliations_user_legacy (user_id, legacy_local_id),
        CONSTRAINT fk_finance_reconciliations_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_finance_reconciliations_transaction FOREIGN KEY (adjustment_transaction_id) REFERENCES finance_transactions(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_app_settings (
        user_id BIGINT NOT NULL,
        `key` VARCHAR(255) NOT NULL,
        value TEXT NOT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, `key`),
        CONSTRAINT fk_finance_app_settings_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_capital_accounts (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        owner_user_id BIGINT NOT NULL,
        capital_account_id BIGINT NOT NULL,
        is_visible BOOLEAN NOT NULL DEFAULT FALSE,
        is_default_target BOOLEAN NOT NULL DEFAULT FALSE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_capital_accounts_target (family_id, owner_user_id, capital_account_id),
        KEY ix_family_capital_accounts_family_visible (family_id, is_visible),
        CONSTRAINT fk_family_capital_accounts_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_accounts_owner FOREIGN KEY (owner_user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_accounts_account FOREIGN KEY (capital_account_id) REFERENCES finance_capital_accounts(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_capital_member_settings (
        family_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        target_owner_user_id BIGINT NULL,
        target_capital_account_id BIGINT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (family_id, user_id),
        CONSTRAINT fk_family_capital_member_settings_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_member_settings_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_member_settings_owner FOREIGN KEY (target_owner_user_id) REFERENCES auth_users(id) ON DELETE SET NULL,
        CONSTRAINT fk_family_capital_member_settings_account FOREIGN KEY (target_capital_account_id) REFERENCES finance_capital_accounts(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_capital_contributions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        source_user_id BIGINT NOT NULL,
        legacy_source_transaction_id INT NOT NULL,
        source_transaction_id BIGINT NULL,
        target_owner_user_id BIGINT NOT NULL,
        target_capital_account_id BIGINT NOT NULL,
        amount_minor BIGINT NOT NULL,
        date DATE NOT NULL,
        comment TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reversed_at DATETIME NULL,
        UNIQUE KEY uq_family_capital_contributions_legacy_source_tx (source_user_id, legacy_source_transaction_id),
        KEY ix_family_capital_contributions_family_reversed (family_id, reversed_at),
        CONSTRAINT fk_family_capital_contributions_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_contributions_source_user FOREIGN KEY (source_user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_contributions_source_tx FOREIGN KEY (source_transaction_id) REFERENCES finance_transactions(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_capital_contributions_target_owner FOREIGN KEY (target_owner_user_id) REFERENCES auth_users(id) ON DELETE RESTRICT,
        CONSTRAINT fk_family_capital_contributions_target_account FOREIGN KEY (target_capital_account_id) REFERENCES finance_capital_accounts(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_categories (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        semantic_key VARCHAR(255) NOT NULL,
        display_name VARCHAR(255) NOT NULL,
        type VARCHAR(20) NOT NULL DEFAULT 'both',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by_user_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_categories_semantic_key (family_id, semantic_key),
        CONSTRAINT fk_family_categories_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_categories_created_by FOREIGN KEY (created_by_user_id) REFERENCES auth_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_category_bindings (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        family_category_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        local_category_id BIGINT NOT NULL,
        local_category_name VARCHAR(255) NOT NULL,
        local_category_type VARCHAR(20) NOT NULL,
        status VARCHAR(40) NOT NULL DEFAULT 'confirmed',
        confirmed_by_user_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_category_bindings_family_user_category (family_id, user_id, local_category_id),
        KEY ix_family_category_bindings_family_status (family_id, status),
        CONSTRAINT fk_family_category_bindings_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_category_bindings_family_category FOREIGN KEY (family_category_id) REFERENCES family_categories(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_category_bindings_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_category_bindings_local_category FOREIGN KEY (local_category_id) REFERENCES finance_categories(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_category_bindings_confirmed_by FOREIGN KEY (confirmed_by_user_id) REFERENCES auth_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS family_category_audit_resolutions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        family_id BIGINT NOT NULL,
        code VARCHAR(255) NOT NULL,
        group_key VARCHAR(255) NOT NULL,
        action VARCHAR(80) NOT NULL,
        category_names_json TEXT NOT NULL,
        note TEXT NOT NULL,
        resolved_by_user_id BIGINT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_family_category_audit_resolutions_item (family_id, code, group_key, action),
        CONSTRAINT fk_family_category_audit_resolutions_family FOREIGN KEY (family_id) REFERENCES family_families(id) ON DELETE CASCADE,
        CONSTRAINT fk_family_category_audit_resolutions_user FOREIGN KEY (resolved_by_user_id) REFERENCES auth_users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS security_user_data_keys (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        key_version INT NOT NULL,
        wrapped_key BLOB NOT NULL,
        wrap_method VARCHAR(80) NOT NULL,
        salt BLOB NULL,
        kdf_params JSON NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        rotated_at DATETIME NULL,
        revoked_at DATETIME NULL,
        UNIQUE KEY uq_security_user_data_keys_user_version (user_id, key_version),
        CONSTRAINT fk_security_user_data_keys_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS security_support_access_grants (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        granted_by_user_id BIGINT NOT NULL,
        support_public_key_id VARCHAR(255) NOT NULL,
        encrypted_grant BLOB NOT NULL,
        reason TEXT NULL,
        expires_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revoked_at DATETIME NULL,
        used_at DATETIME NULL,
        CONSTRAINT fk_security_support_access_grants_user FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        CONSTRAINT fk_security_support_access_grants_granted_by FOREIGN KEY (granted_by_user_id) REFERENCES auth_users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS security_support_access_audit (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        grant_id BIGINT NOT NULL,
        actor VARCHAR(255) NOT NULL,
        action VARCHAR(120) NOT NULL,
        ip VARCHAR(255) NULL,
        user_agent TEXT NULL,
        detail TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_security_support_access_audit_grant FOREIGN KEY (grant_id) REFERENCES security_support_access_grants(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS migration_id_map (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source_db_path VARCHAR(512) NOT NULL,
        source_user_id BIGINT NULL,
        source_table VARCHAR(120) NOT NULL,
        source_local_id BIGINT NOT NULL,
        target_schema VARCHAR(80) NOT NULL,
        target_table VARCHAR(120) NOT NULL,
        target_id BIGINT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_migration_id_map_source (source_db_path, source_user_id, source_table, source_local_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS migration_etl_runs (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        source_root VARCHAR(1024) NOT NULL,
        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at DATETIME NULL,
        status VARCHAR(40) NOT NULL,
        report_json JSON NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

MYSQL_MIGRATIONS = [
    (
        "finance_capital_accounts",
        "purpose",
        "ALTER TABLE finance_capital_accounts ADD COLUMN purpose VARCHAR(40) NOT NULL DEFAULT 'cushion' AFTER color",
    ),
]


def mysql_connect(database_url: str):
    import pymysql

    parsed = urlparse(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("Use mysql+pymysql://user:password@host:3306/database")
    query = dict(parse_qsl(parsed.query))
    return pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "").lstrip("/"),
        charset=query.get("charset", "utf8mb4"),
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def apply_schema(database_url: str, reset_target: bool) -> dict:
    with mysql_connect(database_url) as conn:
        with conn.cursor() as cursor:
            if reset_target:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                for table in MYSQL_TABLES:
                    cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            for statement in DDL:
                cursor.execute(statement)
            for table, column, statement in MYSQL_MIGRATIONS:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND COLUMN_NAME = %s
                    """,
                    (table, column),
                )
                if int(cursor.fetchone()["count"] or 0) == 0:
                    cursor.execute(statement)
            cursor.execute("SHOW TABLES")
            tables = [next(iter(row.values())) for row in cursor.fetchall()]
        conn.commit()
    return {"status": "ok", "tables": len(tables)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create guarded MySQL migration schema.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--reset-target", action="store_true")
    args = parser.parse_args()
    report = apply_schema(args.database_url, reset_target=args.reset_target)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
