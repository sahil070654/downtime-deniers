import time
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from db import SessionLocal, Payment, init_db
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
CORS(app)
init_db()

REQUEST_COUNT = Counter("payment_service_requests_total", "Total requests", ["endpoint", "status"])
REQUEST_LATENCY = Histogram("payment_service_request_latency_seconds", "Request latency", ["endpoint"])
PAYMENT_ERRORS = Counter("payment_service_errors_total", "Total payment errors")

@app.route("/health")
def health():
    return jsonify(status="UP"), 200

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route("/pay", methods=["POST"])
def pay():
    start = time.time()
    data = request.json
    db = SessionLocal()
    try:
        amount = data.get("amount")
        if not amount or amount <= 0:
            REQUEST_COUNT.labels("/pay", "400").inc()
            PAYMENT_ERRORS.inc()
            return jsonify(error="invalid amount"), 400

        payment = Payment(order_id=data.get("orderId"), amount=amount, status="SUCCESS")
        db.add(payment)
        db.commit()
        REQUEST_COUNT.labels("/pay", "200").inc()
        return jsonify(payment_id=payment.id, status="SUCCESS"), 200
    except Exception as e:
        db.rollback()
        REQUEST_COUNT.labels("/pay", "500").inc()
        PAYMENT_ERRORS.inc()
        return jsonify(error=str(e)), 500
    finally:
        db.close()
        REQUEST_LATENCY.labels("/pay").observe(time.time() - start)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083)
