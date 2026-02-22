from app.utils.uploads import upload_dir, upload_web_prefix

_PRODUCTS_UPLOAD_DIR = upload_dir("products")
_PRODUCTS_WEB_PREFIX = upload_web_prefix("products")

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