from app.utils.uploads import UPLOADS_PRODUCTS_DIR

_PRODUCTS_UPLOAD_DIR = UPLOADS_PRODUCTS_DIR
_PRODUCTS_WEB_PREFIX = "/static/uploads/products"

def delete_product_image_if_local(web_path: str | None) -> None:
    """
    Удалить файл с диска, если он из нашей uploads-папки.
    Важно: не удаляем произвольные пути, только наши.
    """
    if not web_path:
        return
    if not web_path.startswith(_PRODUCTS_WEB_PREFIX + "/"):
        return

    filename = web_path.removeprefix(_PRODUCTS_WEB_PREFIX + "/")
    fpath = _PRODUCTS_UPLOAD_DIR / filename
    try:
        if fpath.exists():
            fpath.unlink()
    except OSError:
                                                           
        pass