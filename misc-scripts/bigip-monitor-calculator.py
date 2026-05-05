#!/usr/bin/env python3
"""
BIG-IP Monitor Load Calculator

Parses a BIG-IP configuration file and reports:
  - Per-pool monitor instance counts and check rates
  - Warnings for short intervals, short timeouts, and multi-monitor pools
  - Optimization suggestions for reducing check volume

Usage:
    python bigip-monitor-caculator.py <bigip.conf>
    
If you have partitions, you can create a merged bigip.conf file using the following:
find /config/ -iname "bigip.conf" -not -ipath "*.bak*" -not -ipath "*.diffVer*" -exec cat {} \\; > /var/tmp/merged-bigip.conf
"""

import re
import sys
import argparse
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Set
from collections import defaultdict


DEFAULT_INTERVAL  = 5
DEFAULT_TIMEOUT   = 16
MIN_SAFE_INTERVAL = 5
NICE_INTERVALS    = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Monitor:
    name: str
    monitor_type: str = "unknown"
    interval: Optional[int] = None
    timeout:  Optional[int] = None
    defaults_from: Optional[str] = None

    def get_interval(self, all_monitors: "Dict[str, Monitor]",
                     _seen: Optional[Set[str]] = None) -> int:
        if _seen is None:
            _seen = set()
        if self.name in _seen:
            return DEFAULT_INTERVAL
        _seen.add(self.name)
        if self.interval is not None:
            return self.interval
        if self.defaults_from and self.defaults_from in all_monitors:
            return all_monitors[self.defaults_from].get_interval(all_monitors, _seen)
        return DEFAULT_INTERVAL

    def get_timeout(self, all_monitors: "Dict[str, Monitor]",
                    _seen: Optional[Set[str]] = None) -> int:
        if _seen is None:
            _seen = set()
        if self.name in _seen:
            return DEFAULT_TIMEOUT
        _seen.add(self.name)
        if self.timeout is not None:
            return self.timeout
        if self.defaults_from and self.defaults_from in all_monitors:
            return all_monitors[self.defaults_from].get_timeout(all_monitors, _seen)
        return DEFAULT_TIMEOUT


@dataclass
class PoolMember:
    name: str
    monitors: List[str] = field(default_factory=list)


@dataclass
class Pool:
    name: str
    monitors: List[str] = field(default_factory=list)
    members: List[PoolMember] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_block(text: str, brace_pos: int) -> Tuple[str, int]:
    """
    Return (inner_content, closing_brace_index) for the block starting
    at the opening '{' at brace_pos.  Handles nested braces and quoted strings.
    """
    depth = 0
    in_str = False
    str_char = ""
    pos = brace_pos
    while pos < len(text):
        c = text[pos]
        if in_str:
            if c == "\\" and pos + 1 < len(text):
                pos += 2
                continue
            if c == str_char:
                in_str = False
        elif c in ('"', "'"):
            in_str = True
            str_char = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[brace_pos + 1 : pos], pos
        pos += 1
    raise ValueError(f"Unmatched '{{' at position {brace_pos}")


def normalize_name(name: str) -> str:
    """Add /Common/ partition prefix to unqualified BIG-IP object names."""
    name = name.strip()
    if not name or name.lower() == "none":
        return ""
    if name.startswith("/"):
        return name
    return f"/Common/{name}"


def parse_monitor_names(text: str) -> List[str]:
    """
    Parse a monitor field value into a list of normalized monitor names.
    Handles:
      /Common/http
      /Common/http and /Common/tcp
      min 1 of { /Common/http /Common/tcp }
    """
    text = text.strip()
    if not text or text.lower() == "none":
        return []
    # min N of { name name ... }
    m = re.search(r"\bof\s*\{([^}]*)\}", text)
    if m:
        return [normalize_name(n) for n in m.group(1).split() if n.strip()]
    # name [and name ...]
    result = []
    for part in re.split(r"\s+and\s+", text, flags=re.IGNORECASE):
        n = normalize_name(part.strip())
        if n:
            result.append(n)
    return result


def parse_members(text: str) -> List[PoolMember]:
    """Parse the interior of a  members { }  block into PoolMember objects."""
    members: List[PoolMember] = []
    pos = 0
    header_re = re.compile(r"(\S+)\s*\{")
    while pos < len(text):
        m = header_re.search(text, pos)
        if not m:
            break
        name = m.group(1)
        try:
            inner, end_pos = extract_block(text, m.end() - 1)
        except ValueError:
            break
        member = PoolMember(name=name)
        mon_m = re.search(r"\bmonitor\s+(.+?)(?:\n|$)", inner)
        if mon_m:
            member.monitors = parse_monitor_names(mon_m.group(1).strip())
        members.append(member)
        pos = end_pos + 1
    return members


