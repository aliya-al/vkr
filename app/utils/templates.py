from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

templates = Jinja2Templates(directory="app/templates")


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


# регистрируем фильтр для Jinja
templates.env.filters["moscow_dt"] = moscow_dt
