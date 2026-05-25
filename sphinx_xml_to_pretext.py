#!/usr/bin/env python3
"""sphinx_xml_to_pretext.py  (v28)

Converts Sphinx XML builder output (_build/xml/) into modular PreTeXt.

Key improvements over v27 (this version):
- Removed <introduction> entirely from convert_section and convert_doc_as.
  PreTeXt <introduction> only works when its sibling sections are in the
  same file; when siblings arrive via xi:include PreTeXt level-checker
  fires before XInclude resolves them. Since content renders correctly
  without <introduction>, all block content is now placed directly in
  the structural container before any sections.
- Same change applied to convert_section which had the same pattern.

Key improvements over v26:
- Removed <introduction> wrapper for has_xi_children case. PreTeXt
  level-checker fires on <introduction> before XInclude resolves the
  xi:included sections, causing "does not know its level" errors.
  Body content (paragraphs, blocks) is now placed directly in the
  chapter before the xi:includes; only internal <section> nodes that
  would compete with xi:included sections are wrapped in <introduction>.
- Fixed _section_tag depth offset: convert_section(depth=1) now emits
  <section> not <subsection> when called from a chapter context.
  Internal sections inside a chapter body are now converted at depth=0
  (-> <section>) not depth=1 (-> <subsection>).

Key improvements over v25:
- Duplicate section numbering fixed: when convert_doc_as produces a
  chapter that will later receive xi:include children, internal sections
  from the document body are wrapped in <introduction> so they do not
  compete with the xi:included sections for numbering.
- Image URIs fixed: Sphinx XML stores images as relative paths like
  ../_images/foo.png. These are now resolved to paths relative to the
  PreTeXt output root so PreTeXt can find them.

Key improvements over v24:
- Direct toctree caption entries are never transparent, even when they
  have no body paragraph content. assign_chapter now takes force_chapter
  so that getting_started/introduction/index, step_by_step/index, and
  first_2d_game/index become chapters with their sub-pages as sections,
  matching the RST sidebar grouping.

Key improvements over v23:
- Fixed _load_toctree_captions to use recursive .children traversal
  instead of .traverse(). Captions live at depth 5 inside a bullet_list
  node tree; the old code never reached them.
- Getting started sub-groups (introduction/index, step_by_step/index,
  first_2d_game/index) are now non-transparent chapters whose toctree
  children become sections, matching the RST sidebar structure.

Key improvements over v22:
- Removed "section" from _CONTENT_TAGS. Index files that only contain
  <target> and <section> children were being treated as content pages
  because section was in the content set. Removing it means only
  paragraph, table, literal_block etc. make a doc "real" content.
- Toctree is flat in godot-docs: about/* and getting_started/* are
  direct children of index, not nested under about/index. The converter
  now reads toctree captions from the pickle to create <part> groupings,
  falling back to path-prefix grouping if captions are unavailable.
- Docname normalisation: underscores and hyphens are treated as equivalent
  when matching toctree entries to XML files.

Key improvements over v21:
- Children of content-bearing chapters are now converted as <section>
  instead of <chapter>. PreTeXt renders each <chapter> as its own page,
  so nesting <chapter> inside <chapter> caused the 1->13 numbering jump
  and the extra-click problem. Sections inside a chapter render on the
  same page and appear in the left-hand TOC.
- assign_levels now passes the correct ptx_tag ("section") for children
  of content-bearing docs, and the level map stores it so convert_doc_as
  receives the right tag.

Key improvements over v20:
- Fixed all remaining xref text= deprecation sources:
  * reference handler: resolved xref with no text now gets text="title"
  * reference handler: unresolved provisional xref with text content now
    sets text="custom" so slug-rescue does not later combine text="title"
    with existing text content (the deprecated pattern)
  * pending_xref handler: text="title" set only when no text content
  * slug-rescue pass: already guarded in v19; no change needed

Key improvements over v19:
- Content-aware structural mapping replaces the depth-only heuristic.
  Empty index files (pure toctree containers with no body content) are
  detected via _has_content() and their children are promoted one level
  up. This fixes the extra-click problem (VIII Introduction, IX Step by
  step landing pages) and corrects chapter numbering (about/* was getting
  Roman numerals instead of Arabic because it was outside any <part>).
- ptx_level_map built in a single DFS pass assigns each doc a PreTeXt
  level (part/chapter/section) based on actual content presence rather
  than raw toctree depth.

Key improvements over v18:
- tabular <col> elements now have no width attribute at all. PreTeXt
  2.39 requires percentages (rejects bare integers) but also crashes
  when they sum over 100%. Omitting width entirely lets PreTeXt
  distribute columns equally with no validation.
- slug rescue pass now only sets text="title" when the xref has no
  text content; xrefs with content get text="custom" instead, fixing
  the "xref/@text=title with alternate content" deprecation warning.

Key improvements over v17:
- tabular col widths now use relative integers ("1") instead of
  percentages, avoiding PTX:FATAL sum-over-100%% entirely. PreTeXt
  only applies the percentage sum check when width values end in "%%";
  integer widths are treated as equal relative proportions with no
  overflow possible regardless of column count or rounding.

Key improvements over v16:
- program/input renamed to program/code (PreTeXt deprecation 2024-11-19).
- tabular col widths now sum to exactly 100%% (fixes PTX:FATAL crash).
- slug-rescue pass (pass 2) now sets text="title" on resolved xrefs.

Key improvements over v15:
- Classes directory excluded by default (--include-classes to re-enable).
- xref always emits text="title" when no custom link text is present,
  fixing hundreds of "target does not have a number" PreTeXt warnings.
- tabular emits <col width="X%"> elements so PreTeXt does not warn about
  paragraphs in cells without column widths.
- Depth-3+ docs are now nested as xi:include inside their parent chapter
  file rather than emitted as top-level includes in main.ptx, fixing the
  TOC structure and eliminating extra clicks before content.

Key improvements over v14:
- Pass 3: class-ref URL rewriter converts all <xref provisional="class-*">
  and <xref provisional="enum-*"> into <url href="..."> pointing at the
  online Godot API docs, eliminating ~24k unresolvable cross-references.
  Godot version can be set with --godot-version (default: stable).

Key improvements over v13:
- Pre-registration pass: before any conversion, every section/target ids
  attribute across all XML files is registered in id_map. This means
  resolve_ref can find cross-document anchors regardless of conversion
  order, collapsing most provisional xrefs to real refs.
- _get_or_make_xmlid: convert_section and convert_doc_as reuse the
  xml:id minted during pre-registration rather than minting a duplicate,
  keeping ids stable and avoiding -2/-3 suffix collisions.

Key improvements over v12.1:
- Toctree-aware structure: reads env.toctree_includes from the Sphinx
  environment pickle so the full document tree is walked in the correct
  order, including files that are only reachable via sub-toctrees.
- Depth-aware PreTeXt nesting: top-level toctree entries become <part>,
  second-level become <chapter>, deeper RST sections become <section> etc.
- No more "include_all" sweep that created spurious chapters for every
  XML file regardless of its toctree position.
- Handles missing toctree_includes gracefully (falls back to RST parsing).
- Expanded convert_block: literal_block/code, admonitions (note/warning/
  tip/caution/important), enumerated_list, definition_list, field_list,
  image, table (basic), target (id registration), container (sphinx-tabs).
- convert_node inline fallback: unknown inline tags no longer silently
  lose their text; text+tail are folded into the parent.
- Title extraction uses get_all_text() so inline markup inside titles
  is not lost.

Usage:
  python sphinx_xml_to_pretext.py _build/xml pretext_out \\
      --index-doc index \\
      --title "Godot Docs" \\
      --env-pickle _build/xml/.doctrees/environment.pickle
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JUNK_DOCNAMES: Set[str] = {
    "404", "genindex", "search", "searchindex",
    "objects", "py-modindex", "sitemap", "robots",
}

# RST admonition names → PreTeXt element names
ADMONITION_MAP: Dict[str, str] = {
    "note":      "note",
    "warning":   "warning",
    "tip":       "note",       # PreTeXt has no <tip>; use <note>
    "caution":   "warning",
    "important": "note",
    "attention": "note",
    "danger":    "warning",
    "error":     "warning",
    "hint":      "note",
    "seealso":   "note",
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def strip_ns(tag: str) -> str:
    return tag.split('}', 1)[1] if '}' in tag else tag


def safe_text(s: Optional[str]) -> str:
    return (s or "").strip()


def slugify(text: str) -> str:
    text = (text or "untitled").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"


def _slugify_title(text: str) -> str:
    """Slugify a title string (kebab-case)."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def norm_key(s: str) -> str:
    """Normalise separators so foo-bar, foo_bar and foo:bar all match."""
    return re.sub(r"[-_:]+", "_", (s or "").strip().lower())


