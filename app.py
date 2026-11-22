import math
import os
import socket
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)

MONGO_URL = os.environ.get("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is required")

mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
database = mongo_client.get_default_database()
if database is None:
    raise RuntimeError("MONGO_URL must include a database name, e.g. mongodb://host:27017/emi_db")
calculations = database["calculations"]


def serving_identity():
    pod_name = os.environ.get("HOSTNAME") or socket.gethostname()
    pod_ip = os.environ.get("POD_IP")
    if not pod_ip:
        try:
            pod_ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            pod_ip = "unknown"
    return {"name": pod_name, "ip": pod_ip}


def positive_number(value, field_name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return number


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/emi")
def calculate_emi():
    data = request.get_json(silent=True) or {}
    try:
        principal = positive_number(data.get("principal"), "Loan amount")
        annual_rate = positive_number(data.get("rate"), "Annual interest rate")
        months_value = positive_number(data.get("months"), "Tenure")
        if not months_value.is_integer():
            raise ValueError("Tenure must be a whole number of months")
        months = int(months_value)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    monthly_rate = annual_rate / 12 / 100
    factor = (1 + monthly_rate) ** months
    emi = principal * monthly_rate * factor / (factor - 1)
    total_payment = emi * months
    total_interest = total_payment - principal
    served_by = serving_identity()

    document = {
        "principal": principal,
        "rate": annual_rate,
        "months": months,
        "emi": emi,
        "servedBy": served_by,
        "createdAt": datetime.now(timezone.utc),
    }
    try:
        calculations.insert_one(document)
    except PyMongoError:
        return jsonify({"error": "Unable to save calculation because MongoDB is unavailable"}), 503

    return jsonify({
        "emi": round(emi, 2),
        "totalPayment": round(total_payment, 2),
        "totalInterest": round(total_interest, 2),
        "servedBy": served_by,
    })


@app.get("/api/history")
def history():
    try:
        records = calculations.find({}, {"_id": 0}).sort("createdAt", -1).limit(10)
        result = []
        for item in records:
            created_at = item.get("createdAt")
            item["createdAt"] = created_at.isoformat() if created_at else None
            result.append(item)
        return jsonify(result)
    except PyMongoError:
        return jsonify({"error": "Unable to retrieve calculation history from MongoDB"}), 503


@app.get("/api/health")
@app.get("/health")
def health():
    try:
        mongo_client.admin.command("ping")
        return jsonify({"status": "ok", "mongodb": "reachable"}), 200
    except PyMongoError:
        return jsonify({"status": "error", "mongodb": "unreachable"}), 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
