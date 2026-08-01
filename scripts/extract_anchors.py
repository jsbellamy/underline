"""Print the `## Touches` anchors of an issue as source, not as file names.

An issue's `## Touches` `read:` lines are symbol-scoped — `pipeline/strip.py ::
layout_for_motion_class` names roughly a hundred lines of a two-thousand-line
module. Reading the file to reach the symbol pins the whole module in the
agent's context for the rest of the task, and an agentic loop re-sends that
context on every tool-call round trip. This script resolves each anchor to the
symbol it names, so the bounded context set is bounded in fact.

    npm run agents:anchors -- --issue 223

See `AGENTS.md` § Reading discipline for the rule this implements.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]

_ANCHOR = re.compile(
    r"^-\s+(?P<role>read|modify|create|add|delete)\s*:\s*"
    r"(?:\[(?P<tag>[^\]]+)\]\s*)?"
    r"`(?P<path>[^`]+)`"
    r"(?:\s*::\s*(?P<rest>.*)|\s+—\s+(?P<note>.*))?$"
)
_SECTION = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_BACKTICKED = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
_FENCE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})")

# The em-dash that separates an anchor's symbol field from its trailing note.
_NOTE_SEPARATOR = " — "

# Heading-path separators inside a Markdown anchor ("Consequences → Negative").
_HEADING_PATH = re.compile(r"\s*(?:→|>)\s*")


@dataclass(frozen=True)
class Anchor:
    """One `## Touches` line: what to read, and which part of it."""

    role: str
    tag: str | None
    path: str
    symbols: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class Span:
    """A resolved region of a file, as inclusive 1-based line numbers."""

    name: str
    start: int
    end: int


def parse_touches(issue_body: str) -> tuple[Anchor, ...]:
    """Return the anchors declared under the body's `## Touches` heading.

    Only that section is read: `## Contract` and `## Proof` name the same files
    in prose, and treating those as anchors would re-widen the read set this
    exists to narrow.
    """
    anchors: list[Anchor] = []
    in_touches = False

    for line in issue_body.splitlines():
        section = _SECTION.match(line)
        if section is not None:
            in_touches = section.group("title").strip().lower() == "touches"
            continue
        if not in_touches:
            continue

        match = _ANCHOR.match(line.strip())
        if match is None:
            continue

        if match.group("note") is not None:
            symbols, note = (), match.group("note").strip()
        else:
            symbols, note = _split_symbols_and_note(match.group("rest") or "")
        anchors.append(
            Anchor(
                role=match.group("role"),
                tag=match.group("tag"),
                path=match.group("path"),
                symbols=symbols,
                note=note,
            )
        )

    return tuple(anchors)


def _split_symbols_and_note(rest: str) -> tuple[tuple[str, ...], str]:
    """Split an anchor's `::` remainder into its symbols and trailing note.

    The note routinely contains backticks of its own, so the em-dash is split
    off first; otherwise a note like "swing `frame_w: 24`" would contribute a
    phantom symbol.
    """
    symbol_field, _, note = rest.partition(_NOTE_SEPARATOR)
    symbol_field = symbol_field.strip()

    backticked = tuple(m.group(1).strip() for m in _BACKTICKED.finditer(symbol_field))
    if backticked:
        return backticked, note.strip()

    if not symbol_field:
        return (), note.strip()

    # Bare symbol fields list headings by comma ("Decision, Limit"). An arrow
    # path inside one component stays intact.
    bare = tuple(part.strip() for part in symbol_field.split(",") if part.strip())
    return bare, note.strip()


def python_symbol_spans(source: str, names: Iterable[str]) -> tuple[Span, ...]:
    """Return the span of each named module-level or nested definition.

    Functions, classes, and annotated or plain module constants all resolve;
    a name with no definition is simply absent from the result, which is how
    the caller reports it unresolved.
    """
    wanted = list(names)
    tree = ast.parse(source)
    found: dict[str, Span] = {}

    for node in ast.walk(tree):
        for name in _defined_names(node):
            if name not in wanted or name in found:
                continue
            start = min(
                [node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))]
            )
            end = getattr(node, "end_lineno", None) or node.lineno
            found[name] = Span(name=name, start=start, end=end)

    return tuple(found[name] for name in wanted if name in found)


def _defined_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (node.name,)
    if isinstance(node, ast.Assign):
        return tuple(t.id for t in node.targets if isinstance(t, ast.Name))
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    return ()


def markdown_section_span(source: str, name: str) -> Span | None:
    """Return the span of the heading `name` selects, or None if it has none.

    `name` is either a heading title or an arrow-separated path of them
    ("Consequences → Negative"), which is how an issue points at a subsection
    whose own title is not unique in the document.
    """
    titles = [part for part in _HEADING_PATH.split(name.strip()) if part]
    if not titles:
        return None

    headings = _markdown_headings(source)

    search_from, search_to = 0, len(headings)
    match_index: int | None = None
    for title in titles:
        match_index = next(
            (
                position
                for position in range(search_from, search_to)
                if _normalized(headings[position][2]) == _normalized(title)
            ),
            None,
        )
        if match_index is None:
            return None
        # A later title is a subsection of this one, so the remaining search
        # is bounded by where this heading's own section ends.
        parent_level = headings[match_index][1]
        search_from = match_index + 1
        search_to = next(
            (
                position
                for position in range(match_index + 1, len(headings))
                if headings[position][1] <= parent_level
            ),
            len(headings),
        )

    assert match_index is not None
    start_line, level, title = headings[match_index]
    end_line = next(
        (line for line, depth, _ in headings[match_index + 1 :] if depth <= level),
        len(source.splitlines()) + 1,
    )
    return Span(name=title, start=start_line, end=end_line - 1)


def _markdown_headings(source: str) -> list[tuple[int, int, str]]:
    """Return ATX headings outside fenced code blocks."""
    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None

    for index, line in enumerate(source.splitlines(), start=1):
        fence_match = _FENCE.match(line)
        if fence_match is not None:
            marker = fence_match.group("marker")
            if fence is None:
                fence = (marker[0], len(marker))
            elif (
                marker[0] == fence[0]
                and len(marker) >= fence[1]
                and not line[fence_match.end() :].strip()
            ):
                fence = None
            continue
        if fence is not None:
            continue
        heading = _HEADING.match(line)
        if heading is not None:
            headings.append(
                (index, len(heading.group("hashes")), heading.group("title").strip())
            )

    return headings


def _normalized(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def resolve_anchor(anchor: Anchor, source: str) -> tuple[tuple[Span, ...], tuple[str, ...]]:
    """Return the spans `anchor` resolves to in `source`, and the symbols it
    does not. An anchor naming no symbol resolves to the whole file."""
    line_count = len(source.splitlines())
    if not anchor.symbols or not anchor.path.endswith((".py", ".md")):
        # Sidecars (identity manifests, provenance records, lock files) are
        # small by construction, so a key anchor resolves to the file it keys
        # into rather than to machinery for walking one.
        return (Span(name=anchor.path, start=1, end=line_count),), ()

    if anchor.path.endswith(".py"):
        found = python_symbol_spans(source, anchor.symbols)
        by_symbol = {span.name: span for span in found}
        pairs = [(symbol, by_symbol.get(symbol)) for symbol in anchor.symbols]
    else:
        # A Markdown span is named for the heading it landed on, which is the
        # last component of a heading path rather than the anchor's own text,
        # so each symbol is paired with its own lookup.
        pairs = [
            (symbol, markdown_section_span(source, symbol)) for symbol in anchor.symbols
        ]

    spans = tuple(span for _, span in pairs if span is not None)
    unresolved = tuple(symbol for symbol, span in pairs if span is None)
    return spans, unresolved


def render(
    anchors: Sequence[Anchor],
    sources: Mapping[str, str],
    *,
    unavailable: Mapping[str, str] | None = None,
) -> str:
    """Render every anchor as numbered source under a heading naming it."""
    blocks: list[str] = []
    extracted = 0
    misses: list[str] = []
    unavailable_reasons = unavailable or {}

    for anchor in anchors:
        source = sources.get(anchor.path)
        label = f"{anchor.role}{f' [{anchor.tag}]' if anchor.tag else ''} {anchor.path}"
        if source is None:
            misses.append(
                f"{label} — {unavailable_reasons.get(anchor.path, 'file not found')}"
            )
            continue
        if anchor.role in {"read", "modify"} and not anchor.symbols:
            misses.append(f"{label} — text file has no anchor; repair the manifest")
            continue

        spans, unresolved = resolve_anchor(anchor, source)
        lines = source.splitlines()
        for span in spans:
            blocks.append(f"=== {label} :: {span.name}  ({span.start}-{span.end})")
            blocks.extend(
                f"{number:>5}\t{lines[number - 1]}"
                for number in range(span.start, span.end + 1)
            )
            blocks.append("")
            extracted += span.end - span.start + 1
        misses.extend(f"{label} :: {name} — not found" for name in unresolved)

    total = sum(len(sources.get(a.path, "").splitlines()) for a in anchors)
    footer = [
        f"--- {extracted} lines extracted from {total} lines of anchored files",
    ]
    if misses:
        footer.append("--- unresolved text anchors or entries without readable source:")
        footer.extend(f"      {miss}" for miss in misses)

    return "\n".join([*blocks, *footer])


def _issue_body(issue: str) -> str:
    gh = "gh" if pathlib.Path("/usr/bin/gh").exists() else "/opt/homebrew/bin/gh"
    result = subprocess.run(
        [gh, "issue", "view", issue, "--json", "body", "--jq", ".body"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _load_sources(
    anchors: Sequence[Anchor],
) -> tuple[dict[str, str], dict[str, str]]:
    sources: dict[str, str] = {}
    unavailable: dict[str, str] = {}
    root = ROOT.resolve()

    for anchor in anchors:
        if anchor.path in sources or anchor.path in unavailable:
            continue
        relative = pathlib.PurePosixPath(anchor.path)
        path = (ROOT / pathlib.Path(*relative.parts)).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not path.is_relative_to(root)
        ):
            unavailable[anchor.path] = (
                "invalid manifest path; expected a repo-relative path"
            )
            continue
        if anchor.role == "create":
            unavailable[anchor.path] = "planned create; no source yet"
            continue
        if path.is_dir():
            unavailable[anchor.path] = "directory; inspect entries narrowly"
            continue
        if not path.is_file():
            unavailable[anchor.path] = "file not found"
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unavailable[anchor.path] = "binary file; inspect with the appropriate tool"
            continue
        sources[anchor.path] = source

    return sources, unavailable


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--issue", help="issue number to fetch with gh")
    source.add_argument(
        "--body-file", help="path to a file holding the issue body ('-' for stdin)"
    )
    args = parser.parse_args(argv)

    if args.issue:
        body = _issue_body(args.issue)
    elif args.body_file == "-":
        body = sys.stdin.read()
    else:
        body = pathlib.Path(args.body_file).read_text(encoding="utf-8")

    anchors = parse_touches(body)
    if not anchors:
        print("extract_anchors: no ## Touches anchors found", file=sys.stderr)
        return 1

    sources, unavailable = _load_sources(anchors)
    print(render(anchors, sources, unavailable=unavailable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
