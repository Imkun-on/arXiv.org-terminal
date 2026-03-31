from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import sys
import time
import threading

# Ensure UTF-8 output on Windows terminals
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from concurrent.futures import ThreadPoolExecutor, as_completed

import arxiv
import requests

_sys = sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_sys.path.insert(0, os.path.join(_SCRIPT_DIR, 'Database_Globale'))
import scraper_db

from rich.align import Align
from rich.box import DOUBLE, ROUNDED
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    MofNCompleteColumn, TimeElapsedColumn, TimeRemainingColumn,
    TaskProgressColumn, DownloadColumn, TransferSpeedColumn,
)
from rich.style import Style
from rich.table import Table
from rich.text import Text

from Shared.logger_setup import setup_logger, console, SYM_OK, SYM_FAIL, SYM_ARROW, SYM_DOT

# === SYMBOLS ===
SYM_PAPER = "[accent]\U0001f4c4[/accent]"


def _print_banner() -> None:
    banner_lines = [
        r"                          __  __     _                                      __ _  ",
        r"    o O O  __ _      _ _  \ \/ /    (_)    __ __            ___      _ _   / _` | ",
        r"   o      / _` |    | '_|  >  <     | |    \ V /     _     / _ \    | '_|  \__, | ",
        r"  TS__[O] \__,_|   _|_|_  /_/\_\   _|_|_   _\_/_   _(_)_   \___/   _|_|_   |___/  ",
        r' {======|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""| ',
        r'''./o--000'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-' ''',
    ]
    colors = ["bright_magenta", "magenta", "bright_blue", "blue", "bright_cyan", "cyan"]
    text = Text()
    for i, line in enumerate(banner_lines):
        text.append(line + "\n", style=Style(color=colors[i % len(colors)], bold=True))

    console.print()
    console.print(Panel(
        Align.center(text),
        border_style="bright_blue",
        box=DOUBLE,
        padding=(1, 2),
        expand=False,
    ))


# === CONFIGURATION ===
MAX_SEARCH_RESULTS = 20
MAX_DOWNLOAD_WORKERS = 3
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2
REQUEST_TIMEOUT = 30
MIN_PDF_SIZE = 10 * 1024  # 10 KB min
OUTPUT_DIR = os.path.join(_SCRIPT_DIR, 'Download_Globale', 'download_arxiv')

# === LOGGING ===
log = setup_logger('scraper_arxiv', 'scraper_arxiv.log')

# === GRACEFUL SHUTDOWN ===
_shutdown_event = threading.Event()


def _signal_handler(signum, frame):
    if _shutdown_event.is_set():
        log.warning("Second Ctrl+C - forcing exit")
        os._exit(1)
    log.warning("Ctrl+C received - finishing current work, then stopping...")
    _shutdown_event.set()


# === ARXIV CATEGORIES ===
CATEGORIES = {
    'cs': ('Computer Science', [
        'AI', 'AR', 'CC', 'CE', 'CG', 'CL', 'CR', 'CV', 'CY', 'DB',
        'DC', 'DL', 'DM', 'DS', 'ET', 'FL', 'GL', 'GR', 'GT', 'HC',
        'IR', 'IT', 'LG', 'LO', 'MA', 'MM', 'MS', 'NA', 'NE', 'NI',
        'OH', 'OS', 'PF', 'PL', 'RO', 'SC', 'SD', 'SE', 'SI', 'SY',
    ]),
    'math': ('Mathematics', [
        'AC', 'AG', 'AP', 'AT', 'CA', 'CO', 'CT', 'CV', 'DG', 'DS',
        'FA', 'GM', 'GN', 'GR', 'GT', 'HO', 'IT', 'KT', 'LO', 'MG',
        'MP', 'NA', 'NT', 'OA', 'OC', 'PR', 'QA', 'RA', 'RT', 'SG',
        'SP', 'ST',
    ]),
    'physics': ('Physics', [
        'acc-ph', 'app-ph', 'ao-ph', 'atom-ph', 'atm-clus', 'bio-ph',
        'chem-ph', 'class-ph', 'comp-ph', 'data-an', 'flu-dyn', 'gen-ph',
        'geo-ph', 'hist-ph', 'ins-det', 'med-ph', 'optics', 'ed-ph',
        'soc-ph', 'plasm-ph', 'pop-ph', 'space-ph',
    ]),
    'stat': ('Statistics', ['AP', 'CO', 'ME', 'ML', 'OT', 'TH']),
    'econ': ('Economics', ['EM', 'GN', 'TH']),
    'eess': ('Electrical Eng. & Sys. Science', ['AS', 'IV', 'SP', 'SY']),
    'q-bio': ('Quantitative Biology', [
        'BM', 'CB', 'GN', 'MN', 'NC', 'OT', 'PE', 'QM', 'SC', 'TO',
    ]),
    'q-fin': ('Quantitative Finance', [
        'CP', 'EC', 'GN', 'MF', 'PM', 'PR', 'RM', 'ST', 'TR',
    ]),
    'astro-ph': ('Astrophysics', ['GA', 'CO', 'EP', 'HE', 'IM', 'SR']),
    'cond-mat': ('Condensed Matter', [
        'dis-nn', 'mtrl-sci', 'mes-hall', 'other', 'quant-gas',
        'soft', 'stat-mech', 'str-el', 'supr-con',
    ]),
    'nlin': ('Nonlinear Sciences', ['AO', 'CG', 'CD', 'SI', 'PS']),
    'gr-qc': ('General Relativity & Quantum Cosmology', []),
    'hep-ex': ('High Energy Physics - Experiment', []),
    'hep-lat': ('High Energy Physics - Lattice', []),
    'hep-ph': ('High Energy Physics - Phenomenology', []),
    'hep-th': ('High Energy Physics - Theory', []),
    'math-ph': ('Mathematical Physics', []),
    'nucl-ex': ('Nuclear Experiment', []),
    'nucl-th': ('Nuclear Theory', []),
    'quant-ph': ('Quantum Physics', []),
}

SUBCATEGORY_NAMES = {
    'cs.AI': 'Artificial Intelligence', 'cs.CL': 'Computation & Language',
    'cs.CV': 'Computer Vision', 'cs.LG': 'Machine Learning',
    'cs.CR': 'Cryptography & Security', 'cs.DB': 'Databases',
    'cs.DS': 'Data Structures & Algorithms', 'cs.IR': 'Information Retrieval',
    'cs.NE': 'Neural & Evolutionary Computing', 'cs.RO': 'Robotics',
    'cs.SE': 'Software Engineering', 'cs.PL': 'Programming Languages',
    'cs.DC': 'Distributed Computing', 'cs.SI': 'Social & Info Networks',
    'cs.CG': 'Computational Geometry', 'cs.AR': 'Hardware Architecture',
    'cs.FL': 'Formal Languages', 'cs.GT': 'Computer Science & Game Theory',
    'cs.HC': 'Human-Computer Interaction', 'cs.IT': 'Information Theory',
    'cs.MA': 'Multiagent Systems', 'cs.MM': 'Multimedia',
    'cs.NI': 'Networking & Internet', 'cs.OS': 'Operating Systems',
    'cs.SC': 'Symbolic Computation', 'cs.SD': 'Sound',
    'cs.DL': 'Digital Libraries', 'cs.DM': 'Discrete Mathematics',
    'stat.ML': 'Machine Learning (Statistics)',
    'stat.ME': 'Methodology', 'stat.TH': 'Statistics Theory',
}


# === SEMANTIC SCHOLAR (citations) ===

_S2_API = 'https://api.semanticscholar.org/graph/v1/paper'
_S2_FIELDS = 'title,citationCount,influentialCitationCount'
_citations_cache: dict[str, dict] = {}


