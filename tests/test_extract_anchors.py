"""Unit tests for `## Touches` anchor extraction.

The extractor is exercised as a pure function of an issue body and file
sources — no `gh` subprocess, no filesystem scan. Anchor bodies are the real
shapes issue #223 used, since those are what an implementer actually receives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extract_anchors import (
    Anchor,
    Span,
    forecast_test_selection,
    format_test_impact,
    main,
    markdown_section_span,
    parse_touches,
    python_symbol_spans,
    render,
    write_paths_from_anchors,
)
from scripts.select_changed_tests import (
    Selection,
    select_test_files,
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


def test_an_unanchored_manifest_entry_keeps_its_purpose_note() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- read: [authority] `assets/dwarf/identity.png` — immutable identity\n"
    )

    assert anchors == (
        Anchor(
            role="read",
            tag="authority",
            path="assets/dwarf/identity.png",
            symbols=(),
            note="immutable identity",
        ),
    )


def test_a_create_entry_is_kept_without_requiring_an_anchor() -> None:
    anchors = parse_touches(
        "## Touches\n\n- create: `tests/test_new_seam.py` — prove the new seam\n"
    )

    assert anchors == (
        Anchor(
            role="create",
            tag=None,
            path="tests/test_new_seam.py",
            symbols=(),
            note="prove the new seam",
        ),
    )


_ACQUISITION_CONTROL_COMPANIONS = (
    "tests/test_asset_acquire.py",
    "tests/test_final_polish.py",
    "tests/test_final_polish_cli.py",
)

_ACQUISITION_CONTROL_TEST_SOURCES = {
    "tests/test_asset_acquire.py": 'store_root = tmp_path / "acquisition-controls"',
    "tests/test_final_polish.py": (
        'from tests.final_polish_harness import helper\n'
        'store = ROOT / "acquisition-controls"'
    ),
    "tests/test_final_polish_cli.py": (
        "from tests.final_polish_harness import helper\n"
        'patch.dict("os.environ", {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)})'
    ),
    "tests/final_polish_harness.py": (
        'store_root = bundle.parent / "acquisition-controls"'
    ),
}

_ISSUE_233_TOUCHES = """## Touches

- modify: `pipeline/final_polish.py` :: `initialize_bundle` — C2 registration
- modify: `pipeline/final_polish_cli.py` :: `_configure_parser` — summary output
- create: `acquisition-controls/legacy-bundles.json` — C5 allowlist
"""


def test_a_manifest_write_set_excludes_read_paths_and_dedupes_modify_paths() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- modify: `pipeline/final_polish.py` :: `initialize_bundle` — init\n"
        "- modify: `pipeline/final_polish.py` :: `check_bundle` — check\n"
        "- read: [authority] `pipeline/asset_acquire.py` :: `load_asset_attempts` — store\n"
        "- create: `acquisition-controls/legacy-bundles.json` — allowlist\n"
    )

    assert write_paths_from_anchors(anchors) == (
        "acquisition-controls/legacy-bundles.json",
        "pipeline/final_polish.py",
    )


def test_a_manifest_write_set_forecasts_selected_test_paths() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- modify: `scripts/extract_anchors.py` :: `render` — forecast\n"
        "- modify: `tests/test_extract_anchors.py` :: `test_a_manifest_write_set_forecasts_selected_test_paths` — pin\n"
    )
    existing = {
        "tests/test_extract_anchors.py",
        "tests/test_select_changed_tests.py",
    }

    selection = forecast_test_selection(anchors, existing)

    assert selection == select_test_files(
        ["scripts/extract_anchors.py", "tests/test_extract_anchors.py"],
        existing,
    )
    assert selection.kind == "selected"
    assert selection.files == ("tests/test_extract_anchors.py",)


def test_an_unknown_create_path_forecasts_whole_suite_with_the_selector_reason() -> None:
    anchors = parse_touches(
        "## Touches\n\n- create: `mystery/new-control.json` — unknown top-level file\n"
    )

    selection = forecast_test_selection(anchors, set(_ACQUISITION_CONTROL_COMPANIONS))

    assert selection.kind == "whole_suite"
    assert "no mapping rule" in selection.reason


def test_forecast_nothing_when_the_manifest_has_only_read_paths() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- read: [authority] `scripts/select_changed_tests.py` :: `select_test_files` — mapping\n"
    )

    selection = forecast_test_selection(anchors, {"tests/test_select_changed_tests.py"})

    assert selection == Selection(kind="nothing", reason="no changed files")


def test_the_selected_forecast_footer_lists_test_paths_in_sorted_order() -> None:
    output = format_test_impact(
        Selection(
            kind="selected",
            reason="mapped from the changed-file set",
            files=("tests/test_b.py", "tests/test_a.py"),
        )
    )

    assert "--- planned test selection: selected" in output
    assert "tests/test_a.py" in output
    assert "tests/test_b.py" in output
    assert output.index("tests/test_a.py") < output.index("tests/test_b.py")


def test_the_whole_suite_forecast_footer_includes_the_selector_reason() -> None:
    reason = (
        "mystery/new-control.json has no mapping rule, "
        "so the selection widens to the whole suite"
    )
    output = format_test_impact(Selection(kind="whole_suite", reason=reason))

    assert "--- planned test selection: whole_suite" in output
    assert reason in output


def test_the_nothing_forecast_footer_includes_the_selector_reason() -> None:
    output = format_test_impact(Selection(kind="nothing", reason="no changed files"))

    assert "--- planned test selection: nothing" in output
    assert "no changed files" in output


def test_the_anchor_output_appends_a_read_only_test_forecast() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- modify: `scripts/extract_anchors.py` :: `render` — forecast\n"
    )
    existing = {"tests/test_extract_anchors.py", "tests/test_select_changed_tests.py"}
    source = 'def render() -> str:\n    return ""\n'

    output = render(
        anchors,
        {"scripts/extract_anchors.py": source},
        test_impact=forecast_test_selection(anchors, existing),
    )

    assert "=== modify scripts/extract_anchors.py :: render" in output
    assert "--- planned test selection: selected" in output
    assert "tests/test_extract_anchors.py" in output


def test_a_create_path_participates_in_the_forecast_before_it_exists() -> None:
    anchors = parse_touches(
        "## Touches\n\n"
        "- create: `acquisition-controls/legacy-bundles.json` — C5 allowlist\n"
    )

    selection = forecast_test_selection(
        anchors,
        set(_ACQUISITION_CONTROL_COMPANIONS),
        test_sources=_ACQUISITION_CONTROL_TEST_SOURCES,
    )

    assert selection.kind == "selected"
    assert selection.files == _ACQUISITION_CONTROL_COMPANIONS


def test_issue_233s_manifest_forecasts_acquisition_control_companions() -> None:
    anchors = parse_touches(_ISSUE_233_TOUCHES)

    selection = forecast_test_selection(
        anchors,
        {
            *_ACQUISITION_CONTROL_COMPANIONS,
            "tests/test_strip.py",
        },
        test_sources={
            **_ACQUISITION_CONTROL_TEST_SOURCES,
            "tests/test_final_polish.py": (
                'from tests.final_polish_harness import helper\n'
                'text = (ROOT / "docs" / "strip-acquisition-contract.md").read_text()'
            ),
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert selection.kind == "selected"
    assert selection.files == _ACQUISITION_CONTROL_COMPANIONS


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


def test_a_markdown_section_ignores_heading_syntax_inside_fenced_code() -> None:
    document = """## Operator workflow

