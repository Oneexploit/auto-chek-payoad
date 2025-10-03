#!/usr/bin/env python3
"""
dalfox_auto_full.py

کاربرد:
- اگر گزینه --run-dalfox مشخص شود: Dalfox را روی فایل targets اجرا می‌کند و خروجی را ذخیره می‌کند.
- اگر گزینه --input مشخص شود: خروجی Dalfox موجود را می‌خواند.
- خروجی را پارس می‌کند، URLها و PoCها را استخراج می‌کند، dedupe می‌کند.
- برای هر URL:
    - GET ساده با requests و جستجوی markerها
    - اگر مناسب بود، باز کردن headless با Playwright و گوش دادن به console + بررسی DOM
- نتیجه را به JSON و report.txt می‌نویسد.

توجه: فقط روی اهدافی اجرا شود که مجوز تست دارید.
"""

import argparse
import subprocess
import os
import sys
import re
import json
import time
from urllib.parse import unquote, quote_plus
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup

# Playwright import lazy
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

# تنظیمات
TIMEOUT = 20
HEADLESS = True
PAYLOAD_MARKERS = [
    "alert(", "confirm(", "prompt(", "console.log(", "DALFOX_TEST", "print(", "alert.call", "alert.apply", "prompt.call"
]
URL_PATTERN = re.compile(r'https?://[^\s\]\)\"]+')

def run_dalfox_on_targets(targets_file, out_file):
    """
    اجرای Dalfox به صورت subprocess و ذخیره stdout در out_file.
    (فرض می‌کند dalfox در PATH است)
    """
    cmd = ['dalfox', 'file', targets_file]
    print(f"[+] Running: {' '.join(cmd)}")
    with open(out_file, 'w', encoding='utf-8') as outf:
        try:
            subprocess.run(cmd, stdout=outf, stderr=subprocess.STDOUT, check=False, text=True)
        except FileNotFoundError:
            print("[!] dalfox not found in PATH. Please install dalfox or provide --input file.")
            sys.exit(2)
    print(f"[+] Dalfox output written to {out_file}")

def parse_dalfox_output(path):
    """
    پارس خروجی Dalfox: استخراج URLها و خطوط حاوی payload markers
    برمیگرداند لیست unique urls و لیستی از خطوط خام مرتبط
    """
    urls = []
    raw_lines = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip():
                continue
            raw_lines.append(line.rstrip('\n'))
            found = URL_PATTERN.findall(line)
            if found:
                for u in found:
                    u2 = normalize_url(unquote(u))
                    if u2 and u2 not in urls:
                        urls.append(u2)
            else:
                # بعضی اوقات Dalfox url ها را به فرمت escape شده جدا می‌آورد؛ تلاش برای استخراج نمونه‌های دیگر
                # (حفظ-ساده‌سازی)
                if "http" in line and '/' in line:
                    # fallback: try to find substrings starting with http
                    idx = line.find("http")
                    snippet = line[idx:].split()[0]
                    u2 = normalize_url(unquote(snippet))
                    if u2 and u2 not in urls:
                        urls.append(u2)
    return urls, raw_lines

def normalize_url(u):
    return u.strip().strip(',"\')()[]')

def http_check(url):
    try:
        resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True, headers={'User-Agent':'Dalfox-AutoAutomation/1.0'})
        body = resp.text or ""
        marker_hits = [m for m in PAYLOAD_MARKERS if m in body]
        return {'status_code': resp.status_code, 'content_type': resp.headers.get('Content-Type',''), 'marker_hits': marker_hits, 'body_snippet': body[:4000]}
    except Exception as e:
        return {'error': str(e)}

def headless_check(play, url, watch_markers=None):
    if watch_markers is None:
        watch_markers = ["DALFOX_TEST", "alert(", "console.log("]
    result = {'console_msgs': [], 'detected': [], 'error': None, 'content_contains': []}
    try:
        browser = play.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        def on_console(msg):
            txt = f"{msg.type}: {msg.text}"
            result['console_msgs'].append(txt)
            for m in watch_markers:
                if m in msg.text and m not in result['detected']:
                    result['detected'].append(m)
        page.on("console", on_console)
        page.goto(url, timeout=TIMEOUT*1000)
        time.sleep(2)
        content = page.content()
        for m in watch_markers:
            if m in content and m not in result['content_contains']:
                result['content_contains'].append(m)
        context.close()
        browser.close()
    except Exception as e:
        result['error'] = str(e)
    return result

def inject_payloads_on_url(url_template, payloads, is_query=True):
    """
    تولید لیستی از URLها با payloadهای encode شده.
    url_template باید شامل {PAYLOAD} باشد.
    """
    out = []
    for p in payloads:
        enc = quote_plus(p) if is_query else quote_plus(p)  # برای حالا هر دو را quote_plus می‌کنیم
        out.append(url_template.replace("{PAYLOAD}", enc))
    return out