def _get_citations(arxiv_id: str) -> dict:
    """Fetch citation count from Semantic Scholar (with cache)."""
    clean_id = re.sub(r'v\d+$', '', arxiv_id)
    if clean_id in _citations_cache:
        return _citations_cache[clean_id]

    try:
        response = requests.get(
            f'{_S2_API}/arXiv:{clean_id}',
            params={'fields': _S2_FIELDS},
            headers={'User-Agent': 'ArxivScraper/1.0'},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            result = {
                'citations': data.get('citationCount', 0),
                'influential': data.get('influentialCitationCount', 0),
            }
            _citations_cache[clean_id] = result
            return result
        elif response.status_code == 429:
            log.debug("Semantic Scholar rate limit, skipping citations")
    except Exception as e:
        log.debug("Citations unavailable for %s: %s", arxiv_id, e)

    return {'citations': 0, 'influential': 0}


def _fetch_citations_batch(results: list[arxiv.Result],
                           on_advance: 'Callable[[], None] | None' = None) -> None:
    """Pre-fetch citations for a list of papers (rate limited 1/sec)."""
    for r in results:
        if _shutdown_event.is_set():
            break
        arxiv_id = _short_id(r.entry_id)
        _get_citations(arxiv_id)
        if on_advance:
            on_advance()
        time.sleep(1)


def _format_citations(citations: int) -> str:
    if citations >= 10000:
        return f"[bold green]{citations:,}[/bold green]"
    elif citations >= 1000:
        return f"[green]{citations:,}[/green]"
    elif citations >= 100:
        return f"[yellow]{citations:,}[/yellow]"
    elif citations > 0:
        return f"{citations}"
    return "[dim]-[/dim]"


# === RELATED PAPERS (Semantic Scholar) ===

def _fetch_related_papers(arxiv_id: str, limit: int = 10) -> list[dict]:
    """Fetch related papers via Semantic Scholar Recommendations API."""
    clean_id = re.sub(r'v\d+$', '', arxiv_id)
    try:
        response = requests.get(
            f'{_S2_API}/arXiv:{clean_id}/recommendations',
            params={'fields': 'title,authors,citationCount,externalIds,year,venue', 'limit': limit},
            headers={'User-Agent': 'ArxivScraper/1.0'},
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            papers = []
            for p in data.get('recommendedPapers', []):
                ext_ids = p.get('externalIds', {}) or {}
                papers.append({
                    'title': p.get('title', 'N/A'),
                    'authors': ', '.join(a.get('name', '') for a in (p.get('authors') or [])[:3]),
                    'citations': p.get('citationCount', 0) or 0,
                    'year': p.get('year', ''),
                    'venue': p.get('venue', '') or '',
                    'arxiv_id': ext_ids.get('ArXiv', ''),
                    'doi': ext_ids.get('DOI', ''),
                })
            return papers
        elif response.status_code == 429:
            log.debug("Semantic Scholar rate limit per related papers")
    except Exception as e:
        log.debug("Error fetching related papers for %s: %s", arxiv_id, e)
    return []


def _display_related_papers(arxiv_id: str) -> None:
    """Display related papers table."""
    with console.status("[info]Loading related papers...[/info]", spinner="dots"):
        related = _fetch_related_papers(arxiv_id)

    if not related:
        console.print("[warning]No related papers found.[/warning]")
        return

    table = Table(
        box=ROUNDED, border_style="bright_magenta",
        header_style="bold bright_cyan", expand=False,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Title", style="white", max_width=55, no_wrap=True)
    table.add_column("Authors", style="bright_magenta", max_width=22, no_wrap=True)
    table.add_column("Year", style="cyan", width=6)
    table.add_column("Venue", style="dim", max_width=20, no_wrap=True)
    table.add_column("Cit.", justify="right", width=8)
    table.add_column("arXiv ID", style="info", width=14)

    for i, p in enumerate(related, 1):
        title_display = p['title'][:52] + "..." if len(p['title']) > 55 else p['title']
        table.add_row(
            str(i),
            title_display,
            p['authors'][:22],
            str(p['year']) if p['year'] else '-',
            p['venue'][:20] if p['venue'] else '-',
            _format_citations(p['citations']),
            p['arxiv_id'] or '-',
        )

    console.print()
    console.print(Panel(
        table,
        title=f"[bold bright_white]Related papers to {arxiv_id}[/bold bright_white]",
        border_style="bright_magenta", box=ROUNDED, expand=False, padding=(1, 1),
    ))


# === LOCAL FULL TEXT SEARCH ===

def _search_local_pdfs(keyword: str, search_dir: str = '') -> list[dict]:
    """Search keyword in locally downloaded PDFs."""
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError:
        return []

    if not search_dir:
        search_dir = OUTPUT_DIR

    if not os.path.isdir(search_dir):
        return []

    results = []
    keyword_lower = keyword.lower()

    # Collect all PDFs
    pdf_files = []
    for root, _dirs, files in os.walk(search_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, f))

    if not pdf_files:
        return []

    for pdf_path in pdf_files:
        try:
            doc = fitz.open(pdf_path)
            matches = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if keyword_lower in text.lower():
                    # Extract context (snippet)
                    idx = text.lower().find(keyword_lower)
                    start = max(0, idx - 80)
                    end = min(len(text), idx + len(keyword) + 80)
                    snippet = text[start:end].replace('\n', ' ').strip()
                    matches.append({'page': page_num + 1, 'snippet': snippet})
            doc.close()

            if matches:
                filename = os.path.basename(pdf_path)
                # Extract arXiv ID from filename
                id_match = re.match(r'(\d{4}\.\d{4,5}(?:v\d+)?)', filename)
                arxiv_id = id_match.group(1) if id_match else ''
                results.append({
                    'file': filename,
                    'path': pdf_path,
                    'arxiv_id': arxiv_id,
                    'matches': matches,
                    'total_matches': len(matches),
                })
        except Exception as e:
            log.debug("Error reading PDF %s: %s", pdf_path, e)

    # Sort by match count
    results.sort(key=lambda x: -x['total_matches'])
    return results


def _display_local_search(keyword: str) -> None:
    """Execute and display local full-text search results."""
    try:
        import fitz  # noqa: F401 - PyMuPDF
    except ModuleNotFoundError:
        console.print("[error]PyMuPDF is required for PDF search.[/error]\n"
                      "[dim]Install with: pip install PyMuPDF[/dim]")
        return

    pdf_count = 0
    for root, _dirs, files in os.walk(OUTPUT_DIR):
        pdf_count += sum(1 for f in files if f.lower().endswith('.pdf'))

    if pdf_count == 0:
        console.print("[warning]No PDFs downloaded. Download some papers first.[/warning]")
        return

    with Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold bright_cyan]{task.description}"),
        BarColumn(bar_width=30, style="dim", complete_style="bright_cyan", finished_style="bright_green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task(f"Searching {pdf_count} PDFs...", total=pdf_count)

        # Search with progress
        import fitz
        results = []
        keyword_lower = keyword.lower()

        pdf_files = []
        for root, _dirs, files in os.walk(OUTPUT_DIR):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, f))

        for pdf_path in pdf_files:
            try:
                doc = fitz.open(pdf_path)
                matches = []
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    text = page.get_text()
                    if keyword_lower in text.lower():
                        idx = text.lower().find(keyword_lower)
                        start = max(0, idx - 80)
                        end = min(len(text), idx + len(keyword) + 80)
                        snippet = text[start:end].replace('\n', ' ').strip()
                        matches.append({'page': page_num + 1, 'snippet': snippet})
                doc.close()

                if matches:
                    filename = os.path.basename(pdf_path)
                    id_match = re.match(r'(\d{4}\.\d{4,5}(?:v\d+)?)', filename)
                    arxiv_id = id_match.group(1) if id_match else ''
                    results.append({
                        'file': filename,
                        'path': pdf_path,
                        'arxiv_id': arxiv_id,
                        'matches': matches,
                        'total_matches': len(matches),
                    })
            except Exception as e:
                log.debug("Error searching PDF %s: %s", pdf_path, e)
            progress.advance(task_id)

        progress.update(task_id, description="Search complete!")

    if not results:
        console.print(f"[warning]No matches for \"{keyword}\" in local PDFs.[/warning]")
        return

    results.sort(key=lambda x: -x['total_matches'])

    # Results table
    table = Table(
        box=ROUNDED, border_style="bright_green",
        header_style="bold bright_cyan", expand=False,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("arXiv ID", style="info", width=14)
    table.add_column("File", style="white", max_width=45, no_wrap=True)
    table.add_column("Matches", justify="right", style="bold bright_green", width=11)
    table.add_column("Pages", style="cyan", max_width=20, no_wrap=True)

    total_matches = 0
    for i, r in enumerate(results[:20], 1):
        pages = sorted(set(m['page'] for m in r['matches']))
        pages_str = ', '.join(str(p) for p in pages[:8])
        if len(pages) > 8:
            pages_str += f" +{len(pages) - 8}"
        total_matches += r['total_matches']
        table.add_row(
            str(i),
            r['arxiv_id'] or '-',
            r['file'][:45],
            str(r['total_matches']),
            pages_str,
        )

    console.print()
    console.print(Panel(
        table,
        title=f"[bold bright_white]Full-text search: \"{keyword}\"[/bold bright_white]",
        subtitle=f"[dim]{len(results)} PDFs with matches \u00b7 {total_matches} total matches \u00b7 {pdf_count} PDFs scanned[/dim]",
        border_style="bright_green", box=ROUNDED, expand=False, padding=(1, 1),
    ))

    # Show snippet from top result
    if results:
        best = results[0]
        snippet_lines = []
        for m in best['matches'][:3]:
            # Highlight keyword in snippet
            snip = m['snippet']
            highlighted = re.sub(
                re.escape(keyword), f"[bold bright_yellow]{keyword}[/bold bright_yellow]",
                snip, flags=re.IGNORECASE,
            )
            snippet_lines.append(f"  [dim]p.{m['page']}:[/dim] ...{highlighted}...")

        console.print(Panel(
            '\n'.join(snippet_lines),
            title=f"[bold bright_white]Preview: {best['arxiv_id'] or best['file'][:30]}[/bold bright_white]",
            border_style="dim", box=ROUNDED, expand=False, padding=(1, 2),
        ))


# === TODAY'S PAPERS ===

_RSS_CATEGORIES = [
    ('cs', 'Computer Science'),
    ('math', 'Mathematics'),
    ('stat', 'Statistics'),
    ('eess', 'Electrical Eng.'),
    ('physics', 'Physics'),
    ('astro-ph', 'Astrophysics'),
    ('cond-mat', 'Condensed Matter'),
    ('quant-ph', 'Quantum Physics'),
    ('hep-th', 'HEP Theory'),
    ('gr-qc', 'Gen. Relativity'),
    ('econ', 'Economics'),
    ('q-bio', 'Quant. Biology'),
    ('q-fin', 'Quant. Finance'),
]


def _fetch_single_rss(code: str, name: str) -> dict:
    """Count today's announced papers for a category using RSS feed (lightweight)."""
    import xml.etree.ElementTree as ET
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'arxiv': 'http://arxiv.org/schemas/atom'}

    result = {'code': code, 'name': name, 'new': 0, 'updated': 0, 'subcats': {}}
    try:
        r = requests.get(
            f'https://rss.arxiv.org/atom/{code}',
            timeout=10,
            headers={'User-Agent': 'ArxivScraper/1.0'},
        )
        if r.status_code != 200:
            return result

        root = ET.fromstring(r.text)
        for entry in root.findall('atom:entry', ns):
            # New vs updated: title in feed contains "(UPDATED)" if updated
            title_el = entry.find('atom:title', ns)
            title_text = title_el.text.strip() if title_el is not None else ''
            if 'UPDATED' in title_text.upper():
                result['updated'] += 1
            else:
                result['new'] += 1

            # Subcategories
            for cat in entry.findall('atom:category', ns):
                term = cat.get('term', '')
                if term:
                    result['subcats'][term] = result['subcats'].get(term, 0) + 1
    except Exception as e:
        log.warning("Error fetching today's stats (%s): %s", code, e)
    return result


