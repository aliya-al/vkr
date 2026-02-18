import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, func, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

class OrderStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"
    canceled = "canceled"

class DeliveryType(str, enum.Enum):
    delivery = "delivery"
    pickup = "pickup"

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_type: Mapped[DeliveryType] = mapped_column(
        Enum(DeliveryType),
        nullable=False,
    )

                                    
    delivery_address: Mapped[str | None] = mapped_column(String, nullable=True)
                                                       
    pickup_address: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.new,
    )

    total_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

                                                                                     
    total_weight_kg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
                                                                            
    total_volume_m3: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True)

    manager = relationship("AdminUser", back_populates="orders")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
