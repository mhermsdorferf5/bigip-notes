#!/usr/bin/env python3
"""
Optimize F5 BIG-IP net address-list configurations by:
  - Removing redundant subnets (overlapped by a larger network in the same list)
  - Consolidating adjacent subnets of the same prefix length into a supernet

Reads all bigip.conf and bigip_base.conf files from a BIG-IP config directory
(including partition subdirectories).
"""

import argparse
import sys
from ipaddress import ip_network, collapse_addresses, IPv4Network, IPv6Network
from pathlib import Path


CONFIG_FILENAMES = ("bigip.conf", "bigip_base.conf")


# ---------------------------------------------------------------------------
# Config file discovery (same logic as bigipConfigParser_getAFMConfig.py)
# ---------------------------------------------------------------------------

def find_config_files(config_dir: Path) -> list[Path]:
    """Find all bigip.conf and bigip_base.conf files in the config directory."""
    files = []
    for filename in CONFIG_FILENAMES:
        f = config_dir / filename
        if f.exists():
            files.append(f)

    partitions_dir = config_dir / "partitions"
    if partitions_dir.is_dir():
        for part_dir in sorted(partitions_dir.iterdir()):
            if part_dir.is_dir():
                for filename in CONFIG_FILENAMES:
                    f = part_dir / filename
                    if f.exists():
                        files.append(f)

    return files


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_address_lists(file_path: Path) -> list[tuple[str, str]]:
    """Return list of (name, stanza_text) for each net address-list stanza."""
    results = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
        return results

    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("net address-list "):
            parts = stripped.split()
            name = parts[2] if len(parts) >= 3 else stripped

            stanza_lines = [lines[i]]
            brace_depth = lines[i].count("{") - lines[i].count("}")
            i += 1
            while i < len(lines) and brace_depth > 0:
                stanza_lines.append(lines[i])
                brace_depth += lines[i].count("{") - lines[i].count("}")
                i += 1

            results.append((name, "".join(stanza_lines)))
        else:
            i += 1

    return results


def parse_networks(stanza: str) -> list:
    """Extract IP network objects from the 'addresses' block of a stanza."""
    networks = []
    in_addresses = False
    depth = 0

    for line in stanza.splitlines():
        stripped = line.strip()
        if stripped == "addresses {":
            in_addresses = True
            depth = 1
            continue
        if in_addresses:
            depth += stripped.count("{") - stripped.count("}")
            if depth <= 0:
                in_addresses = False
                continue
            # Each entry looks like: "1.2.3.4/24 { }" — grab the address part
            addr = stripped.split("{")[0].strip()
            if addr:
                try:
                    networks.append(ip_network(addr, strict=False))
                except ValueError:
                    pass  # Skip non-IP lines (e.g. address-lists references)

    return networks


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _collapse_by_version(networks: list) -> list:
    """Collapse networks, handling IPv4 and IPv6 separately."""
    v4 = [n for n in networks if isinstance(n, IPv4Network)]
    v6 = [n for n in networks if isinstance(n, IPv6Network)]
    result = []
    if v4:
        result.extend(collapse_addresses(v4))
    if v6:
        result.extend(collapse_addresses(v6))
    return result


def analyze_address_list(networks: list) -> dict | None:
    """
    Analyze an address list for overlaps and consolidation opportunities.

    Returns a dict with findings, or None if no optimization is possible.
    """
    if len(networks) < 2:
        return None

    original = sorted(set(networks), key=lambda n: (n.version, n.network_address, n.prefixlen))
    collapsed = sorted(_collapse_by_version(original), key=lambda n: (n.version, n.network_address, n.prefixlen))

    if original == collapsed:
        return None

    original_set = set(original)

    # Overlaps: entries in the original that are a strict subnet of another original entry
    overlaps = []
    for net in original:
        for other in original:
            if net != other and net.subnet_of(other):
                overlaps.append((net, other))
                break

    # Consolidations: collapsed entries that are new supernets not present in the original
    new_supernets = [n for n in collapsed if n not in original_set]
    consolidations = []
    for supernet in new_supernets:
        members = [n for n in original if n == supernet or n.subnet_of(supernet)]
        consolidations.append((supernet, members))

    return {
        "original": original,
        "optimized": collapsed,
        "overlaps": overlaps,
        "consolidations": consolidations,
        "saved": len(original) - len(collapsed),
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_summary(name: str, source: Path, result: dict) -> str:
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"Address List : {name}")
    lines.append(f"Source       : {source}")
    lines.append(f"Original     : {len(result['original'])} entries")
    lines.append(f"Optimized    : {len(result['optimized'])} entries  (saves {result['saved']})")

    return "\n".join(lines)

