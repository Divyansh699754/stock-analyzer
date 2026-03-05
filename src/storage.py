"""
Storage — save daily analyses as JSON and Markdown reports.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
DATA_DIR = _ROOT / 'data' / 'analyses'
REPORT_DIR = _ROOT / 'reports'


def save_daily_report(results: list, market_review: str = None,
                      retention_days: int = 30) -> None:
    """Save today's analysis as JSON and Markdown."""
    today = datetime.now().strftime('%Y-%m-%d')

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = DATA_DIR / f'{today}.json'
    json_data = []
    for r in results:
        entry = {
            'symbol': r['symbol'],
            'name': r['name'],
            'market': r['market'],
            'indicators': r['indicators'],
            'news': r.get('news', []),
            'analysis': {k: v for k, v in r['analysis'].items() if k != 'raw'},
        }
        json_data.append(entry)

    json_path.write_text(
        json.dumps({'date': today, 'market_review': market_review, 'stocks': json_data},
                   indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    logger.info(f'Saved JSON report: {json_path}')

    # Save Markdown
    md_path = REPORT_DIR / f'{today}.md'
    md_lines = [f'# Daily Stock Analysis — {today}\n']

    if market_review:
        md_lines.append('## Market Overview\n')
        md_lines.append(f'```\n{market_review}\n```\n')

    md_lines.append('## Stock Analysis\n')
    for r in results:
        a = r['analysis']
        md_lines.append(f'### {a["signal_emoji"]} {r["symbol"]} — {r["name"]}\n')
        md_lines.append(f'- **Signal**: {a["signal"]} (Score: {a["score"]})')
        md_lines.append(f'- **Conclusion**: {a["core_conclusion"]}')
        if a.get('entry_price'):
            md_lines.append(f'- **Entry**: {a["entry_price"]} | '
                          f'**Stop**: {a["stop_loss"]} | '
                          f'**Target**: {a["target_price"]}')
        if a['checklist']:
            md_lines.append('- **Checklist**:')
            for c in a['checklist']:
                md_lines.append(f'  - {c["status"]} {c["item"]}')
        if a['risk_factors']:
            md_lines.append('- **Risk Factors**:')
            for risk in a['risk_factors']:
                md_lines.append(f'  - {risk}')
        md_lines.append('')

    md_lines.append('---\n*Not financial advice. Educational only.*\n')
    md_path.write_text('\n'.join(md_lines), encoding='utf-8')
    logger.info(f'Saved Markdown report: {md_path}')

    # Cleanup old files
    _cleanup_old_files(DATA_DIR, retention_days)
    _cleanup_old_files(REPORT_DIR, retention_days)


def _cleanup_old_files(directory: Path, retention_days: int) -> None:
    """Delete files older than retention_days."""
    cutoff = datetime.now() - timedelta(days=retention_days)

    for f in directory.iterdir():
        if not f.is_file():
            continue
        # Try to parse date from filename
        try:
            date_str = f.stem[:10]  # YYYY-MM-DD
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
            if file_date < cutoff:
                f.unlink()
                logger.debug(f'Deleted old file: {f}')
        except (ValueError, IndexError):
            pass
