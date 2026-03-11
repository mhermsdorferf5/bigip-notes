#!/usr/bin/env python3
"""
Extract AFM-related configuration stanzas from F5 BIG-IP configuration files.

Reads all bigip.conf and bigip_base.conf files from a BIG-IP config directory
(including partition subdirectories) and outputs only AFM-related stanzas:
  - net address-list
  - net port-list
  - security firewall *
"""

import argparse
import sys
from pathlib import Path


AFM_PREFIXES = (
    "auth partition ",
    "net vlan",
    "net route-domain",
    "net address-list ",
    "net port-list ",
    "security firewall ",
)

AFM_EXCLUDE_PREFIXES = (
    "security firewall config-entity-id ",
    "security firewall port-list ",
    "security firewall address-list ",
)

CONFIG_FILENAMES = ("bigip.conf", "bigip_base.conf")


def find_config_files(config_dir: Path) -> list[Path]:
    """Find all bigip.conf and bigip_base.conf files in the config directory."""
    files = []
    for filename in CONFIG_FILENAMES:
        root_file = config_dir / filename
        if root_file.exists():
            files.append(root_file)

    partitions_dir = config_dir / "partitions"
    if partitions_dir.is_dir():
        for partition_dir in sorted(partitions_dir.iterdir()):
            if partition_dir.is_dir():
                for filename in CONFIG_FILENAMES:
                    part_file = partition_dir / filename
                    if part_file.exists():
                        files.append(part_file)

    return files


def extract_afm_stanzas(file_path: Path) -> list[str]:
    """Extract AFM stanzas from a single config file."""
    stanzas = []

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
        return stanzas

    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this line starts an AFM stanza (and is not excluded)
        if (any(stripped.startswith(prefix) for prefix in AFM_PREFIXES)
                and not any(stripped.startswith(ex) for ex in AFM_EXCLUDE_PREFIXES)):
            stanza_lines = [line]
            brace_depth = line.count("{") - line.count("}")

            if brace_depth == 0 and "{" not in line:
                # Single-line stanza with no braces (unlikely but handle it)
                stanzas.append("".join(stanza_lines))
                i += 1
                continue

            # Collect lines until braces balance back to 0
            i += 1
            while i < len(lines) and brace_depth > 0:
                stanza_lines.append(lines[i])
                brace_depth += lines[i].count("{") - lines[i].count("}")
                i += 1

            stanza = "".join(stanza_lines)
            if stripped.startswith("net vlan "):
                stanza = remove_sub_block(stanza, "interfaces")
            stanzas.append(stanza)
        else:
            i += 1

    return stanzas


def remove_sub_block(stanza: str, block_name: str) -> str:
    """Remove a named sub-block (e.g. 'interfaces { ... }') from a stanza."""
    result = []
    lines = stanza.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == f"{block_name} {{" or stripped.startswith(f"{block_name} {{"):
            # Skip this line and all lines until the block's closing brace
            depth = lines[i].count("{") - lines[i].count("}")
            i += 1
            while i < len(lines) and depth > 0:
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
        else:
            result.append(lines[i])
            i += 1
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(
        description="Extract AFM configuration stanzas from BIG-IP config files."
    )
    parser.add_argument(
        "config_dir",
        help="Path to the BIG-IP configuration directory",
    )
    parser.add_argument(
        "-o", "--output",
        default="afm_config.conf",
        help="Output file path (default: afm_config.conf)",
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

    output_lines = []
    total_stanzas = 0

    for config_file in config_files:
        stanzas = extract_afm_stanzas(config_file)
        if stanzas:
            header = f"# --- Source: {config_file} ---\n"
            output_lines.append(header)
            for stanza in stanzas:
                output_lines.append(stanza)
                if not stanza.endswith("\n"):
                    output_lines.append("\n")
                output_lines.append("\n")
            total_stanzas += len(stanzas)
            print(f"  {config_file}: {len(stanzas)} stanza(s) extracted")
        else:
            print(f"  {config_file}: no AFM stanzas found")

    output_path = Path(args.output)
    output_path.write_text("".join(output_lines), encoding="utf-8")

    print(f"\nExtracted {total_stanzas} total stanza(s) -> {output_path}")


if __name__ == "__main__":
    main()
