import hmac
import json
import logging
import os
import time

import requests
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ACCOUNT_NAME = "stportfoliodemo01"
CONTAINER_NAME = "demo-list"

CONTAINER_APP_NAME = "ca-portfolio-flask"
RESOURCE_GROUP = "rg-portfolio-demo"
SUBSCRIPTION_ID = "bb8f8c0b-6d1b-4593-882b-d9f264692833"
MANAGEMENT_API_VERSION = "2023-05-01"

PIN = os.environ.get("APP_PIN", "")

FAIL_LIMIT = 5
FAIL_WINDOW_SECONDS = 600
_failures = {}

RESOURCE_TYPE_LABELS = {
    "storageaccounts": "Storage account",
    "containerapps": "Container app",
    "managedenvironments": "Container Apps environment",
    "virtualmachines": "Virtual machine",
}


def friendly_resource(resource_id):
    parts = resource_id.rstrip("/").split("/")
    name = parts[-1]
    rtype = parts[-2] if len(parts) > 1 else ""
    label = RESOURCE_TYPE_LABELS.get(rtype, rtype.upper())
    return name, label


def _azure_token():
    return DefaultAzureCredential().get_token("https://management.azure.com/.default").token


def _container_app_url():
    return (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.App/containerApps/{CONTAINER_APP_NAME}"
        f"?api-version={MANAGEMENT_API_VERSION}"
    )


