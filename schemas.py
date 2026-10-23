
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    stock_quantity: int = Field(ge=0)
    description: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    price: float | None = Field(default=None, gt=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    description: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    price: float
    stock_quantity: int
    description: str | None
    created_at: datetime


class CartItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartItemResponse(BaseModel):
    product_id: int
    product_name: str
    price: float
    quantity: int
    subtotal: float


class CartResponse(BaseModel):
    user_id: int
    items: list[CartItemResponse]
    total_amount: float


class OrderItemResponse(BaseModel):
    product_id: int | None
    product_name: str
    price: float
    quantity: int
    subtotal: float


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    created_at: datetime
    items: list[OrderItemResponse]




class OrderStatusUpdate(BaseModel):
    status: Literal[
        "Pending",
        "Confirmed",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]


class PaymentCreate(BaseModel):
    payment_method: Literal[
        "UPI",
        "Card",
        "Net Banking",
        "Cash on Delivery"
    ]
    simulate_failure: bool = False


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    amount: float
    payment_method: str
    payment_status: str
    payment_date: datetime


class OrderHistoryItem(BaseModel):
    order_id: int
    order_date: datetime
    total_amount: float
    order_status: str
    payment_status: str


class SalesReport(BaseModel):
    total_orders: int
    total_sales_amount: float
    total_cancelled_orders: int
    total_successful_payments: int
    best_selling_product: str | None
    total_products_sold: int
