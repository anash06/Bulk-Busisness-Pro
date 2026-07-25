"""
Main entry point for Bulk Business Search & Export Pro.
"""

import sys
from logger import logger
from database import initialize_database
from gui import BusinessSearchGUI

def main():
    try:
        logger.info("Starting Bulk Business Search & Export Pro application...")
        # 1. Initialize SQLite Database Tables
        initialize_database()
        
        # 2. Check if web flag is passed
        if len(sys.argv) > 1 and sys.argv[1] in ["--web", "-w", "--mobile"]:
            from web_app import run_web_server
            run_web_server()
        else:
            # Launch Desktop GUI Window
            app = BusinessSearchGUI()
            app.mainloop()
        
    except Exception as e:
        logger.critical(f"Application crashed during startup: {e}", exc_info=True)

if __name__ == "__main__":
    main()
