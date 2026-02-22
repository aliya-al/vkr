from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import FOOTER_DEV_URL, FOOTER_DEV_NAME, FOOTER_DEV_ENABLED

templates = Jinja2Templates(directory="app/templates")

templates.env.globals["FOOTER_DEV_URL"] = FOOTER_DEV_URL
templates.env.globals["FOOTER_DEV_NAME"] = FOOTER_DEV_NAME
templates.env.globals["FOOTER_DEV_ENABLED"] = FOOTER_DEV_ENABLED

def moscow_dt(value: datetime | None, fmt: str = "%d.%m.%Y") -> str:
    """
    Форматирование даты/времени в московском часовом поясе.
    """
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    msk = value.astimezone(ZoneInfo("Europe/Moscow"))
    return msk.strftime(fmt)

templates.env.filters["moscow_dt"] = moscow_dt
