from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.scrapers.runner import run_full_scrape

scheduler = BackgroundScheduler()


def _weekly_scrape():
    print("Scheduled scrape starting...")
    db = SessionLocal()
    try:
        run_full_scrape(db)
    except Exception as exc:
        print(f"Scheduled scrape failed: {exc}")
    finally:
        db.close()


def start():
    scheduler.add_job(_weekly_scrape, "interval", weeks=1, id="weekly_scrape", replace_existing=True)
    scheduler.start()
    print("Scheduler started: scraping weekly")


def stop():
    scheduler.shutdown(wait=False)