def format_report(name: str, source: Path, result: dict) -> str:
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"Address List : {name}")
    lines.append(f"Source       : {source}")
    lines.append(f"Original     : {len(result['original'])} entries")
    lines.append(f"Optimized    : {len(result['optimized'])} entries  (saves {result['saved']})")

    if result["overlaps"]:
        lines.append(f"\n  Overlapping entries ({len(result['overlaps'])} found):")
        for subnet, parent in result["overlaps"]:
            lines.append(f"    {subnet}  is already covered by  {parent}  -> remove {subnet}")

    if result["consolidations"]:
        lines.append(f"\n  Consolidation opportunities ({len(result['consolidations'])} found):")
        for supernet, members in result["consolidations"]:
            member_str = ", ".join(str(m) for m in members)
            lines.append(f"    {member_str}  ->  {supernet}")

    return "\n".join(lines)


def format_optimized_stanza(name: str, networks: list) -> str:
    lines = []
    lines.append(f"net address-list {name} {{")
    lines.append("    addresses {")
    for net in sorted(networks, key=lambda n: (n.version, n.network_address, n.prefixlen)):
        lines.append(f"        {net} {{ }}")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Optimize BIG-IP net address-list stanzas."
    )
    parser.add_argument(
        "config_dir",
        help="Path to the BIG-IP configuration directory",
    )
    parser.add_argument(
        "-o", "--output",
        default="optimized_address_lists.conf",
        help="Output file for optimized address-list stanzas (default: optimized_address_lists.conf)",
    )
    parser.add_argument(
        "-r", "--report",
        default=None,
        help="Write findings report to this file instead of printing to console",
    )
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    if not config_dir.is_dir():
        print(f"Error: '{config_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    config_files = find_config_files(config_dir)
    if not config_files:
        print(f"No config files found in '{config_dir}'.", file=sys.stderr)
        sys.exit(1)

    report_sections = []
    summary_sections = []
    optimized_stanzas = []
    total_lists = 0
    total_optimized = 0
    total_saved = 0

    for config_file in config_files:
        address_lists = extract_address_lists(config_file)
        total_lists += len(address_lists)

        for name, stanza in address_lists:
            networks = parse_networks(stanza)
            if not networks:
                continue

            result = analyze_address_list(networks)
            if result:
                total_optimized += 1
                total_saved += result["saved"]
                report_sections.append(format_report(name, config_file, result))
                summary_sections.append(format_summary(name, config_file, result))
                optimized_stanzas.append(
                    f"# Optimized from {config_file}\n"
                    + format_optimized_stanza(name, result["optimized"])
                )
            else:
                optimized_stanzas.append(
                    f"# Unchanged from {config_file}\n"
                    + format_optimized_stanza(name, networks)
                )

    summary = (
        f"\n"
        f"\n{'='*70}"
        f"\nSummary: scanned {total_lists} address list(s) across {len(config_files)} file(s)."
        f"\n         {total_optimized} list(s) can be optimized, saving {total_saved} total entries."
        f"\n{'='*70}"
    )
    summary += "".join(summary_sections) + "\n"
    summary += f"\n{'='*70}\n\n"

    full_report = "".join(report_sections) + "\n" + summary

    if args.report:
        Path(args.report).write_text(full_report, encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(full_report)

    output_path = Path(args.output)
    output_path.write_text("\n\n".join(optimized_stanzas) + "\n", encoding="utf-8")
    print(f"Optimized address lists written to {output_path}")


if __name__ == "__main__":
    main()
