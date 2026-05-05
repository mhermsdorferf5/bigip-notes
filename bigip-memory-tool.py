#!/usr/bin/env python3
"""Parse /proc/meminfo and /proc/*/smaps for BIG-IP memory analysis.

Usage:
    cat /proc/meminfo | bigip-memory-tool.py
    bigip-memory-tool.py meminfo.txt
    bigip-memory-tool.py meminfo.txt --proc-dir /path/to/extracted/proc
    bigip-memory-tool.py --proc-dir /proc          # live system, no meminfo needed
"""

import sys
import re
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_meminfo(text):
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if ':' not in line:
            # iHealth/qkviews sometimes strip colons; fall back to 2+ space split
            parts = re.split(r'\s{2,}', line, maxsplit=1)
            if len(parts) == 2:
                key, rest = parts
            else:
                continue
        else:
            key, _, rest = line.partition(':')
        key = key.strip()
        rest = rest.strip()
        if rest.endswith(' kB'):
            try:
                data[key] = int(rest[:-3])
            except ValueError:
                pass
        else:
            try:
                data[key] = int(rest)
            except ValueError:
                data[key] = rest
    return data


_MAPPING_HEADER = re.compile(r'^[0-9a-f]+-[0-9a-f]+\s', re.IGNORECASE)


def parse_smaps(text):
    """Return (total_rss_kb, hugepage_kb) by inspecting KernelPageSize per mapping.

    Each mapping block starts with a hex address-range line.  Within the block,
    KernelPageSize tells us whether the mapping is backed by 4 kB pages (normal)
    or 2048 kB pages (hugepages).  We bucket the block's Rss accordingly.
    """
    rss_total = 0
    rss_huge = 0

    block_rss = 0
    block_page_size = 4  # kB; assume 4 kB until we see KernelPageSize

    def commit():
        nonlocal rss_total, rss_huge
        rss_total += block_rss
        if block_page_size >= 2048:
            rss_huge += block_rss

    in_block = False
    for line in text.splitlines():
        if _MAPPING_HEADER.match(line):
            if in_block:
                commit()
            block_rss = 0
            block_page_size = 4
            in_block = True
            continue

        if not in_block:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(':')
        try:
            val = int(parts[1])
        except ValueError:
            continue

        if key == 'Size':
            block_rss = val
        elif key == 'KernelPageSize':
            block_page_size = val

    if in_block:
        commit()

    return rss_total, rss_huge


def read_proc_name(pid_dir):
    """Return the process name from comm, falling back to cmdline basename."""
    try:
        return (pid_dir / 'comm').read_text().strip()
    except OSError:
        pass
    try:
        cmdline = (pid_dir / 'cmdline').read_text()
        return cmdline.split('\x00')[0].rsplit('/', 1)[-1][:15] or '?'
    except OSError:
        return '?'


def scan_smaps(proc_dir):
    """Scan proc_dir/*/smaps; return list of (pid, name, rss_kb, huge_kb)."""
    results = []
    for smaps_path in sorted(Path(proc_dir).glob('*/smaps')):
        pid_str = smaps_path.parent.name
        if not pid_str.isdigit():
            continue
        try:
            text = smaps_path.read_text(errors='replace')
        except OSError:
            continue
        rss, huge = parse_smaps(text)
        name = read_proc_name(smaps_path.parent)
        results.append((int(pid_str), name, rss, huge))
    return results


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def human(kb):
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.2f} GB"
    elif kb >= 1024:
        return f"{kb / 1024:.2f} MB"
    return f"{kb} KB"


def pct(part, total):
    if total == 0:
        return "n/a"
    return f"{100 * part / total:.1f}%"


def row(label, kb, total_for_pct=None, pct_label=""):
    val = human(kb)
    base = f"  {label:<34} {val:>12}"
    if total_for_pct is not None:
        base += f"  ({pct(kb, total_for_pct):>6} of {pct_label})"
    print(base)


