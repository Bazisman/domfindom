from fastapi import APIRouter

from backend.api.routes import accounts, budgets, categories, dashboard, forecast, health, recurring, settings, transactions, transfers


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(transfers.router, prefix="/transfers", tags=["transfers"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["budgets"])
api_router.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(recurring.router, prefix="/recurring-templates", tags=["recurring"])
