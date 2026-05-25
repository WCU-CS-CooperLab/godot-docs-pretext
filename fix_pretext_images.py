#!/usr/bin/env python3
"""fix_pretext_images.py

Post-processing pass to fix image paths in PreTeXt output produced by
sphinx_xml_to_pretext.py.

Background
----------
Sphinx's XML builder does NOT copy images to a _images/ folder the way
the HTML builder does.  The `uri=` attributes in the XML files are
relative paths like `../../_images/foo.png` or
`external/about/img/foo.png`, but the actual files only exist under the
HTML build tree (e.g. output/html/external/about/img/foo.png).

This script:
  1. Scans every .ptx file in the PreTeXt output for <image source="...">
     attributes.
  2. For each source value, tries to locate the real file by:
       a. Checking if the path already exists relative to the PTX out dir.
       b. Searching the HTML build tree (--html-dir) by filename.
       c. Searching the Sphinx XML source dir (--xml-dir) by filename.
  3. Copies every found image into  <ptx_out_dir>/images/<filename>
     (preserving only the basename, deduplicating with a counter suffix
     if two different files share a name).
  4. Rewrites all <image source="..."> in every .ptx file to use the
     canonical  images/<filename>  path.
  5. Reports any images it could not find.

Usage
-----
    python fix_pretext_images.py \\
        --ptx-dir  pretext_out \\
        --html-dir output/output/html \\
        --xml-dir  _build/xml

All three flags are optional; omit --html-dir / --xml-dir if you only
want the rewrite pass without copying (e.g. if you have already placed
images in pretext_out/images/ manually).

The script is safe to re-run: it skips copies when the destination file
already exists and has the same content.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IMAGE_EXTS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tiff", ".tif",
}


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_ptx_files(ptx_dir: str) -> List[str]:
    out = []
    for dirpath, _, files in os.walk(ptx_dir):
        for fn in files:
            if fn.endswith(".ptx"):
                out.append(os.path.join(dirpath, fn))
    return out


def _build_filename_index(search_dirs: List[str]) -> Dict[str, List[str]]:
    """Return {basename_lower: [abs_path, ...]} for all image files found."""
    idx: Dict[str, List[str]] = {}
    for root_dir in search_dirs:
        if not root_dir or not os.path.isdir(root_dir):
            continue
        for dirpath, _, files in os.walk(root_dir):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMAGE_EXTS:
                    key = fn.lower()
                    idx.setdefault(key, []).append(os.path.join(dirpath, fn))
    return idx


def _locate_image(
    source_val: str,
    ptx_dir: str,
    filename_index: Dict[str, List[str]],
) -> Optional[str]:
    """Try to find the file for a given <image source="..."> value.

    Returns an absolute path if found, else None.
    """
    if not source_val:
        return None

    # External URLs – skip
    if source_val.startswith(("http://", "https://", "//", "data:")):
        return None

    # 1. Direct path relative to ptx_dir
    candidate = os.path.normpath(os.path.join(ptx_dir, source_val))
    if os.path.isfile(candidate):
        return candidate

    # 2. Strip ../ segments and try _images/<name> pattern
    #    e.g. ../../_images/foo.png -> look for foo.png in index
    norm = source_val.replace("\\", "/")
    # Remove leading ../
    while norm.startswith("../"):
        norm = norm[3:]
    # e.g. _images/foo.png -> just want foo.png for filename search
    basename = os.path.basename(norm)
    if not basename:
        return None

    # 3. Filename index (search HTML build + XML source trees)
    key = basename.lower()
    candidates = filename_index.get(key, [])
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Prefer a path whose directory matches hints from source_val
        # e.g. if source_val contains "engine_details/development", prefer that
        path_hint = norm.replace("_images/", "").replace("../", "").lower()
        for c in candidates:
            if path_hint.replace("/", os.sep) in c.lower():
                return c
        # Fall back to first match
        return candidates[0]

    return None


def _dedupe_dest(images_dir: str, basename: str, src_path: str) -> str:
    """Return a destination path under images_dir that doesn't collide.

    If <basename> already exists but has different content, append a
    counter: foo.png -> foo-2.png, foo-3.png, ...
    """
    dest = os.path.join(images_dir, basename)
    if not os.path.exists(dest):
        return dest
    # Same content -> reuse
    if _file_hash(dest) == _file_hash(src_path):
        return dest
    # Different file with same name -> rename
    name, ext = os.path.splitext(basename)
    counter = 2
    while True:
        new_name = f"{name}-{counter}{ext}"
        dest = os.path.join(images_dir, new_name)
        if not os.path.exists(dest):
            return dest
        if _file_hash(dest) == _file_hash(src_path):
            return dest
        counter += 1


# ---------------------------------------------------------------------------
# Main pass
# ---------------------------------------------------------------------------

def fix_images(
    ptx_dir: str,
    html_dir: Optional[str],
    xml_dir: Optional[str],
    dry_run: bool = False,
) -> None:
    # PreTeXt copies the entire "external" folder flat into output/html/external/,
    # so images must live directly in ptx_dir (next to main.ptx), not in a
    # subdirectory.  We use ptx_dir itself as the images destination.
    images_dir = ptx_dir + '/../assets' 

    # Build a filename -> [path] index from all available image sources
    search_dirs = [d for d in [html_dir, xml_dir, ptx_dir] if d]
    print(f"Building image filename index from: {search_dirs}")
    filename_index = _build_filename_index(search_dirs)
    print(f"  Found {sum(len(v) for v in filename_index.values())} image files "
          f"({len(filename_index)} unique names)")

    ptx_files = _collect_ptx_files(ptx_dir)
    print(f"Scanning {len(ptx_files)} .ptx files …")

    # Map original source value -> canonical "images/<name>" path
    # so we rewrite consistently across all files
    source_to_canonical: Dict[str, str] = {}
    # Track copies we've made: abs_src -> dest_basename
    copied: Dict[str, str] = {}
    not_found: Set[str] = set()

    # ---- Pass 1: collect all unique source= values ----
    all_sources: Set[str] = set()
    for ptx_path in ptx_files:
        try:
            tree = ET.parse(ptx_path)
        except ET.ParseError as e:
            print(f"  WARN: could not parse {ptx_path}: {e}", file=sys.stderr)
            continue
        for el in tree.getroot().iter():
            if strip_ns(el.tag) == "image":
                src = el.get("source", "").strip()
                if src and not src.startswith(("http://", "https://", "//")):
                    all_sources.add(src)

    print(f"Found {len(all_sources)} unique image source values.")

    # ---- Pass 2: locate + copy ----
    for src in sorted(all_sources):
        # Already resolved this one
        if src in source_to_canonical:
            continue

        # Check if already a bare filename pointing at ptx_dir (idempotent re-run)
        if "/" not in src and os.path.isfile(os.path.join(ptx_dir, src)):
            source_to_canonical[src] = src
            continue

        real_path = _locate_image(src, ptx_dir, filename_index)
        if real_path is None:
            not_found.add(src)
            continue

        # Determine destination basename (avoid collisions)
        basename = os.path.basename(real_path)
        if real_path in copied:
            dest_basename = copied[real_path]
        else:
            if not dry_run:
                dest_path = _dedupe_dest(images_dir, basename, real_path)
                dest_basename = os.path.basename(dest_path)
                if not os.path.exists(dest_path):
                    shutil.copy2(real_path, dest_path)
                    print(f"  Copied: {os.path.relpath(real_path)} -> {dest_basename}")
                else:
                    print(f"  Exists: {dest_basename}  (from {os.path.relpath(real_path)})")
            else:
                dest_basename = basename
                print(f"  [DRY] Would copy: {real_path} -> {dest_basename}")
            copied[real_path] = dest_basename

        canonical = dest_basename
        source_to_canonical[src] = canonical

    # ---- Pass 3: rewrite .ptx files ----
    rewrites = 0
    files_changed = 0
    for ptx_path in ptx_files:
        try:
            tree = ET.parse(ptx_path)
        except ET.ParseError:
            continue
        root = tree.getroot()
        changed = False
        for el in root.iter():
            if strip_ns(el.tag) != "image":
                continue
            src = el.get("source", "").strip()
            if not src:
                continue
            canonical = source_to_canonical.get(src)
            if canonical and canonical != src:
                el.set("source", canonical)
                changed = True
                rewrites += 1
        if changed and not dry_run:
            tree.write(ptx_path, encoding="utf-8", xml_declaration=True)
            files_changed += 1

    # ---- Summary ----
    print()
    print("=" * 60)
    print(f"Images copied/verified : {len(copied)}")
    print(f"<image source=> rewrites: {rewrites} across {files_changed} files")
    if not_found:
        print(f"NOT FOUND ({len(not_found)} images):")
        for s in sorted(not_found):
            print(f"  {s}")
    else:
        print("All image sources resolved successfully.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fix image paths in PreTeXt output from sphinx_xml_to_pretext.py"
    )
    ap.add_argument(
        "--ptx-dir",
        required=True,
        help="PreTeXt output directory (the one containing main.ptx and chapters/)",
    )
    ap.add_argument(
        "--html-dir",
        default=None,
        help="Sphinx HTML build directory (e.g. output/output/html). "
             "Images are searched here first.",
    )
    ap.add_argument(
        "--xml-dir",
        default=None,
        help="Sphinx XML build directory (e.g. _build/xml). "
             "Used as a secondary search location.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without copying or rewriting files.",
    )
    args = ap.parse_args(argv)

    if not os.path.isdir(args.ptx_dir):
        print(f"ERROR: --ptx-dir does not exist: {args.ptx_dir}", file=sys.stderr)
        return 1

    fix_images(
        ptx_dir=args.ptx_dir,
        html_dir=args.html_dir,
        xml_dir=args.xml_dir,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
