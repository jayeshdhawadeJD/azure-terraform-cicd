import json
from flask import Flask, render_template
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

app = Flask(__name__)

ACCOUNT_NAME = "stportfoliodemo01"
CONTAINER_NAME = "demo-list"

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
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)