def get_all_text(node: ET.Element) -> str:
    """Recursively concatenate all text content of a node."""
    parts: List[str] = []
    if node.text:
        parts.append(node.text)
    for ch in node:
        parts.append(get_all_text(ch))
        if ch.tail:
            parts.append(ch.tail)
    return "".join(parts).strip()


def iter_local(root: ET.Element, localname: str):
    for e in root.iter():
        if strip_ns(e.tag) == localname:
            yield e


def children_local(parent: ET.Element, localname: str) -> List[ET.Element]:
    return [c for c in parent if strip_ns(c.tag) == localname]


def indent_xml(elem: ET.Element, level: int = 0) -> None:
    i = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent_xml(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ---------------------------------------------------------------------------
# Pass 2: title-slug xref rescue (global across all output PTX files)
# ---------------------------------------------------------------------------

def _build_title_slug_index_for_root(ptx_root: ET.Element) -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for el in ptx_root.iter():
        xmlid = el.get("xml:id") or el.get("{http://www.w3.org/XML/1998/namespace}id")
        if not xmlid:
            continue
        title_text = None
        for ch in el:
            if strip_ns(ch.tag) == "title":
                title_text = get_all_text(ch)
                break
        if not title_text:
            continue
        s = _slugify_title(title_text)
        if s and s not in idx:
            idx[s] = xmlid
    return idx


def _build_global_title_slug_index(ptx_paths: List[str]) -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for p in ptx_paths:
        try:
            root = ET.parse(p).getroot()
        except Exception:
            continue
        for k, v in _build_title_slug_index_for_root(root).items():
            idx.setdefault(k, v)
    return idx


def _slug_rescue_second_pass_files(ptx_paths: List[str]) -> Tuple[int, int]:
    """Rewrite <xref provisional="X"> using a global title-slug index.

    Matching strategy (in order):
      1) slug(provisional text)
      2) slug with common prefixes stripped
      3) slug(visible link text)
    """
    idx = _build_global_title_slug_index(ptx_paths)

    def slug_candidates(prov: str, visible: str) -> List[str]:
        prov = (prov or "").strip()
        visible = (visible or "").strip()
        cands = []
        if prov:
            cands.append(_slugify_title(prov))
            for pref in ("doc-", "class-", "sec-", "chapter-", "section-"):
                if prov.startswith(pref):
                    cands.append(_slugify_title(prov[len(pref):]))
        if visible:
            cands.append(_slugify_title(visible))
        seen: Set[str] = set()
        out = []
        for c in cands:
            if c and c not in seen:
                seen.add(c)
                out.append(c)
        return out

    fixed_total = remaining_total = 0
    for p in ptx_paths:
        try:
            tree = ET.parse(p)
        except Exception:
            continue
        root = tree.getroot()
        fixed = remaining = 0
        for el in root.iter():
            if strip_ns(el.tag) != "xref":
                continue
            prov = el.get("provisional")
            if not prov:
                continue
            visible = "".join(el.itertext()).strip()
            target = None
            for s in slug_candidates(prov, visible):
                target = idx.get(s)
                if target:
                    break
            if target:
                el.attrib.pop("provisional", None)
                el.set("ref", target)
                # text="title" is only valid when the xref has no content.
                # If content is present, use text="custom" to avoid the
                # "xref/@text=title with alternate content" deprecation.
                has_content = bool((el.text or "").strip())
                el.set("text", "custom" if has_content else "title")
                fixed += 1
            else:
                remaining += 1
        if fixed or remaining:
            tree.write(p, encoding="utf-8", xml_declaration=True)
        fixed_total += fixed
        remaining_total += remaining
    return fixed_total, remaining_total


# ---------------------------------------------------------------------------
# Pass 3: class/enum ref -> external URL rewriter
# ---------------------------------------------------------------------------

# Matches labels like:
#   class-characterbody3d-method-move-and-slide
#   class-control-property-mouse-filter
#   class-visualshader-enum-type   (enum nested inside a class)
#   enum-visualshader-type         (top-level enum)
# Matches Godot cross-reference labels of the form:
#   class-<classname>[-<member-kind>-<member-name>]
#   enum-<classname>[-<enum-name>]    (top-level enum on a class page)
#
# Examples:
#   class-characterbody3d-method-move-and-slide
#   class-control-property-mouse-filter
#   enum-visualshader-type              (top-level enum, class=visualshader)
#   class-visualshader-enum-type        (enum member of VisualShader)
#
# Strategy: the classname is always the token immediately after the prefix.
# Because classnames are single alphanumeric words and member kinds are a
# fixed set, we match the classname greedily up to a known member-kind word
# or end-of-string.
_MEMBER_KINDS = r'(?:method|property|signal|constant|enum|theme-item|constructor|operator)'
_CLASS_REF_RE = re.compile(
    r'^(class|enum)-([a-z0-9]+)'                    # prefix + classname
    r'(?:-(?:' + _MEMBER_KINDS + r')-(.+))?$'       # optional: -kind-membername
)
# Top-level enum: enum-<classname>-<enumname> with no member-kind word.
# e.g. enum-visualshader-type  -> class=visualshader, page anchor = full label
_TOP_ENUM_RE = re.compile(r'^enum-([a-z0-9]+)-(.+)$')


def _provisional_to_godot_url(prov: str, version: str) -> Optional[str]:
    """Convert a class-/enum- provisional label to a Godot docs URL.

    The anchor fragment in the Godot HTML docs matches the label name exactly,
    and the page is always class_{classname}.html under /classes/.
    """
    base = f"https://docs.godotengine.org/en/{version}/classes"

    # Try the member-kind pattern first (class- and enum- with kind word)
    m = _CLASS_REF_RE.match(prov)
    if m:
        classname = m.group(2)
        page = f"{base}/class_{classname}.html"
        return f"{page}#{prov}"

    # Fallback: top-level enum label like enum-visualshader-type
    m2 = _TOP_ENUM_RE.match(prov)
    if m2:
        classname = m2.group(1)
        page = f"{base}/class_{classname}.html"
        return f"{page}#{prov}"

    return None


def _class_ref_third_pass(
    ptx_paths: List[str], godot_version: str = "stable"
) -> Tuple[int, int]:
    """Pass 3: rewrite <xref provisional="class-*|enum-*"> as <url href="...">.

    These labels refer to the Godot API class reference, which is a separate
    repository and not part of the built XML.  Rather than leave them as
    unresolved provisional xrefs, we convert them to external hyperlinks
    pointing at the online Godot API documentation.

    Returns (fixed, remaining_unmatched).
    """
    fixed_total = remaining_total = 0

    for p in ptx_paths:
        try:
            tree = ET.parse(p)
        except Exception:
            continue
        root = tree.getroot()
        changed = False
        fixed = remaining = 0

        for el in root.iter():
            if strip_ns(el.tag) != "xref":
                continue
            prov = el.get("provisional", "")
            if not (prov.startswith("class-") or prov.startswith("enum-")):
                continue

            url = _provisional_to_godot_url(prov, godot_version)
            if url:
                # Mutate the element in-place: xref -> url
                el.tag = "url"
                el.attrib.pop("provisional", None)
                el.attrib.pop("text", None)
                el.set("href", url)
                # Use existing text if present, else fall back to the label
                if not (el.text and el.text.strip()):
                    el.text = prov
                fixed += 1
                changed = True
            else:
                remaining += 1

        if changed:
            tree.write(p, encoding="utf-8", xml_declaration=True)

        fixed_total += fixed
        remaining_total += remaining

    return fixed_total, remaining_total


# ---------------------------------------------------------------------------
# Toctree helpers
# ---------------------------------------------------------------------------

def parse_index_rst_toctrees(index_rst_text: str) -> List[str]:
    """Fallback: extract toctree entries from raw RST text."""
    def _normalize(entry: str) -> Optional[str]:
        entry = entry.strip()
        if not entry or entry.startswith(".."):
            return None
        m = re.search(r"<([^>]+)>", entry)
        if m:
            entry = m.group(1).strip()
        if entry == "self":
            entry = "index"
        entry = entry.lstrip("/").replace("\\", "/")
        entry = re.sub(r"\.(rst|md)$", "", entry)
        if entry in JUNK_DOCNAMES:
            return None
        return entry

    out: List[str] = []
    in_toctree = False
    base_indent = 0
    for raw in index_rst_text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith(".. toctree::"):
            in_toctree = True
            base_indent = len(line) - len(line.lstrip(" "))
            continue
        if not in_toctree:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped and indent <= base_indent:
            in_toctree = False
            continue
        if not stripped or stripped.startswith(":"):
            continue
        doc = _normalize(stripped)
        if doc and doc not in out:
            out.append(doc)
    return out


def _load_toctree_includes(env_pickle_path: str) -> Optional[Dict[str, List[str]]]:
    """Load env.toctree_includes from the Sphinx pickle.

    Returns a dict {parent_docname: [child_docname, ...]} or None on failure.
    """
    try:
        with open(env_pickle_path, "rb") as f:
            env = pickle.load(f)
        ti = getattr(env, "toctree_includes", None)
        if isinstance(ti, dict):
            return dict(ti)
    except Exception:
        pass
    return None


def _find_toctree_nodes(node, results=None):
    """Recursively find all toctree nodes using .children traversal.

    Sphinx stores toctree nodes inside a bullet_list tree. The nodes can
    be at arbitrary depth (depth=5 in godot-docs), so we must recurse
    through .children rather than using .traverse() which may not reach
    deeply nested nodes.
    """
    if results is None:
        results = []
    if type(node).__name__ == "toctree":
        results.append(node)
    for child in getattr(node, "children", []):
        _find_toctree_nodes(child, results)
    return results


def _load_toctree_captions(env_pickle_path: str) -> Dict[str, str]:
    """Load toctree captions from the Sphinx pickle.

    Returns {docname: caption_text} for the first doc in each captioned
    toctree, allowing the converter to create <part> groupings that match
    the Sphinx HTML sidebar sections.
    """
    captions: Dict[str, str] = {}
    try:
        with open(env_pickle_path, "rb") as f:
            env = pickle.load(f)

        tocs = getattr(env, "tocs", {})
        idx_toc = tocs.get("index")
        if idx_toc is None:
            return captions

        for toctree_node in _find_toctree_nodes(idx_toc):
            attrs = getattr(toctree_node, "attributes", {})
            caption = attrs.get("caption")
            if not caption:
                continue
            entries = attrs.get("entries", [])
            for _title, docname in entries:
                if docname:
                    captions[docname] = caption
    except Exception:
        pass
    return captions


def _walk_toctree(
    root_doc: str,
    toctree: Dict[str, List[str]],
    junk: Set[str],
) -> List[Tuple[str, int]]:
    """DFS walk of toctree returning (docname, depth) pairs in document order.

    depth=0 is the root document itself (becomes the book).
    depth=1 entries become <part>, depth=2 become <chapter>, etc.
    """
    visited: Set[str] = set()
    result: List[Tuple[str, int]] = []

    def walk(doc: str, depth: int) -> None:
        if doc in visited or doc in junk:
            return
        visited.add(doc)
        result.append((doc, depth))
        for child in toctree.get(doc, []):
            walk(child, depth + 1)

    walk(root_doc, 0)
    return result


# ---------------------------------------------------------------------------
# Main Converter class
# ---------------------------------------------------------------------------

class Converter:
    def __init__(
        self,
        xml_dir: str,
        out_dir: str,
        title: str,
        index_doc: str,
        env_pickle: Optional[str],
        godot_version: str = "stable",
        include_classes: bool = False,
    ) -> None:
        self.xml_dir = xml_dir
        self.out_dir = out_dir
        self.title = title
        self.index_doc = index_doc          # e.g. "index" (no extension)
        self.env_pickle = env_pickle
        self.godot_version = godot_version  # e.g. "stable", "4.3", "latest"
        self.include_classes = include_classes  # include Godot API class pages

        self.doc_to_path: Dict[str, str] = self._index_xml()
        self.roots: Dict[str, ET.Element] = {}
        self.visited_docs: Set[str] = set()

        self.used_ids: Set[str] = set()
        self.id_map: Dict[Tuple[str, str], str] = {}
        self.global_id_index: Dict[str, Set[str]] = {}
        self.doc_top_xmlid: Dict[str, str] = {}

        self.label_map: Dict[str, Tuple[str, str]] = {}
        self.label_norm_map: Dict[str, Tuple[str, str]] = {}
        self.env_pickle_error: Optional[str] = None
        self._load_labels()

        self.unresolved_xrefs: Dict[str, int] = {}
        self.seen_counts: Dict[str, int] = {}
        self.unhandled_counts: Dict[str, int] = {}

        # Pre-register all ids across every XML file so resolve_ref works
        # regardless of document conversion order.
        self._preregister_all_ids()

    # ------------------------------------------------------------------
    # XML file index
    # ------------------------------------------------------------------

    def _index_xml(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for dirpath, _, files in os.walk(self.xml_dir):
            for fn in files:
                if not fn.endswith(".xml"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, self.xml_dir)
                docname = rel[:-4].replace(os.sep, "/")
                # Skip Sphinx internal build artefacts
                if any(seg.startswith("_") for seg in docname.split("/")):
                    continue
                # Skip Godot API class-reference pages unless requested
                if not self.include_classes:
                    segs = docname.split("/")
                    if segs[0] == "classes" or (len(segs) > 1 and segs[1] == "classes"):
                        continue
                mapping[docname] = full
        return mapping

    # ------------------------------------------------------------------
    # Environment pickle loading
    # ------------------------------------------------------------------

    def _guess_env(self) -> Optional[str]:
        candidates = []
        if self.env_pickle:
            candidates.append(self.env_pickle)
        candidates += [
            os.path.join(self.xml_dir, ".doctrees", "environment.pickle"),
            os.path.join(os.path.dirname(self.xml_dir), ".doctrees", "environment.pickle"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def _add_label(self, label: str, docname: str, nodeid: str) -> None:
        if not label or not docname or not nodeid:
            return
        self.label_map.setdefault(label, (docname, nodeid))
        self.label_norm_map.setdefault(norm_key(label), (docname, nodeid))

    def _load_labels(self) -> None:
        path = self._guess_env()
        if not path:
            return
        try:
            with open(path, "rb") as f:
                env = pickle.load(f)
        except Exception as e:
            self.env_pickle_error = f"{type(e).__name__}: {e}"
            return

        labels = getattr(env, "labels", None)
        if isinstance(labels, dict):
            for k, v in labels.items():
                try:
                    self._add_label(k, v[0], v[1])
                except Exception:
                    pass

        domaindata = getattr(env, "domaindata", None)
        if isinstance(domaindata, dict):
            std = domaindata.get("std", {})
            if isinstance(std, dict):
                for label, val in std.get("labels", {}).items():
                    try:
                        docname = val[0]
                        nodeid = val[1][0] if isinstance(val[1], tuple) else val[1]
                        self._add_label(label, docname, nodeid)
                    except Exception:
                        pass
                for label, val in std.get("anonlabels", {}).items():
                    try:
                        self._add_label(label, val[0], val[1])
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # ID management
    # ------------------------------------------------------------------

    def make_unique_xmlid(self, docname: str, candidate: str) -> str:
        base = slugify(candidate) if candidate else "untitled"
        if re.fullmatch(r"id\d+", base):
            base = f"{slugify(docname)}-{base}"
        else:
            base = f"{slugify(docname)}-{base}"
        base = base[:140]
        if base not in self.used_ids:
            self.used_ids.add(base)
            return base
        i = 2
        while f"{base}-{i}" in self.used_ids:
            i += 1
        out = f"{base}-{i}"
        self.used_ids.add(out)
        return out

    def register_ids(self, docname: str, ids_value: str, ptx_id: str) -> None:
        for did in (ids_value or "").split():
            self.id_map[(docname, did)] = ptx_id
            self.id_map[(docname, norm_key(did))] = ptx_id
            self.global_id_index.setdefault(did, set()).add(docname)
            self.global_id_index.setdefault(norm_key(did), set()).add(docname)

    def _get_or_make_xmlid(self, docname: str, ids_val: str) -> str:
        """Return the already-registered xml:id for ids_val if it exists,
        otherwise mint a fresh unique one.

        Using this during conversion prevents double-minting: the pre-
        registration pass already called make_unique_xmlid for every ids
        attribute, so conversion reuses those ids rather than creating
        a second one with a -2 suffix.
        """
        if ids_val:
            primary = ids_val.split()[0]
            for key in (primary, norm_key(primary)):
                existing = self.id_map.get((docname, key))
                if existing:
                    return existing
        candidate = ids_val.split()[0] if ids_val else f"doc-{docname}"
        return self.make_unique_xmlid(docname, candidate)

    def _preregister_all_ids(self) -> None:
        """Walk every XML doc and register all section/target ids before
        any conversion takes place.

        This ensures resolve_ref can find cross-document anchors regardless
        of the order in which documents happen to be converted.
        """
        for docname, path in self.doc_to_path.items():
            try:
                root = ET.parse(path).getroot()
            except Exception:
                continue

            # Register the document root
            ids_val = root.attrib.get("ids", "")
            if ids_val:
                pid = self.make_unique_xmlid(docname, ids_val.split()[0])
                self.doc_top_xmlid[docname] = pid
                self.register_ids(docname, ids_val, pid)
            else:
                # Synthetic root id so doc-level refs resolve
                pid = self.make_unique_xmlid(docname, f"doc-{docname}")
                self.doc_top_xmlid[docname] = pid

            # Register every section and target node in the document
            for node in root.iter():
                tag = strip_ns(node.tag)
                if tag not in ("section", "target"):
                    continue
                ids_val = node.attrib.get("ids", "")
                if not ids_val:
                    continue
                pid = self.make_unique_xmlid(docname, ids_val.split()[0])
                self.register_ids(docname, ids_val, pid)

    # ------------------------------------------------------------------
    # Xref resolution
    # ------------------------------------------------------------------

    def note_unresolved(self, ref: str) -> None:
        self.unresolved_xrefs[ref] = self.unresolved_xrefs.get(ref, 0) + 1

    def resolve_ref(self, current_doc: str, refid: str) -> Optional[str]:
        if not refid:
            return None
        if refid == "self":
            return self.doc_top_xmlid.get(current_doc)

        cands = {refid, refid.lower(), norm_key(refid),
                 refid.replace("-", "_"), refid.replace("_", "-")}

        # 1) Local id_map
        for c in cands:
            result = self.id_map.get((current_doc, c))
            if result:
                return result

        # 2) Via label_map
        for c in cands:
            if c in self.label_map:
                tdoc, tid = self.label_map[c]
                for t in (tid, tid.lower(), norm_key(tid),
                          tid.replace("-", "_"), tid.replace("_", "-")):
                    result = self.id_map.get((tdoc, t))
                    if result:
                        return result
            nk = norm_key(c)
            if nk in self.label_norm_map:
                tdoc, tid = self.label_norm_map[nk]
                for t in (tid, tid.lower(), norm_key(tid),
                          tid.replace("-", "_"), tid.replace("_", "-")):
                    result = self.id_map.get((tdoc, t))
                    if result:
                        return result

        # 3) Global id index (unambiguous matches only)
        for c in cands:
            docs = (self.global_id_index.get(c)
                    or self.global_id_index.get(norm_key(c)))
            if docs and len(docs) == 1:
                only_doc = next(iter(docs))
                for k in (c, norm_key(c), c.replace("-", "_"), c.replace("_", "-")):
                    result = self.id_map.get((only_doc, k))
                    if result:
                        return result
        return None

    # ------------------------------------------------------------------
    # Inline node conversion
    # ------------------------------------------------------------------

    def seen(self, node: ET.Element) -> None:
        k = strip_ns(node.tag)
        self.seen_counts[k] = self.seen_counts.get(k, 0) + 1

    def convert_inline_children(
        self, docname: str, src: ET.Element, dst: ET.Element
    ) -> None:
        """Copy inline content of src into dst, converting known inline tags."""
        if src.text:
            dst.text = (dst.text or "") + src.text
        for ch in src:
            elem = self.convert_node(docname, ch)
            if elem is not None:
                dst.append(elem)
                if ch.tail:
                    # attach tail to the new child element
                    elem.tail = (elem.tail or "") + ch.tail
            else:
                # Unknown inline: fold text+tail into parent text so nothing is lost
                combined = (ch.text or "") + "".join(
                    (get_all_text(gc) + (gc.tail or "")) for gc in ch
                ) + (ch.tail or "")
                if dst.text is None:
                    dst.text = combined
                elif len(dst):
                    last = dst[-1]
                    last.tail = (last.tail or "") + combined
                else:
                    dst.text += combined

    def convert_node(self, docname: str, node: ET.Element) -> Optional[ET.Element]:
        """Convert an inline Docutils node to a PreTeXt inline element."""
        self.seen(node)
        tag = strip_ns(node.tag)

        if tag == "emphasis":
            em = ET.Element("em")
            self.convert_inline_children(docname, node, em)
            return em

        if tag == "strong":
            term = ET.Element("term")
            self.convert_inline_children(docname, node, term)
            return term

        if tag == "literal":
            c = ET.Element("c")
            c.text = get_all_text(node)
            return c

        if tag == "inline":
            # Roles like :button:, :menu:, :ui: etc. – render as <c> for now
            classes = node.get("classes", "")
            if any(cls in classes for cls in ("role-button", "role-ui", "role-menu",
                                               "role-inspector", "guilabel")):
                c = ET.Element("c")
                c.text = get_all_text(node)
                return c
            # Generic inline – preserve text
            span = ET.Element("em")  # closest neutral inline in PreTeXt
            self.convert_inline_children(docname, node, span)
            return span

        if tag == "reference":
            refid = node.attrib.get("refid")
            refuri = node.attrib.get("refuri")
            text = get_all_text(node)
            if refid:
                resolved = self.resolve_ref(docname, refid)
                if resolved:
                    if text:
                        x = ET.Element("xref", {"ref": resolved, "text": "custom"})
                        x.text = text
                    else:
                        x = ET.Element("xref", {"ref": resolved, "text": "title"})
                    return x
                self.note_unresolved(refid)
                if text:
                    x = ET.Element("xref", {"provisional": refid, "text": "custom"})
                    x.text = text
                else:
                    x = ET.Element("xref", {"provisional": refid})
                return x
            if refuri and re.match(r"^[a-zA-Z]+://", refuri):
                u = ET.Element("url", {"href": refuri})
                u.text = text or refuri
                return u
            # Internal Sphinx cross-reference without refid
            if text:
                # Set text="custom" now so slug-rescue does not later combine
                # text="title" with existing text content (deprecated pattern).
                x = ET.Element("xref", {"provisional": text, "text": "custom"})
                x.text = text
                return x

        if tag == "pending_xref":
            reftarget = node.attrib.get("reftarget", "")
            text = get_all_text(node)
            resolved = self.resolve_ref(docname, reftarget)
            if resolved:
                if text:
                    x = ET.Element("xref", {"ref": resolved, "text": "custom"})
                    x.text = text
                else:
                    x = ET.Element("xref", {"ref": resolved, "text": "title"})
                return x
            self.note_unresolved(reftarget)
            if text:
                x = ET.Element("xref",
                               {"provisional": reftarget or text, "text": "custom"})
                x.text = text
            else:
                x = ET.Element("xref", {"provisional": reftarget or text})
            return x

        if tag in ("subscript",):
            sub = ET.Element("m")
            sub.text = f"_{{{get_all_text(node)}}}"
            return sub

        if tag in ("superscript",):
            sup = ET.Element("m")
            sup.text = f"^{{{get_all_text(node)}}}"
            return sup

        if tag == "math":
            m = ET.Element("m")
            m.text = node.get("latex") or get_all_text(node)
            return m

        # Unknown inline – return None so caller can fold text into parent
        self.unhandled_counts[tag] = self.unhandled_counts.get(tag, 0) + 1
        return None

    # ------------------------------------------------------------------
    # Block node conversion
    # ------------------------------------------------------------------

    def _make_id_attrs(
        self, docname: str, node: ET.Element
    ) -> Dict[str, str]:
        """Return {'xml:id': ...} if the node carries ids, else {}."""
        ids_val = node.attrib.get("ids", "")
        if not ids_val:
            return {}
        pid = self.make_unique_xmlid(docname, ids_val.split()[0])
        self.register_ids(docname, ids_val, pid)
        return {"xml:id": pid}

    def _resolve_image_uri(self, uri: str) -> str:
        """Resolve a Sphinx image URI to a path usable by PreTeXt.

        Sphinx XML stores image paths relative to the source RST file, e.g.:
          ../_images/foo.png
          _images/foo.png
          ../../_images/foo.png

        PreTeXt resolves image source= relative to the project root (where
        project.ptx lives). We rewrite all _images/* references to just
        _images/filename so they resolve from the project root regardless
        of which subdirectory the PTX file lives in.

        Absolute URLs (http://, https://) are left unchanged.
        """
        if not uri:
            return uri
        # Leave external URLs alone
        if re.match(r'^[a-zA-Z]+://', uri):
            return uri
        # Normalise path separators
        uri = uri.replace('\\', '/')
        # Strip leading ../ segments to get the canonical path
        # e.g. ../../_images/foo.png -> _images/foo.png
        parts = uri.split('/')
        # Find _images in the parts and take from there
        try:
            idx = next(i for i, p in enumerate(parts) if p == '_images')
            return '/'.join(parts[idx:])
        except StopIteration:
            pass
        # No _images segment — return as-is (may be an external path or
        # a correctly rooted path already)
        return uri

    def convert_block(self, docname: str, node: ET.Element) -> Optional[ET.Element]:
        """Convert a block-level Docutils node to a PreTeXt block element."""
        self.seen(node)
        tag = strip_ns(node.tag)

        # ---- silently dropped nodes ----
        if tag in {"comment", "substitution_definition", "raw",
                   "pending_xref", "only"}:
            return None

        # ---- target nodes: register ids but produce no output ----
        if tag == "target":
            ids_val = node.attrib.get("ids", "")
            refid = node.attrib.get("refid", "")
            if ids_val:
                pid = self.make_unique_xmlid(docname, ids_val.split()[0])
                self.register_ids(docname, ids_val, pid)
            return None

        # ---- paragraph ----
        if tag == "paragraph":
            p = ET.Element("p", self._make_id_attrs(docname, node))
            self.convert_inline_children(docname, node, p)
            return p

        # ---- literal_block / code-block ----
        if tag == "literal_block":
            lang = node.attrib.get("language", "")
            prog = ET.Element("program")
            if lang:
                prog.set("language", lang)
            inp = ET.SubElement(prog, "code")
            inp.text = get_all_text(node)
            return prog

        # ---- block_quote ----
        if tag == "block_quote":
            bq = ET.Element("blockquote")
            for ch in node:
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    bq.append(blk)
            return bq

        # ---- admonitions ----
        if tag in ADMONITION_MAP:
            ptx_tag = ADMONITION_MAP[tag]
            adm = ET.Element(ptx_tag, self._make_id_attrs(docname, node))
            # Use the explicit title if present, else the admonition type
            title_node = next(
                (c for c in node if strip_ns(c.tag) == "title"), None
            )
            title_text = get_all_text(title_node) if title_node is not None else tag.capitalize()
            ET.SubElement(adm, "title").text = title_text
            for ch in node:
                if strip_ns(ch.tag) == "title":
                    continue
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    adm.append(blk)
            return adm

        # Generic admonition directive
        if tag == "admonition":
            adm = ET.Element("note", self._make_id_attrs(docname, node))
            title_node = next(
                (c for c in node if strip_ns(c.tag) == "title"), None
            )
            if title_node is not None:
                ET.SubElement(adm, "title").text = get_all_text(title_node)
            for ch in node:
                if strip_ns(ch.tag) == "title":
                    continue
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    adm.append(blk)
            return adm

        # ---- lists ----
        if tag == "bullet_list":
            ul = ET.Element("ul")
            for li_src in children_local(node, "list_item"):
                li = self._convert_list_item(docname, li_src)
                ul.append(li)
            return ul

        if tag == "enumerated_list":
            ol = ET.Element("ol")
            for li_src in children_local(node, "list_item"):
                li = self._convert_list_item(docname, li_src)
                ol.append(li)
            return ol

        if tag == "list_item":
            return self._convert_list_item(docname, node)

        # ---- definition list ----
        if tag == "definition_list":
            dl = ET.Element("dl")
            for item in children_local(node, "definition_list_item"):
                term_node = next(
                    (c for c in item if strip_ns(c.tag) == "term"), None
                )
                def_node = next(
                    (c for c in item if strip_ns(c.tag) == "definition"), None
                )
                dt = ET.SubElement(dl, "dt")
                if term_node is not None:
                    self.convert_inline_children(docname, term_node, dt)
                dd = ET.SubElement(dl, "dd")
                if def_node is not None:
                    for ch in def_node:
                        blk = self.convert_block(docname, ch)
                        if blk is not None:
                            dd.append(blk)
            return dl

        # ---- field list (e.g. :param:, :returns:) ----
        if tag == "field_list":
            dl = ET.Element("dl")
            for field in children_local(node, "field"):
                fname = next(
                    (c for c in field if strip_ns(c.tag) == "field_name"), None
                )
                fbody = next(
                    (c for c in field if strip_ns(c.tag) == "field_body"), None
                )
                dt = ET.SubElement(dl, "dt")
                if fname is not None:
                    dt.text = get_all_text(fname)
                dd = ET.SubElement(dl, "dd")
                if fbody is not None:
                    for ch in fbody:
                        blk = self.convert_block(docname, ch)
                        if blk is not None:
                            dd.append(blk)
            return dl

        # ---- image ----
        if tag == "image":
            uri = self._resolve_image_uri(node.attrib.get("uri", ""))
            alt = node.attrib.get("alt", "")
            fig = ET.Element("figure")
            img = ET.SubElement(fig, "image")
            if uri:
                img.set("source", uri)
            if alt:
                cap = ET.SubElement(fig, "caption")
                cap.text = alt
            return fig

        # ---- figure (image + caption) ----
        if tag == "figure":
            fig = ET.Element("figure", self._make_id_attrs(docname, node))
            img_node = next(
                (c for c in node if strip_ns(c.tag) == "image"), None
            )
            cap_node = next(
                (c for c in node if strip_ns(c.tag) == "caption"), None
            )
            if img_node is not None:
                uri = self._resolve_image_uri(img_node.attrib.get("uri", ""))
                img = ET.SubElement(fig, "image")
                if uri:
                    img.set("source", uri)
            if cap_node is not None:
                cap = ET.SubElement(fig, "caption")
                self.convert_inline_children(docname, cap_node, cap)
            return fig

        # ---- table ----
        if tag in {"table", "tabular_col_spec"}:
            return self._convert_table(docname, node)

        # ---- math block ----
        if tag in {"math_block", "displaymath"}:
            me = ET.Element("me")
            me.text = node.get("latex") or get_all_text(node)
            return me

        # ---- rubric (bold paragraph used as an informal heading) ----
        if tag == "rubric":
            p = ET.Element("p")
            b = ET.SubElement(p, "term")
            b.text = get_all_text(node)
            return p

        # ---- line_block (poetry / addresses) ----
        if tag == "line_block":
            p = ET.Element("p")
            lines = []
            for line in iter_local(node, "line"):
                lines.append(get_all_text(line))
            p.text = "\n".join(lines)
            return p

        # ---- transition (horizontal rule) ----
        if tag == "transition":
            return None  # no clean PreTeXt equivalent; drop

        # ---- sphinx-tabs container ----
        if tag == "container":
            classes = node.attrib.get("classes", "")
            # Outer sphinx-tabs wrapper: recurse into panels, drop tab labels
            if "sphinx-tabs" in classes:
                return self._convert_sphinx_tabs(docname, node)
            # Individual panel: just recurse
            if "sphinx-tabs-panel" in classes:
                wrapper = ET.Element("p")  # placeholder; caller unwraps
                blks = []
                for ch in node:
                    blk = self.convert_block(docname, ch)
                    if blk is not None:
                        blks.append(blk)
                if len(blks) == 1:
                    return blks[0]
                # Multiple blocks: wrap in a remark (neutral container)
                rem = ET.Element("remark")
                for b in blks:
                    rem.append(b)
                return rem
            # Tab label container: suppress (it's just the button text)
            if "sphinx-tabs-tab" in classes:
                return None
            # Other containers: recurse
            blks = []
            for ch in node:
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    blks.append(blk)
            if not blks:
                return None
            if len(blks) == 1:
                return blks[0]
            rem = ET.Element("remark")
            for b in blks:
                rem.append(b)
            return rem

        # ---- desc (Sphinx domain object descriptions) ----
        if tag == "desc":
            p = ET.Element("p", self._make_id_attrs(docname, node))
            p.text = get_all_text(node)
            return p

        if tag in {"desc_signature", "desc_content", "desc_annotation",
                   "desc_name", "desc_parameterlist", "desc_parameter"}:
            p = ET.Element("p")
            p.text = get_all_text(node)
            return p

        # ---- system_message: drop ----
        if tag == "system_message":
            return None

        # ---- topic (e.g. contents:: directive) ----
        if tag == "topic":
            # Render as a note with optional title
            note = ET.Element("note", self._make_id_attrs(docname, node))
            title_node = next(
                (c for c in node if strip_ns(c.tag) == "title"), None
            )
            if title_node is not None:
                ET.SubElement(note, "title").text = get_all_text(title_node)
            for ch in node:
                if strip_ns(ch.tag) == "title":
                    continue
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    note.append(blk)
            return note

        # ---- section is handled by convert_section, not here ----
        if tag == "section":
            return None  # should not be reached via convert_block

        # ---- fallback: preserve ids, dump text ----
        self.unhandled_counts[tag] = self.unhandled_counts.get(tag, 0) + 1
        p = ET.Element("p", self._make_id_attrs(docname, node))
        p.text = get_all_text(node)
        return p if p.text else None

    # ------------------------------------------------------------------
    # Block helpers
    # ------------------------------------------------------------------

    def _convert_list_item(self, docname: str, node: ET.Element) -> ET.Element:
        li = ET.Element("li")
        children = list(node)
        if len(children) == 1 and strip_ns(children[0].tag) == "paragraph":
            # Simple single-paragraph item: inline content directly in <li>
            self.convert_inline_children(docname, children[0], li)
        else:
            for ch in children:
                blk = self.convert_block(docname, ch)
                if blk is None:
                    blk = self._inline_fallback(docname, ch)
                if blk is not None:
                    li.append(blk)
        return li

    def _inline_fallback(self, docname: str, node: ET.Element) -> Optional[ET.Element]:
        """Try convert_node (inline); if that fails, dump text into a <p>."""
        el = self.convert_node(docname, node)
        if el is not None:
            return el
        text = get_all_text(node)
        if text:
            p = ET.Element("p")
            p.text = text
            return p
        return None

    def _convert_sphinx_tabs(self, docname: str, outer: ET.Element) -> Optional[ET.Element]:
        """Convert a sphinx-tabs container into sequential PreTeXt blocks.

        Tab labels are suppressed; each panel's content is emitted in order.
        If every panel contains exactly one literal_block, wrap as a
        <listing> so readers see them as code alternatives.
        """
        panels = [
            c for c in outer
            if "sphinx-tabs-panel" in c.attrib.get("classes", "")
        ]
        if not panels:
            return None

        converted = []
        for panel in panels:
            for ch in panel:
                blk = self.convert_block(docname, ch)
                if blk is not None:
                    converted.append(blk)

        if not converted:
            return None
        if len(converted) == 1:
            return converted[0]

        # Multiple panels: wrap in a remark (neutral named container)
        rem = ET.Element("remark")
        ET.SubElement(rem, "title").text = "Code examples"
        for b in converted:
            rem.append(b)
        return rem

    def _convert_table(self, docname: str, node: ET.Element) -> Optional[ET.Element]:
        """Convert a Docutils table node to a PreTeXt <tabular>."""
        # Find the tgroup(s)
        tgroups = list(iter_local(node, "tgroup"))
        if not tgroups:
            return None
        tgroup = tgroups[0]

        tabular = ET.Element("tabular")

        # Emit <col width="X%"> so PreTeXt does not warn about missing widths
        # when cells contain block content like <p>.
        ncols = int(tgroup.attrib.get("cols", 0))
        if not ncols:
            # Count entries in the first available row as a fallback
            first_row = next(iter_local(tgroup, "row"), None)
            if first_row is not None:
                ncols = len(list(iter_local(first_row, "entry")))
        if ncols > 0:
            # Emit <col> elements with no width attribute.
            # PreTeXt 2.39+ requires percentages but crashes when they sum
            # over 100%; bare integers are also rejected. Omitting width
            # entirely causes PreTeXt to distribute columns equally with
            # no percentage validation at all.
            for _ in range(ncols):
                ET.SubElement(tabular, "col")

        # Header rows
        thead = next(iter_local(tgroup, "thead"), None)
        if thead is not None:
            for row in iter_local(thead, "row"):
                tr = ET.SubElement(tabular, "row", {"header": "yes"})
                for entry in iter_local(row, "entry"):
                    cell = ET.SubElement(tr, "cell")
                    for ch in entry:
                        blk = self.convert_block(docname, ch)
                        if blk is not None:
                            cell.append(blk)
                    if not len(cell):
                        cell.text = get_all_text(entry)

        # Body rows
        tbody = next(iter_local(tgroup, "tbody"), None)
        if tbody is not None:
            for row in iter_local(tbody, "row"):
                tr = ET.SubElement(tabular, "row")
                for entry in iter_local(row, "entry"):
                    cell = ET.SubElement(tr, "cell")
                    for ch in entry:
                        blk = self.convert_block(docname, ch)
                        if blk is not None:
                            cell.append(blk)
                    if not len(cell):
                        cell.text = get_all_text(entry)

        return tabular

    # ------------------------------------------------------------------
    # Section / document conversion
    # ------------------------------------------------------------------

    # PreTeXt structural elements by nesting depth inside a chapter
    _SECTION_TAGS = ["section", "subsection", "subsubsection", "paragraphs"]

    def _section_tag(self, depth: int) -> str:
        return self._SECTION_TAGS[min(depth, len(self._SECTION_TAGS) - 1)]

    def convert_section(
        self, docname: str, sec: ET.Element, depth: int
    ) -> List[ET.Element]:
        """Recursively convert a Docutils <section> into PreTeXt structural elements."""
        tag = self._section_tag(depth)
        ids_val = sec.attrib.get("ids", "")
        title_node = next(iter_local(sec, "title"), None)
        sid = self._get_or_make_xmlid(docname, ids_val)
        self.register_ids(docname, ids_val, sid)

        div = ET.Element(tag, {"xml:id": sid})
        ET.SubElement(div, "title").text = (
            get_all_text(title_node) if title_node is not None else "Untitled"
        )

        blocks_before: List[ET.Element] = []
        blocks_after: List[ET.Element] = []
        subsections: List[ET.Element] = []
        seen_section = False

        for child in sec:
            lname = strip_ns(child.tag)
            if lname == "title":
                continue
            if lname == "section":
                seen_section = True
                for s in self.convert_section(docname, child, depth + 1):
                    subsections.append(s)
                continue
            blk = self.convert_block(docname, child)
            if blk is None:
                continue
            if not seen_section:
                blocks_before.append(blk)
            else:
                blocks_after.append(blk)

        # Place all block content directly in the division, then subsections.
        # We do not use <introduction>/<conclusion> wrappers because when
        # subsections arrive via xi:include, PreTeXt's level-checker fires
        # before XInclude resolves them and reports "introduction does not
        # know its level".
        for b in blocks_before:
            div.append(b)
        for s in subsections:
            div.append(s)
        for b in blocks_after:
            div.append(b)

        return [div]

    def convert_doc_as(
        self, docname: str, ptx_tag: str,
        has_xi_children: bool = False,
    ) -> Optional[ET.Element]:
        """Convert a single Sphinx XML document into a PreTeXt element.

        ptx_tag is one of: 'part', 'chapter', 'section', etc.

        has_xi_children=True means this element will later have xi:include
        children appended (toctree sub-pages). In that case, any sections
        already present in the document body must be wrapped in <introduction>
        so they do not compete with the xi:included sections for numbering.
        Without this, both the internal section and the first xi:included
        section get the same number (e.g. two "8.1" entries).
        """
        if docname not in self.doc_to_path:
            return None
        if docname in self.visited_docs:
            return None
        self.visited_docs.add(docname)

        root = self._load_doc(docname)

        ids_val = root.attrib.get("ids", "")
        # Reuse the id minted during pre-registration if available
        top_id = self.doc_top_xmlid.get(docname) or self._get_or_make_xmlid(docname, ids_val)
        self.doc_top_xmlid[docname] = top_id
        self.register_ids(docname, ids_val, top_id)

        container = ET.Element(ptx_tag, {"xml:id": top_id})
        title_node = next(iter_local(root, "title"), None)
        ET.SubElement(container, "title").text = (
            get_all_text(title_node) if title_node is not None else docname
        )

        blocks_before: List[ET.Element] = []
        blocks_after: List[ET.Element] = []
        sections: List[ET.Element] = []
        seen_section = False

        for child in root:
            lname = strip_ns(child.tag)
            if lname == "title":
                continue
            if lname == "section":
                seen_section = True
                # depth=0 -> <section>, depth=1 -> <subsection>, etc.
                # Use depth=0 so internal sections inside a chapter become
                # <section> not <subsection>.
                for s in self.convert_section(docname, child, depth=0):
                    sections.append(s)
                continue
            blk = self.convert_block(docname, child)
            if blk is None:
                continue
            if not seen_section:
                blocks_before.append(blk)
            else:
                blocks_after.append(blk)

        # Place all content directly: blocks first, then sections.
        # No <introduction> or <conclusion> wrappers — these cause
        # "introduction does not know its level" errors in PreTeXt when
        # sibling sections arrive via xi:include (level-checker runs before
        # XInclude expansion). Content renders correctly without wrappers.
        for b in blocks_before:
            container.append(b)
        for s in sections:
            container.append(s)
        for b in blocks_after:
            container.append(b)

        return container

    def _load_doc(self, docname: str) -> ET.Element:
        if docname not in self.roots:
            self.roots[docname] = ET.parse(self.doc_to_path[docname]).getroot()
        return self.roots[docname]

    # Content tags that make a doc a "real" page vs a pure toctree index
    _CONTENT_TAGS = frozenset({
        # Deliberately excludes "section" and "target": a document whose only
        # direct children are <section> and <target> nodes is a pure toctree
        # index with no body content and should be treated as transparent.
        "paragraph", "bullet_list", "enumerated_list",
        "literal_block", "note", "warning", "tip", "caution", "important",
        "table", "figure", "image", "block_quote", "definition_list",
        "field_list", "math_block", "rubric", "admonition",
    })

    def _has_content(self, docname: str) -> bool:
        """Return True if this doc has body content beyond a bare title.

        Pure toctree-index files (e.g. tutorials/scripting/index) have only
        a title node at the document root, no sections or paragraphs of their
        own. We use this to decide whether to emit them as structural containers
        (part/chapter) or collapse them so their children are promoted.
        """
        if docname not in self.doc_to_path:
            return False
        root = self._load_doc(docname)
        for child in root:
            if strip_ns(child.tag) in self._CONTENT_TAGS:
                return True
        return False

    # ------------------------------------------------------------------
    # Main run() — toctree-aware
    # ------------------------------------------------------------------

    def run(self) -> None:
        os.makedirs(self.out_dir, exist_ok=True)
        chapters_dir = os.path.join(self.out_dir, "chapters")
        os.makedirs(chapters_dir, exist_ok=True)

        # --- Build the ordered doc list from the toctree ---
        env_path = self._guess_env()
        toctree_includes: Optional[Dict[str, List[str]]] = None
        if env_path:
            toctree_includes = _load_toctree_includes(env_path)

        if toctree_includes is not None:
            ordered_with_depth = _walk_toctree(
                self.index_doc, toctree_includes, JUNK_DOCNAMES
            )
        else:
            # Fallback: flat list from RST parsing, all treated as chapters
            print("Warning: could not load toctree from pickle; falling back to RST parsing.")
            try:
                with open(
                    os.path.join(os.path.dirname(self.xml_dir), "index.rst"),
                    encoding="utf-8",
                ) as f:
                    index_text = f.read()
            except OSError:
                index_text = ""
            flat = parse_index_rst_toctrees(index_text)
            # depth=1 so everything is a chapter
            ordered_with_depth = [(self.index_doc, 0)] + [(d, 1) for d in flat]

        # --- Load toctree captions for part grouping -----------------------
        # godot-docs has a FLAT toctree: about/*, getting_started/*,
        # tutorials/* etc. are all direct children of index at depth 1.
        # Sphinx groups them into sidebar sections using toctree :caption:
        # directives. We read those captions to create <part> elements,
        # grouping all docs that share the same caption under one part.
        env_path_for_captions = self._guess_env()
        caption_map: Dict[str, str] = {}  # docname -> caption text
        if env_path_for_captions:
            caption_map = _load_toctree_captions(env_path_for_captions)

        # --- Assign PreTeXt structural levels via content-aware DFS --------
        #
        # Strategy:
        # 1. Direct children of index that share a toctree caption are grouped
        #    into a synthetic <part>. Children with no caption get a part derived
        #    from their path prefix.
        # 2. Within each group, docs that are empty index files (no body content,
        #    only section/target children) are transparent: their toctree children
        #    are promoted as direct chapters under the part.
        # 3. Docs with real body content become <chapter>; their toctree children
        #    become <section> (same page, appears in left TOC).

        # PreTeXt level for each doc
        ptx_level: Dict[str, str] = {}
        # Parent for xi:include nesting
        ptx_parent: Dict[str, Optional[str]] = {}
        # Children to xi:include inside each doc
        toc_children: Dict[str, List[str]] = {}
        # Synthetic part nodes (caption text -> synthetic part docname)
        synthetic_parts: Dict[str, str] = {}   # caption -> synthetic_id
        synthetic_part_titles: Dict[str, str] = {}  # synthetic_id -> title

        def _path_prefix(docname: str) -> str:
            """Return the first path component, used as fallback part grouping."""
            return docname.split("/")[0] if "/" in docname else docname

        def _get_or_create_part(caption: str) -> str:
            """Return synthetic part id for a caption, creating it if needed."""
            if caption not in synthetic_parts:
                pid = f"part-{slugify(caption)}"
                synthetic_parts[caption] = pid
                synthetic_part_titles[pid] = caption
                ptx_level[pid] = "part"
                ptx_parent[pid] = None
            return synthetic_parts[caption]

        def assign_chapter(
            docname: str, part_id: str, force_chapter: bool = False
        ) -> None:
            """Assign a doc and its descendants under the given part.

            force_chapter=True prevents transparent promotion even when the
            doc has no body content. Used for direct toctree caption entries
            (e.g. getting_started/introduction/index) which represent an
            intentional grouping that should always become a chapter.
            """
            if docname not in self.doc_to_path:
                return
            ti = toctree_includes or {}
            children = [
                c for c in ti.get(docname, [])
                if c in self.doc_to_path
            ]
            has_content = self._has_content(docname)

            if has_content or not children or force_chapter:
                # Emit as <chapter>; children become <section> on the same page
                ptx_level[docname] = "chapter"
                ptx_parent[docname] = part_id
                toc_children.setdefault(part_id, []).append(docname)
                for child in children:
                    assign_section(child, docname)
            else:
                # Empty intermediate index → transparent: promote to part level
                for child in children:
                    assign_chapter(child, part_id)

        def assign_section(docname: str, chapter_id: str) -> None:
            """Assign a doc as a <section> (or subsection) inside a chapter."""
            if docname not in self.doc_to_path:
                return
            ti = toctree_includes or {}
            children = [
                c for c in ti.get(docname, [])
                if c in self.doc_to_path
            ]
            has_content = self._has_content(docname)

            if has_content or not children:
                ptx_level[docname] = "section"
                ptx_parent[docname] = chapter_id
                toc_children.setdefault(chapter_id, []).append(docname)
                # Deeper children become subsections
                for child in children:
                    assign_subsection(child, docname)
            else:
                # Empty intermediate → transparent
                for child in children:
                    assign_section(child, chapter_id)

        def assign_subsection(docname: str, section_id: str) -> None:
            """Assign a doc as a <subsection> inside a section."""
            if docname not in self.doc_to_path:
                return
            ptx_level[docname] = "subsection"
            ptx_parent[docname] = section_id
            toc_children.setdefault(section_id, []).append(docname)

        # Walk direct children of the root index
        root_children = (toctree_includes or {}).get(self.index_doc, [])
        seen_prefixes: Dict[str, str] = {}  # prefix -> part_id for fallback grouping

        for docname in root_children:
            if docname not in self.doc_to_path:
                continue
            # Determine which part this doc belongs to
            caption = caption_map.get(docname)
            if caption:
                part_id = _get_or_create_part(caption)
            else:
                # Fallback: group by path prefix (e.g. "tutorials", "community")
                prefix = _path_prefix(docname)
                if prefix not in seen_prefixes:
                    part_title = prefix.replace("_", " ").replace("-", " ").title()
                    seen_prefixes[prefix] = _get_or_create_part(part_title)
                part_id = seen_prefixes[prefix]
            # Direct caption entries are always chapters even with no body content:
            # they represent intentional groupings (e.g. introduction/index,
            # step_by_step/index) that should appear as chapters with their
            # sub-pages as sections rather than being promoted transparently.
            is_caption_entry = bool(caption_map.get(docname))
            assign_chapter(docname, part_id, force_chapter=is_caption_entry)

        # Ordered list: synthetic parts first (in caption order), then their
        # children in toctree DFS order.
        # Build ordered_docs by walking synthetic parts in the order they were
        # first seen, then their chapter children in toctree order.
        part_order = list(dict.fromkeys(synthetic_parts.values()))  # insertion order
        ordered_docs: List[Tuple[str, str]] = []
        for part_id in part_order:
            ordered_docs.append((part_id, "part"))
            for chapter in toc_children.get(part_id, []):
                ordered_docs.append((chapter, ptx_level[chapter]))
                for section in toc_children.get(chapter, []):
                    ordered_docs.append((section, ptx_level[section]))
                    for subsec in toc_children.get(section, []):
                        ordered_docs.append((subsec, ptx_level.get(subsec, "subsection")))

        # --- Convert and write ---
        ET.register_namespace("xi", "http://www.w3.org/2001/XInclude")
        pre = ET.Element("pretext")
        book = ET.SubElement(pre, "book", {"xml:id": "generated"})
        ET.SubElement(book, "title").text = self.title

        chapter_paths: List[str] = []

        # Pass A: convert every assigned doc into a PreTeXt Element
        converted: Dict[str, ET.Element] = {}
        file_paths: Dict[str, str] = {}
        file_hrefs: Dict[str, str] = {}

        for docname, level in ordered_docs:
            if docname in synthetic_part_titles:
                # Synthetic part: create a bare <part> with just a title
                elem = ET.Element("part", {"xml:id": docname})
                ET.SubElement(elem, "title").text = synthetic_part_titles[docname]
                self.doc_top_xmlid[docname] = docname
            else:
                # Signal whether this doc will receive xi:include children so
                # convert_doc_as can wrap its body in <introduction> and avoid
                # competing section numbers (the duplicate 8.1 problem).
                will_have_xi_children = bool(toc_children.get(docname))
                elem = self.convert_doc_as(
                    docname, level,
                    has_xi_children=will_have_xi_children,
                )
            if elem is None:
                continue
            converted[docname] = elem

            doc_norm = docname.replace("\\", "/").lstrip("/")
            parts = [p for p in doc_norm.split("/") if p not in ("", ".", "..")]
            if not parts:
                parts = ["index"]
            rel_dir = os.path.join("chapters", *parts[:-1])
            abs_dir = os.path.join(self.out_dir, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)

            fname = f"{parts[-1]}.ptx"
            fpath = os.path.join(abs_dir, fname)
            href = os.path.join(rel_dir, fname).replace(os.sep, "/")
            file_paths[docname] = fpath
            file_hrefs[docname] = href

        # Pass B: append xi:includes for nested children, then write
        for docname, level in ordered_docs:
            if docname not in converted:
                continue
            elem = converted[docname]

            for child in toc_children.get(docname, []):
                if child not in file_hrefs:
                    continue
                parent_dir = os.path.dirname(file_paths[docname])
                child_rel = os.path.relpath(
                    file_paths[child], parent_dir
                ).replace(os.sep, "/")
                elem.append(ET.Element(
                    "{http://www.w3.org/2001/XInclude}include",
                    {"href": child_rel},
                ))

            indent_xml(elem)
            ET.ElementTree(elem).write(
                file_paths[docname], encoding="utf-8", xml_declaration=True
            )
            chapter_paths.append(file_paths[docname])

            # Only part/chapter docs without a nesting parent go into main.ptx
            if ptx_parent.get(docname) is None:
                book.append(ET.Element(
                    "{http://www.w3.org/2001/XInclude}include",
                    {"href": file_hrefs[docname]},
                ))

        # --- Pass 2: rescue provisional xrefs via title slugs ---
        slug_fixed, slug_remaining = _slug_rescue_second_pass_files(chapter_paths)

        # --- Pass 3: rewrite class-/enum- refs as external Godot API URLs ---
        class_fixed, class_remaining = _class_ref_third_pass(
            chapter_paths, self.godot_version
        )

        # --- Write main.ptx ---
        indent_xml(pre)
        ET.ElementTree(pre).write(
            os.path.join(self.out_dir, "main.ptx"),
            encoding="utf-8",
            xml_declaration=True,
        )

        # --- Write report ---
        report = {
            "xml_doc_count": len(self.doc_to_path),
            "docs_converted": len(chapter_paths),
            "labels_loaded": len(self.label_map),
            "env_pickle_error": self.env_pickle_error,
            "toctree_source": "pickle" if toctree_includes is not None else "rst_fallback",
            "toctree_entries": len(ordered_with_depth),
            "seen_counts": self.seen_counts,
            "unhandled_counts": self.unhandled_counts,
            "unresolved_xrefs": self.unresolved_xrefs,
            "slug_rescue_fixed": slug_fixed,
            "provisional_remaining_after_slug_rescue": slug_remaining,
            "class_refs_converted_to_url": class_fixed,
            "provisional_remaining_final": class_remaining,
            "chapter_files_written": len(chapter_paths),
        }
        with open(
            os.path.join(self.out_dir, "report.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(
            f"Done. Wrote {len(chapter_paths)} PTX files, main.ptx, and report.json."
        )
        print(
            f"  Toctree source: {report['toctree_source']} "
            f"({report['toctree_entries']} entries)"
        )
        print(f"  Pass 2 slug rescue fixed:          {slug_fixed}")
        print(f"  Pass 3 class refs -> URLs:         {class_fixed}")
        print(f"  Provisional xrefs remaining (final): {class_remaining}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Convert Sphinx XML output to modular PreTeXt."
    )
    ap.add_argument("xml_dir", help="Path to sphinx-build -b xml output directory")
    ap.add_argument("out_dir", help="Directory to write PreTeXt files into")
    ap.add_argument(
        "--index-doc",
        default="index",
        help="Root docname (no extension), default: index",
    )
    ap.add_argument("--title", default="Converted Book", help="Book title")
    ap.add_argument(
        "--env-pickle",
        default=None,
        help="Path to Sphinx environment.pickle (auto-detected if omitted)",
    )
    ap.add_argument(
        "--godot-version",
        default="stable",
        help="Godot docs version for class-ref URLs, e.g. 'stable', '4.3' (default: stable)",
    )
    ap.add_argument(
        "--include-classes",
        action="store_true",
        default=False,
        help="Include Godot API class-reference pages (excluded by default)",
    )
    args = ap.parse_args(argv)

    conv = Converter(
        xml_dir=args.xml_dir,
        out_dir=args.out_dir,
        title=args.title,
        index_doc=args.index_doc,
        env_pickle=args.env_pickle,
        godot_version=args.godot_version,
        include_classes=args.include_classes,
    )
    conv.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
