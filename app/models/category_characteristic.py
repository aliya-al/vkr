import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


class CategoryCharacteristic(Base):
    __tablename__ = "category_characteristics"
    __table_args__ = (
        UniqueConstraint("category_id", "characteristic_id", name="uq_category_characteristic"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

                                                      
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )

                                               
    characteristic_id: Mapped[int] = mapped_column(
        ForeignKey("characteristics.id", ondelete="CASCADE"),
        nullable=False,
    )

                                              
    category = relationship("Category", back_populates="characteristics_links")

                                                               
    characteristic = relationship("GlobalCharacteristic", back_populates="category_links")

