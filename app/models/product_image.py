import uuid
from sqlalchemy import String, ForeignKey, Boolean, Column, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )                                                                                    
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    product = relationship("Product", back_populates="images")
    is_main = Column(Boolean, nullable=False, default=False, server_default="false")

                                            
    __table_args__ = (
        Index(
            "ux_product_images_one_main_per_product",
            "product_id",
            unique=True,
            postgresql_where=(is_main.is_(True)),
        ),
    )
