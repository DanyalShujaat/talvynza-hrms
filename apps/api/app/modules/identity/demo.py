"""Explicitly enabled, fictional local demo. Uses normal login and session checks."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.session import get_db
from app.modules.identity.deps import check_origin
from app.modules.identity.router import LoginIn, login

router = APIRouter(prefix="/demo", tags=["local demo"], dependencies=[Depends(check_origin)])


def accounts() -> list[dict]:
    s = get_settings()
    if s.environment != "development" or not s.demo_accounts_file:
        raise NotFound("Demo is not enabled")
    path = Path(s.demo_accounts_file)
    if not path.is_file():
        raise NotFound("Demo is being prepared")
    return json.loads(path.read_text(encoding="utf-8"))["accounts"]


@router.get("/accounts")
def list_accounts(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return [{k: a[k] for k in ("key", "label", "email", "name")} for a in accounts()]


class DemoLogin(BaseModel):
    account: str


@router.post("/login")
def demo_login(body: DemoLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    account = next((a for a in accounts() if a["key"] == body.account), None)
    if account is None:
        raise NotFound("Demo account not found")
    response.headers["Cache-Control"] = "no-store"
    return login(LoginIn(email=account["email"], password=account["password"]), request, response, db)
