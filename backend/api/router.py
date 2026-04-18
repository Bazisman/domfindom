from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_user
from backend.api.routes import account, accounts, budgets, categories, dashboard, families, forecast, health, reconciliation, recurring, settings, transactions, transfers
from backend.api.routes import auth


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, tags=["dashboard"], dependencies=[Depends(require_user)])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"], dependencies=[Depends(require_user)])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"], dependencies=[Depends(require_user)])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"], dependencies=[Depends(require_user)])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"], dependencies=[Depends(require_user)])
api_router.include_router(transfers.router, prefix="/transfers", tags=["transfers"], dependencies=[Depends(require_user)])
api_router.include_router(budgets.router, prefix="/budgets", tags=["budgets"], dependencies=[Depends(require_user)])
api_router.include_router(forecast.router, prefix="/forecast", tags=["forecast"], dependencies=[Depends(require_user)])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=[Depends(require_user)])
api_router.include_router(recurring.router, prefix="/recurring-templates", tags=["recurring"], dependencies=[Depends(require_user)])
api_router.include_router(account.router, prefix="/account", tags=["account"], dependencies=[Depends(require_user)])
api_router.include_router(families.router, prefix="/families", tags=["families"], dependencies=[Depends(require_user)])
