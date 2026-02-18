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

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    price_per_item: Mapped[int] = mapped_column(Integer, nullable=False)                
    final_price_per_item: Mapped[int] = mapped_column(Integer, nullable=False, default=0)                                     
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)

    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)

    weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    volume_m3: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    product_image: Mapped[str | None] = mapped_column(String, nullable=True)

    category_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order = relationship("Order", back_populates="items")

    product = relationship("Product")
