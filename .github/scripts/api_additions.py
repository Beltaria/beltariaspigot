#!/usr/bin/env python3
"""Render the "what BeltariaSpigot adds" section of the Pages landing page.

BeltariaSpigot is a patch stack on top of PandaSpigot, and its API patches wrap every change in
Paper-style `// BeltariaSpigot start [- why]` / `// BeltariaSpigot end` markers. Those markers
survive into the published -sources.jar, so the list of additions can be derived from the
artifact itself rather than maintained by hand.

Signatures are matched against the javadoc's own anchors instead of being reconstructed from
source, which is what makes the deep links correct: getChunkAtAsync has upstream overloads
taking a ChunkLoadCallback, and only comparing full parameter types tells those apart from the
overloads Beltaria added.

The parser is deliberately small - it walks braces to keep a stack of enclosing types and only
accepts a declaration sitting one level inside a type. That is enough for Bukkit's API sources
(interfaces, a few nested classes) without pulling in a real Java grammar.
"""
from __future__ import annotations

import html
import re
import sys
import zipfile
from pathlib import Path

MARKER_START = re.compile(r"//\s*BeltariaSpigot start\b[ \t]*-?[ \t]*(.*?)\s*$")
MARKER_END = re.compile(r"//\s*BeltariaSpigot end\b")
COMMENT_LINE = re.compile(r"^//[ \t]?(.*?)\s*$")
TYPE_DECL = re.compile(r"\b(?:class|interface|enum|record|@interface)\s+(\w+)")
LEADING_ANNOTATION = re.compile(r"^@\w+(?:\([^)]*\))?\s*")
MEMBER = re.compile(
    r"^(?:(?:public|protected|private|static|final|abstract|default|synchronized|native|strictfp)\s+)*"
    r"(?P<ret>[\w.$<>,\[\]\s?]+?)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*[;{]"
)
MODIFIERS = {
    "public", "protected", "private", "static", "final", "abstract", "default",
    "synchronized", "native", "strictfp", "transient", "volatile",
}
# A declaration never starts with one of these; a statement that happens to look like a call
# (`throw new UnsupportedOperationException(...)`) does.
STATEMENTS = {
    "throw", "return", "new", "if", "for", "while", "do", "switch", "case", "else",
    "try", "catch", "finally", "assert", "break", "continue", "super", "this",
}
FIRST_SENTENCE = re.compile(r"^(.*?[.!?])(?:\s|$)")


def strip_code(line, in_block_comment):
    """Blank out string/char literals and comments so brace counting cannot be fooled."""
    out, i, n = [], 0, len(line)
    while i < n:
        if in_block_comment:
            end = line.find("*/", i)
            if end == -1:
                return "".join(out), True
            i, in_block_comment = end + 2, False
            continue
        c = line[i]
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if c == "/" and i + 1 < n and line[i + 1] == "*":
            i, in_block_comment = i + 2, True
            continue
        if c == '"' or c == "'":
            quote, i = c, i + 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == quote:
                    i += 1
                    break
                i += 1
            out.append("_")
            continue
        out.append(c)
        i += 1
    return "".join(out), in_block_comment


def strip_generics(text):
    out, depth = [], 0
    for c in text:
        if c == "<":
            depth += 1
        elif c == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(c)
    return "".join(out)


def simple_type(token):
    """org.bukkit.Location -> Location, java.lang.String[] -> String[]."""
    token = strip_generics(token).strip()
    arrays = token.count("[")
    base = token.split("[")[0].strip().split(".")[-1]
    return base + "[]" * arrays


def split_params(params):
    """Parameter list -> simple type names, dropping parameter names and annotations."""
    params = strip_generics(params).strip()
    if not params:
        return []
    types = []
    for raw in params.split(","):
        tokens = [t for t in raw.replace("...", "[]").split() if not t.startswith("@")]
        tokens = [t for t in tokens if t not in MODIFIERS]
        if tokens:
            types.append(simple_type(tokens[0]))
    return types


