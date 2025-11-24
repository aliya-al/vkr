import uuid

from sqlalchemy import ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


class CategoryCharacteristic(Base):
    __tablename__ = "category_characteristics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Категория, для которой подключена характеристика
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Какую глобальную характеристику мы подключаем
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristics.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Обязательна ли характеристика для заполнения на товаре
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Категория, к которой относится эта настройка
    category = relationship("Category", back_populates="characteristics_links")

    # Глобальная характеристика, которая подключена к категории
    characteristic = relationship("GlobalCharacteristic", back_populates="category_links")


# Доразобрать эту модель. В классе Category не добавляла связь с CategoryCharacteristic.