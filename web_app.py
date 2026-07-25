"""
Mobile-Responsive Web Application Server for Bulk Business Search & Export Pro.
Runs an HTTP server delivering a mobile-first responsive web interface for smartphones, tablets, and desktop browsers.
"""

import os
import sys
import json
import queue
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import initialize_database
from settings import AppSettings
from search_engine import SearchEngine
from exporter import Exporter
from config import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT, WORKSPACE_DIR

# Global shared state for Web App
PROGRESS_QUEUE = queue.Queue()
SEARCH_ENGINE = SearchEngine(PROGRESS_QUEUE)
WEB_RESULTS = []
CURRENT_STATUS = {"status": "Ready", "message": "Engine initialized", "is_running": False, "grid_processed": 0, "grid_total": 0, "found": 0, "progress": 0.0}

def queue_poller_thread():
    """Background thread polling progress queue from SearchEngine."""
    global WEB_RESULTS, CURRENT_STATUS
    while True:
        try:
            data = PROGRESS_QUEUE.get(timeout=0.5)
            status = data.get("status")
            msg = data.get("message", "")
            
            CURRENT_STATUS["status"] = status.capitalize() if status else "Ready"
            CURRENT_STATUS["message"] = msg
            
            if status in ["started", "geocoding", "grid", "running", "details", "business_found"]:
                CURRENT_STATUS["is_running"] = True
            
            grid_total = data.get("grid_total", 0)
            grid_proc = data.get("grid_processed", 0)
            found = data.get("found", 0)
            proc = data.get("processed", 0)
            
            CURRENT_STATUS["grid_total"] = grid_total
            CURRENT_STATUS["grid_processed"] = grid_proc
            CURRENT_STATUS["found"] = found
            
            if status == "details" and found > 0:
                CURRENT_STATUS["progress"] = proc / found
            elif grid_total > 0:
                CURRENT_STATUS["progress"] = grid_proc / grid_total

            if status == "business_found":
                biz = data.get("data")
                if biz:
                    # Normalize key fields for web UI rendering
                    if "type" not in biz or not biz["type"]:
                        b_types = biz.get("business_types", [])
                        biz["type"] = ", ".join([t.title() for t in b_types]) if isinstance(b_types, list) and b_types else "General"
                    if "status" not in biz or not biz["status"]:
                        b_status = str(biz.get("business_status", "OPERATIONAL")).upper()
                        biz["status"] = "Active" if "CLOSED" not in b_status else ("Temporarily Closed" if "TEMPORARILY" in b_status else "Permanently Closed")
                    if "city" not in biz or not biz["city"]:
                        biz["city"] = data.get("city") or CURRENT_STATUS.get("city") or ""

                    existing_ids = {item.get("place_id") for item in WEB_RESULTS}
                    if biz.get("place_id") not in existing_ids:
                        WEB_RESULTS.append(biz)
            
            elif status in ["finished", "stopped", "error"]:
                CURRENT_STATUS["is_running"] = False
                CURRENT_STATUS["status"] = "Ready" if status != "error" else "Error"
                
            PROGRESS_QUEUE.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            time.sleep(0.5)

class WebAppRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving static files and API endpoints."""

    def log_message(self, format, *args):
        # Silence routine HTTP access logging in stdout
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "File Not Found")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Static assets
        web_dir = Path(WORKSPACE_DIR) / "web"
        if path == "/" or path == "/index.html":
            return self._send_file(web_dir / "index.html", "text/html")
        elif path == "/style.css":
            return self._send_file(web_dir / "style.css", "text/css")
        elif path == "/app.js":
            return self._send_file(web_dir / "app.js", "application/javascript")

        # API Endpoints
        elif path == "/api/stats":
            ratings = [b["rating"] for b in WEB_RESULTS if b.get("rating")]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            with_website = sum(1 for b in WEB_RESULTS if b.get("website"))
            with_phone = sum(1 for b in WEB_RESULTS if b.get("phone_number"))

            return self._send_json({
                "total_businesses": len(WEB_RESULTS),
                "avg_rating": avg_rating,
                "with_website": with_website,
                "with_phone": with_phone,
                "export_folder": AppSettings.get_export_folder()
            })

        elif path == "/api/results":
            return self._send_json({"businesses": WEB_RESULTS})

        elif path == "/api/search/status":
            return self._send_json(CURRENT_STATUS)

        elif path == "/api/export":
            query = parse_qs(parsed.query)
            fmt = query.get("format", ["xlsx"])[0].lower()
            
            export_dir = Path(WORKSPACE_DIR) / "data" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")

            if fmt == "xlsx":
                filepath = export_dir / f"Web_Export_{timestamp}.xlsx"
                Exporter.export_to_excel(WEB_RESULTS, str(filepath))
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif fmt == "csv":
                filepath = export_dir / f"Web_Export_{timestamp}.csv"
                Exporter.export_to_csv(WEB_RESULTS, str(filepath))
                content_type = "text/csv"
            else:
                filepath = export_dir / f"Web_Export_{timestamp}.json"
                Exporter.export_to_json(WEB_RESULTS, str(filepath))
                content_type = "application/json"

            if os.path.exists(filepath):
                filename = os.path.basename(filepath)
                with open(filepath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(500, "Export failed")

        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            body = {}

        if path == "/api/search/start":
            cities = body.get("cities", [])
            keywords = body.get("keywords", [])
            radius = body.get("radius", 2000)

            if not cities or not keywords:
                return self._send_json({"error": "Cities and keywords required"}, status=400)

            WEB_RESULTS.clear()
            SEARCH_ENGINE.start_bulk_search(cities, keywords, radius)
            CURRENT_STATUS["is_running"] = True
            return self._send_json({"message": "Search started"})

        elif path == "/api/search/stop":
            SEARCH_ENGINE.stop()
            CURRENT_STATUS["is_running"] = False
            return self._send_json({"message": "Search stopping"})

        elif path == "/api/results/clear":
            WEB_RESULTS.clear()
            return self._send_json({"message": "Results cleared"})

        elif path == "/api/settings":
            if "api_key" in body:
                AppSettings.set_api_key(body["api_key"])
            if "export_folder" in body:
                AppSettings.set_export_folder(body["export_folder"])
            if "search_radius" in body:
                AppSettings.set_search_radius(body["search_radius"])
            if "request_delay" in body:
                AppSettings.set_request_delay(body["request_delay"])
            if "headless" in body:
                AppSettings.set_headless(body["headless"])

            return self._send_json({"message": "Settings saved"})

        else:
            self.send_error(404, "Endpoint Not Found")

def run_web_server(host=None, port=None):
    """Starts the HTTPServer and queue listener."""
    if host is None:
        host = os.environ.get("HOST", DEFAULT_WEB_HOST)
    if port is None:
        port = int(os.environ.get("PORT", DEFAULT_WEB_PORT))

    initialize_database()

    poller = threading.Thread(target=queue_poller_thread, daemon=True)
    poller.start()

    server = HTTPServer((host, port), WebAppRequestHandler)
    print(f"\n=======================================================")
    print(f" Bulk Business Pro - Mobile Responsive Web Server")
    print(f" Access on local device:  http://localhost:{port}")
    print(f" Access on mobile/network: http://<Your-IP>:{port}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
        server.server_close()

if __name__ == "__main__":
    run_web_server()
