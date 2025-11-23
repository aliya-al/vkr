import uuid

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

class OrderItem(Base): # строка заказа
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # какому заказу принадлежит эта строка
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    # какому товару соответствует эта строка
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_item: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True) # если была скидка

    total_price: Mapped[int] = mapped_column(Integer, nullable=False)


    order = relationship("Order", back_populates="items")
    product = relationship("Product")