def _fetch_today_stats() -> list[dict]:
    """Fetch today's announced papers for all categories (in parallel via RSS)."""
    stats = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_single_rss, code, name): code
                   for code, name in _RSS_CATEGORIES}
        for future in as_completed(futures):
            try:
                stats.append(future.result())
            except Exception:
                pass
    return stats


def _display_today_stats() -> None:
    """Display panel with today's submitted papers."""
    with console.status("[info]Loading today's papers...[/info]", spinner="dots"):
        stats = _fetch_today_stats()

    total_new = sum(s['new'] for s in stats)
    total_upd = sum(s['updated'] for s in stats)
    total = total_new + total_upd

    if total == 0:
        console.print("[dim]No data available for today.[/dim]")
        return

    from datetime import datetime
    today = datetime.now().strftime('%d/%m/%Y')

    # Main table
    table = Table(
        box=ROUNDED, border_style="bright_blue",
        header_style="bold bright_cyan",
        expand=False, show_footer=True,
    )
    table.add_column("Category", style="cyan", footer_style="bold bright_white")
    table.add_column("Name", style="white", footer_style="bold bright_white")
    table.add_column("New", justify="right", style="bold green", footer_style="bold bright_green")
    table.add_column("Updated", justify="right", style="dim yellow", footer_style="dim yellow")
    table.add_column("Total", justify="right", style="bold", footer_style="bold bright_green")
    table.add_column("Subcategories", max_width=65, no_wrap=True)

    _sub_colors = ["bright_cyan", "bright_magenta", "bright_yellow"]

    for s in sorted(stats, key=lambda x: -(x['new'] + x['updated'])):
        count = s['new'] + s['updated']
        if count == 0:
            continue

        # Top 3 subcategories
        top_subs = sorted(s['subcats'].items(), key=lambda x: -x[1])[:3]
        if top_subs:
            parts = []
            for j, (k, v) in enumerate(top_subs):
                c = _sub_colors[j % len(_sub_colors)]
                parts.append(f"[{c}]{k}[/{c}][dim]({v})[/dim]")
            sub_str = '  '.join(parts)
        else:
            sub_str = '-'

        if count >= 500:
            total_str = f"[bold bright_green]{count}[/bold bright_green]"
        elif count >= 100:
            total_str = f"[green]{count}[/green]"
        elif count >= 50:
            total_str = f"[yellow]{count}[/yellow]"
        else:
            total_str = str(count)

        table.add_row(
            s['code'], s['name'],
            str(s['new']), str(s['updated']),
            total_str, sub_str,
        )

    table.columns[0].footer = "TOTAL"
    table.columns[1].footer = ""
    table.columns[2].footer = f"{total_new:,}"
    table.columns[3].footer = f"{total_upd:,}"
    table.columns[4].footer = f"{total:,}"
    table.columns[5].footer = ""

    console.print()
    console.print(Panel(
        table,
        title=f"[bold bright_white]\U0001f4ca Papers announced today ({today})[/bold bright_white]",
        subtitle="[dim]Latest arXiv daily announcement[/dim]",
        border_style="bright_blue", box=DOUBLE, expand=False, padding=(1, 2),
    ))


# === UTILITIES ===

def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()[:200]


def _extract_pages(comment: str | None) -> str:
    if not comment:
        return ''
    match = re.search(r'(\d+)\s*pages?', comment, re.IGNORECASE)
    return match.group(1) if match else ''


def _short_id(entry_id: str) -> str:
    """Extract short ID from arxiv URL (e.g. '2107.05580v1')."""
    match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', entry_id)
    if match:
        return match.group(1)
    # Old format (e.g. 'cond-mat/0011267v1')
    match = re.search(r'([\w-]+/\d+(?:v\d+)?)', entry_id)
    return match.group(1) if match else entry_id.split('/')[-1]


def _format_date(dt) -> str:
    if dt:
        return dt.strftime('%Y-%m-%d')
    return '?'


def _format_size(bytes_val: int | float) -> str:
    if bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    return f"{bytes_val / 1024:.1f} KB"


