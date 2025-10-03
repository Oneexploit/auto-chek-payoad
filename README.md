# Dalfox Auto Full (`dalfox_auto_full.py`)

## Overview

**Dalfox Auto Full** is a Python automation script that integrates with [Dalfox](https://github.com/hahwul/dalfox) to parse its output, verify PoCs, and perform additional checks (HTTP + headless browser) to help triage potential XSS findings.
**Important:** Only run this against targets you are explicitly authorized to test.

---

## What it does

* Runs Dalfox against a list of targets (optional) or consumes an existing Dalfox output file.
* Parses Dalfox output to extract unique URLs and raw lines containing PoC/payload traces.
* Performs HTTP GET checks on each extracted URL to search for payload markers in the response body.
* Optionally launches a headless browser (Playwright) to:

  * Listen to `console` messages,
  * Inspect the DOM for execution markers,
  * Provide more reliable detection of client-side execution (e.g., XSS).
* Optionally injects user-provided payloads into URL templates and tests the resulting URLs.
* Writes a JSON output and a textual summary report.

---

## Key features

* **Dalfox execution** (`--run-dalfox`): Run Dalfox as a subprocess on a targets file and save stdout.
* **Input mode** (`--input` / `-i`): Use an existing Dalfox output file instead of re-running Dalfox.
* **HTTP triage**: Requests each URL and checks for common payload markers in HTML responses.
* **Headless verification**: Uses Playwright (if installed) to detect console messages and DOM indicators of successful payload execution.
* **Payload injection** (`--inject` + `--payloads`): Generate test URLs by injecting payloads into templates and evaluate responses.
* **Reporting**: Saves full results to JSON and a human-readable `report.txt` summary.

---

## Important command-line options

* `--run-dalfox` : Run Dalfox on the specified targets file (Dalfox must be in `PATH`).
* `--targets <file>` : File with one target per line (used with `--run-dalfox`).
* `--input, -i <file>` : Use an existing Dalfox output file (mutually exclusive with `--run-dalfox`).
* `--out, -o <file>` : Output JSON path (default: `reports/results.json`).
* `--report <file>` : Text summary report path (default: `reports/report.txt`).
* `--payloads <file>` : File containing payloads (one per line) for injection tests.
* `--inject` : Enable payload injection testing (requires `--payloads`).

---

## How it works (high-level flow)

1. **Input selection**: either run Dalfox on `--targets` or load an existing Dalfox output via `--input`.
2. **Parse output**: extract unique URLs and capture raw Dalfox lines for context.
3. **HTTP checks**: send GET requests to each URL, record status, `Content-Type`, and search for payload markers in the response body.
4. **Headless checks** (if Playwright present): open each promising URL in a headless Chromium instance, capture `console` messages, and search page content for markers.
5. **Injection tests** (optional): build test URLs by inserting payloads into templates and re-run HTTP checks to look for evidence of reflection/execution.
6. **Save results**: write structured JSON plus a readable text report summarizing findings and recommended follow-up.

---

## Detection markers

The script looks for several common indicators of payload reflection/execution, including (but not limited to):

* `alert(`
* `confirm(`
* `prompt(`
* `console.log(`
* `DALFOX_TEST`
* `print(`
* `alert.call` / `alert.apply`

These markers are used as heuristics — manual verification is required to confirm real exploitability.

---

## Dependencies & requirements

* Python 3
* `requests`, `tqdm`, `beautifulsoup4`
* **Dalfox** in `PATH` if using `--run-dalfox`
* **Playwright** is optional; install it to enable headless checks. If Playwright is not available, headless checks are skipped and a warning is printed.

---

## Output

* **JSON** (default `reports/results.json`): full structured results including HTTP checks, headless results (if any), injection attempts, timestamps and raw Dalfox lines.
* **Text report** (default `reports/report.txt`): human-readable summary showing each URL, HTTP status, markers found, headless console messages, and a short risk hint when execution markers are present.

---

## Usage examples

Run Dalfox on `targets.txt`, then analyze and produce reports:

```bash
python3 dalfox_auto_full.py --run-dalfox --targets targets.txt --out reports/results.json --report reports/report.txt
```

Analyze an existing Dalfox output and run injection tests with a payloads list:

```bash
python3 dalfox_auto_full.py --input tmp_dalfox_output.txt --payloads payloads.txt --inject
```

---

## Notes & caveats

* The script uses simple heuristics to find URLs and markers — false positives and false negatives are possible.
* Headless verification is more reliable for detecting client-side execution but requires Playwright and may be subject to JavaScript timing/DOM-driven behavior.
* The injection logic uses a basic template heuristic (e.g., URL ending with `=` or containing `{PAYLOAD}`) — complex parameter contexts may need manual crafting.
* Always verify findings manually before reporting or remediating.

---


