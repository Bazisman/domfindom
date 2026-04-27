from core_money import MONEY_SOURCE_CASHLESS, normalize_money_source


def get_app_setting(get_connection, key, default=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ? LIMIT 1", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_app_setting(get_connection, key, value):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, str(value)),
        )
        conn.commit()
        return True


def get_auto_capital_settings(get_connection):
    enabled_raw = get_app_setting(get_connection, "auto_capital_enabled", "1")
    percent_raw = get_app_setting(get_connection, "auto_capital_percent", "10")
    try:
        percent = int(percent_raw)
    except (TypeError, ValueError):
        percent = 10
    return {
        "enabled": str(enabled_raw) == "1",
        "percent": max(0, min(percent, 100)),
    }


def set_auto_capital_settings(get_connection, enabled: bool, percent: int):
    normalized_percent = max(0, min(int(percent), 100))
    set_app_setting(get_connection, "auto_capital_enabled", "1" if enabled else "0")
    set_app_setting(get_connection, "auto_capital_percent", str(normalized_percent))
    return {
        "enabled": bool(enabled),
        "percent": normalized_percent,
    }


def get_default_money_source(get_connection):
    return normalize_money_source(
        get_app_setting(get_connection, "default_money_source", MONEY_SOURCE_CASHLESS)
    )


def set_default_money_source(get_connection, money_source: str):
    normalized = normalize_money_source(money_source)
    set_app_setting(get_connection, "default_money_source", normalized)
    return normalized


def get_family_visible_daily_money_sources(get_connection):
    result = set()
    for source in ("cashless", "cash"):
        if str(get_app_setting(get_connection, f"family_visible_daily_{source}", "0")) == "1":
            result.add(source)
    return result


def set_family_visible_daily_money_source(get_connection, money_source: str, visible: bool):
    normalized = normalize_money_source(money_source)
    set_app_setting(get_connection, f"family_visible_daily_{normalized}", "1" if visible else "0")
    return visible