# === SEARCH ===

def _is_arxiv_id(query: str) -> bool:
    """Check if query is an arXiv ID (e.g. 1706.03762 or cs/0101010)."""
    return bool(re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', query.strip()) or
                re.match(r'^[\w-]+/\d+(v\d+)?$', query.strip()))


def search_papers(query: str, category: str = '', max_results: int = MAX_SEARCH_RESULTS,
                  sort_by: str = 'relevance',
                  on_progress: 'Callable[[str, int, int], None] | None' = None,
                  ) -> list[arxiv.Result]:
    """Search papers on arXiv with smart search.

    Strategy:
    1. If query is an arXiv ID -> search by direct ID
    2. If query looks like a title (>3 words) -> search by title first (ti:)
    3. If few results -> fallback to global search (all:)

    on_progress(description, current_step, total_steps) is called at each phase.
    """
    def _progress(desc: str, step: int, total: int):
        if on_progress:
            on_progress(desc, step, total)

    client = arxiv.Client(page_size=max_results, delay_seconds=5.0, num_retries=5)

    sort_map = {
        'relevance': arxiv.SortCriterion.Relevance,
        'date': arxiv.SortCriterion.SubmittedDate,
        'updated': arxiv.SortCriterion.LastUpdatedDate,
    }
    sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)

    # 1) Search by direct ID
    if _is_arxiv_id(query):
        _progress("Searching by arXiv ID...", 1, 1)
        log.info("Search by ID: %s", query)
        search = arxiv.Search(id_list=[query.strip()])
        results = list(client.results(search))
        if results:
            log.info("Found paper by ID: %s", results[0].title[:60])
            return results

    # 2) Check if query uses an explicit prefix
    _KNOWN_PREFIXES = ('au:', 'ti:', 'abs:', 'all:', 'cat:', 'co:', 'jr:', 'doi:')
    has_prefix = any(query.startswith(p) for p in _KNOWN_PREFIXES)

    # If user specified a prefix, respect their choice
    if has_prefix:
        _progress("Searching arXiv...", 1, 1)
        if category:
            full_query = f"cat:{category} AND {query}"
        else:
            full_query = query
        log.info("Search with prefix: '%s'", full_query)
        search = arxiv.Search(query=full_query, max_results=max_results,
                              sort_by=sort_criterion, sort_order=arxiv.SortOrder.Descending)
        results = list(client.results(search))
        log.info("Found %d papers", len(results))
        return results

    # 2b) Build automatic query
    words = query.split()
    is_title_search = len(words) >= 3

    results = []
    total_steps = 3 if is_title_search else 1

    # 2a) If it looks like a title, search by exact title first
    if is_title_search:
        _progress("Exact title search...", 1, total_steps)
        if category:
            title_query = f'cat:{category} AND ti:"{query}"'
        else:
            title_query = f'ti:"{query}"'
        log.info("Title search: '%s'", title_query)

        search = arxiv.Search(query=title_query, max_results=max_results,
                              sort_by=sort_criterion, sort_order=arxiv.SortOrder.Descending)
        results = list(client.results(search))

        if results:
            log.info("Found %d papers by title", len(results))
            return results

        # 2b) Title without quotes (more flexible, AND between keywords)
        _progress("Flexible title search...", 2, total_steps)
        time.sleep(3)
        ti_parts = ' AND '.join(f'ti:{w}' for w in words)
        if category:
            title_query = f'cat:{category} AND {ti_parts}'
        else:
            title_query = ti_parts
        log.info("Flexible title search: '%s'", title_query)

        search = arxiv.Search(query=title_query, max_results=max_results,
                              sort_by=sort_criterion, sort_order=arxiv.SortOrder.Descending)
        results = list(client.results(search))

        if results:
            log.info("Found %d papers by title (flexible)", len(results))
            return results

        time.sleep(3)

    # 3) Fallback: global search (AND between keywords)
    step_now = total_steps
    _progress("Global arXiv search...", step_now, total_steps)
    # Join keywords with AND to find papers containing all of them
    kw_parts = [f'all:{w}' for w in words] if words else []
    kw_query = ' AND '.join(kw_parts) if kw_parts else query
    if category:
        full_query = f"cat:{category} AND {kw_query}" if query else f"cat:{category}"
    else:
        full_query = kw_query

    log.info("Global search: '%s'", full_query)
    search = arxiv.Search(query=full_query, max_results=max_results,
                          sort_by=sort_criterion, sort_order=arxiv.SortOrder.Descending)
    results = list(client.results(search))
    log.info("Found %d papers", len(results))
    return results


# === DISPLAY ===

