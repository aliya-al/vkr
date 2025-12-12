import uuid
from sqlalchemy import String, Integer, Boolean, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Категория, к которой относится товар
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
    # Бренд товара (null, если бренда нет)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id"),
        nullable=True,
    )

    price: Mapped[int] = mapped_column(Integer, nullable=False)

    # ОБЯЗАТЕЛЬНЫЕ ФИЗИЧЕСКИЕ ХАРАКТЕРИСТИКИ
    # Если для товара это не важно - ставит 0.
    volume_m3: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True) # Товар активен/отключён в каталоге
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Скидка в процентах: 10 = 10%. NULL - "нет скидки"

    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    # чтобы достать ввсе характеристики из товара сввязью
    characteristics_values = relationship(
        "ProductCharacteristicValue",
        back_populates="product",
        cascade="all, delete-orphan",
    )



