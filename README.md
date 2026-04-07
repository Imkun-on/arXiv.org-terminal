```
                          __  __     _                                      __ _
    o O O  __ _      _ _  \ \/ /    (_)    __ __            ___      _ _   / _` |
   o      / _` |    | '_|  >  <     | |    \ V /     _     / _ \    | '_|  \__, |
  TS__[O] \__,_|   _|_|_  /_/\_\   _|_|_   _\_/_   _(_)_   \___/   _|_|_   |___/
 {======|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|
./o--000'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'
```

<h1 align="center">arXiv Paper Scraper & Research Tool</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/arXiv-API-B31B1B?logo=arxiv&logoColor=white" alt="arXiv">
  <img src="https://img.shields.io/badge/Rich-13.0+-4EC820?logo=terminal&logoColor=white" alt="Rich">
  <img src="https://img.shields.io/badge/Semantic%20Scholar-API-1857B6?logo=semanticscholar&logoColor=white" alt="Semantic Scholar">
  <img src="https://img.shields.io/badge/Requests-2.31+-FF6600?logo=python&logoColor=white" alt="Requests">
  <img src="https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/PyMuPDF-PDF%20Search-CC0000?logo=adobeacrobatreader&logoColor=white" alt="PyMuPDF">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  A terminal-based research paper tool for <a href="https://arxiv.org">arXiv.org</a> with Rich UI,<br>
  built to overcome the limitations of the standard arXiv web interface.
</p>

```bash
git clone https://github.com/Imkun-on/arXiv.org-terminal.git
cd arXiv.org-terminal
pip install -r requirements.txt
python Scraper_Arxiv.py
```

---

## Table of Contents