def load_payloads(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [ln.strip() for ln in f if ln.strip()]

def main():
    ap = argparse.ArgumentParser(description="Dalfox full automation: run dalfox, parse, verify PoCs with headless")
    ap.add_argument('--run-dalfox', action='store_true', help='Run dalfox on targets file (requires dalfox in PATH)')
    ap.add_argument('--targets', help='Targets file (one target per line) for dalfox when --run-dalfox used')
    ap.add_argument('--input', '-i', help='Use existing dalfox output file (mutually exclusive with --run-dalfox)')
    ap.add_argument('--out', '-o', default='reports/results.json', help='Output JSON file')
    ap.add_argument('--report', default='reports/report.txt', help='Text summary report')
    ap.add_argument('--payloads', help='Optional payloads file (one payload per line) to inject into detected params/templates')
    ap.add_argument('--inject', action='store_true', help='Also perform payload injection tests using payloads file (requires payloads and template present)')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(args.report) or '.', exist_ok=True)

    dalfox_out = None
    if args.run_dalfox:
        if not args.targets:
            print("[!] --run-dalfox requires --targets")
            sys.exit(1)
        dalfox_out = 'tmp_dalfox_output.txt'
        run_dalfox_on_targets(args.targets, dalfox_out)
    elif args.input:
        dalfox_out = args.input
    else:
        print("[!] You must provide either --run-dalfox with --targets or --input existing dalfox output.")
        sys.exit(1)

    urls, raw_lines = parse_dalfox_output(dalfox_out)
    print(f"[+] Parsed {len(raw_lines)} raw lines; found {len(urls)} unique URLs/PoCs.")

    payloads = load_payloads(args.payloads) if args.payloads else []
    if args.inject and not payloads:
        print("[!] --inject requires --payloads file. Continuing without injection.")

    results = []
    # مرحله HTTP
    for u in tqdm(urls, desc="HTTP checks"):
        hc = http_check(u)
        entry = {'url': u, 'http_check': hc, 'headless': None, 'notes': [], 'raw_lines': []}
        for rl in raw_lines:
            if u in rl:
                entry['raw_lines'].append(rl)
        results.append(entry)

    # مرحله headless (اگر Playwright نصب است)
    if PLAYWRIGHT_AVAILABLE:
        with sync_playwright() as play:
            for r in tqdm(results, desc="Headless checks"):
                try_headless = False
                hc = r['http_check']
                if not hc:
                    try_headless = False
                else:
                    if hc.get('marker_hits'):
                        try_headless = True
                    elif hc.get('status_code') == 200 and 'text/html' in (hc.get('content_type') or ''):
                        try_headless = True
                if try_headless:
                    r['headless'] = headless_check(play, r['url'])
                else:
                    r['headless'] = {'skipped': True}
    else:
        print("[!] Playwright not available; headless checks skipped. Install playwright to enable them.")

    # optional injection: if user wants to inject payloads into templates
    injection_results = []
    if args.inject and payloads:
        # Simple heuristic: find urls that contain patterns suitable for injection like ?param= or {PAYLOAD} placeholders
        # If targets file used originally, it might include templates; else skip
        # We will attempt to inject into query parameters: replace last '=' with payload
        print("[+] Starting injection tests (simple query-based injection).")
        inj_targets = []
        # build simple templates: if url ends with '=' we can use it as template
        for u in urls:
            if u.endswith('='):
                inj_targets.append(u + "{PAYLOAD}")
            elif "{PAYLOAD}" in u:
                inj_targets.append(u)
        for tmpl in tqdm(inj_targets, desc="Injection targets"):
            tests = inject_payloads_on_url(tmpl, payloads, is_query=True)
            for tu in tests:
                hc = http_check(tu)
                detected = bool(hc.get('marker_hits')) if isinstance(hc, dict) else False
                injection_results.append({'template': tmpl, 'test_url': tu, 'http_check': hc, 'detected_marker_in_body': detected})
        print(f"[+] Injection tests done: {len(injection_results)} attempts.")

    out = {'generated_at': time.asctime(), 'summary': {'num_raw_lines': len(raw_lines), 'num_urls': len(urls)}, 'results': results, 'injection_results': injection_results}
    with open(args.out, 'w', encoding='utf-8') as jf:
        json.dump(out, jf, indent=2, ensure_ascii=False)
    # text report
    with open(args.report, 'w', encoding='utf-8') as rf:
        rf.write(f"Dalfox Auto Full Report - {time.asctime()}\n\n")
        rf.write(f"Parsed raw lines: {len(raw_lines)}\nFound URLs: {len(urls)}\n\n")
        for r in results:
            rf.write(f"URL: {r['url']}\n")
            hc = r['http_check']
            if not hc:
                rf.write("  HTTP: no data\n\n")
                continue
            if 'error' in hc:
                rf.write(f"  HTTP Error: {hc['error']}\n\n")
                continue
            rf.write(f"  HTTP status: {hc.get('status_code')}  Content-Type: {hc.get('content_type')}\n")
            if hc.get('marker_hits'):
                rf.write(f"  Markers in body: {hc.get('marker_hits')}\n")
            if r.get('headless') and r['headless'].get('skipped'):
                rf.write("  Headless: skipped\n")
            elif r.get('headless'):
                hc2 = r['headless']
                if hc2.get('error'):
                    rf.write(f"  Headless error: {hc2['error']}\n")
                else:
                    rf.write(f"  Console messages: {len(hc2.get('console_msgs',[]))}\n")
                    if hc2.get('detected'):
                        rf.write(f"  DETECTED execution markers: {hc2['detected']}\n  RISK: HIGH — possible XSS (manual verification required)\n")
                    else:
                        rf.write("  DETECTED execution markers: none\n")
            rf.write("\n")
        if injection_results:
            rf.write("----- Injection Results -----\n")
            for ir in injection_results:
                rf.write(f"{ir['test_url']} => detected_in_body: {bool(ir['http_check'].get('marker_hits')) if isinstance(ir['http_check'], dict) else 'error'}\n")
    print(f"[+] Done. JSON: {args.out}  Report: {args.report}")

if __name__ == '__main__':
    main()
