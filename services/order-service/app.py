import os
import time
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from db import SessionLocal, Order, init_db
from circuit_breaker import CircuitBreaker
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8083")

app = Flask(__name__)
CORS(app)
init_db()
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=15)

REQUEST_COUNT = Counter("order_service_requests_total", "Total requests", ["endpoint", "status"])
REQUEST_LATENCY = Histogram("order_service_request_latency_seconds", "Request latency", ["endpoint"])
CIRCUIT_STATE = Gauge("order_service_circuit_breaker_state", "0=closed 1=open 2=half-open")

def call_payment_service(order_id, amount, max_retries=3):
    if not breaker.allow_request():
        return None, "circuit_open"

    delay = 0.5
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.post(
                f"{PAYMENT_SERVICE_URL}/pay",
                json={"orderId": order_id, "amount": amount},
                timeout=3,
            )
            if res.status_code == 200:
                breaker.record_success()
                return res.json(), None
            raise Exception(f"payment service returned {res.status_code}")
        except Exception as e:
            if attempt == max_retries:
                breaker.record_failure()
                return None, str(e)
            time.sleep(delay)
            delay *= 2
    return None, "unknown_error"

def _state_to_int(s):
    return {"closed": 0, "open": 1, "half-open": 2}.get(s, 0)

@app.route("/health")
def health():
    CIRCUIT_STATE.set(_state_to_int(breaker.get_state()))
    return jsonify(status="UP", circuit_breaker_state=breaker.get_state()), 200

@app.route("/metrics")
def metrics():
    CIRCUIT_STATE.set(_state_to_int(breaker.get_state()))
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route("/api/orders", methods=["POST"])
def create_order():
    start = time.time()
    data = request.json
    db = SessionLocal()
    try:
        order = Order(
            user_id=data["userId"],
            item_name=data["itemName"],
            quantity=data["quantity"],
            amount=data["amount"],
            status="PENDING",
        )
        db.add(order)
        db.commit()

        payment_result, error = call_payment_service(order.id, data["amount"])

        if payment_result:
            order.status = "COMPLETED"
            order.payment_id = payment_result.get("payment_id")
            db.commit()
            REQUEST_COUNT.labels("/api/orders", "201").inc()
            return jsonify(status="COMPLETED", paymentId=order.payment_id), 201
        else:
            order.status = "FAILED"
            db.commit()
            REQUEST_COUNT.labels("/api/orders", "502").inc()
            return jsonify(status="FAILED", error=error), 502
    except Exception as e:
        db.rollback()
        REQUEST_COUNT.labels("/api/orders", "400").inc()
        return jsonify(error=str(e)), 400
    finally:
        db.close()
        REQUEST_LATENCY.labels("/api/orders").observe(time.time() - start)

@app.route("/api/orders", methods=["GET"])
def list_orders():
    user_id = request.args.get("userId")
    db = SessionLocal()
    try:
        query = db.query(Order)
        if user_id:
            query = query.filter_by(user_id=user_id)
        orders = query.all()
        return jsonify([
            {
                "id": o.id,
                "itemName": o.item_name,
                "quantity": o.quantity,
                "amount": float(o.amount),
                "status": o.status,
            }
            for o in orders
        ]), 200
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082)
