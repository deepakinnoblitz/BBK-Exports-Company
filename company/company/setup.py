# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import os
import getpass
import click
from frappe.utils import get_bench_path

DAEMON_PROCFILE_LINE = "biometric_sync: env/bin/python -m company.company.biometric.sync_daemon"


def setup_biometric_daemon():
    """
    Automatically registers the dedicated biometric sync daemon into Procfile
    and supervisor.conf (if present).
    Attached to after_install and after_migrate hooks in hooks.py.
    """
    bench_path = get_bench_path()
    procfile_path = os.path.join(bench_path, "Procfile")
    supervisor_conf_path = os.path.join(bench_path, "config", "supervisor.conf")

    procfile_updated = False
    procfile_already_present = False
    supervisor_updated = False

    # 1. Automatically update Procfile (Development / bench start)
    if os.path.exists(procfile_path):
        try:
            with open(procfile_path, "r") as f:
                content = f.read()

            if "biometric_sync:" not in content:
                with open(procfile_path, "a") as f:
                    f.write(f"\n{DAEMON_PROCFILE_LINE}\n")
                procfile_updated = True
            else:
                procfile_already_present = True
        except Exception as e:
            click.secho(f"[!] Warning: Could not update Procfile: {e}", fg="yellow")

    # 2. Automatically update supervisor.conf (Production, if generated)
    if os.path.exists(supervisor_conf_path):
        supervisor_updated = patch_supervisor_config(supervisor_conf_path, bench_path)

    # 3. Print the confirmation banner in terminal
    click.secho("\n" + "=" * 62, fg="green", bold=True)
    click.secho("✓ Biometric Sync Daemon Setup Completed", fg="green", bold=True)
    if procfile_updated:
        click.secho("  • Procfile: Registered 'biometric_sync'", fg="cyan")
    elif procfile_already_present:
        click.secho("  • Procfile: 'biometric_sync' is already active", fg="cyan")
    if supervisor_updated:
        click.secho("  • Supervisor: Registered biometric-sync program in supervisor.conf", fg="cyan")
    click.secho("=" * 62 + "\n", fg="green", bold=True)


def patch_supervisor_config(conf_path, bench_path):
    """
    Injects biometric-sync program into supervisor.conf if not already present.
    """
    try:
        with open(conf_path, "r") as f:
            content = f.read()

        if "biometric-sync" in content:
            return False

        bench_name = os.path.basename(bench_path)
        user = getpass.getuser()

        program_block = f"""
[program:{bench_name}-biometric-sync]
command={bench_path}/env/bin/python -m company.company.biometric.sync_daemon
priority=4
autostart=true
autorestart=true
stdout_logfile={bench_path}/logs/biometric-sync.log
stderr_logfile={bench_path}/logs/biometric-sync.error.log
user={user}
directory={bench_path}
startretries=10
"""
        content += f"\n{program_block}\n"

        # Add to workers group if present
        group_target = f"[group:{bench_name}-workers]"
        if group_target in content:
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("programs=") and group_target in "\n".join(lines[max(0, i - 5):i]):
                    lines[i] = f"{line},{bench_name}-biometric-sync"
                    break
            content = "\n".join(lines)

        with open(conf_path, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        click.secho(f"[!] Warning: Could not update supervisor.conf: {e}", fg="yellow")
        return False

