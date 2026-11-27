"""Location checks for self-service punches. Coordinates are used only for the check."""
from math import asin, cos, radians, sin, sqrt

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, ValidationFailed
from app.modules.employees.models import Employee
from app.modules.organization.models import Branch


class PunchLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float = Field(ge=0, allow_inf_nan=False)


def branch_premises(db: Session, emp: Employee) -> list[dict]:
    if emp.branch_id is None:
        return []
    return db.scalar(select(Branch.premises).where(Branch.id == emp.branch_id)) or []


def _distance_m(location: PunchLocation, premise: dict) -> float:
    latitude, other_latitude = radians(location.latitude), radians(premise["latitude"])
    delta_latitude = other_latitude - latitude
    delta_longitude = radians(premise["longitude"] - location.longitude)
    haversine = sin(delta_latitude / 2) ** 2 + cos(latitude) * cos(other_latitude) * sin(delta_longitude / 2) ** 2
    return 2 * 6_371_008.8 * asin(sqrt(min(1, max(0, haversine))))


def validate_location(premises: list[dict], location: PunchLocation | None) -> None:
    if not premises:
        return
    if location is None:
        raise ValidationFailed("Share your location to punch at your branch", code="location_required")
    margins = [p["radius_m"] - _distance_m(location, p) for p in premises]
    if max(margins) < 0:
        raise Forbidden("Your location is outside your branch premises", code="outside_premises")
    if max(margins) < location.accuracy_m:
        raise ValidationFailed("Your location is too uncertain. Move farther inside the premises and try again.",
                               code="location_inaccurate")
