
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

import models
import schemas
from database import Base, engine, get_db

from datetime import date, datetime, time, timedelta
from sqlalchemy import func
from sqlalchemy.orm import joinedload


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="E-Commerce Order Processing API",
    description="Manage products, shopping carts, stock and orders.",
    version="1.0.0"
)


# ---------------- PRODUCT MANAGEMENT ----------------

@app.post("/products", response_model=schemas.ProductResponse, status_code=201)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db)
):
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@app.get("/products", response_model=list[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()


@app.get("/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(
        models.Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@app.put("/products/{product_id}", response_model=schemas.ProductResponse)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    db: Session = Depends(get_db)
):
    product = db.query(models.Product).filter(
        models.Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(
        models.Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Keep order history even if the product is deleted.
    db.query(models.OrderItem).filter(
        models.OrderItem.product_id == product_id
    ).update({"product_id": None}, synchronize_session=False)

    # Do not delete products currently present in shopping carts.
    in_cart = db.query(models.CartItem).filter(
        models.CartItem.product_id == product_id
    ).first()

    if in_cart:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Remove this product from carts before deleting it"
        )

    db.delete(product)
    db.commit()
    return {"message": "Product deleted successfully"}


# ---------------- CART HELPERS ----------------

def get_or_create_cart(user_id: int, db: Session):
    cart = db.query(models.Cart).filter(
        models.Cart.user_id == user_id
    ).first()

    if not cart:
        cart = models.Cart(user_id=user_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)

    return cart


def build_cart_response(cart):
    items = []
    total = 0.0

    for item in cart.items:
        subtotal = round(item.product.price * item.quantity, 2)
        total += subtotal

        items.append({
            "product_id": item.product.id,
            "product_name": item.product.name,
            "price": item.product.price,
            "quantity": item.quantity,
            "subtotal": subtotal
        })

    return {
        "user_id": cart.user_id,
        "items": items,
        "total_amount": round(total, 2)
    }


# ---------------- CART MANAGEMENT ----------------

@app.post("/cart/{user_id}/items", response_model=schemas.CartResponse)
def add_to_cart(
    user_id: int,
    data: schemas.CartItemCreate,
    db: Session = Depends(get_db)
):
    product = db.query(models.Product).filter(
        models.Product.id == data.product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = get_or_create_cart(user_id, db)

    item = db.query(models.CartItem).filter(
        models.CartItem.cart_id == cart.id,
        models.CartItem.product_id == data.product_id
    ).first()

    new_quantity = data.quantity + (item.quantity if item else 0)

    if new_quantity > product.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock_quantity} items are in stock"
        )

    if item:
        item.quantity = new_quantity
    else:
        db.add(models.CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=data.quantity
        ))

    db.commit()

    cart = db.query(models.Cart).options(
        joinedload(models.Cart.items).joinedload(models.CartItem.product)
    ).filter(models.Cart.id == cart.id).first()

    return build_cart_response(cart)


@app.get("/cart/{user_id}", response_model=schemas.CartResponse)
def view_cart(user_id: int, db: Session = Depends(get_db)):
    cart = db.query(models.Cart).options(
        joinedload(models.Cart.items).joinedload(models.CartItem.product)
    ).filter(models.Cart.user_id == user_id).first()

    if not cart:
        return {"user_id": user_id, "items": [], "total_amount": 0.0}

    return build_cart_response(cart)


@app.put(
    "/cart/{user_id}/items/{product_id}",
    response_model=schemas.CartResponse
)
def update_cart_quantity(
    user_id: int,
    product_id: int,
    data: schemas.CartItemUpdate,
    db: Session = Depends(get_db)
):
    cart = db.query(models.Cart).filter(
        models.Cart.user_id == user_id
    ).first()

    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    item = db.query(models.CartItem).filter(
        models.CartItem.cart_id == cart.id,
        models.CartItem.product_id == product_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if data.quantity > item.product.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {item.product.stock_quantity} items are in stock"
        )

    item.quantity = data.quantity
    db.commit()

    cart = db.query(models.Cart).options(
        joinedload(models.Cart.items).joinedload(models.CartItem.product)
    ).filter(models.Cart.id == cart.id).first()

    return build_cart_response(cart)


@app.delete("/cart/{user_id}/items/{product_id}")
def remove_from_cart(
    user_id: int,
    product_id: int,
    db: Session = Depends(get_db)
):
    cart = db.query(models.Cart).filter(
        models.Cart.user_id == user_id
    ).first()

    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    item = db.query(models.CartItem).filter(
        models.CartItem.cart_id == cart.id,
        models.CartItem.product_id == product_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(item)
    db.commit()
    return {"message": "Product removed from cart"}


@app.delete("/cart/{user_id}")
def clear_cart(user_id: int, db: Session = Depends(get_db)):
    cart = db.query(models.Cart).filter(
        models.Cart.user_id == user_id
    ).first()

    if not cart:
        return {"message": "Cart is already empty"}

    db.query(models.CartItem).filter(
        models.CartItem.cart_id == cart.id
    ).delete(synchronize_session=False)

    db.commit()
    return {"message": "Cart cleared successfully"}


# ---------------- ORDER CREATION ----------------

@app.post("/orders/{user_id}", response_model=schemas.OrderResponse, status_code=201)
def create_order(user_id: int, db: Session = Depends(get_db)):
    cart = db.query(models.Cart).options(
        joinedload(models.Cart.items).joinedload(models.CartItem.product)
    ).filter(models.Cart.user_id == user_id).first()

    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Validate every item before changing stock.
    for item in cart.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="Invalid quantity")

        if item.quantity > item.product.stock_quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {item.product.name}. "
                       f"Available: {item.product.stock_quantity}"
            )

    try:
        order = models.Order(
            user_id=user_id,
            total_amount=0,
            status="Placed"
        )
        db.add(order)
        db.flush()

        total = 0.0

        for item in cart.items:
            product = item.product
            subtotal = round(product.price * item.quantity, 2)
            total += subtotal

            order_item = models.OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=item.quantity,
                subtotal=subtotal
            )
            db.add(order_item)

            product.stock_quantity -= item.quantity

        order.total_amount = round(total, 2)

        # Remove cart items only after all order items are created.
        db.query(models.CartItem).filter(
            models.CartItem.cart_id == cart.id
        ).delete(synchronize_session=False)

        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Order could not be processed. No changes were saved."
        )

    result = db.query(models.Order).options(
        joinedload(models.Order.items)
    ).filter(models.Order.id == order.id).first()

    return result


