from typing import Callable, TypeVar

import core
from backend.auth.service import auth_service
from models import Transaction
from services.category_service import CategoryService
from services.transaction_service import TransactionService


T = TypeVar("T")

transaction_service = TransactionService()
category_service = CategoryService()


def run_in_user_finance_db(user_id: int, action: Callable[[], T]) -> T:
    """Выполняет действие в контексте финансовой базы конкретного пользователя."""
    db_path = auth_service.ensure_user_finance_db(user_id)
    token = core.push_db_name(db_path)
    try:
        return action()
    finally:
        core.pop_db_name(token)


def row_to_transaction_response(transaction: Transaction) -> dict:
    return {
        "id": transaction.id or 0,
        "type": transaction.type,
        "category": transaction.category,
        "amount": transaction.amount,
        "comment": transaction.comment,
        "date": transaction.date,
        "status": transaction.status or "actual",
        "money_source": getattr(transaction, "money_source", "cashless") or "cashless",
    }
