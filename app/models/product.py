import uuid
from sqlalchemy import String, Integer, Boolean, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

                                          
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
                                          
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id"),
        nullable=True,
    )

    price: Mapped[int] = mapped_column(Integer, nullable=False)

                                            
                                              
    volume_m3: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)                                    
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
                                                       

    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan",
                          order_by="(ProductImage.is_main.desc(), ProductImage.id.asc())")
                                                        
    characteristics_values = relationship(
        "ProductCharacteristicValue",
        back_populates="product",
        cascade="all, delete-orphan",
    )



