from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.routers.admin import router as admin_router

routers = APIRouter()


@routers.get("/", response_class=HTMLResponse)
async def home_page():
    return HTMLResponse(
        """
        <html>
          <head><title>Главная</title></head>
          <body>
            <h1>Домашняя страница</h1>
            <p>Доступные пользовательские разделы:</p>
            <ul>
              <li><a href="/catalog/example-slug">Каталог (пример)</a></li>
              <li><a href="/product/example-product">Карточка товара (пример)</a></li>
              <li><a href="/compare">Сравнение</a></li>
              <li><a href="/cart">Корзина</a></li>
              <li><a href="/favorites">Избранное</a></li>
              <li><a href="/search">Поиск</a></li>
              <li><a href="/checkout">Оформление заказа</a></li>
            </ul>
            <p><a href="/admin/login">Админ-панель</a></p>
          </body>
        </html>
        """
    )


routers.include_router(admin_router)