def section(title):
    print()
    print(f"--- {title} " + "-" * (55 - len(title)))


# ---------------------------------------------------------------------------
# Output sections
# ---------------------------------------------------------------------------

def print_meminfo_summary(m):
    total_ram   = m.get("MemTotal", 0)
    mem_free    = m.get("MemFree", 0)
    mem_avail   = m.get("MemAvailable")
    buffers     = m.get("Buffers", 0)
    cached      = m.get("Cached", 0)
    swap_cached = m.get("SwapCached", 0)

    hp_total   = m.get("HugePages_Total", 0)
    hp_free    = m.get("HugePages_Free", 0)
    hp_rsvd    = m.get("HugePages_Rsvd", 0)
    hp_surp    = m.get("HugePages_Surp", 0)
    hp_size_kb = m.get("Hugepagesize", 2048)

    hp_total_kb = hp_total * hp_size_kb
    hp_used_kb  = (hp_total - hp_free) * hp_size_kb
    hp_rsvd_kb  = hp_rsvd * hp_size_kb
    hp_avail_kb = max(0, hp_free - hp_rsvd) * hp_size_kb

    non_hp_total = total_ram - hp_total_kb
    non_hp_free  = mem_free
    reclaimable  = buffers + cached + swap_cached
    non_hp_used  = max(0, non_hp_total - non_hp_free - reclaimable)

    print()
    print("=" * 59)
    print("  Memory Overview")
    print("=" * 59)
    row("Total RAM:", total_ram)
    row("HugePage pool:", hp_total_kb, total_ram, "RAM")
    row("Non-HugePage pool:", non_hp_total, total_ram, "RAM")

    if hp_total == 0:
        print()
        print("  (No HugePages configured)")
    else:
        section("HugePage Memory")
        print(f"  {'HugePage size:':<34} {human(hp_size_kb):>12}")
        print(f"  {'HugePages total (count):':<34} {hp_total:>12,}  ({pct(hp_total_kb, total_ram):>6} of RAM)")
        print(f"  {'HugePages used:':<34} {human(hp_used_kb):>12}  ({pct(hp_used_kb, hp_total_kb):>6} of HugePage pool)")
        print(f"  {'HugePages reserved (not yet used):':<34} {human(hp_rsvd_kb):>12}  ({pct(hp_rsvd_kb, hp_total_kb):>6} of HugePage pool)")
        print(f"  {'HugePages available:':<34} {human(hp_avail_kb):>12}  ({pct(hp_avail_kb, hp_total_kb):>6} of HugePage pool)")
        if hp_surp:
            row("HugePages surplus:", hp_surp * hp_size_kb)

    section("Non-HugePage Memory")
    row("Total non-hugepage pool:", non_hp_total, total_ram, "RAM")
    row("Used (excl. buffers/cache):", non_hp_used, non_hp_total, "non-HP pool")
    row("Buffers + cache (reclaimable):", reclaimable, non_hp_total, "non-HP pool")
    row("Free:", non_hp_free, non_hp_total, "non-HP pool")
    if mem_avail is not None:
        row("Available (incl. reclaimable):", mem_avail, non_hp_total, "non-HP pool")