# ---------------- ORDER HISTORY ----------------

@app.get(
    "/orders/my-orders",
    response_model=list[schemas.OrderHistoryItem]
)
def get_my_orders(
    user_id: int,
    db: Session = Depends(get_db)
):
    orders = db.query(models.Order).options(
        joinedload(models.Order.payment)
    ).filter(
        models.Order.user_id == user_id
    ).order_by(
        models.Order.created_at.desc()
    ).all()

    return [
        {
            "order_id": order.id,
            "order_date": order.created_at,
            "total_amount": order.total_amount,
            "order_status": order.status,
            "payment_status": (
                order.payment.payment_status
                if order.payment else "Not Initiated"
            )
        }
        for order in orders
    ]



# ---------------- ORDER SEARCH AND FILTERING ----------------

@app.get("/orders", response_model=list[schemas.OrderResponse])
def filter_orders(
    status: str | None = None,
    payment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    db: Session = Depends(get_db)
):
    if min_amount is not None and min_amount < 0:
        raise HTTPException(
            status_code=400,
            detail="Minimum amount cannot be negative"
        )

    if max_amount is not None and max_amount < 0:
        raise HTTPException(
            status_code=400,
            detail="Maximum amount cannot be negative"
        )

    if (
        min_amount is not None
        and max_amount is not None
        and min_amount > max_amount
    ):
        raise HTTPException(
            status_code=400,
            detail="Minimum amount cannot exceed maximum amount"
        )

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after end date"
        )

    query = db.query(models.Order).options(
        joinedload(models.Order.items)
    )

    if payment_status:
        query = query.join(
            models.Payment,
            models.Payment.order_id == models.Order.id
        ).filter(
            models.Payment.payment_status == payment_status
        )

    if status:
        query = query.filter(models.Order.status == status)

    if start_date:
        query = query.filter(
            models.Order.created_at >= datetime.combine(
                start_date, time.min
            )
        )

    if end_date:
        query = query.filter(
            models.Order.created_at < datetime.combine(
                end_date + timedelta(days=1), time.min
            )
        )

    if min_amount is not None:
        query = query.filter(
            models.Order.total_amount >= min_amount
        )

    if max_amount is not None:
        query = query.filter(
            models.Order.total_amount <= max_amount
        )

    return query.order_by(models.Order.id.desc()).all()



