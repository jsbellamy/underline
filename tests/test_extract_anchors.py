"""Unit tests for `## Touches` anchor extraction.

The extractor is exercised as a pure function of an issue body and file
sources — no `gh` subprocess, no filesystem scan. Anchor bodies are the real
shapes issue #223 used, since those are what an implementer actually receives.
"""

from __future__ import annotations

from scripts.extract_anchors import (
    Anchor,
    Span,
    markdown_section_span,
    parse_touches,
    python_symbol_spans,
    render,
)

MODULE = '''"""A module docstring."""

CONSTANT = {"a": 1}


@decorator
def wanted(argument: int) -> int:
    """Do the thing."""
    return argument


def unwanted() -> None:
    pass


class Holder:
    def method(self) -> None:
        pass
'''

DOCUMENT = """# Title

## Decision

Decided.

## Consequences

### Positive

Good.

### Negative

- The bad part.

## Later

Not part of Negative.
"""

TOUCHES = """## Contract

Some contract prose naming `pipeline/strip.py` that is not an anchor.

## Touches

- modify: `pipeline/final_polish.py` :: `initialize_bundle` — C1 probe layout
- modify: `docs/adr/0003-swing-action-canvas.md` :: Consequences → Negative — C5
- read: [authority] `docs/adr/0003-swing-action-canvas.md` :: Decision — swing `frame_w: 24`
- read: [seam] `pipeline/strip.py` :: `layout_for_motion_class`, `embed_on_class_canvas` — the resolver

The manifest is expected scope; justify each deviation in the PR body.

## Proof

- C1: a test naming `pipeline/strip.py` that is not an anchor either.
"""


def test_only_the_touches_section_yields_anchors() -> None:
    anchors = parse_touches(TOUCHES)

    assert len(anchors) == 4


def test_an_anchor_records_its_role_path_and_symbols() -> None:
    anchors = parse_touches(TOUCHES)

    assert anchors[0] == Anchor(
        role="modify",
        tag=None,
        path="pipeline/final_polish.py",
        symbols=("initialize_bundle",),
        note="C1 probe layout",
    )


def test_an_anchor_records_its_bracketed_tag() -> None:
    anchors = parse_touches(TOUCHES)

    assert anchors[2].tag == "authority"
    assert anchors[2].path == "docs/adr/0003-swing-action-canvas.md"


def test_a_backtick_free_symbol_field_is_taken_whole() -> None:
    anchors = parse_touches(TOUCHES)

    assert anchors[1].symbols == ("Consequences → Negative",)


def test_a_comma_separated_symbol_field_yields_each_symbol() -> None:
    anchors = parse_touches(TOUCHES)

    assert anchors[3].symbols == ("layout_for_motion_class", "embed_on_class_canvas")


def test_a_comma_separated_bare_symbol_field_yields_each_symbol() -> None:
    anchors = parse_touches(
        "## Touches\n\n- read: [authority] `adr.md` :: Decision, Later — both\n"
    )

    assert anchors[0].symbols == ("Decision", "Later")


def test_a_sidecar_anchor_resolves_to_the_whole_file() -> None:
    anchors = parse_touches(
        "## Touches\n\n- read: [authority] `identity.json` :: `seed_pad_px` — the pad\n"
    )

    output = render(anchors, {"identity.json": '{\n  "seed_pad_px": 4\n}\n'})

    assert '    2\t  "seed_pad_px": 4' in output
    assert "unresolved" not in output


def test_a_note_containing_backticks_does_not_become_a_symbol() -> None:
    anchors = parse_touches(TOUCHES)

    assert anchors[2].symbols == ("Decision",)
    assert anchors[2].note == "swing `frame_w: 24`"


def test_a_body_with_no_touches_section_yields_no_anchors() -> None:
    assert parse_touches("## Delta\n\nSomething changed.\n") == ()


def test_a_named_function_span_covers_its_decorator_through_its_last_line() -> None:
    assert python_symbol_spans(MODULE, ["wanted"]) == (Span(name="wanted", start=6, end=9),)


def test_a_module_constant_resolves_to_its_assignment() -> None:
    assert python_symbol_spans(MODULE, ["CONSTANT"]) == (
        Span(name="CONSTANT", start=3, end=3),
    )


def test_a_nested_method_resolves_without_its_class() -> None:
    assert python_symbol_spans(MODULE, ["method"]) == (Span(name="method", start=17, end=18),)


def test_spans_follow_the_order_the_anchor_named_them() -> None:
    spans = python_symbol_spans(MODULE, ["unwanted", "wanted"])

    assert [span.name for span in spans] == ["unwanted", "wanted"]


def test_an_undefined_symbol_yields_no_span() -> None:
    assert python_symbol_spans(MODULE, ["absent"]) == ()


def test_a_heading_span_stops_at_the_next_heading_of_its_level() -> None:
    assert markdown_section_span(DOCUMENT, "Decision") == Span(
        name="Decision", start=3, end=6
    )


def test_a_heading_path_selects_the_nested_heading() -> None:
    assert markdown_section_span(DOCUMENT, "Consequences → Negative") == Span(
        name="Negative", start=13, end=16
    )


def test_a_heading_path_whose_parent_is_absent_does_not_resolve() -> None:
    assert markdown_section_span(DOCUMENT, "Decision → Negative") is None


def test_a_rendered_anchor_carries_the_source_and_its_line_numbers() -> None:
    anchors = parse_touches(
        "## Touches\n\n- read: [seam] `mod.py` :: `wanted` — the seam\n"
    )

    output = render(anchors, {"mod.py": MODULE})

    assert "=== read [seam] mod.py :: wanted  (6-9)" in output
    assert "    7\tdef wanted(argument: int) -> int:" in output
    assert "def unwanted" not in output


def test_an_unresolved_symbol_is_reported_rather_than_silently_dropped() -> None:
    anchors = parse_touches("## Touches\n\n- read: `mod.py` :: `absent` — nowhere\n")

    output = render(anchors, {"mod.py": MODULE})

    assert "unresolved" in output
    assert "mod.py :: absent" in output


def test_a_resolved_heading_path_is_not_also_reported_unresolved() -> None:
    anchors = parse_touches(
        "## Touches\n\n- modify: `adr.md` :: Consequences → Negative — C5\n"
    )

    output = render(anchors, {"adr.md": DOCUMENT})

    assert "- The bad part." in output
    assert "unresolved" not in output


def test_a_missing_file_is_reported_rather_than_silently_dropped() -> None:
    anchors = parse_touches("## Touches\n\n- read: `gone.py` :: `wanted` — moved\n")

    output = render(anchors, {})

    assert "gone.py — file not found" in output