def _display_results(results: list[arxiv.Result]) -> None:
    # Pre-fetch citations from Semantic Scholar
    with Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold bright_cyan]{task.description}"),
        BarColumn(bar_width=30, style="dim", complete_style="bright_cyan", finished_style="bright_green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as cit_progress:
        cit_task = cit_progress.add_task("Loading citations...", total=len(results))
        _fetch_citations_batch(results,
                               on_advance=lambda: cit_progress.advance(cit_task))
        cit_progress.update(cit_task, description="Citations loaded!")

    table = Table(
        title=f"Results ({len(results)})",
        box=ROUNDED, border_style="bright_blue",
        header_style="bold bright_cyan", row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Title", style="white", max_width=55, no_wrap=True)
    table.add_column("Authors", style="bright_magenta", max_width=22, no_wrap=True)
    table.add_column("Cat.", style="cyan", width=10)
    table.add_column("Date", style="dim", width=10)
    table.add_column("Cit.", justify="right", width=8)
    table.add_column("Pages", style="dim", justify="right", width=5)

    for i, r in enumerate(results, 1):
        authors = ', '.join(a.name for a in r.authors[:2])
        if len(r.authors) > 2:
            authors += f' +{len(r.authors) - 2}'
        pages = _extract_pages(r.comment)
        arxiv_id = _short_id(r.entry_id)
        cit = _get_citations(arxiv_id)
        title_display = r.title[:52] + "..." if len(r.title) > 55 else r.title
        table.add_row(
            str(i),
            title_display,
            authors[:22],
            r.primary_category,
            _format_date(r.published),
            _format_citations(cit['citations']),
            pages or '-',
        )

    console.print()
    console.print(table)


def _display_paper_details(r: arxiv.Result) -> None:
    lines = []
    lines.append(f"[bold bright_white]{r.title}[/bold bright_white]")
    lines.append("")

    # Authors
    authors = ', '.join(a.name for a in r.authors)
    lines.append(f"[bright_magenta]Authors:[/bright_magenta] {authors}")

    # Categories
    cat_parts = [f"[cyan]{r.primary_category}[/cyan]"]
    if r.categories:
        other_cats = [c for c in r.categories if c != r.primary_category]
        if other_cats:
            cat_parts.extend(f"[bright_blue]{c}[/bright_blue]" for c in other_cats)
    lines.append(f"[dim_label]Categories:[/dim_label]   {', '.join(cat_parts)}")

    # Date
    date_str = f"[dim_label]Published:[/dim_label]  [bold]{_format_date(r.published)}[/bold]"
    if r.updated and r.updated != r.published:
        date_str += f"  [dim]|[/dim]  [dim_label]Updated:[/dim_label] {_format_date(r.updated)}"
    lines.append(date_str)

    # Identifiers
    arxiv_id = _short_id(r.entry_id)
    lines.append(f"[dim_label]arXiv ID:[/dim_label]    [info]{arxiv_id}[/info]")
    if r.doi:
        lines.append(f"[dim_label]DOI:[/dim_label]         [info]{r.doi}[/info]")

    # Journal / Publication
    if r.journal_ref:
        lines.append(f"[dim_label]Journal:[/dim_label]     [bright_yellow]{r.journal_ref}[/bright_yellow]")

    # Author comments (pages, conference, etc.)
    if r.comment:
        lines.append(f"[dim_label]Comments:[/dim_label]    {r.comment}")

    # Links
    lines.append(f"[dim_label]PDF:[/dim_label]         [info]{r.pdf_url}[/info]")
    lines.append(f"[dim_label]Page:[/dim_label]      [info]{r.entry_id}[/info]")

    # Citations from Semantic Scholar
    cit = _get_citations(arxiv_id)
    if cit['citations'] > 0:
        lines.append(
            f"[dim_label]Citations:[/dim_label]   {_format_citations(cit['citations'])}  "
            f"[dim](influential: {cit['influential']})[/dim]"
        )

    # Abstract
    lines.append("")
    lines.append("[dim_label]Abstract:[/dim_label]")
    lines.append(f"[dim]{r.summary}[/dim]")

    console.print()
    console.print(Panel(
        '\n'.join(lines),
        title="[bold bright_white]Paper Details[/bold bright_white]",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 3),
    ))


# === DOWNLOAD ===

def _is_already_downloaded(arxiv_id: str, output_dir: str) -> str | None:
    """Check if the PDF is already downloaded."""
    safe_id = _sanitize_filename(arxiv_id)
    if not os.path.isdir(output_dir):
        return None
    for f in os.listdir(output_dir):
        if safe_id in f and f.lower().endswith('.pdf'):
            full = os.path.join(output_dir, f)
            if os.path.getsize(full) > MIN_PDF_SIZE:
                return full
    return None


def _download_latex_source(arxiv_id: str, safe_title: str, output_dir: str) -> bool:
    """Download LaTeX source (.tar.gz) of a paper."""
    clean_id = re.sub(r'v\d+$', '', arxiv_id)
    src_url = f"https://arxiv.org/src/{clean_id}"
    src_filename = f"{_sanitize_filename(arxiv_id)}_{safe_title}.tar.gz"
    src_filepath = os.path.join(output_dir, src_filename)

    if os.path.isfile(src_filepath) and os.path.getsize(src_filepath) > 1024:
        log.debug("[%s] LaTeX source already present", arxiv_id)
        return True

    try:
        response = requests.get(src_url, stream=True, timeout=REQUEST_TIMEOUT,
                                 headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            with open(src_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            fsize = os.path.getsize(src_filepath)
            if fsize > 1024:
                log.info("  %s LaTeX source: %s (%s)", SYM_OK, arxiv_id, _format_size(fsize))
                return True
            os.remove(src_filepath)
        else:
            log.debug("[%s] LaTeX source not available (HTTP %d)", arxiv_id, response.status_code)
    except Exception as e:
        log.debug("[%s] LaTeX download error: %s", arxiv_id, e)
        if os.path.exists(src_filepath):
            os.remove(src_filepath)
    return False


def download_paper(result: arxiv.Result, output_dir: str,
                   progress: Progress | None = None,
                   task_id=None, download_latex: bool = False) -> dict:
    """Download a single paper (PDF + optionally LaTeX source)."""
    arxiv_id = _short_id(result.entry_id)
    title = result.title
    info = {
        'id': arxiv_id, 'title': title, 'status': 'fail',
        'file': '', 'error': '', 'size': 0,
    }

    if _shutdown_event.is_set():
        info['error'] = 'shutdown'
        return info

    # Skip if already downloaded
    existing = _is_already_downloaded(arxiv_id, output_dir)
    if existing:
        log.info("Already downloaded: %s", arxiv_id)
        info['status'] = 'skip'
        info['file'] = os.path.basename(existing)
        info['size'] = os.path.getsize(existing)
        if progress and task_id is not None:
            progress.update(task_id, completed=1, total=1)
        return info

    os.makedirs(output_dir, exist_ok=True)

    # Filename: ID_Title.pdf
    safe_title = _sanitize_filename(title)[:100]
    filename = f"{_sanitize_filename(arxiv_id)}_{safe_title}.pdf"
    filepath = os.path.join(output_dir, filename)

    for attempt in range(1, MAX_RETRIES + 1):
        if _shutdown_event.is_set():
            info['error'] = 'shutdown'
            return info

        try:
            pdf_url = result.pdf_url
            log.debug("[%s] Download PDF: %s", arxiv_id, pdf_url)

            response = requests.get(pdf_url, stream=True, timeout=REQUEST_TIMEOUT,
                                     headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()

            total_size = int(response.headers.get('Content-Length', 0))
            if progress and task_id is not None and total_size:
                progress.update(task_id, total=total_size)

            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if _shutdown_event.is_set():
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, completed=downloaded)

            fsize = os.path.getsize(filepath)
            if fsize >= MIN_PDF_SIZE:
                info['status'] = 'ok'
                info['file'] = filename
                info['size'] = fsize
                log.info("%s Downloaded: %s (%s)", SYM_OK, arxiv_id, _format_size(fsize))

                # Download LaTeX source (optional)
                if download_latex:
                    _download_latex_source(arxiv_id, safe_title, output_dir)

                # Record metadata in database
                authors = ', '.join(a.name for a in result.authors)
                # Extra metadata in collection_id field (compact JSON)
                import json as _json
                extra_meta = {
                    'categories': result.categories or [],
                    'doi': result.doi or '',
                    'journal': result.journal_ref or '',
                    'comment': result.comment or '',
                    'updated': result.updated.isoformat() if result.updated else '',
                    'published': result.published.isoformat() if result.published else '',
                    'pdf_url': result.pdf_url or '',
                }
                scraper_db.record_audio_download(
                    source_id=arxiv_id,
                    title=title,
                    source_url=result.entry_id,
                    file_path=filepath,
                    file_size_bytes=fsize,
                    collection_name=result.primary_category,
                    collection_id=_json.dumps(extra_meta, ensure_ascii=False),
                    artist=authors,
                    duration_secs=0,
                    audio_format='pdf+latex' if download_latex else 'pdf',
                    track_number=0,
                )
                return info
            else:
                log.warning("[%s] PDF too small (%s)", arxiv_id, _format_size(fsize))
                os.remove(filepath)

        except Exception as e:
            log.warning("[%s] Attempt %d/%d failed: %s", arxiv_id, attempt, MAX_RETRIES, e)
            info['error'] = str(e)[:100]
            if os.path.exists(filepath):
                os.remove(filepath)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * attempt)

    log.error("%s Failed: %s - %s", SYM_FAIL, arxiv_id, info['error'])
    return info


def download_batch(results: list[arxiv.Result], output_dir: str,
                   max_workers: int = MAX_DOWNLOAD_WORKERS,
                   download_latex: bool = False) -> list[dict]:
    """Download multiple papers in parallel."""
    os.makedirs(output_dir, exist_ok=True)
    total = len(results)
    dl_results = []

    dl_label = "Download PDF + LaTeX" if download_latex else "Download PDF"
    console.print()
    console.rule(f"[phase]\u2b07 {dl_label}[/phase]", style="bright_green")
    console.print(f"  [dim_label]Thread:[/dim_label] [info]{max_workers}[/info]  "
                  f"[dim_label]Paper:[/dim_label] [bold]{total}[/bold]\n")

    overall_progress = Progress(
        SpinnerColumn("dots", style="bright_green"),
        TextColumn("[bold bright_green]{task.description}"),
        BarColumn(bar_width=50, style="bar.back", complete_style="bright_green", finished_style="bold green"),
        TaskProgressColumn(), MofNCompleteColumn(),
        TextColumn("[dim]\u2502[/dim]"),
        TimeElapsedColumn(), TextColumn("[dim]\u2192[/dim]"), TimeRemainingColumn(),
        console=console, expand=False,
    )
    file_progress = Progress(
        SpinnerColumn("dots", style="cyan"),
        TextColumn("{task.description}", markup=True),
        BarColumn(bar_width=30, style="bar.back", complete_style="cyan", finished_style="bold cyan"),
        TaskProgressColumn(), DownloadColumn(), TransferSpeedColumn(),
        TextColumn("[dim]\u2192[/dim]"), TimeRemainingColumn(),
        console=console, expand=False,
    )
    overall_task = overall_progress.add_task("Paper", total=total)

    with Live(Group(overall_progress, file_progress), console=console, refresh_per_second=10):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            task_ids = {}

            for i, result in enumerate(results):
                if _shutdown_event.is_set():
                    break
                arxiv_id = _short_id(result.entry_id)
                tid = file_progress.add_task(
                    f"[bold]#{i+1}[/bold] {arxiv_id}",
                    total=None, visible=True,
                )
                task_ids[i] = tid
                future = executor.submit(download_paper, result, output_dir,
                                          progress=file_progress, task_id=tid,
                                          download_latex=download_latex)
                futures[future] = i

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {'id': '?', 'title': '?', 'status': 'fail',
                           'error': str(e)[:100], 'file': '', 'size': 0}
                dl_results.append(res)
                overall_progress.advance(overall_task)

                tid = task_ids.get(idx)
                if tid is not None:
                    try:
                        file_progress.remove_task(tid)
                    except Exception:
                        pass

                if _shutdown_event.is_set():
                    for f in futures:
                        f.cancel()
                    break

    return dl_results


def _display_summary(results: list[dict]) -> None:
    ok = sum(1 for r in results if r['status'] == 'ok')
    fail = sum(1 for r in results if r['status'] == 'fail')
    skip = sum(1 for r in results if r['status'] == 'skip')
    total_size = sum(r.get('size', 0) for r in results)

    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column("Label", style="dim_label")
    table.add_column("Value")

    table.add_row("Total papers", f"[bold]{len(results)}[/bold]")
    table.add_row(f"{SYM_OK} Downloaded", f"[success]{ok}[/success]")
    if skip:
        table.add_row(f"{SYM_DOT} Already present", f"[info]{skip}[/info]")
    if fail:
        table.add_row(f"{SYM_FAIL} Failed", f"[error]{fail}[/error]")
    table.add_row("Total size", f"[bold]{_format_size(total_size)}[/bold]")

    border = "red" if fail else "bright_green"
    icon = "\u274c" if fail else "\u2705"
    console.print()
    console.print(Panel(table, title=f"{icon} Summary", border_style=border,
                        box=DOUBLE, expand=False, padding=(1, 3)))


# === SELECTION ===

def _select_papers(results: list[arxiv.Result]) -> list[arxiv.Result]:
    console.print(
        f"\n[dim_label]Select:[/dim_label] "
        f"single number ([accent]3[/accent]), "
        f"range ([accent]1-5[/accent]), "
        f"multiple ([accent]1,3,7[/accent]), "
        f"[accent]all[/accent] for all, "
        f"[accent]q[/accent] to quit"
    )

    while True:
        choice = console.input("\n[bold]Choose > [/bold]").strip().lower()
        if choice in ('q', 'quit', 'exit'):
            return []
        if choice in ('all', 'a'):
            return results

        selected = []
        try:
            parts = choice.replace(' ', ',').split(',')
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if '-' in part:
                    start, end = part.split('-', 1)
                    for n in range(int(start), int(end) + 1):
                        if 1 <= n <= len(results):
                            selected.append(results[n - 1])
                else:
                    n = int(part)
                    if 1 <= n <= len(results):
                        selected.append(results[n - 1])
            if selected:
                # Remove duplicates
                seen = set()
                unique = []
                for s in selected:
                    sid = s.entry_id
                    if sid not in seen:
                        seen.add(sid)
                        unique.append(s)
                return unique
        except ValueError:
            pass
        console.print("[error]Invalid selection. Try again.[/error]")


# === EXPLORE TODAY'S PAPERS ===

def _fetch_today_papers(category: str) -> list[dict]:
    """Fetch papers submitted today for a category using the arXiv API."""
    from datetime import date

    today_date = date.today()
    date_start = today_date.strftime('%Y%m%d') + '0000'
    date_end = today_date.strftime('%Y%m%d') + '2359'

    papers = []
    try:
        client = arxiv.Client(page_size=200, delay_seconds=5.0, num_retries=5)
        if category:
            query = f'cat:{category} AND submittedDate:[{date_start} TO {date_end}]'
        else:
            query = f'submittedDate:[{date_start} TO {date_end}]'
        search = arxiv.Search(query=query, max_results=500,
                              sort_by=arxiv.SortCriterion.SubmittedDate,
                              sort_order=arxiv.SortOrder.Descending)

        for paper in client.results(search):
            if paper.published.date() != today_date:
                continue

            is_new = not (paper.updated and paper.updated != paper.published)

            papers.append({
                'id': _short_id(paper.entry_id),
                'title': paper.title,
                'authors': [a.name for a in paper.authors],
                'summary': paper.summary or '',
                'categories': paper.categories or [],
                'primary_category': paper.primary_category or category,
                'pdf_url': paper.pdf_url or '',
                'entry_url': paper.entry_id or '',
                'is_new': is_new,
                'date': today_date,
            })
    except Exception as e:
        log.warning("Error fetching today's papers (%s): %s", category, e)

    return papers


def _filter_today_papers(papers: list[dict]) -> list[dict]:
    """Interactive menu to filter today's papers."""
    filt_table = Table(box=ROUNDED, border_style="bright_blue",
                       show_header=True, header_style="bold bright_cyan",
                       expand=False, padding=(0, 2))
    filt_table.add_column("Filter", style="accent", width=20)
    filt_table.add_column("Description", style="white")
    filt_table.add_row("all", "Show all papers")
    filt_table.add_row("new", "New papers only (no updates)")
    filt_table.add_row("sub:cs.LG", "Filter by subcategory")
    filt_table.add_row("key:transformer", "Search keyword in title/abstract")
    filt_table.add_row("au:Hinton", "Search by author")
    filt_table.add_row("top:20", "Show only first N")
    filt_table.add_row("q", "Back to search")

    console.print()
    console.print(Panel(
        filt_table,
        title="[bold bright_white]Filters[/bold bright_white]",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 1),
    ))

    while True:
        filt = console.input(f"\n  [bold]Filter > [/bold]").strip()

        if not filt or filt.lower() in ('q', 'quit', 'exit'):
            return []

        filtered = list(papers)

        if filt.lower() == 'all':
            pass
        elif filt.lower() == 'new':
            filtered = [p for p in filtered if p['is_new']]
        elif filt.lower().startswith('sub:'):
            sub = filt[4:].strip()
            filtered = [p for p in filtered if sub in p['categories']]
        elif filt.lower().startswith('key:'):
            keyword = filt[4:].strip().lower()
            filtered = [p for p in filtered
                        if keyword in p['title'].lower() or keyword in p['summary'].lower()]
        elif filt.lower().startswith('au:'):
            author = filt[3:].strip().lower()
            filtered = [p for p in filtered
                        if any(author in a.lower() for a in p['authors'])]
        elif filt.lower().startswith('top:'):
            try:
                n = int(filt[4:].strip())
                filtered = filtered[:n]
            except ValueError:
                console.print("[error]Invalid number.[/error]")
                continue
        else:
            # Treat as keyword
            keyword = filt.lower()
            filtered = [p for p in filtered
                        if keyword in p['title'].lower() or keyword in p['summary'].lower()]

        if not filtered:
            console.print("[warning]No papers found with this filter.[/warning]")
            continue

        return filtered


def _display_today_papers(papers: list[dict], max_show: int = 30) -> None:
    """Display today's papers table."""
    show = papers[:max_show]

    table = Table(
        title=f"Today's papers ({len(papers)} total{', first ' + str(max_show) if len(papers) > max_show else ''})",
        box=ROUNDED, border_style="bright_blue",
        header_style="bold bright_cyan", row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Title", style="white", max_width=55, no_wrap=True)
    table.add_column("Authors", style="bright_magenta", max_width=22, no_wrap=True)
    table.add_column("Cat.", style="cyan", width=10)
    table.add_column("Date", style="dim", width=10)
    table.add_column("New", justify="center", width=5)

    for i, p in enumerate(show, 1):
        authors = ', '.join(p['authors'][:2])
        if len(p['authors']) > 2:
            authors += f' +{len(p["authors"]) - 2}'
        new_icon = "[green]yes[/green]" if p['is_new'] else "[dim]upd.[/dim]"
        date_str = str(p.get('date', '')) if p.get('date') else '-'
        table.add_row(
            str(i),
            p['title'][:55],
            authors[:22],
            p['primary_category'],
            date_str,
            new_icon,
        )

    console.print()
    console.print(table)


def _today_paper_to_arxiv_result(paper: dict) -> arxiv.Result | None:
    """Convert an RSS paper to arxiv.Result by looking it up via API."""
    if paper['id']:
        try:
            client = arxiv.Client(page_size=1, delay_seconds=5.0, num_retries=3)
            search = arxiv.Search(id_list=[paper['id']])
            results = list(client.results(search))
            if results:
                return results[0]
        except Exception as e:
            log.debug("Failed to fetch arxiv.Result for %s: %s", paper.get('id', '?'), e)
    return None


def _explore_today(category: str) -> None:
    """Explore today's papers for a category (or all if empty)."""
    cat_label = category if category else 'all categories'
    with console.status(f"[info]Loading today's papers for {cat_label}...[/info]", spinner="dots"):
        papers = _fetch_today_papers(category)

    if not papers:
        console.print(f"[warning]No papers found for {cat_label} today.[/warning]")
        return

    new_count = sum(1 for p in papers if p['is_new'])
    upd_count = len(papers) - new_count

    # Show available subcategories
    from collections import Counter
    subcats = Counter()
    for p in papers:
        for c in p['categories']:
            subcats[c] += 1
    top_subs = subcats.most_common(10)

    info_lines = [
        f"[bold bright_white]{cat_label}[/bold bright_white]  "
        f"[green]{new_count} new[/green]  "
        f"[dim yellow]{upd_count} updated[/dim yellow]  "
        f"[bold]{len(papers)} total[/bold]",
    ]
    if top_subs:
        sub_table = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        sub_table.add_column("Cat", style="cyan")
        sub_table.add_column("N", style="bold", justify="right")
        for k, v in top_subs:
            sub_table.add_row(k, str(v))
        info_lines.append("")

    console.print()
    console.print(Panel(
        Group(Text.from_markup(info_lines[0]), sub_table) if top_subs else info_lines[0],
        title=f"[bold bright_white]\U0001f4c4 Today's papers[/bold bright_white]",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 2),
    ))

    filtered = _filter_today_papers(papers)
    if not filtered:
        return

    _display_today_papers(filtered)

    # Selection and download
    console.print(
        f"\n[dim_label]Select papers to download or [accent]d <num>[/accent] for details[/dim_label]"
    )

    while True:
        choice = console.input(f"\n[bold]Choose > [/bold]").strip().lower()
        if not choice or choice in ('q', 'quit'):
            break

        # Paper details
        if choice.startswith('d ') or choice.startswith('d:'):
            try:
                idx = int(choice.split()[1] if ' ' in choice else choice[2:]) - 1
                if 0 <= idx < len(filtered):
                    p = filtered[idx]
                    console.print(Panel(
                        f"[bold bright_white]{p['title']}[/bold bright_white]\n\n"
                        f"[bright_magenta]Authors:[/bright_magenta] {', '.join(p['authors'])}\n"
                        f"[cyan]Categories:[/cyan] {', '.join(p['categories'])}\n"
                        f"ID: [info]{p['id']}[/info]  PDF: [info]{p['pdf_url']}[/info]\n"
                        f"\n[dim]{p['summary'][:500]}{'...' if len(p['summary']) > 500 else ''}[/dim]",
                        title="[bold]Details[/bold]",
                        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 3),
                    ))
                    continue
            except (ValueError, IndexError):
                pass

        # Selection for download
        if choice in ('all', 'a'):
            selected_papers = filtered
        else:
            selected_papers = []
            try:
                parts = choice.replace(' ', ',').split(',')
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if '-' in part:
                        start, end = part.split('-', 1)
                        for n in range(int(start), int(end) + 1):
                            if 1 <= n <= len(filtered):
                                selected_papers.append(filtered[n - 1])
                    else:
                        n = int(part)
                        if 1 <= n <= len(filtered):
                            selected_papers.append(filtered[n - 1])
            except ValueError:
                console.print("[error]Invalid selection.[/error]")
                continue

        if not selected_papers:
            continue

        # Convert to arxiv.Result for download
        console.print(f"\n  {SYM_ARROW} Preparing download of {len(selected_papers)} papers...")
        arxiv_results = []
        for p in selected_papers:
            if p['id']:
                try:
                    client = arxiv.Client(page_size=1, delay_seconds=5.0, num_retries=3)
                    search = arxiv.Search(id_list=[p['id']])
                    r_list = list(client.results(search))
                    if r_list:
                        arxiv_results.append(r_list[0])
                except Exception:
                    log.warning("Paper %s not found via API", p['id'])

        if arxiv_results:
            # Download format
            console.print(
                f"\n  [dim_label]Format:[/dim_label] "
                f"[accent]1[/accent] PDF only  "
                f"[accent]2[/accent] PDF + LaTeX source"
            )
            fmt = console.input("  [dim_label]Choice (1/2, default 1):[/dim_label] ").strip() or '1'

            sub_dir = os.path.join(OUTPUT_DIR, _sanitize_filename(category))
            dl_results = download_batch(arxiv_results, sub_dir, download_latex=(fmt == '2'))
            _display_summary(dl_results)
        break