def first_sentence(text):
    """Marker rationales wrap over several // lines; one sentence is enough for a label."""
    text = " ".join(text.split())
    match = FIRST_SENTENCE.match(text)
    return (match.group(1) if match else text).rstrip(".")


class Addition(object):
    def __init__(self, owner, package, kind, name, params, display, why):
        self.owner = owner        # enclosing type as javadoc names it, e.g. "ItemMeta.Spigot"
        self.package = package
        self.kind = kind          # "method" or "type"
        self.name = name
        self.params = params
        self.display = display
        self.why = why


def scan_sources(jar_path):
    additions = []
    with zipfile.ZipFile(jar_path) as zf:
        for entry in sorted(zf.namelist()):
            if entry.endswith(".java"):
                text = zf.read(entry).decode("utf-8", "replace")
                if "BeltariaSpigot start" in text:
                    additions.extend(scan_file(entry, text))
    return additions


def scan_file(entry, text):
    package = str(Path(entry).parent).replace("\\", "/").replace("/", ".")
    found = []
    stack = []                     # [(type name, brace depth the type was opened at)]
    depth, in_comment = 0, False
    why, in_block = "", False
    collecting_why = False
    block_owner, block_mark = "", 0
    pending, pending_depth = "", 0
    pending_type = None

    for line in text.splitlines():
        raw = line.strip()
        marker = MARKER_START.search(line)
        if marker:
            why, in_block, collecting_why, pending = marker.group(1) or "", True, True, ""
            block_owner, block_mark = ".".join(n for n, _ in stack), len(found)
        elif MARKER_END.search(line):
            if in_block and len(found) == block_mark:
                # A block that declares nothing changed behaviour rather than surface: /reload
                # still exists, it just refuses. Worth listing, but not as an API addition.
                found.append(Addition(block_owner, package, "behaviour", block_owner, [],
                                      block_owner, first_sentence(why)))
            in_block, collecting_why, pending = False, False, ""
        elif collecting_why:
            # The rationale usually runs on over the next few // lines before the javadoc.
            more = COMMENT_LINE.match(raw)
            if more:
                why = (why + " " + more.group(1)).strip()
            else:
                collecting_why = False

        code, in_comment = strip_code(line, in_comment)
        stripped = code.strip()
        line_depth = depth
        owner = ".".join(n for n, _ in stack)
        member_level = bool(stack) and line_depth == stack[-1][1] + 1

        decl = TYPE_DECL.search(code)
        if decl:
            pending_type = (decl.group(1), in_block, why)
            pending = ""
        elif in_block and stripped and member_level:
            if not pending:
                pending_depth = line_depth
            pending = (pending + " " + stripped).strip()
            if stripped.endswith((";", "{", "}")) and pending_depth == line_depth:
                candidate = LEADING_ANNOTATION.sub("", pending).strip()
                member = MEMBER.match(candidate)
                head = candidate.split(None, 1)[0] if candidate else ""
                if member and owner and head not in STATEMENTS:
                    params = split_params(member.group("params"))
                    display = "%s(%s)" % (member.group("name"), ", ".join(params))
                    found.append(Addition(owner, package, "method", member.group("name"),
                                          params, display, first_sentence(why)))
                pending = ""

        for c in code:
            if c == "{":
                if pending_type:
                    name, was_in_block, type_why = pending_type
                    if was_in_block:
                        found.append(Addition(".".join(n for n, _ in stack), package, "type",
                                              name, [], name, first_sentence(type_why)))
                    stack.append((name, depth))
                    pending_type = None
                depth += 1
            elif c == "}":
                depth -= 1
                while stack and depth <= stack[-1][1]:
                    stack.pop()
    return found


def javadoc_anchors(page):
    """Map (method name, simple param types) -> the anchor javadoc actually emitted."""
    anchors = {}
    if not page.is_file():
        return anchors
    text = page.read_text("utf-8", "replace")
    for raw in re.findall(r'id="([^"]+\([^"]*\))"', text):
        name, _, params = raw.partition("(")
        if name.startswith("&lt;"):          # <init>, i.e. a constructor
            continue
        types = tuple(simple_type(p) for p in params.rstrip(")").split(",") if p.strip())
        anchors[(name, types)] = raw
    return anchors


