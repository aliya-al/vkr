from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base
import enum

class CharacteristicType(str, enum.Enum):
    string = "string"   # любое текстовое значение: "M300", "красный", "гладкий"
    number = "number"   # числовое: длина, ширина, толщина, плотность и т.п.

class GlobalCharacteristic(Base):
    __tablename__ = "characteristics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    value_type: Mapped[CharacteristicType] = mapped_column(
        Enum(CharacteristicType),
        nullable=False,
        default=CharacteristicType.string,
    )

    # ед измерения: "м", "мм", "шт", "%", ...
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)

    category_links = relationship("CategoryCharacteristic", back_populates="characteristic")
    product_values = relationship("ProductCharacteristicValue", back_populates="characteristic")
