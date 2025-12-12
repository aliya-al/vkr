import uuid

from sqlalchemy import ForeignKey, String, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

class ProductCharacteristicValue(Base):
    """
    Значение характеристики для конкретного товара.

    Пример:
    - товар X, характеристика "длина", value_number = 2.5, unit = "м"
    - товар X, характеристика "цвет", value_string = "красный"
    """
    __tablename__ = "product_characteristic_values"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Какому товару принадлежит это значение
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Какая глобальная характеристика
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristics.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Текстовое значение (для строковых характеристик)
    value_string: Mapped[str | None] = mapped_column(String, nullable=True)

    # Числовое значение (для числовых характеристик)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)



    product = relationship("Product", back_populates="characteristics_values")

    characteristic = relationship("GlobalCharacteristic", back_populates="product_values")