def print_smaps_summary(procs, show_all):
    """Print per-process hugepage usage table.

    procs: list of (pid, name, rss_kb, huge_kb)
    """
    if not procs:
        section("Process HugePage Usage")
        print("  (no smaps data found)")
        return

    huge_users = [(pid, name, rss, huge) for pid, name, rss, huge in procs if huge > 0]
    huge_users.sort(key=lambda x: x[3], reverse=True)

    normal_only = [p for p in procs if p[3] == 0]
    normal_rss_total = sum(p[2] for p in normal_only)

    section("Process HugePage Usage")

    if not huge_users:
        print("  No processes using hugepages found.")
    else:
        # Column widths
        W_PID  = 7
        W_NAME = 20
        W_HP   = 14
        W_NHP  = 14
        W_RSS  = 14

        header = (
            f"  {'PID':>{W_PID}}  {'Name':<{W_NAME}}"
            f"  {'HugePage':>{W_HP}}  {'%':>5}"
            f"  {'Non-HugePage':>{W_NHP}}  {'%':>5}"
            f"  {'Total RSS':>{W_RSS}}"
        )
        print(header)
        print("  " + "-" * (W_PID + W_NAME + W_HP + W_NHP + W_RSS + 26))

        for pid, name, rss, huge in huge_users:
            non_huge = max(0, rss - huge)
            print(
                f"  {pid:>{W_PID}}  {name:<{W_NAME}}"
                f"  {human(huge):>{W_HP}}  {pct(huge, rss):>5}"
                f"  {human(non_huge):>{W_NHP}}  {pct(non_huge, rss):>5}"
                f"  {human(rss):>{W_RSS}}"
            )

        if show_all and normal_only:
            print()
            print(f"  --- Processes using only 4KB pages ---")
            print(header)
            print("  " + "-" * (W_PID + W_NAME + W_HP + W_NHP + W_RSS + 26))
            for pid, name, rss, _ in sorted(normal_only, key=lambda x: x[2], reverse=True):
                print(
                    f"  {pid:>{W_PID}}  {name:<{W_NAME}}"
                    f"  {'0 KB':>{W_HP}}  {'0.0%':>5}"
                    f"  {human(rss):>{W_NHP}}  {'100.0%':>5}"
                    f"  {human(rss):>{W_RSS}}"
                )
        elif normal_only:
            print()
            n = len(normal_only)
            print(f"  {n} other process{'es' if n != 1 else ''} using only 4KB pages,"
                  f" total RSS: {human(normal_rss_total)}"
                  f"  (use --all-procs to list)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Summarize BIG-IP /proc/meminfo and per-process smaps memory usage.",
        epilog=(
            "Reads meminfo from stdin if no file is given.\n"
            "smaps are read from --proc-dir (default: /proc)."
        ),
    )
    ap.add_argument("file", nargs="?", help="saved /proc/meminfo file")
    ap.add_argument(
        "--proc-dir", default="/proc", metavar="DIR",
        help="proc filesystem root for smaps scanning (default: /proc)",
    )
    ap.add_argument(
        "--all-procs", action="store_true",
        help="also list processes that use only 4KB pages",
    )
    ap.add_argument(
        "--no-smaps", action="store_true",
        help="skip smaps scanning entirely",
    )
    args = ap.parse_args()

    # --- meminfo ---
    if args.file:
        with open(args.file, encoding='utf-8', errors='replace') as fh:
            meminfo_text = fh.read()
    elif not sys.stdin.isatty():
        meminfo_text = sys.stdin.buffer.read().decode('utf-8', errors='replace')
    else:
        # No meminfo input; still show smaps if proc-dir is available
        meminfo_text = None

    if meminfo_text:
        m = parse_meminfo(meminfo_text)
        if not m:
            print("WARNING: meminfo parsed no values — check file format.", file=sys.stderr)
        print_meminfo_summary(m)
    else:
        # Try reading meminfo directly from proc-dir
        meminfo_path = Path(args.proc_dir) / 'meminfo'
        if meminfo_path.exists():
            m = parse_meminfo(meminfo_path.read_text(errors='replace'))
            print_meminfo_summary(m)
        else:
            print("(No meminfo input; pass a file or pipe cat /proc/meminfo)", file=sys.stderr)

    # --- smaps ---
    if not args.no_smaps:
        proc_path = Path(args.proc_dir)
        if not proc_path.is_dir():
            print(f"\n(smaps skipped: {args.proc_dir} not found)", file=sys.stderr)
        else:
            procs = scan_smaps(proc_path)
            print_smaps_summary(procs, args.all_procs)

    print()


if __name__ == "__main__":
    main()