```bash
# 1. Score the attempt
npm run gate-control:score
```

Still part of the workflow.

## Later

Outside the workflow.
"""

    assert markdown_section_span(document, "Operator workflow") == Span(
        name="Operator workflow", start=1, end=9
    )


def test_text_after_a_fence_marker_does_not_close_the_fence() -> None:
    document = """## Outer

```text
```still code
# Still code too
```

After the fence.

## Later
"""

    assert markdown_section_span(document, "Outer") == Span(
        name="Outer", start=1, end=9
    )


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


def test_an_unanchored_directory_is_reported_for_manual_inspection() -> None:
    anchors = parse_touches(
        "## Touches\n\n- modify: `assets/dwarf/swing` — replace the bundle\n"
    )

    output = render(
        anchors,
        {},
        unavailable={"assets/dwarf/swing": "directory; inspect entries narrowly"},
    )

    assert "assets/dwarf/swing — directory; inspect entries narrowly" in output


def test_the_cli_reports_a_create_path_as_planned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = tmp_path / "issue.md"
    body.write_text(
        "## Touches\n\n- create: `tests/test_new_seam.py` — prove the seam\n",
        encoding="utf-8",
    )

    assert main(["--body-file", str(body)]) == 0

    captured = capsys.readouterr()
    assert "tests/test_new_seam.py — planned create; no source yet" in captured.out


def test_the_cli_rejects_an_unanchored_readable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = tmp_path / "issue.md"
    body.write_text(
        "## Touches\n\n"
        "- read: [authority] `docs/agents/issue-tracker.md` — tracker rules\n",
        encoding="utf-8",
    )

    assert main(["--body-file", str(body)]) == 0

    captured = capsys.readouterr()
    assert "text file has no anchor; repair the manifest" in captured.out
    assert "# Issue tracker: GitHub Issues" not in captured.out


def test_an_anchored_entry_does_not_let_a_duplicate_bypass_anchor_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = tmp_path / "issue.md"
    body.write_text(
        "## Touches\n\n"
        "- read: [authority] `docs/agents/issue-tracker.md` :: Conventions — rules\n"
        "- read: [authority] `docs/agents/issue-tracker.md` — all rules\n",
        encoding="utf-8",
    )

    assert main(["--body-file", str(body)]) == 0

    captured = capsys.readouterr()
    assert "## Conventions" in captured.out
    assert "text file has no anchor; repair the manifest" in captured.out
    assert "# Issue tracker: GitHub Issues" not in captured.out


def test_an_unanchored_entry_does_not_hide_a_later_valid_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = tmp_path / "issue.md"
    body.write_text(
        "## Touches\n\n"
        "- read: [authority] `docs/agents/issue-tracker.md` — all rules\n"
        "- read: [authority] `docs/agents/issue-tracker.md` :: Conventions — rules\n",
        encoding="utf-8",
    )

    assert main(["--body-file", str(body)]) == 0

    captured = capsys.readouterr()
    assert "text file has no anchor; repair the manifest" in captured.out
    assert "## Conventions" in captured.out
    assert "# Issue tracker: GitHub Issues" not in captured.out


@pytest.mark.parametrize("manifest_path", ["/etc/hosts", "../outside.md"])
def test_the_cli_rejects_paths_outside_the_repository(
    manifest_path: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = tmp_path / "issue.md"
    body.write_text(
        "## Touches\n\n"
        f"- read: [authority] `{manifest_path}` :: Hosts — outside\n",
        encoding="utf-8",
    )

    assert main(["--body-file", str(body)]) == 0

    captured = capsys.readouterr()
    assert "invalid manifest path; expected a repo-relative path" in captured.out
