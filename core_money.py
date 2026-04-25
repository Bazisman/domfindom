MONEY_SOURCE_CASHLESS = "cashless"
MONEY_SOURCE_CASH = "cash"

CASHLESS_ACCOUNT_ID = 1
CASH_ACCOUNT_ID = 2

DAILY_ACCOUNT_IDS = (CASHLESS_ACCOUNT_ID, CASH_ACCOUNT_ID)
MONEY_SOURCES = (MONEY_SOURCE_CASHLESS, MONEY_SOURCE_CASH)


def normalize_money_source(value):
    return MONEY_SOURCE_CASH if value == MONEY_SOURCE_CASH else MONEY_SOURCE_CASHLESS


def account_id_for_money_source(value):
    source = normalize_money_source(value)
    return CASH_ACCOUNT_ID if source == MONEY_SOURCE_CASH else CASHLESS_ACCOUNT_ID


def money_source_for_account_id(account_id):
    return MONEY_SOURCE_CASH if int(account_id) == CASH_ACCOUNT_ID else MONEY_SOURCE_CASHLESS
