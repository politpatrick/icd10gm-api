#!/usr/bin/env python3
"""
icd10gm_tools.py
================

Erweitertes Toolkit für die ICD-10-GM (ClaML XML → JSON/SQLite/API/Diff)

Features:
* Hierarchischer JSON-Export (Folder per Kapitel/Block/Kategorie)
* Kompaktes Gesamt-JSON
* SQLite-Export
* Index-Datei (Code → Pfad)
* Suche & Lookup (get_by_code, search)
* Strukturvalidierung
* Versionen-Vergleich (Diff)
* FastAPI-Blueprint
* CLI mit Sub-Commands

Autor: ChatGPT | Lizenz: MIT | Stand: 10.05.2025
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sqlite3
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

@dataclass
class Node:
    code: str
    kind: str
    label: str
    rubrics: Dict[str, str]
    children: List[Node]

    def to_dict(self, recursive: bool = True) -> Dict:
        data = {"code": self.code, "kind": self.kind, "label": self.label, "rubrics": self.rubrics}
        if recursive:
            data["children"] = [child.to_dict(True) for child in self.children]
        return data

    def fulltext(self) -> str:
        parts = [self.code, self.label] + list(self.rubrics.values())
        return "\u0000".join(parts).lower()

# ---- Parsing ClaML ----
def parse_claml(xml_path: pathlib.Path) -> Dict[str, Node]:
    nodes: Dict[str, Node] = {}
    refs: Dict[str, List[str]] = defaultdict(list)
    context = ET.iterparse(str(xml_path), events=("start", "end"))
    _, root = next(context)
    for event, elem in context:
        if event == "end" and elem.tag == "Class":
            code = elem.attrib.get("code", "")
            kind = elem.attrib.get("kind", "")
            rubrics: Dict[str, str] = {}
            label = ""
            for rub in elem.findall("Rubric"):
                k = rub.attrib.get("kind", "other")
                text = "".join(rub.itertext()).strip()
                rubrics[k] = text
                if k == "preferred":
                    label = text
            nodes[code] = Node(code, kind, label, rubrics, [])
            for sub in elem.findall("SubClass"):
                c = sub.attrib.get("code")
                if c:
                    refs[code].append(c)
            elem.clear()
    for parent, children in refs.items():
        if parent in nodes:
            nodes[parent].children = [nodes[c] for c in children if c in nodes]
    return nodes

# ---- Baumaufbau ----
def build_tree(nodes: Dict[str, Node]) -> List[Node]:
    children_codes = {c.code for n in nodes.values() for c in n.children}
    roots = [n for n in nodes.values() if n.code not in children_codes and n.kind == "chapter"]
    roots.sort(key=lambda n: n.code)
    return roots

# ---- Pfad-Utilities ----
def slugify(text: str) -> str:
    return text.replace(" ", "_")

def path_for(node: Node) -> List[str]:
    if node.kind == "chapter":
        return [f"{node.code}_{slugify(node.label)}"]
    if "-" in node.code:
        return [node.code.replace("-", "_")]
    if len(node.code) == 3:
        return [node.code[0], node.code]
    return [node.code[0], node.code[:3], node.code]

# ---- Exporte ----
def export_hierarchical_json(roots: Sequence[Node], out_dir: pathlib.Path, pretty: bool = False, kind_filter: Optional[Sequence[str]] = None) -> None:
    for root in roots:
        _export_node(root, out_dir, pretty, kind_filter)

def _export_node(node: Node, base: pathlib.Path, pretty: bool, kind_filter: Optional[Sequence[str]]) -> None:
    if kind_filter and node.kind not in kind_filter:
        return
    parts = path_for(node)
    dir_path = base.joinpath(*parts[:-1])
    dir_path.mkdir(parents=True, exist_ok=True)
    with (dir_path / f"{parts[-1]}.json").open("w", encoding="utf-8") as f:
        json.dump(node.to_dict(True), f, ensure_ascii=False, indent=2 if pretty else None)
    for ch in node.children:
        _export_node(ch, base, pretty, kind_filter)

def export_single_json(roots: Sequence[Node], file_path: pathlib.Path, pretty: bool = False) -> None:
    data = [r.to_dict(True) for r in roots]
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2 if pretty else None)

def export_sqlite(nodes: Dict[str, Node], db_path: pathlib.Path) -> None:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE icd (code TEXT PRIMARY KEY, kind TEXT, label TEXT, rubrics TEXT)""")
    entries = ((n.code, n.kind, n.label, json.dumps(n.rubrics, ensure_ascii=False)) for n in nodes.values())
    cur.executemany("INSERT INTO icd VALUES (?, ?, ?, ?)", entries)
    cur.execute("CREATE INDEX idx_label ON icd(label)")
    con.commit(); con.close()

