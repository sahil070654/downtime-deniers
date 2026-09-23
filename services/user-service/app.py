import time
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from db import SessionLocal, User, init_db
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
CORS(app)
init_db()

REQUEST_COUNT = Counter("user_service_requests_total", "Total requests", ["endpoint", "status"])
REQUEST_LATENCY = Histogram("user_service_request_latency_seconds", "Request latency", ["endpoint"])

@app.route("/health")
def health():
    return jsonify(status="UP"), 200

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route("/register", methods=["POST"])
def register():
    start = time.time()
    data = request.json
    db = SessionLocal()
    try:
        user = User(
            username=data["username"],
            email=data["email"],
            password_hash=generate_password_hash(data["password"]),
        )
        db.add(user)
        db.commit()
        REQUEST_COUNT.labels("/register", "201").inc()
        return jsonify(message="registered", user_id=user.id), 201
    except Exception as e:
        db.rollback()
        REQUEST_COUNT.labels("/register", "400").inc()
        return jsonify(error=str(e)), 400
    finally:
        db.close()
        REQUEST_LATENCY.labels("/register").observe(time.time() - start)

@app.route("/login", methods=["POST"])
def login():
    start = time.time()
    data = request.json
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=data["username"]).first()
        if user and check_password_hash(user.password_hash, data["password"]):
            REQUEST_COUNT.labels("/login", "200").inc()
            return jsonify(message="ok", user_id=user.id, username=user.username), 200
        REQUEST_COUNT.labels("/login", "401").inc()
        return jsonify(error="invalid credentials"), 401
    finally:
        db.close()
        REQUEST_LATENCY.labels("/login").observe(time.time() - start)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
