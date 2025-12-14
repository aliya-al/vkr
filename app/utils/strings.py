import re
import unicodedata


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
    slug_base = re.sub(r"[^a-z0-9]+", "-", slug_base)
    slug_base = slug_base.strip("-")
    slug_base = re.sub(r"-+", "-", slug_base)
    return slug_base