def build_index_file(nodes: Dict[str, Node], out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    idx: Dict[str, str] = {}
    for n in nodes.values(): idx[n.code] = "/".join(path_for(n)) + ".json"
    with (out_dir / "index.json").open("w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

# ---- Suche & Lookup ----
def get_by_code(code: str, nodes: Dict[str, Node]) -> Optional[Node]: return nodes.get(code.upper())

def search(term: str, nodes: Dict[str, Node], full_text: bool = False, limit: int = 30) -> List[Node]:
    key = term.lower(); res: List[Node] = []
    for n in nodes.values():
        if key in n.code.lower() or key in n.label.lower() or (full_text and key in n.fulltext()):
            res.append(n)
        if len(res) >= limit: break
    return res

# ---- Validierung ----
def validate_structure(nodes: Dict[str, Node]) -> List[str]:
    errs: List[str] = []
    for n in nodes.values():
        if not n.label: errs.append(f"{n.code}: fehlendes Label")
    vis: Dict[str, bool] = {}
    def dfs(n: Node, path: List[str]):
        if n.code in path: errs.append(f"Zyklus: {'→'.join(path + [n.code])}"); return
        if vis.get(n.code): return
        vis[n.code] = True
        for c in n.children: dfs(c, path + [n.code])
    for n in nodes.values(): dfs(n, [])
    return errs

# ---- Diff ----
def diff_claml(old_xml: pathlib.Path, new_xml: pathlib.Path) -> Dict[str, List[str]]:
    old = parse_claml(old_xml); new = parse_claml(new_xml)
    oset, nset = set(old), set(new)
    added = sorted(nset - oset); removed = sorted(oset - nset)
    changed = [c for c in oset & nset if old[c].fulltext() != new[c].fulltext()]
    return {"added": added, "removed": removed, "changed": changed}

# ---- FastAPI Blueprint ----
def create_fastapi_app(nodes: Dict[str, Node]):
    from fastapi import FastAPI, HTTPException
    app = FastAPI(title="ICD-10-GM API")
    @app.get("/icd/{code}")
    def read_code(code: str):
        node = get_by_code(code, nodes)
        if not node: raise HTTPException(404, "Nicht gefunden")
        return node.to_dict(True)
    @app.get("/search")
    def api_search(q: str, full_text: bool = False):
        return [n.to_dict(False) for n in search(q, nodes, full_text)]
    return app

# ---- CLI ----
def _cli_export(args):
    nodes = parse_claml(args.xml); roots = build_tree(nodes)
    export_hierarchical_json(roots, args.out_dir, pretty=args.pretty, kind_filter=args.kind)
    build_index_file(nodes, args.out_dir)
    print("Hierarchischer Export abgeschlossen.")

def _cli_single(args):
    nodes = parse_claml(args.xml); roots = build_tree(nodes)
    export_single_json(roots, args.file, pretty=args.pretty)
    print("Einzel-JSON erstellt.")

def _cli_sqlite(args):
    nodes = parse_claml(args.xml)
    export_sqlite(nodes, args.db)
    print("SQLite erstellt.")

def _cli_validate(args):
    errs = validate_structure(parse_claml(args.xml))
    if errs: print("FEHLER:\n" + "\n".join(errs)); sys.exit(1)
    print("Keine Fehler.")

def _cli_diff(args):
    print(json.dumps(diff_claml(args.old, args.new), indent=2, ensure_ascii=False))

def main():
    p = argparse.ArgumentParser(description="ICD-10-GM Toolkit CLI")
    sp = p.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("export", help="Hierarchischer JSON-Export")
    e.add_argument("xml", type=pathlib.Path)
    e.add_argument("out_dir", type=pathlib.Path)
    e.add_argument("--pretty", action="store_true")
    e.add_argument("--kind", nargs="*")
    e.set_defaults(func=_cli_export)

    s = sp.add_parser("single", help="Einzel-JSON-Export")
    s.add_argument("xml", type=pathlib.Path)
    s.add_argument("file", type=pathlib.Path)
    s.add_argument("--pretty", action="store_true")
    s.set_defaults(func=_cli_single)

    sq = sp.add_parser("sqlite", help="SQLite-Export")
    sq.add_argument("xml", type=pathlib.Path, help="Pfad zur ClaML-XML-Datei")
    sq.add_argument("db", type=pathlib.Path, help="Pfad zur SQLite-DB-Datei")
    sq.set_defaults(func=_cli_sqlite)

    v = sp.add_parser("validate", help="Strukturvalidierung")
    v.add_argument("xml", type=pathlib.Path)
    v.set_defaults(func=_cli_validate)

    d = sp.add_parser("diff", help="Versionen-Vergleich")
    d.add_argument("old", type=pathlib.Path)
    d.add_argument("new", type=pathlib.Path)
    d.set_defaults(func=_cli_diff)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