# ---------------- VIEW ORDERS ----------------

@app.get("/orders/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).options(
        joinedload(models.Order.items)
    ).filter(models.Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@app.get("/users/{user_id}/orders", response_model=list[schemas.OrderResponse])
def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Order).options(
        joinedload(models.Order.items)
    ).filter(
        models.Order.user_id == user_id
    ).order_by(models.Order.id.desc()).all()
    
    



# ---------------- ORDER STATUS WORKFLOW ----------------

ALLOWED_TRANSITIONS = {
    "Pending": ["Confirmed", "Cancelled"],
    "Confirmed": ["Shipped", "Cancelled"],
    "Shipped": ["Delivered", "Cancelled"],
    "Delivered": [],
    "Cancelled": []
}


@app.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).options(
        joinedload(models.Order.items)
    ).filter(models.Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    new_status = data.status

    if new_status not in ALLOWED_TRANSITIONS[order.status]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change order status from "
                   f"{order.status} to {new_status}"
        )

    # Restore stock exactly once when the order is cancelled.
    if new_status == "Cancelled":
        for item in order.items:
            if item.product_id is not None:
                product = db.query(models.Product).filter(
                    models.Product.id == item.product_id
                ).first()

                if product:
                    product.stock_quantity += item.quantity

   
    old_status = order.status
    order.status = new_status

    try:
       db.commit()
       db.refresh(order)
    except Exception:
       db.rollback()
       raise HTTPException(
             status_code=500,
             detail="Could not update order status"
    )

    return {
     "message": "Order status updated successfully",
     "order_id": order.id,
     "old_status": old_status,
     "status": order.status
}



# ---------------- PAYMENT SIMULATION ----------------

@app.post(
    "/payments/{order_id}",
    response_model=schemas.PaymentResponse,
    status_code=201
)
def create_payment(
    order_id: int,
    data: schemas.PaymentCreate,
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(
        models.Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status == "Cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cannot pay for a cancelled order"
        )

    existing_payment = db.query(models.Payment).filter(
        models.Payment.order_id == order_id
    ).first()

    if existing_payment:
        raise HTTPException(
            status_code=409,
            detail="Payment already exists for this order"
        )

    if data.simulate_failure:
        payment_status = "Failed"
    elif data.payment_method == "Cash on Delivery":
        payment_status = "Pending"
    else:
        payment_status = "Successful"

    payment = models.Payment(
        order_id=order.id,
        amount=order.total_amount,
        payment_method=data.payment_method,
        payment_status=payment_status
    )

    try:
        db.add(payment)
        db.commit()
        db.refresh(payment)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Payment could not be processed"
        )

    return payment



# ---------------- SALES REPORT ----------------

@app.get("/reports/sales", response_model=schemas.SalesReport)
def sales_report(db: Session = Depends(get_db)):

    total_orders = db.query(
        func.count(models.Order.id)
    ).scalar() or 0

    total_cancelled_orders = db.query(
        func.count(models.Order.id)
    ).filter(
        models.Order.status == "Cancelled"
    ).scalar() or 0

    total_sales_amount = db.query(
        func.sum(models.Order.total_amount)
    ).filter(
        models.Order.status != "Cancelled"
    ).scalar() or 0

    total_successful_payments = db.query(
        func.count(models.Payment.id)
    ).filter(
        models.Payment.payment_status == "Successful"
    ).scalar() or 0

    total_products_sold = db.query(
        func.sum(models.OrderItem.quantity)
    ).join(
        models.Order,
        models.Order.id == models.OrderItem.order_id
    ).filter(
        models.Order.status != "Cancelled"
    ).scalar() or 0

    best_seller = db.query(
        models.OrderItem.product_name,
        func.sum(models.OrderItem.quantity).label("quantity_sold")
    ).join(
        models.Order,
        models.Order.id == models.OrderItem.order_id
    ).filter(
        models.Order.status != "Cancelled"
    ).group_by(
        models.OrderItem.product_name
    ).order_by(
        func.sum(models.OrderItem.quantity).desc()
    ).first()

    return {
        "total_orders": total_orders,
        "total_sales_amount": round(float(total_sales_amount), 2),
        "total_cancelled_orders": total_cancelled_orders,
        "total_successful_payments": total_successful_payments,
        "best_selling_product": (
            best_seller[0] if best_seller else None
        ),
        "total_products_sold": int(total_products_sold)
    }




@app.get("/")
def home():
    return {"message": "E-Commerce Order Processing API is running"}
