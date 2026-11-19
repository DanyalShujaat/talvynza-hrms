from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import models  # noqa: F401  (register all tables on Base.metadata)
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.db import session as dbsession
from app.modules.assets.router import router as assets_router
from app.modules.attendance.router import router as attendance_router
from app.modules.attendance.router import shifts_router
from app.modules.employees import service as employees_service
from app.modules.employees.router import router as employees_router
from app.modules.expenses.router import router as expenses_router
from app.modules.helpdesk.router import router as helpdesk_router
from app.modules.identity.demo import router as demo_router
from app.modules.identity.router import me_router
from app.modules.identity.router import router as auth_router
from app.modules.leave import service as leave_service
from app.modules.leave.router import router as leave_router
from app.modules.loans.router import router as loans_router
from app.modules.notifications.router import router as notifications_router
from app.modules.offboarding.router import router as offboarding_router
from app.modules.organization.router import router as structure_router
from app.modules.payroll.router import router as payroll_router
from app.modules.payroll.templates import router as salary_templates_router
from app.modules.performance.router import router as performance_router
from app.modules.recruitment.router import public as careers_router
from app.modules.recruitment.router import router as recruitment_router
from app.modules.reporting.reports import router as reports_router
from app.modules.reporting.router import router as reporting_router
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.router import router as org_router
from app.modules.training.router import router as training_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with dbsession.SessionLocal() as db:
        tenancy_service.sync_permission_catalog(db)
        tenancy_service.sync_system_roles(db)
        employees_service.backfill_owner_employees(db)
    yield


def create_app() -> FastAPI:
    employees_service.register_handlers()
    leave_service.register_handlers()
    s = get_settings()
    configure_logging(s.log_json)
    app = FastAPI(title="Talvynza HRMS API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"])
    register_exception_handlers(app)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(auth_router)
    v1.include_router(demo_router)
    v1.include_router(me_router)
    v1.include_router(org_router)
    for r in (structure_router, employees_router, attendance_router, shifts_router, leave_router,
              notifications_router, payroll_router, salary_templates_router, recruitment_router, careers_router, reporting_router,
              expenses_router, loans_router, assets_router, helpdesk_router, performance_router, training_router,
              offboarding_router, reports_router):
        v1.include_router(r)
    app.include_router(v1)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"])
    def ready():
        with dbsession.SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