def _display_categories() -> None:
    table = Table(
        title="arXiv Categories", box=ROUNDED, border_style="bright_blue",
        header_style="bold bright_cyan", expand=False,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Code", style="cyan", width=12)
    table.add_column("Name", style="white", min_width=35)
    table.add_column("Subcategories", style="dim", max_width=40, no_wrap=True)

    for i, (code, (name, subs)) in enumerate(sorted(CATEGORIES.items()), 1):
        sub_str = ', '.join(subs[:8])
        if len(subs) > 8:
            sub_str += f' +{len(subs) - 8}'
        table.add_row(str(i), code, name, sub_str or '-')

    console.print()
    console.print(table)


# === MAIN ===

def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)

    scraper_db.init_db()

    _print_banner()

    cmd_table = Table(box=ROUNDED, border_style="bright_blue",
                      show_header=True, header_style="bold bright_cyan",
                      expand=False, padding=(0, 2))
    cmd_table.add_column("Type", style="bold bright_white", width=14)
    cmd_table.add_column("Example", style="accent", width=20)
    cmd_table.add_column("Description", style="white")

    cmd_table.add_row(
        "[bright_green]Search[/bright_green]",
        "transformer",
        "Search papers by keyword",
    )
    cmd_table.add_row(
        "",
        "1706.03762",
        "Search paper by arXiv ID",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[bright_cyan]Prefixes[/bright_cyan]",
        "au:[bright_cyan]hinton[/bright_cyan]",
        "Search by author",
    )
    cmd_table.add_row(
        "",
        "ti:[bright_cyan]attention[/bright_cyan]",
        "Search in title",
    )
    cmd_table.add_row(
        "",
        "abs:[bright_cyan]reinforcement[/bright_cyan]",
        "Search in abstract",
    )
    cmd_table.add_row(
        "",
        "co:[bright_cyan]NeurIPS[/bright_cyan]",
        "Search in comments (conference, pages)",
    )
    cmd_table.add_row(
        "",
        "jr:[bright_cyan]Nature[/bright_cyan]",
        "Search by journal",
    )
    cmd_table.add_row(
        "",
        "doi:[bright_cyan]10.1038/...[/bright_cyan]",
        "Search by DOI",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[bright_magenta]Categories[/bright_magenta]",
        "cat",
        "Show all categories list",
    )
    cmd_table.add_row(
        "",
        "cat:[bright_cyan]cs.AI[/bright_cyan]",
        "Search within a category",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[bright_yellow]Today's papers[/bright_yellow]",
        "today",
        "All papers submitted today",
    )
    cmd_table.add_row(
        "",
        "today:[bright_cyan]cs[/bright_cyan]",
        "Today's papers by category",
    )
    cmd_table.add_row(
        "",
        "today:[bright_cyan]cs.AI[/bright_cyan]",
        "Today's papers by subcategory",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[bright_white]Related[/bright_white]",
        "related:[bright_cyan]1706.03762[/bright_cyan]",
        "Related papers (via Semantic Scholar)",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[bright_green]Full-text[/bright_green]",
        "search:[bright_cyan]attention[/bright_cyan]",
        "Search keyword in downloaded PDFs",
    )
    cmd_table.add_row("", "", "")
    cmd_table.add_row(
        "[dim]Other[/dim]",
        "stats",
        "Show today's announcement stats",
    )
    cmd_table.add_row(
        "",
        "q",
        "Exit program",
    )

    console.print()
    console.print(Panel(
        cmd_table,
        title="[bold bright_white]Available commands[/bold bright_white]",
        subtitle="[dim]Type a command and press Enter[/dim]",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 1),
    ))

    while not _shutdown_event.is_set():
        try:
            query = console.input(f"\n{SYM_PAPER} [bold]Search papers > [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query or query.lower() in ('q', 'quit', 'exit'):
            break

        if query.lower() == 'cat':
            _display_categories()
            continue

        if query.lower() == 'stats':
            _display_today_stats()
            continue

        if query.lower() == 'today' or query.lower().startswith('today:'):
            cat = query[6:].strip() if ':' in query else ''
            _explore_today(cat)
            continue

        if query.lower().startswith('related:'):
            rid = query[8:].strip()
            if rid:
                _display_related_papers(rid)
            else:
                console.print("[error]Specify an arXiv ID (e.g. related:1706.03762)[/error]")
            continue

        if query.lower().startswith('search:'):
            kw = query[7:].strip()
            if kw:
                _display_local_search(kw)
            else:
                console.print("[error]Specify a keyword (e.g. search:transformer)[/error]")
            continue

        # Parse category
        category = ''
        search_query = query
        if query.lower().startswith('cat:'):
            parts = query.split(' ', 1)
            category = parts[0][4:]
            search_query = parts[1] if len(parts) > 1 else ''

        # Search options (compact block)
        opt_table = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        opt_table.add_column("", style="dim_label")
        opt_table.add_column("", style="white")
        opt_table.add_row("Sort:", "[accent]1[/accent] Relevance  [accent]2[/accent] Date  [accent]3[/accent] Last updated")
        opt_table.add_row("Max:", f"[accent]{MAX_SEARCH_RESULTS}[/accent] (default)")
        opt_table.add_row("Period:", "[accent]1[/accent] All  [accent]2[/accent] Today only  [accent]3[/accent] Last week")
        console.print(opt_table)

        opts = console.input(
            "  [dim_label]Sort, Max, Period (default 1,20,1):[/dim_label] "
        ).strip()
        parts = [p.strip() for p in opts.replace(' ', ',').split(',') if p.strip()] if opts else []
        sort_choice = parts[0] if len(parts) >= 1 else '1'
        max_res_str = parts[1] if len(parts) >= 2 else ''
        date_filter_choice = parts[2] if len(parts) >= 3 else '1'

        sort_map = {'1': 'relevance', '2': 'date', '3': 'updated'}
        sort_by = sort_map.get(sort_choice, 'relevance')
        max_res = int(max_res_str) if max_res_str.isdigit() else MAX_SEARCH_RESULTS

        with Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold bright_cyan]{task.description}"),
            BarColumn(bar_width=30, style="dim", complete_style="bright_cyan", finished_style="bright_green"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("Starting search...", total=1)

            def _on_progress(desc: str, step: int, total: int):
                progress.update(task_id, description=desc, total=total, completed=step - 1)

            try:
                results = search_papers(search_query, category=category,
                                         max_results=max_res, sort_by=sort_by,
                                         on_progress=_on_progress)
            except Exception as e:
                results = []
                log.warning("Search error: %s", e)
                if '429' in str(e):
                    console.print("[warning]arXiv rate limit reached. Wait a few seconds and try again.[/warning]")
                    continue
                console.print(f"[error]Search error: {e}[/error]")
                continue
            progress.update(task_id, description="Search complete!", completed=progress.tasks[task_id].total)

        if not results:
            console.print(Panel(
                "[error]No results found.[/error]\n\n"
                "[dim]Suggestions:[/dim]\n"
                f"  [accent]\u2022[/accent] Try different keywords (e.g. [accent]neural network[/accent])\n"
                f"  [accent]\u2022[/accent] Search by arXiv ID (e.g. [accent]1706.03762[/accent])\n"
                f"  [accent]\u2022[/accent] Filter by category (e.g. [accent]cat:cs.AI transformer[/accent])\n"
                f"  [accent]\u2022[/accent] Prefixes: [accent]au:[/accent] author, [accent]ti:[/accent] title, "
                f"[accent]abs:[/accent] abstract, [accent]co:[/accent] comments, [accent]jr:[/accent] journal, "
                f"[accent]doi:[/accent] DOI",
                border_style="red", box=ROUNDED, expand=False, padding=(1, 2),
                title="[bold red]No results[/bold red]",
            ))
            continue

        # Date filter
        from datetime import date, timedelta
        if date_filter_choice == '2':
            # Today only
            today_date = date.today()
            filtered_results = [r for r in results if r.published.date() == today_date]
            if filtered_results:
                results = filtered_results
            else:
                latest = max(r.published.date() for r in results)
                filtered_results = [r for r in results if r.published.date() == latest]
                results = filtered_results
                console.print(
                    f"[warning]No papers published on {today_date.strftime('%d/%m/%Y')}. "
                    f"Showing {len(results)} papers from {latest.strftime('%d/%m/%Y')} "
                    f"(most recent date available).[/warning]"
                )
        elif date_filter_choice == '3':
            # Last week
            one_week_ago = date.today() - timedelta(days=7)
            results = [r for r in results if r.published.date() >= one_week_ago]
            if not results:
                console.print("[warning]No papers found in the last week.[/warning]")
                continue

        _display_results(results)

        # Single paper details?
        console.print(
            f"\n  {SYM_DOT} [accent]d <num>[/accent] for paper details"
        )

        selected = _select_papers(results)
        if not selected:
            continue

        # Show details for each selected paper (if few)
        if len(selected) <= 3:
            for r in selected:
                _display_paper_details(r)

        # Download format
        console.print(
            f"\n  [dim_label]Format:[/dim_label] "
            f"[accent]1[/accent] PDF only  "
            f"[accent]2[/accent] PDF + LaTeX source (.tar.gz)"
        )
        fmt_choice = console.input("  [dim_label]Choice (1/2, default 1):[/dim_label] ").strip() or '1'
        download_latex = fmt_choice == '2'
        fmt_label = "PDF + LaTeX" if download_latex else "PDF only"

        # Output folder
        if category:
            sub_dir = os.path.join(OUTPUT_DIR, _sanitize_filename(category))
        else:
            sub_dir = OUTPUT_DIR

        # Confirm before download
        console.print(Panel(
            f"  [dim_label]Paper:[/dim_label]    [bold]{len(selected)}[/bold]\n"
            f"  [dim_label]Format:[/dim_label]  [bold]{fmt_label}[/bold]\n"
            f"  [dim_label]Folder:[/dim_label]   [info]{sub_dir}[/info]",
            title="[bold bright_white]Download summary[/bold bright_white]",
            border_style="bright_yellow", box=ROUNDED, expand=False, padding=(1, 2),
        ))
        confirm = console.input("  [dim_label]Proceed? (y/n, default y):[/dim_label] ").strip().lower() or 'y'
        if confirm not in ('y', 'yes'):
            console.print("[dim]Download cancelled.[/dim]")
            continue

        dl_results = download_batch(selected, sub_dir, download_latex=download_latex)
        _display_summary(dl_results)

    console.print("\n[dim]Goodbye![/dim]\n")


if __name__ == '__main__':
    main()
