"""
Bi-Monthly Server Scheduler Daemon

This script runs the FMCG pipeline automatically every 15 days.
It is designed to be run in the background on a server (e.g., via `nohup` or `tmux`).
Command to start: nohup python scheduler.py &
"""

import time
import schedule
import subprocess
import logging
from datetime import datetime

# Set up basic logging for the scheduler daemon
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Scheduler")

def run_pipeline():
    """Runs the FMCG pipeline in live mode."""
    logger.info("⏰ Starting scheduled Bi-Monthly Pipeline Run...")
    try:
        # Run the main pipeline script as a subprocess
        result = subprocess.run(
            ["python", "main.py", "--source", "live"],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info("✅ Pipeline finished successfully! Dashboard files are updated.")
        
        # Log the last few lines summarizing the run
        summary_lines = result.stdout.strip().split('\n')[-20:]
        for line in summary_lines:
            if "PIPELINE SUMMARY" in line or "TOP 3 DEALS" in line or line.startswith("  "):
                logger.info(f"   {line}")
                
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Pipeline failed with exit code {e.returncode}")
        logger.error(e.stderr)

def start_daemon():
    logger.info("🚀 FMCG Scheduler Daemon Started.")
    logger.info("📅 Job configured to run every 15 days.")
    
    # Schedule the job to run every 15 days
    schedule.every(15).days.do(run_pipeline)
    
    # Infinite loop to keep the daemon alive
    # Sleep to save CPU (checking schedule once an hour is plenty for a 15-day job)
    logger.info("⏳ Waiting for the first scheduled run...")
    while True:
        schedule.run_pending()
        time.sleep(3600)

if __name__ == "__main__":
    start_daemon()
