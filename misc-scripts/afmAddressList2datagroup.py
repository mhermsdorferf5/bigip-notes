#!/usr/bin/env python3
"""
Convert AFM Address Lists to data-groups.
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

def create_address_dg(name: str, networks: list) -> str:
    if not networks:
        return ""

    dataGroup = f"ltm data-group internal {name} {{\n"
    dataGroup += "    type ip\n"
    dataGroup += "    records {\n"
    for net in sorted(networks, key=lambda n: (n.version, n.network_address, n.prefixlen)):
        dataGroup += f"        {net} {{ }}\n"   
    dataGroup += "    }\n"
    dataGroup += "}\n"

    return dataGroup

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert BIG-IP AFM address lists to data-group stanzas."
    )
    parser.add_argument(
        "config_dir",
        help="Path to the BIG-IP configuration directory",
    )
    parser.add_argument(
        "-o", "--output",
        default="address_data_groups.conf",
        help="Output file for data-group stanzas (default: address_data_groups.conf)",
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

    data_groups = []
    
    for config_file in config_files:
        address_lists = extract_address_lists(config_file)

        for name, stanza in address_lists:
            networks = parse_networks(stanza)
            if not networks:
                continue

            result = create_address_dg(name, networks)
            if result:
                data_groups.append(
                    f"# Converted from {config_file}\n"
                    f"{result}"
                )

    output_path = Path(args.output)
    output_path.write_text("\n\n".join(data_groups) + "\n", encoding="utf-8")
    print(f"Data groups written to {output_path}")


if __name__ == "__main__":
    main()