def get_container_app():
    resp = requests.get(
        _container_app_url(),
        headers={"Authorization": f"Bearer {_azure_token()}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_control_state():
    app = get_container_app()
    scale = app["properties"]["template"].get("scale") or {}
    return "stopped" if scale.get("maxReplicas", 0) == 0 else "running"


def set_replicas(min_replicas, max_replicas):
    app = get_container_app()
    template = app["properties"]["template"]
    template.setdefault("scale", {})["minReplicas"] = min_replicas
    template["scale"]["maxReplicas"] = max_replicas

    body = {
        "location": app["location"],
        "identity": app.get("identity"),
        "properties": {
            "managedEnvironmentId": app["properties"]["managedEnvironmentId"],
            "configuration": app["properties"]["configuration"],
            "template": template,
        },
    }
    resp = requests.put(
        _container_app_url(),
        headers={
            "Authorization": f"Bearer {_azure_token()}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _client_locked(ip):
    rec = _failures.get(ip)
    if not rec:
        return False
    if time.time() - rec["first"] > FAIL_WINDOW_SECONDS:
        _failures.pop(ip, None)
        return False
    return rec["count"] >= FAIL_LIMIT


def _record_failure(ip):
    rec = _failures.get(ip)
    now = time.time()
    if rec and now - rec["first"] <= FAIL_WINDOW_SECONDS:
        rec["count"] += 1
    else:
        _failures[ip] = {"count": 1, "first": now}


def _pin_ok(candidate):
    return bool(PIN) and hmac.compare_digest(str(candidate), PIN)


def get_suggestions(latest):
    suggestions = []

    try:
        date_str = latest["filename"].replace("cost-data-", "").replace(".json", "")
        data_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        age_days = (datetime.now(timezone.utc).date() - data_date).days
        if age_days > 1:
            suggestions.append({
                "level": "warning",
                "title": "Cost data may be stale",
                "message": f"Latest data is {age_days} days old ({latest['date']}). Check the Cost Data Pull workflow."
            })
    except ValueError:
        pass

    resources = latest.get("resources", [])
    if not resources:
        return suggestions

    total = sum(r.get("cost", 0) for r in resources)

    top = max(resources, key=lambda r: r.get("cost", 0))
    if total and top.get("cost", 0) / total >= 0.5:
        name, _ = friendly_resource(top.get("resourceId", ""))
        suggestions.append({
            "level": "warning",
            "title": "Largest cost driver: " + name,
            "message": f"{name} accounts for {top['cost']/total:.0%} of total cost. Review if it must run 24/7 or can be right-sized."
        })

    inactive = [friendly_resource(r.get("resourceId", ""))[0] for r in resources if r.get("cost") == 0]
    if inactive:
        suggestions.append({
            "level": "danger",
            "title": "Inactive resources",
            "message": ", ".join(inactive) + " reported zero cost. Consider deleting to avoid future charges."
        })

    if not suggestions:
        suggestions.append({
            "level": "info",
            "title": "Costs look healthy",
            "message": "No major cost concerns detected right now."
        })

    return suggestions


def fetch_all_cost_data():
    credential = DefaultAzureCredential()
    service = BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=credential,
    )
    container = service.get_container_client(CONTAINER_NAME)

    blobs = [b for b in container.list_blobs() if b.name.startswith("cost-data-")]
    blobs.sort(key=lambda b: b.name)

    history = []
    for blob in blobs:
        raw = container.get_blob_client(blob.name).download_blob().readall().decode("utf-8-sig")
        data = json.loads(raw)
        resources = data.get("resources", [])
        history.append({
            "filename": blob.name,
            "date": data.get("date", blob.name),
            "total": sum(r.get("cost", 0) for r in resources),
            "resources": resources,
        })
    return history


@app.route("/")
def dashboard():
    history = fetch_all_cost_data()

    if not history:
        return render_template(
            "index.html",
            empty=True,
            resources=[],
            data_date="—",
            currency="—",
            total_cost="—",
            total_cost_raw=0,
            resource_count=0,
            days_tracked=0,
            trend_labels=[],
            trend_totals=[],
            suggestions=[],
        )

    latest = history[-1]
    resources = latest["resources"]
    currency = resources[0].get("currency", "INR") if resources else "INR"
    symbol = "₹" if currency.upper() == "INR" else f"{currency} "
    total = latest["total"]

    rows = []
    for r in resources:
        name, rtype = friendly_resource(r.get("resourceId", ""))
        cost = r.get("cost", 0)
        share = (cost / total * 100) if total else 0
        rows.append({
            "name": name,
            "type": rtype,
            "cost": cost,
            "cost_display": f"{symbol}{cost:,.4f}",
            "percent": f"{share:.1f}%",
        })
    rows.sort(key=lambda r: r["cost"], reverse=True)

    return render_template(
        "index.html",
        empty=False,
        resources=rows,
        data_date=latest["date"],
        currency=currency,
        total_cost=f"{symbol}{total:,.4f}",
        total_cost_raw=total,
        resource_count=len(rows),
        days_tracked=len(history),
        trend_labels=[h["date"] for h in history],
        trend_totals=[h["total"] for h in history],
        suggestions=get_suggestions(latest),
    )


@app.route("/state")
def control_state():
    try:
        return jsonify(ok=True, state=get_control_state())
    except Exception as exc:
        logging.error("state check failed: %s", exc)
        return jsonify(ok=False, error="Unable to read container app state"), 500


@app.route("/action", methods=["POST"])
def control_action():
    ip = request.remote_addr or "unknown"
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    pin = data.get("pin", "")

    if _client_locked(ip):
        logging.warning("denied (rate limit) ip=%s action=%s", ip, action)
        return jsonify(ok=False, error="Too many failed attempts. Try again in a few minutes."), 429

    if not _pin_ok(pin):
        _record_failure(ip)
        logging.warning("denied (bad pin) ip=%s action=%s", ip, action)
        return jsonify(ok=False, error="Invalid PIN"), 401

    _failures.pop(ip, None)

    targets = {"stop": (0, 0), "start": (1, 10)}
    if action not in targets:
        logging.warning("rejected (unknown action) ip=%s action=%s", ip, action)
        return jsonify(ok=False, error="Unknown action"), 400

    try:
        min_replicas, max_replicas = targets[action]
        set_replicas(min_replicas, max_replicas)
        state = "stopped" if action == "stop" else "running"
        logging.info("success action=%s ip=%s", action, ip)
        return jsonify(ok=True, state=state)
    except Exception as exc:
        logging.error("action failed action=%s ip=%s error=%s", action, ip, exc)
        return jsonify(ok=False, error="Azure update failed: " + str(exc)), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)