def render(additions, docroot, url_prefix):
    if not additions:
        return ""

    by_type = {}
    for a in additions:
        by_type.setdefault((a.package, a.owner), []).append(a)

    out = [
        "<h2>What BeltariaSpigot adds</h2>",
        '<p class="sub">Additions on top of PandaSpigot, derived from the '
        "<code>// BeltariaSpigot</code> markers in the published sources jar - so this list "
        "cannot drift from the artifact it documents.</p>",
    ]
    behaviour = []

    for package, owner in sorted(by_type):
        items = by_type[(package, owner)]
        if not any(a.kind in ("method", "type") for a in items):
            continue

        # A type added at the top level of a file has no enclosing type: it IS the page, so
        # there are no member anchors to resolve and the heading is just the package.
        page_name = owner
        pkg_path = package.replace(".", "/")
        anchors = javadoc_anchors(docroot / pkg_path / ("%s.html" % page_name)) if page_name else {}
        base = "%s/%s/%s.html" % (url_prefix, pkg_path, page_name)

        heading = "%s.%s" % (package, page_name) if page_name else package
        out.append("<h3><code>%s</code></h3>" % html.escape(heading))

        # One marker block is one feature; keep them apart so each keeps its own rationale.
        seen_why, blocks = [], {}
        for a in items:
            if a.why not in blocks:
                blocks[a.why] = []
                seen_why.append(a.why)
            blocks[a.why].append(a)

        for why in seen_why:
            if why:
                out.append('<p class="sub">%s</p>' % html.escape(why))
            out.append("<ul>")
            for a in blocks[why]:
                if a.kind == "type":
                    # javadoc names a nested type Outer.Inner.html and a top-level one Name.html
                    qualified = "%s.%s" % (page_name, a.name) if page_name else a.name
                    href = "%s/%s/%s.html" % (url_prefix, pkg_path, qualified)
                    out.append('<li><a href="%s"><code>%s</code></a> &mdash; new type</li>'
                               % (html.escape(href), html.escape(a.name)))
                    continue
                anchor = anchors.get((a.name, tuple(a.params)))
                label = html.escape(a.display)
                if anchor:
                    out.append('<li><a href="%s#%s"><code>%s</code></a></li>'
                               % (html.escape(base), html.escape(anchor), label))
                else:
                    # In the sources jar but with no javadoc anchor - package-private, or the
                    # two jars are out of step. Say so rather than emit a link that 404s.
                    out.append('<li><code>%s</code> <span class="sub">(not in the javadoc)'
                               "</span></li>" % label)
            out.append("</ul>")

    for a in additions:
        if a.kind == "behaviour":
            behaviour.append((("%s.%s" % (a.package, a.owner)).strip("."), a.why))
    if behaviour:
        out.append("<h3>Behaviour changes</h3>")
        out.append("<ul>")
        # One line per type, keeping the first block's rationale in source order - a type with
        # several marker blocks (ReloadCommand has two) is still one behaviour change.
        deduped, seen = [], set()
        for owner, why in behaviour:
            if owner not in seen:
                seen.add(owner)
                deduped.append((owner, why))
        for owner, why in deduped:
            suffix = " &mdash; " + html.escape(why) if why else ""
            out.append("<li><code>%s</code>%s</li>" % (html.escape(owner), suffix))
        out.append("</ul>")
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 4:
        print("usage: api_additions.py <sources.jar> <unpacked-javadoc-dir> <url-prefix>",
              file=sys.stderr)
        return 2
    sources, docroot, url_prefix = Path(argv[1]), Path(argv[2]), argv[3].rstrip("/")
    if not sources.is_file():
        return 0                # no sources jar published: nothing to say, and not an error
    sys.stdout.write(render(scan_sources(sources), docroot, url_prefix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
