# app/utils/category_image.py
from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from PIL import Image, UnidentifiedImageError

# Разрешаем реальные форматы (по содержимому файла), а не только по content-type/расширению
_ALLOWED_FORMATS_TO_EXT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def category_image_dir() -> Path:
    p = _project_root() / "app" / "static" / "uploads" / "categories"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_category_image_url(category_id: str) -> Optional[str]:
    d = category_image_dir()
    matches = sorted(d.glob(f"{category_id}.*"))
    if not matches:
        return None
    filename = matches[0].name
    return f"/static/uploads/categories/{filename}"


def delete_category_image(category_id: str) -> None:
    d = category_image_dir()
    for f in d.glob(f"{category_id}.*"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


def save_category_image(category_id: str, upload: UploadFile) -> str:
    """
    Сохраняем фото категории как {category_id}.ext
    Перед сохранением удаляем старое фото категории (если было).

    ВАЖНО:
    - Проверяем размер
    - Проверяем, что файл реально является JPEG/PNG/WEBP (Pillow verify)
    - На любую проблему кидаем ValueError, чтобы роут отрендерил image_error, а не упал.
    """
    if not upload or not upload.filename:
        raise ValueError("Файл не выбран.")

    # читаем файл в память, чтобы не уронить сервер огромным файлом
    try:
        upload.file.seek(0)
        data = upload.file.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("Файл слишком большой. Максимум 5 МБ.")
        if not data:
            raise ValueError("Пустой файл.")
    except ValueError:
        raise
    except Exception:
        raise ValueError("Не удалось прочитать файл изображения.")

    # проверяем реальный формат по содержимому
    try:
        bio = BytesIO(data)
        img = Image.open(bio)
        img.verify()  # проверка целостности
        fmt = (img.format or "").upper()
    except (UnidentifiedImageError, OSError):
        raise ValueError("Файл не является корректным изображением.")
    except Exception:
        raise ValueError("Не удалось проверить изображение.")

    ext = _ALLOWED_FORMATS_TO_EXT.get(fmt)
    if not ext:
        raise ValueError("Неверный формат. Разрешены только JPG, PNG или WEBP.")

    # сохраняем
    delete_category_image(category_id)

    d = category_image_dir()
    target = d / f"{category_id}{ext}"

    try:
        with target.open("wb") as f:
            f.write(data)
    except Exception:
        raise ValueError("Не удалось сохранить изображение. Попробуйте другой файл.")

    return f"/static/uploads/categories/{target.name}"
