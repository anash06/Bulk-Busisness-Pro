import os
import sys
import queue
import time
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import initialize_database
from settings import AppSettings
from search_engine import SearchEngine
from exporter import Exporter

def main():
    # Make sure settings exist
    initialize_database()
    
    # Check arguments or prompt user
    if len(sys.argv) >= 4:
        city = sys.argv[1]
        keyword = sys.argv[2]
        try:
            radius = int(sys.argv[3])
        except ValueError:
            print("Radius must be an integer (meters).")
            return
    else:
        print("--- Bulk Business Search CLI Tool ---")
        city = input("Enter City Name (e.g. Springfield, IL): ").strip()
        keyword = input("Enter Keyword/Category (e.g. cafe): ").strip()
        radius_str = input("Enter Search Radius in meters (default 5000): ").strip()
        radius = int(radius_str) if radius_str.isdigit() else 5000

    if not city or not keyword:
        print("City and keyword cannot be empty.")
        return

    # Force headless browser for CLI execution
    AppSettings.set_headless(True)

    print(f"\n[INFO] Starting search for '{keyword}' in '{city}' within a {radius}m radius...")
    
    progress_queue = queue.Queue()
    engine = SearchEngine(progress_queue)
    
    # Start search thread
    engine.start_bulk_search([city], [keyword], radius)
    
    results = []
    
    try:
        while True:
            try:
                data = progress_queue.get_nowait()
                status = data.get("status")
                msg = data.get("message")
                
                if status == "business_found":
                    biz = data.get("data")
                    if biz:
                        # Prevent duplicate
                        if not any(item.get("place_id") == biz.get("place_id") for item in results):
                            results.append(biz)
                            print(f" -> Found: {biz.get('name')} | Phone: {biz.get('phone_number') or 'N/A'} | Website: {biz.get('website') or 'N/A'} | Rating: {biz.get('rating') or 'N/A'}")
                
                elif status in ["finished", "stopped"]:
                    print(f"\n[INFO] Search completed. Total businesses found: {len(results)}")
                    break
                elif status == "error":
                    print(f"[ERROR] {msg}")
                    break
                else:
                    # Update messages
                    if msg:
                        print(f"[{status.upper()}] {msg}")
                        
                progress_queue.task_done()
            except queue.Empty:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping search engine...")
        engine.stop()
        
    if results:
        # Export
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        export_path = export_dir / f"CLI_Export_{timestamp}.xlsx"
        
        print(f"\n[INFO] Exporting {len(results)} records to styled Excel workbook...")
        success = Exporter.export_to_excel(results, str(export_path.resolve()))
        if success:
            print(f"[SUCCESS] Exported successfully to: {export_path.resolve()}")
        else:
            print("[ERROR] Export to Excel failed.")
    else:
        print("\n[INFO] No businesses were found.")

if __name__ == "__main__":
    main()
