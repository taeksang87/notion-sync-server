
from flask import Flask
import subprocess

app = Flask(__name__)

@app.route("/sync", methods=["GET"])
def sync():
    try:
        subprocess.Popen(["python", "notion_gcal_sync_both_clean.py"])
        return "✅ Sync started", 200
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

@app.route("/", methods=["GET"])
def health():
    return "🟢 Notion sync server running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
