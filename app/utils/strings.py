import re
import unicodedata
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


_RU_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

def slugify(value: str) -> str:
    transliterated = []
    for char in value.lower():
        if char in _RU_TO_LATIN:
            transliterated.append(_RU_TO_LATIN[char])
            continue

        normalized = unicodedata.normalize("NFKD", char)
        ascii_char = normalized.encode("ascii", "ignore").decode("ascii")
        transliterated.append(ascii_char)

    slug_base = "".join(transliterated)
    slug_base = re.sub(r"[^a-z0-9]+", "_", slug_base)
    slug_base = slug_base.strip("_")
    slug_base = re.sub(r"_+", "_", slug_base)
    return slug_base


async def ensure_unique_slug(
    session: AsyncSession,
    model,
    base_slug: str,
    *,
    slug_field: str = "slug",
    exclude_id=None,
    max_len: int = 255,
) -> str:
    """
    Возвращает уникальный slug для model.slug (или другого поля).
    Если base_slug занят — добавляет суффиксы -2, -3, ...
    exclude_id — чтобы при edit не конфликтовать с самой собой.
    """
    base = (base_slug or "").strip("_")[:max_len]
    if not base:
        base = "item"

    slug = base
    i = 2

    slug_col = getattr(model, slug_field)

    while True:
        q = select(model.id).where(slug_col == slug)
        if exclude_id is not None:
            q = q.where(model.id != exclude_id)

        exists = (await session.execute(q)).first()
        if not exists:
            return slug

        suffix = f"_{i}"
        cut = max_len - len(suffix)
        slug = (base[:cut].rstrip("_")) + suffix
        i += 1