def parse_config(text: str) -> Tuple[Dict[str, Monitor], List[Pool]]:
    """Parse all ltm monitor and ltm pool stanzas from BIG-IP config text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # ── Monitors ──────────────────────────────────────────────────────────────
    monitors: Dict[str, Monitor] = {}
    for m in re.finditer(r"\bltm\s+monitor\s+(\S+)\s+(\S+)\s*\{", text):
        mon_type = m.group(1)
        mon_name = normalize_name(m.group(2))
        if not mon_name:
            continue
        try:
            inner, _ = extract_block(text, m.end() - 1)
        except ValueError:
            continue
        mon = Monitor(name=mon_name, monitor_type=mon_type)
        iv_m = re.search(r"\binterval\s+(\d+)", inner)
        if iv_m:
            mon.interval = int(iv_m.group(1))
        to_m = re.search(r"\btimeout\s+(\d+)", inner)
        if to_m:
            mon.timeout = int(to_m.group(1))
        df_m = re.search(r"\bdefaults-from\s+(\S+)", inner)
        if df_m:
            df_name = normalize_name(df_m.group(1))
            if df_name:
                mon.defaults_from = df_name
        monitors[mon_name] = mon

    # ── Pools ─────────────────────────────────────────────────────────────────
    pools: List[Pool] = []
    for m in re.finditer(r"\bltm\s+pool\s+(\S+)\s*\{", text):
        pool_name = m.group(1)
        try:
            inner, _ = extract_block(text, m.end() - 1)
        except ValueError:
            continue
        pool = Pool(name=pool_name)

        # Extract members sub-block first, then look for pool-level monitor
        mm = re.search(r"\bmembers\s*\{", inner)
        if mm:
            try:
                members_inner, end_pos = extract_block(inner, mm.end() - 1)
                pool.members = parse_members(members_inner)
                stripped = inner[: mm.start()] + inner[end_pos + 1 :]
            except ValueError:
                stripped = inner
        else:
            stripped = inner

        mon_m = re.search(r"^\s*monitor\s+(.+?)(?:\s*\n|\s*$)", stripped, re.MULTILINE)
        if mon_m:
            pool.monitors = parse_monitor_names(mon_m.group(1))

        pools.append(pool)

    return monitors, pools


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def checks_per_minute(instances: int, interval: int) -> float:
    return (instances * 60.0) / max(interval, 1)


def resolve_interval(mon_name: str,
                     monitors: Dict[str, Monitor]) -> Tuple[int, bool]:
    """Return (interval_seconds, is_assumed). is_assumed when not in config."""
    if mon_name in monitors:
        return monitors[mon_name].get_interval(monitors), False
    return DEFAULT_INTERVAL, True


def resolve_timeout(mon_name: str,
                    monitors: Dict[str, Monitor]) -> Tuple[int, bool]:
    if mon_name in monitors:
        return monitors[mon_name].get_timeout(monitors), False
    return DEFAULT_TIMEOUT, True


@dataclass
class PoolStats:
    pool: Pool
    monitor_instances: Dict[str, int]   # monitor_name -> instance count
    total_instances: int
    checks_per_min: float
    assumed_monitors: Set[str]


def calc_pool_stats(pool: Pool, monitors: Dict[str, Monitor]) -> PoolStats:
    """Calculate monitoring load for a single pool."""
    mon_inst: Dict[str, int] = defaultdict(int)
    assumed:  Set[str] = set()

    for member in pool.members:
        # Per-member monitor overrides pool-level monitor
        active = member.monitors if member.monitors else pool.monitors
        for mn in active:
            mon_inst[mn] += 1

    for mn in list(mon_inst.keys()):
        _, is_assumed = resolve_interval(mn, monitors)
        if is_assumed:
            assumed.add(mn)

    total_inst = sum(mon_inst.values())
    total_cpm = sum(
        checks_per_minute(cnt, resolve_interval(mn, monitors)[0])
        for mn, cnt in mon_inst.items()
    )
    return PoolStats(
        pool=pool,
        monitor_instances=dict(mon_inst),
        total_instances=total_inst,
        checks_per_min=total_cpm,
        assumed_monitors=assumed,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt(n: float, dec: int = 1) -> str:
    """Format a number, removing a trailing '.0' when the value is whole."""
    rounded = round(n, dec)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{dec}f}"


def next_nice_interval(current: int) -> int:
    """Return the next 'nice' interval that is at least 2× the current."""
    target = current * 2
    for n in NICE_INTERVALS:
        if n >= target:
            return n
    return current * 2


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

POOL_CPS_THRESHOLD   = 10.0   # hide pools below this checks/sec by default
OPT_PCT_THRESHOLD    =  1.0   # hide suggestions below this % savings by default


def run(config_path: str, show_all: bool = False) -> None:
    try:
        with open(config_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        sys.exit(f"Error reading {config_path}: {exc}")

    monitors, pools = parse_config(text)
    all_stats = [calc_pool_stats(p, monitors) for p in pools]

    # Aggregate global monitor instance counts
    global_inst: Dict[str, int] = defaultdict(int)
    for ps in all_stats:
        for mn, cnt in ps.monitor_instances.items():
            global_inst[mn] += cnt

    all_assumed   = {mn for ps in all_stats for mn in ps.assumed_monitors}
    total_inst    = sum(global_inst.values())
    total_cpm_val = sum(ps.checks_per_min for ps in all_stats)
    total_cps_val = total_cpm_val / 60.0

    W = 74  # report width

    # ── Header ───────────────────────────────────────────────────────────────
    print("=" * W)
    print("  BIG-IP Monitor Load Calculator")
    print(f"  Config : {config_path}")
    print("=" * W)

    # ── Per-pool breakdown ────────────────────────────────────────────────────
    print()
    print("-- Pool Monitor Breakdown " + "-" * (W - 26))
    print()

    max_name = max((len(ps.pool.name) for ps in all_stats), default=20)
    max_name = max(max_name, 28)
    C = (max_name + 2, 10, 12, 14)   # column widths: name, instances, cpm, cps

    print(f"  {'Pool':<{C[0]}} {'Instances':>{C[1]}} {'Chks/Min':>{C[2]}} {'Chks/Sec':>{C[3]}}")
    print("  " + "-" * (sum(C) + 3))

    hidden_pool_count = 0
    for ps in sorted(all_stats, key=lambda x: x.checks_per_min, reverse=True):
        cps_val = ps.checks_per_min / 60.0
        if not show_all and (not ps.monitor_instances or cps_val <= POOL_CPS_THRESHOLD):
            hidden_pool_count += 1
            continue
        if not ps.monitor_instances:
            print(f"  {ps.pool.name:<{C[0]}} {'-':>{C[1]}} {'-':>{C[2]}} {'-':>{C[3]}}  (no monitor)")
            continue
        print(f"  {ps.pool.name:<{C[0]}} "
              f"{ps.total_instances:>{C[1]}} "
              f"{fmt(ps.checks_per_min):>{C[2]}} "
              f"{fmt(cps_val, 3):>{C[3]}}")
        for mn in sorted(ps.monitor_instances):
            cnt = ps.monitor_instances[mn]
            iv, assumed = resolve_interval(mn, monitors)
            mon_cpm = checks_per_minute(cnt, iv)
            tag  = " *interval assumed" if assumed else ""
            label = f"    {mn}{tag}"
            print(f"  {label:<{C[0]}} "
                  f"{cnt:>{C[1]}} "
                  f"{fmt(mon_cpm):>{C[2]}} "
                  f"{fmt(mon_cpm / 60.0, 3):>{C[3]}}  (interval={iv}s)")
    if hidden_pool_count:
        print(f"  ... {hidden_pool_count} pool(s) with <= {POOL_CPS_THRESHOLD} chks/sec hidden"
              f" (use --all to show)")
    print()

    # ── Warnings ─────────────────────────────────────────────────────────────
    warnings: List[str] = []

    for mn in sorted(monitors):
        mon = monitors[mn]
        iv = mon.get_interval(monitors)
        to = mon.get_timeout(monitors)
        if iv < MIN_SAFE_INTERVAL:
            warnings.append(
                f"[SHORT INTERVAL]  {mn}\n"
                f"                  interval={iv}s  (minimum recommended: {MIN_SAFE_INTERVAL}s)"
            )
        min_to = iv * 3 + 1
        if to < min_to:
            warnings.append(
                f"[SHORT TIMEOUT]   {mn}\n"
                f"                  timeout={to}s < recommended minimum "
                f"{min_to}s  (interval {iv}s x 3 + 1 = {min_to}s)"
            )

    for ps in sorted(all_stats, key=lambda x: x.pool.name):
        p = ps.pool
        if len(p.monitors) <= 1:
            continue
        # Members whose monitoring comes from pool-level monitors
        pool_mbr_count = sum(1 for mb in p.members if not mb.monitors)
        # Members with per-member override (count their individual monitor instances)
        override_inst  = sum(len(mb.monitors) for mb in p.members if mb.monitors)
        current_inst   = pool_mbr_count * len(p.monitors) + override_inst
        single_inst    = pool_mbr_count * 1               + override_inst
        warnings.append(
            f"[MULTI-MONITOR]   {p.name}\n"
            f"                  Monitors: {', '.join(p.monitors)}\n"
            f"                  Instances with all monitors : {current_inst}\n"
            f"                  Instances with single monitor: {single_inst}"
        )

    for mn in sorted(all_assumed):
        warnings.append(
            f"[NOT IN CONFIG]   {mn}\n"
            f"                  Monitor definition not found; "
            f"assuming interval={DEFAULT_INTERVAL}s, timeout={DEFAULT_TIMEOUT}s"
        )

    if warnings:
        print("-- Warnings " + "-" * (W - 12))
        print()
        for w in warnings:
            for line in w.split("\n"):
                print(f"  {line}")
            print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("-- Summary " + "-" * (W - 11))
    print()
    print(f"  Pools parsed              : {len(pools)}")
    print(f"  Monitor definitions found : {len(monitors)}")
    print(f"  Total monitor instances   : {total_inst}")
    print(f"  Total checks / minute     : {fmt(total_cpm_val)}")
    print(f"  Total checks / second     : {fmt(total_cps_val, 3)}")
    print()

    # ── Optimization suggestions ──────────────────────────────────────────────
    # Rank monitors by current check volume; suggest doubling the interval
    candidates = sorted(
        [(mn, cnt) for mn, cnt in global_inst.items() if cnt >= 2],
        key=lambda x: checks_per_minute(x[1], resolve_interval(x[0], monitors)[0]),
        reverse=True,
    )

    suggestions: List[Tuple] = []
    for mn, cnt in candidates:
        iv, _ = resolve_interval(mn, monitors)
        to, _ = resolve_timeout(mn, monitors)
        new_iv = next_nice_interval(iv)
        if new_iv <= iv:
            continue
        # Never reduce timeout below the new safe minimum
        new_to  = max(new_iv * 3 + 1, to)
        old_cpm = checks_per_minute(cnt, iv)
        new_cpm = checks_per_minute(cnt, new_iv)
        savings = old_cpm - new_cpm
        suggestions.append((mn, cnt, iv, to, new_iv, new_to, old_cpm, new_cpm, savings))

    print("-- Optimization Suggestions " + "-" * (W - 28))
    print()

    if not suggestions:
        print("  No significant optimization opportunities identified.")
        print()
        return

    print("  Monitors below are ranked by current check volume. Doubling the")
    print("  interval halves the number of checks sent to those targets.")
    print()

    visible   = [s for s in suggestions
                 if show_all or (s[8] / total_cpm_val * 100 if total_cpm_val else 0) > OPT_PCT_THRESHOLD]
    hidden_ct = len(suggestions) - len(visible)

    projected_cpm = total_cpm_val
    for mn, cnt, iv, to, new_iv, new_to, old_c, new_c, sav in suggestions:
        projected_cpm -= sav   # always deduct all savings for accurate combined total

    for mn, cnt, iv, to, new_iv, new_to, old_c, new_c, sav in visible:
        pct = (sav / total_cpm_val * 100) if total_cpm_val > 0 else 0.0
        tag = "  [assumed - not in config]" if mn in all_assumed else ""
        print(f"  {mn}{tag}")
        print(f"    Instances : {cnt}")
        print(f"    Current   : interval={iv}s, timeout={to}s"
              f"  -> {fmt(old_c)} chks/min  ({fmt(old_c / 60, 3)} chks/sec)")
        print(f"    Proposed  : interval={new_iv}s, timeout={new_to}s"
              f"  -> {fmt(new_c)} chks/min  ({fmt(new_c / 60, 3)} chks/sec)")
        print(f"    Saves     : {fmt(sav)} chks/min  ({pct:.1f}% of current total)")
        print()

    if hidden_ct:
        print(f"  ... {hidden_ct} suggestion(s) with <= {OPT_PCT_THRESHOLD}% savings hidden"
              f" (use --all to show)")
        print()

    print(f"  -- Combined impact if all suggestions applied --")
    print(f"  Current  : {fmt(total_cpm_val)} chks/min  "
          f"({fmt(total_cps_val, 3)} chks/sec)")
    print(f"  Proposed : {fmt(projected_cpm)} chks/min  "
          f"({fmt(projected_cpm / 60.0, 3)} chks/sec)")
    if total_cpm_val > 0:
        pct_saved = (total_cpm_val - projected_cpm) / total_cpm_val * 100
        print(f"  Reduction: {fmt(total_cpm_val - projected_cpm)} chks/min  "
              f"({pct_saved:.1f}%)")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Calculate BIG-IP health-monitor load from a .conf file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="  Example: %(prog)s /var/tmp/bigip_base.conf",
    )
    ap.add_argument("config_file", help="Path to BIG-IP configuration file")
    ap.add_argument(
        "--all", dest="show_all", action="store_true",
        help=(f"Show all pools (default hides pools with <= {POOL_CPS_THRESHOLD} chks/sec) "
              f"and all optimization suggestions (default hides those saving <= {OPT_PCT_THRESHOLD}%% of total)"),
    )
    args = ap.parse_args()
    run(args.config_file, show_all=args.show_all)


if __name__ == "__main__":
    main()
