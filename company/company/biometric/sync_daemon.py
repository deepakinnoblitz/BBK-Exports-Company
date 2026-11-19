# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import os
import sys
import time
import signal
from datetime import timedelta

import frappe
from frappe.utils import get_bench_path, now_datetime, get_datetime, cint

running = True


def handle_shutdown(sig, frame):
    global running
    print("\n[!] Biometric Sync Daemon received shutdown signal. Exiting gracefully...")
    running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def get_bench_sites(bench_path: str):
    """
    Discover all active sites in sites/ directory with site_config.json.
    100% dynamic - zero hardcoded site names.
    """
    sites_dir = os.path.join(bench_path, "sites")
    sites = []
    if os.path.exists(sites_dir):
        for item in sorted(os.listdir(sites_dir)):
            site_path = os.path.join(sites_dir, item)
            config_file = os.path.join(site_path, "site_config.json")
            if os.path.isdir(site_path) and os.path.exists(config_file):
                sites.append(item)
    return sites


def sync_site_biometric(site: str, sites_dir: str):
    """
    Process biometric sync for a single site if enabled in Biometric Settings.
    """
    try:
        if os.path.exists(sites_dir) and os.getcwd() != sites_dir:
            os.chdir(sites_dir)

        frappe.init(site=site, sites_path=sites_dir)
        frappe.connect()

        # 1. Skip if company app is not installed on this site
        if "company" not in frappe.get_installed_apps():
            return

        # 2. Check Biometric Settings
        settings = frappe.get_single("Biometric Settings")
        if not getattr(settings, "enabled", False) or not getattr(settings, "auto_sync_enabled", False):
            return

        from company.company.biometric.biometric_sync import evaluate_and_run_scheduled_sync
        evaluate_and_run_scheduled_sync()
        frappe.db.commit()

    except Exception as e:
        print(f"[!] Error accessing site {site}: {e}")
    finally:
        frappe.destroy()


def run_daemon():
    """
    Main loop for the dedicated biometric sync daemon.
    Discovers all sites dynamically and checks for sync readiness every 15s.
    """
    bench_path = get_bench_path()
    sites_dir = os.path.join(bench_path, "sites")
    # Frappe logger expects cwd to be the 'sites' directory so '../logs' resolves correctly
    if os.path.exists(sites_dir):
        os.chdir(sites_dir)

    print("=" * 64)
    print(" [*] SmartOffice Biometric Sync Daemon Started")
    print(f" [*] Bench Path: {bench_path}")
    print(" [*] Dynamic Site Discovery Active. Checking every 15s...")
    print("=" * 64)

    while running:
        try:
            sites = get_bench_sites(bench_path)
            for site in sites:
                if not running:
                    break
                sync_site_biometric(site, sites_dir)
        except Exception as e:
            print(f"[!] Unexpected error in daemon iteration: {e}")

        # Sleep in 1-second chunks for 15s to react instantly to shutdown signals (SIGINT/SIGTERM)
        for _ in range(15):
            if not running:
                break
            time.sleep(1)

    print("[*] Biometric Sync Daemon stopped cleanly.")


if __name__ == "__main__":
    run_daemon()
