# app/models/order_item.py
import uuid
from sqlalchemy import Integer, ForeignKey, String, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ВАЖНО: nullable + SET NULL, чтобы можно было удалять products физически
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # snapshot-цены на момент заказа
    price_per_item: Mapped[int] = mapped_column(Integer, nullable=False)              # базовая цена
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)     # скидка
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)                # line_total по цене со скидкой

    # snapshot-данные товара (минимум, чтобы история не зависела от products)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)

    weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    volume_m3: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # опционально: сохранить картинку/путь на момент заказа
    product_image: Mapped[str | None] = mapped_column(String, nullable=True)

    order = relationship("Order", back_populates="items")

    product = relationship("Product")
