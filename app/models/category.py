import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # slug — уникальное имя для URL. Например:
    # "ventilation", "facade", ...

    # Родительская категория (если это подкатегория).
    # Если parent_id = NULL — это категория верхнего уровня.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=True,
    )

    # отношение "один ко многим" — категория -> товары
    products = relationship("Product", back_populates="category")

    # Родительская категория (Category -> Category)
    parent = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )

    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Дочерние категории (подкатегории)
    children = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    # категория -> настройки характеристик для этой категории
    characteristics_links = relationship(
        "CategoryCharacteristic",
        back_populates="category",
        cascade="all, delete-orphan",
    )
