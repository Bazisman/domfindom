from models import Transaction
from services.category_service import CategoryService
from services.transaction_service import TransactionService


transaction_service = TransactionService()
category_service = CategoryService()


def row_to_transaction_response(transaction: Transaction) -> dict:
    return {
        "id": transaction.id or 0,
        "type": transaction.type,
        "category": transaction.category,
        "amount": transaction.amount,
        "comment": transaction.comment,
        "date": transaction.date,
        "status": transaction.status or "actual",
    }
