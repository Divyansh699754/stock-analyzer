"""
Scheduler — APScheduler for local cron mode.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def start_scheduler(config, run_fn) -> None:
    """
    Start the blocking scheduler that runs the analysis daily.

    Args:
        config: Config instance with schedule_time
        run_fn: Callable to run (no args) — typically a wrapped run_analysis
    """
    hour, minute = _parse_time(config.schedule_time)
    scheduler = BlockingScheduler()

    # Run Monday–Friday at configured time
    trigger = CronTrigger(
        day_of_week='mon-fri',
        hour=hour,
        minute=minute,
    )

    scheduler.add_job(
        _guarded_run,
        trigger=trigger,
        args=[run_fn],
        id='daily_analysis',
        name='Daily Stock Analysis',
    )

    logger.info(f'Scheduler started — will run at {hour:02d}:{minute:02d} Mon-Fri')
    logger.info('Press Ctrl+C to stop.')

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Scheduler stopped.')


def _guarded_run(run_fn) -> None:
    """Run the analysis with error handling."""
    try:
        logger.info(f'Scheduled run started at {datetime.now().strftime("%H:%M:%S")}')
        run_fn()
        logger.info('Scheduled run completed.')
    except Exception as e:
        logger.error(f'Scheduled run failed: {e}', exc_info=True)


def _parse_time(time_str: str) -> tuple:
    """Parse 'HH:MM' into (hour, minute)."""
    parts = time_str.strip().split(':')
    return int(parts[0]), int(parts[1])
