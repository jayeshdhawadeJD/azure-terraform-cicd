import os
from flask import Flask
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

app = Flask(__name__)

ACCOUNT_NAME = "stportfoliodemo01"
CONTAINER_NAME = "demo-list"

def get_latest_cost_data():
    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=credential,
    )
    container = blob_service.get_container_client(CONTAINER_NAME)

    cost_blobs = [b for b in container.list_blobs() if b.name.startswith("cost-data-")]
    if not cost_blobs:
        return "<p>No cost data found.</p>"

    latest = max(cost_blobs, key=lambda b: b.name)
    blob_client = container.get_blob_client(latest.name)
    data = blob_client.download_blob().readall().decode("utf-8")

    return f"<p>Latest file: {latest.name}</p><pre>{data}</pre>"

@app.route("/")
def home():
    return (
        "<h1>Azure Cost Dashboard</h1>"
        + get_latest_cost_data()
    )

if __name__ == "__main__":
    DefaultAzureCredential()
    app.run(host="0.0.0.0", port=5000)