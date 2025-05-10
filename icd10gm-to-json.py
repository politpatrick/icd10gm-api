#!/usr/bin/env python3
"""
icd10gm_to_json.py

Convert the ICD‑10‑GM ClaML (Classification Markup Language) XML file into a set of
human‑friendly JSON files organised in folders that reflect the nosological hierarchy
(Chapter → Block → Three‑char category → Four‑char category).

Author: Generated with ChatGPT (OpenAI)
Date: 2025‑05‑10
"""
from __future__ import annotations

import argparse
import json
import pathlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable


@dataclass
class Node:
    """Single ICD‑10‑GM concept."""

    code: str
    kind: str
    label: str
    rubrics: Dict[str, str]
    children: List["Node"]

    def to_dict(self, recursive: bool = True) -> Dict:
        """Return a JSON‑serialisable representation."""
        data = {
            "code": self.code,
            "kind": self.kind,
            "label": self.label,
            "rubrics": self.rubrics,
        }
        if recursive:
            data["children"] = [c.to_dict(True) for c in self.children]
        return data


def parse_claml(xml_path: pathlib.Path) -> Dict[str, Node]:
    """Parse the ClaML XML file and return a mapping *code → Node*.

    Child links are resolved in a second step (see :func:`build_tree`).
    """
    nodes: Dict[str, Node] = {}
    child_refs: Dict[str, List[str]] = {}

    # ``iterparse`` avoids loading the entire file into memory.
    ctx = ET.iterparse(str(xml_path), events=("start", "end"))
    _, root = next(ctx)  # advance to the root element (<ClaML>)

    for event, elem in ctx:
        if event != "end" or elem.tag != "Class":
            continue

        code = elem.attrib["code"]
        kind = elem.attrib.get("kind", "")

        rubrics: Dict[str, str] = {}
        preferred_label = ""
        for rub in elem.findall("Rubric"):
            kind_attr = rub.attrib.get("kind", "other")
            text = "".join(rub.itertext()).strip()
            rubrics[kind_attr] = text
            if kind_attr == "preferred":
                preferred_label = text

        nodes[code] = Node(
            code=code,
            kind=kind,
            label=preferred_label,
            rubrics=rubrics,
            children=[],
        )

        # Remember child codes for later linking.
        refs = [sub.attrib["code"] for sub in elem.findall("SubClass")]
        if refs:
            child_refs[code] = refs

        # Clear the processed element to free memory.
        elem.clear()

    # Resolve child links ----------------------------------------------------
    for parent_code, codes in child_refs.items():
        parent = nodes[parent_code]
        parent.children = [nodes[c] for c in codes if c in nodes]

    return nodes


def build_tree(nodes: Dict[str, Node]) -> List[Node]:
    """Return a list with the chapter nodes (top‑level roots)."""
    referenced = {child.code for node in nodes.values() for child in node.children}
    roots = [n for n in nodes.values() if n.code not in referenced and n.kind == "chapter"]

    # Chapters are coded with Roman numerals (I–XXII), so lexical sort is OK.
    roots.sort(key=lambda n: n.code)
    return roots


def path_for(node: Node) -> List[str]:
    """Compute a folder path for *node* relative to the chosen output directory."""
    if node.kind == "chapter":
        return [f"{node.code} {node.label}"]

    # Blocks (e.g. A00‑A09) keep the dash, but convert it to an underscore so we
    # get valid file/folder names on every OS.
    if "-" in node.code:
        return [node.code.replace("-", "_")]

    # Three‑/four‑char categories → umbrella folder by first letter.
    return [node.code[0], node.code]


def export_json(roots: Iterable[Node], out_dir: pathlib.Path, pretty: bool = False) -> None:
    """Write each node to ``out_dir`` in a mirrored folder structure."""
    for chapter in roots:
        _export_node(chapter, out_dir, pretty)


def _export_node(node: Node, base: pathlib.Path, pretty: bool) -> None:
    parts = path_for(node)
    dir_path = base.joinpath(*parts[:-1])
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / f"{parts[-1]}.json"
    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(
            node.to_dict(True),
            fh,
            ensure_ascii=False,
            indent=2 if pretty else None,
        )

    for child in node.children:
        _export_node(child, base, pretty)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert ICD‑10‑GM ClaML XML into a hierarchy of JSON files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("xml", type=pathlib.Path, help="Path to the ClaML XML file")
    parser.add_argument(
        "out_dir", type=pathlib.Path, help="Destination directory for the JSON export"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty‑print JSON using indentation (larger file size).",
    )

    args = parser.parse_args(argv)
    if not args.xml.is_file():
        sys.exit(f"XML source '{args.xml}' not found.")

    print("Parsing ICD‑10‑GM …")
    nodes = parse_claml(args.xml)
    print(f"Found {len(nodes):,} concepts.")

    roots = build_tree(nodes)
    print(f"Identified {len(roots)} chapters; exporting …")
    export_json(roots, args.out_dir, pretty=args.pretty)
    print("Done.")


if __name__ == "__main__":
    main()