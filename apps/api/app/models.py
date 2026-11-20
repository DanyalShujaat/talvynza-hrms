"""Imports every model module so Alembic and create_all see the full metadata. Add new modules here."""
from app.db.base import Base  # noqa: F401
from app.modules.ai import models as _ai  # noqa: F401
from app.modules.assets import models as _assets  # noqa: F401
from app.modules.attendance import models as _attendance  # noqa: F401
from app.modules.employees import models as _employees  # noqa: F401
from app.modules.expenses import models as _expenses  # noqa: F401
from app.modules.helpdesk import models as _helpdesk  # noqa: F401
from app.modules.identity import models as _identity  # noqa: F401
from app.modules.leave import models as _leave  # noqa: F401
from app.modules.loans import models as _loans  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.offboarding import models as _offboarding  # noqa: F401
from app.modules.organization import models as _organization  # noqa: F401
from app.modules.payroll import models as _payroll  # noqa: F401
from app.modules.performance import models as _performance  # noqa: F401
from app.modules.recruitment import models as _recruitment  # noqa: F401
from app.modules.tenancy import models as _tenancy  # noqa: F401
from app.modules.training import models as _training  # noqa: F401