- [Why use this instead of arxiv.org?](#why-use-this-instead-of-arxivorg)
- [Libraries Used & Why](#libraries-used--why)
- [Requirements & Installation](#requirements--installation)
- [Usage & Examples](#usage--examples)
  - [Example 1: Search by Keyword](#example-1-search-by-keyword)
  - [Example 2: Search by arXiv ID](#example-2-search-by-arxiv-id)
  - [Example 3: Today's Papers](#example-3-todays-papers)
- [Commands](#commands)
  - [Search](#search)
  - [Prefix search](#prefix-search)
  - [Today's papers](#todays-papers)
  - [Other commands](#other-commands)
- [Search options](#search-options)
- [Results table](#results-table)
- [Paper details](#paper-details)
- [Download](#download)
- [Full-text search](#full-text-search)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Rate limiting](#rate-limiting)
- [Graceful shutdown](#graceful-shutdown)
- [Cross-platform support](#cross-platform-support)
- [License](#license)

---

## Why use this instead of arxiv.org?

| Feature | arxiv.org (website) | Arxiv_Scraper |
|---|---|---|
| **Search** | Basic keyword search, one field at a time | Smart multi-keyword search with AND logic, auto title/global fallback |
| **Today's papers** | Browse by category, no filtering | `today` command with interactive filters (keyword, author, subcategory) |
| **Citations** | Not shown at all | Citation count from Semantic Scholar displayed inline |
| **Related papers** | Not available | `related:` command via Semantic Scholar recommendations |
| **Download** | Manual, one PDF at a time | Batch download with parallel threads, progress bars, resume support |
| **LaTeX source** | Manual download per paper | One-click PDF + LaTeX source download |
| **Full-text search** | Not available | `search:` command to grep through all downloaded PDFs |
| **Date filtering** | Limited to daily listings | Filter by today / last week on any search |
| **UI** | Web browser required | Terminal-native with colored tables, panels, progress bars |
| **Offline** | Nothing | All downloaded papers searchable locally with metadata in SQLite |

---

## Libraries Used & Why

| Library | Version | Purpose | Why this library? |
|---------|---------|---------|-------------------|
| `arxiv` | >= 2.4 | Python client for the arXiv API — handles search, metadata retrieval, and PDF download | The official Python wrapper for arXiv's API. Manages query construction, pagination, rate limiting (built-in `delay_seconds`), and automatic retries on HTTP 429. Without it, you'd need to manually build Atom/XML queries and parse RSS responses — this abstracts all of that into clean Python objects (`arxiv.Result`) |
| `requests` | >= 2.31 | HTTP client for Semantic Scholar API and direct file downloads (LaTeX source, RSS feeds) | The de facto Python HTTP library. Used here for everything *outside* the arXiv API: citation counts from Semantic Scholar, related paper recommendations, RSS feed fetching for today's stats, and LaTeX source `.tar.gz` downloads. Lightweight, synchronous, and reliable |
| `rich` | >= 13.0 | Terminal UI — tables, panels, progress bars, spinners, colored text, live rendering | Transforms the CLI from plain text into a polished interface. Provides `Table` for search results, `Panel` for paper details, `Progress` with spinners for downloads, and `Live` for real-time multi-progress rendering. All without external dependencies beyond Python |
| `SQLite` | built-in | Persistent storage for download history and paper metadata | Part of Python's standard library (`sqlite3`), so zero extra dependencies. Tracks every downloaded paper with metadata (arXiv ID, title, authors, categories, DOI, file path, size). Enables skip-if-already-downloaded logic and could support future features like local search by metadata |
| `PyMuPDF` | optional | Full-text PDF search across all downloaded papers | The only library needed for the `search:` command. Extracts text from PDF pages and allows keyword searching with page numbers and context snippets. Marked as optional — if not installed, the tool simply shows an install message instead of crashing. Chosen over `pdfminer` for its speed and lower memory footprint |

### Standard Library Modules (no install needed)

| Module | Purpose |
|--------|---------|
| `threading` + `concurrent.futures` | Parallel downloads (3 threads by default via `ThreadPoolExecutor`) and concurrent citation fetching |
| `signal` | Graceful shutdown — first `Ctrl+C` finishes current work, second forces exit |
| `re` | Regex for arXiv ID extraction, filename sanitization, page count parsing |
| `xml.etree.ElementTree` | RSS feed parsing for today's paper statistics (Atom format) |
| `argparse` | Command-line argument parsing |
| `logging` | Rotating file logs for debugging (`logs/scraper_arxiv.log`) |

---

## Requirements & Installation

### Python

Requires **Python 3.10+**.

### Install dependencies

```bash
pip install -r requirements.txt
```

Or manually (only what's needed for this scraper):

```bash
pip install arxiv requests rich
```

Optional (for full-text PDF search):

```bash
pip install PyMuPDF
```

If `PyMuPDF` is not installed, the `search:` command will show a helpful install message instead of crashing. Everything else works without it.

---

## Usage & Examples

```bash
python Scraper_Arxiv.py
```

The interactive prompt appears:

```
📄 Search papers >
```

### Example 1: Search by Keyword

```
📄 Search papers > transformer

  Sort:    1 Relevance  2 Date  3 Last updated
  Max:     20 (default)
  Period:  1 All  2 Today only  3 Last week
  Sort, Max, Period (default 1,20,1): 1,10

  ⠋ Searching arXiv...  ████████████████  1/1  0:00:05

  ⠋ Loading citations...  ██████████████  10/10  0:00:12

                      Results (10)
  ┌────┬──────────────────────────────────┬────────────────┬────────┬────────────┬──────┬───────┐
  │  # │ Title                            │ Authors        │ Cat.   │ Date       │ Cit. │ Pages │
  ├────┼──────────────────────────────────┼────────────────┼────────┼────────────┼──────┼───────┤
  │  1 │ Attention Is All You Need        │ Vaswani +7     │ cs.CL  │ 2017-06-12 │ 130k │ 15    │
  │  2 │ BERT: Pre-training of Deep Bi... │ Devlin +3      │ cs.CL  │ 2018-10-11 │ 95k  │ 14    │
  │  3 │ An Image is Worth 16x16 Words... │ Dosovitskiy +11│ cs.CV  │ 2020-10-22 │ 42k  │ 22    │
  │  4 │ ...                              │ ...            │ ...    │ ...        │ ...  │ ...   │
  └────┴──────────────────────────────────┴────────────────┴────────┴────────────┴──────┴───────┘

  · d <num> for paper details

  Choose > d 1

  ╭──────────────────── Paper Details ────────────────────╮
  │  Attention Is All You Need                            │
  │                                                       │
  │  Authors:    Ashish Vaswani, Noam Shazeer, ...        │
  │  Categories: cs.CL, cs.LG                            │
  │  Published:  2017-06-12  |  Updated: 2023-08-02      │
  │  arXiv ID:   1706.03762                               │
  │  Comments:   15 pages, NeurIPS 2017                   │
  │  PDF:        https://arxiv.org/pdf/1706.03762         │
  │  Citations:  130,234 (influential: 12,456)            │
  │                                                       │
  │  Abstract:                                            │
  │  The dominant sequence transduction models are        │
  │  based on complex recurrent or convolutional neural   │
  │  networks...                                          │
  ╰───────────────────────────────────────────────────────╯

  Choose > 1

  Format: 1 PDF only  2 PDF + LaTeX source (.tar.gz)
  Choice (1/2, default 1): 2

  ╭──────────── Download summary ────────────╮
  │  Paper:   1                              │
  │  Format:  PDF + LaTeX                    │
  │  Folder:  Download_Globale/download_arxiv│
  ╰──────────────────────────────────────────╯
  Proceed? (y/n, default y): y

  ──────────────── ⬇ Download PDF + LaTeX ────────────────
    Thread: 3  Paper: 1

    ⠋ Paper  ████████████████████████████  100%  1/1  │ 0:00:03 → 0:00:00

  ╔══════════ ✅ Summary ══════════╗
  ║  Total papers    1             ║
  ║  ✔ Downloaded    1             ║
  ║  Total size      1.2 MB        ║
  ╚════════════════════════════════╝
```

---

### Example 2: Search by arXiv ID

```
📄 Search papers > 1706.03762

  Sort, Max, Period (default 1,20,1):

  ⠋ Searching by arXiv ID...

                      Results (1)
  ┌────┬───────────────────────────┬────────────────┬────────┬────────────┬───────┬───────┐
  │  # │ Title                     │ Authors        │ Cat.   │ Date       │ Cit.  │ Pages │
  ├────┼───────────────────────────┼────────────────┼────────┼────────────┼───────┼───────┤
  │  1 │ Attention Is All You Need │ Vaswani +7     │ cs.CL  │ 2017-06-12 │ 130k  │ 15    │
  └────┴───────────────────────────┴────────────────┴────────┴────────────┴───────┴───────┘

  Choose > 1
  ...
```

> With a direct arXiv ID, the tool skips the search step and retrieves the paper directly.

---

### Example 3: Today's Papers

```
📄 Search papers > today:cs.AI

  ⠋ Loading today's papers for cs.AI...

  ╭───────────── 📄 Today's papers ─────────────╮
  │  cs.AI  12 new  3 updated  15 total          │
  │                                               │
  │  cs.AI   15                                   │
  │  cs.LG    8                                   │
  │  cs.CL    4                                   │
  ╰───────────────────────────────────────────────╯

  ╭──────────── Filters ────────────╮
  │  Filter          Description    │
  │  all             Show all       │
  │  new             New only       │
  │  sub:cs.LG       By subcategory │
  │  key:transformer  By keyword    │
  │  au:Hinton        By author     │
  │  top:20           First N       │
  │  q                Back          │
  ╰─────────────────────────────────╯

  Filter > key:attention

            Today's papers (3 total)
  ┌────┬────────────────────────────┬──────────────┬────────┬────────────┬─────┐
  │  # │ Title                      │ Authors      │ Cat.   │ Date       │ New │
  ├────┼────────────────────────────┼──────────────┼────────┼────────────┼─────┤
  │  1 │ Cross-Attention Fusion ... │ Smith +2     │ cs.AI  │ 2026-04-07 │ yes │
  │  2 │ Efficient Self-Attentio... │ Lee, Kim     │ cs.AI  │ 2026-04-07 │ yes │
  │  3 │ Attention-Based Graph N... │ Rossi +4     │ cs.AI  │ 2026-04-07 │ upd.│
  └────┴────────────────────────────┴──────────────┴────────┴────────────┴─────┘

  Choose > 1-3
  ...
```

---

## Commands

### Search

| Command | Description |
|---|---|
| `transformer` | Search by keyword |
| `password cracking` | Multi-keyword search (AND logic) |
| `1706.03762` | Search by arXiv ID |

Multiple keywords are joined with AND automatically: `password cracking` finds papers containing **both** words, not just one.

### Prefix search

| Prefix | Example | Searches in |
|---|---|---|
| `au:` | `au:hinton` | Author names |
| `ti:` | `ti:attention` | Paper title |
| `abs:` | `abs:reinforcement` | Abstract |
| `co:` | `co:NeurIPS` | Comments (conference, pages) |
| `jr:` | `jr:Nature` | Journal reference |
| `doi:` | `doi:10.1038/...` | DOI |
| `cat:` | `cat:cs.AI transformer` | Within a specific category |

### Today's papers

| Command | Description |
|---|---|
| `today` | All papers submitted today (all categories) |
| `today:cs` | Today's CS papers only |
| `today:cs.AI` | Today's cs.AI papers only |

The `today` command uses the arXiv API with `submittedDate` filter to show only papers whose submission date matches today. Interactive filters are available after loading:

- `all` -- show all
- `new` -- new papers only (no updates)
- `sub:cs.LG` -- filter by subcategory
- `key:transformer` -- keyword in title/abstract
- `au:Hinton` -- filter by author
- `top:20` -- show first N

### Other commands

| Command | Description |
|---|---|
| `related:1706.03762` | Find related papers via Semantic Scholar |
| `search:attention` | Full-text search in downloaded PDFs |
| `cat` | Show all arXiv categories and subcategories |
| `stats` | Show today's announcement statistics by category |
| `q` | Exit |

---

## Search options

When you search, a single prompt asks for three settings at once:

```
Sort, Max, Period (default 1,20,1):
```

| Position | Options |
|---|---|
| **Sort** | `1` Relevance, `2` Date, `3` Last updated |
| **Max** | Number of results (default 20) |
| **Period** | `1` All time, `2` Today only, `3` Last week |

Examples:
- Press Enter = relevance, 20 results, all dates
- `2,50` = sort by date, 50 results, all dates
- `1,20,2` = relevance, 20 results, today only

---

## Results table

Search results are displayed with:

```
# | Title | Authors | Cat. | Date | Cit. | Pages
```

- **Cit.** = citation count from Semantic Scholar (fetched automatically)
- **Date** = paper submission date
- After the table: `d <num>` to see full details of a paper

---

## Paper details

Selecting a paper shows:

- Full title and all authors
- All categories
- Published / updated dates
- arXiv ID, DOI, journal reference
- Author comments (conference, page count)
- PDF and page links
- Citation count (total + influential)
- Full abstract

---

## Download

After selecting papers (single number, range `1-5`, comma-separated `1,3,7`, or `all`):

1. Choose format: **PDF only** or **PDF + LaTeX source**
2. Confirm the download
3. Papers download in parallel (3 threads) with real-time progress bars
4. Already-downloaded papers are automatically skipped
5. Metadata is saved to SQLite database

Downloaded files are saved to `Download_Globale/download_arxiv/` with naming: `{arXiv_ID}_{Title}.pdf`

---

## Full-text search

```
search:transformer
```

Searches all downloaded PDFs for the keyword and shows:

- Which papers contain it
- How many matches per paper
- Which pages
- A context snippet with the keyword highlighted

Requires `PyMuPDF` (`pip install PyMuPDF`).

---

## Architecture

```
Scraper_Arxiv.py
    │
    ├── arXiv API (arxiv python package)
    │       Search, paper metadata, PDF download
    │
    ├── arXiv RSS feed (rss.arxiv.org)
    │       Today's announcement statistics (stats command)
    │
    ├── Semantic Scholar API
    │       Citation counts, related papers
    │
    ├── Rich (terminal UI)
    │       Tables, panels, progress bars, colors
    │
    ├── SQLite (via scraper_db)
    │       Download history and metadata storage
    │
    └── PyMuPDF (optional)
            Full-text PDF search
```

---

## Configuration

Constants at the top of the script:

| Constant | Default | Description |
|---|---|---|
| `MAX_SEARCH_RESULTS` | 20 | Default max results per search |
| `MAX_DOWNLOAD_WORKERS` | 3 | Parallel download threads |
| `MAX_RETRIES` | 3 | Download retry attempts |
| `REQUEST_TIMEOUT` | 30s | HTTP timeout |
| `MIN_PDF_SIZE` | 10 KB | Skip corrupted/empty PDFs |
| `OUTPUT_DIR` | `Download_Globale/download_arxiv` | Download folder |

---

## Rate limiting

arXiv enforces strict rate limits (~1 request every 3-5 seconds). The script handles this with:

- `delay_seconds=5.0` between API calls
- Automatic retry (up to 5 attempts) on HTTP 429 errors
- Graceful error message instead of crash

If you see `arXiv rate limit reached`, just wait 30-60 seconds and try again.

---

## Graceful shutdown

Press `Ctrl+C` once to finish current downloads and exit cleanly. Press twice to force quit.

---

## Cross-platform support

Works on **Windows**, **macOS**, and **Linux**. No hardcoded paths — all directories are relative to the script location. UTF-8 output is automatically configured on Windows terminals.

---

## License

This project is licensed under the MIT License.
