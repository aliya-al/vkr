import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.utils.database import Base

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
                                              
                                  

                                                     
                                                            
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=True,
    )

                                                      
    products = relationship("Product", back_populates="category")

                                                   
    parent = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )

    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

                                       
    children = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

                                                             
    characteristics_links = relationship(
        "CategoryCharacteristic",
        back_populates="category",
        cascade="all, delete-orphan",
    )
