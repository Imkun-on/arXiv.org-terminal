# Arxiv_Scraper.py

A terminal-based research paper tool for [arXiv.org](https://arxiv.org) with Rich UI, built to overcome the limitations of the standard arXiv web interface.

```
                          __  __     _                                      __ _
    o O O  __ _      _ _  \ \/ /    (_)    __ __            ___      _ _   / _` |
   o      / _` |    | '_|  >  <     | |    \ V /     _     / _ \    | '_|  \__, |
  TS__[O] \__,_|   _|_|_  /_/\_\   _|_|_   _\_/_   _(_)_   \___/   _|_|_   |___/
 {======|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|_|"""""|
./o--000'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'"`-0-0-'
```

---

## Table of Contents

- [Built with](#built-with)
- [Why use this instead of arxiv.org?](#why-use-this-instead-of-arxivorg)
- [Requirements](#requirements)
- [Quick start](#quick-start)
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

---

## Built with

<p>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/arXiv_API-B31B1B?style=for-the-badge&logo=arxiv&logoColor=white" alt="arXiv"/>
  <img src="https://img.shields.io/badge/Rich-Terminal_UI-4EC820?style=for-the-badge" alt="Rich"/>
  <img src="https://img.shields.io/badge/Semantic_Scholar-1857B6?style=for-the-badge&logo=semanticscholar&logoColor=white" alt="Semantic Scholar"/>
  <img src="https://img.shields.io/badge/Requests-HTTP-FF6600?style=for-the-badge" alt="Requests"/>
  <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite"/>
  <img src="https://img.shields.io/badge/PyMuPDF-PDF_Search-CC0000?style=for-the-badge" alt="PyMuPDF"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License"/>
</p>

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

## Requirements

```
pip install arxiv requests rich
```

Optional (for full-text PDF search):
```
pip install PyMuPDF
```

If `PyMuPDF` is not installed, the `search:` command will show a helpful install message instead of crashing. Everything else works without it.

---

## Quick start

```bash
python Arxiv_Scraper.py
```

The interactive prompt appears:

```
📄 Search papers >
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
Arxiv_Scraper.py
    |
    |-- arXiv API (arxiv python package)
    |       Search, paper metadata, PDF download
    |
    |-- arXiv RSS feed (rss.arxiv.org)
    |       Today's announcement statistics (stats command)
    |
    |-- Semantic Scholar API
    |       Citation counts, related papers
    |
    |-- Rich (terminal UI)
    |       Tables, panels, progress bars, colors
    |
    |-- SQLite (via scraper_db)
    |       Download history and metadata storage
    |
    |-- PyMuPDF (optional)
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

Works on **Windows**, **macOS**, and **Linux**. No hardcoded paths -- all directories are relative to the script location. UTF-8 output is automatically configured on Windows terminals.
