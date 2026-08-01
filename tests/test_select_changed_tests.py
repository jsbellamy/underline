"""Unit tests for the changed-file -> test-file mapping (issue #193, C6).

The mapping is exercised as a pure function of a synthetic changed-file list
and a synthetic existing-test-file set — no git subprocess, no filesystem
scan. One test per `## Contract` C2 row, plus the C3 whole-suite fallback.
"""

from __future__ import annotations

from scripts.select_changed_tests import Selection, select_test_files

_ACQUISITION_CONTROL_COMPANIONS = (
    "tests/test_asset_acquire.py",
    "tests/test_final_polish.py",
    "tests/test_final_polish_cli.py",
)

_FINAL_POLISH_HARNESS_CONSUMERS = (
    "tests/test_final_polish.py",
    "tests/test_final_polish_cli.py",
)

_PR_240_CHANGED_PATHS = (
    "acquisition-controls/legacy-bundles.json",
    "docs/strip-acquisition-contract.md",
    "pipeline/final_polish.py",
    "pipeline/final_polish_cli.py",
    "tests/test_final_polish.py",
    "tests/test_final_polish_cli.py",
)


def test_no_changed_files_selects_nothing() -> None:
    result = select_test_files([], existing_tests=set())

    assert result == Selection(kind="nothing", reason=result.reason, files=())


def test_a_changed_test_file_selects_itself() -> None:
    result = select_test_files(
        ["tests/test_strip.py"],
        existing_tests={"tests/test_strip.py"},
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_strip.py",)


def test_a_changed_pipeline_module_selects_its_test_and_split_variants() -> None:
    result = select_test_files(
        ["pipeline/asset_pack.py"],
        existing_tests={
            "tests/test_asset_pack.py",
            "tests/test_asset_pack_cli.py",
            "tests/test_strip.py",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_asset_pack.py", "tests/test_asset_pack_cli.py")


def test_a_changed_prototype_module_selects_its_test_and_split_variants() -> None:
    result = select_test_files(
        ["prototype/strip-coherence/corpus.py"],
        existing_tests={"tests/test_corpus.py", "tests/test_derive_budgets.py"},
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_corpus.py",)


def test_a_changed_script_selects_its_test() -> None:
    result = select_test_files(
        ["scripts/select_changed_tests.py"],
        existing_tests={"tests/test_select_changed_tests.py", "tests/test_corpus.py"},
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_select_changed_tests.py",)


def _acquisition_control_test_sources() -> dict[str, str]:
    return {
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


def test_a_changed_support_module_selects_from_import_consumers() -> None:
    result = select_test_files(
        ["tests/final_polish_harness.py"],
        existing_tests={
            "tests/test_final_polish.py",
            "tests/test_final_polish_cli.py",
            "tests/test_strip.py",
        },
        test_sources={
            "tests/test_final_polish.py": "from tests.final_polish_harness import helper",
            "tests/test_final_polish_cli.py": "import tests.final_polish_harness",
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_final_polish.py", "tests/test_final_polish_cli.py")


def test_a_changed_nested_support_module_selects_its_importers() -> None:
    result = select_test_files(
        ["tests/support/polish_bundle.py"],
        existing_tests={"tests/test_polish_bundle.py", "tests/test_strip.py"},
        test_sources={
            "tests/support/polish_bundle.py": "BUNDLE = {}",
            "tests/test_polish_bundle.py": "from tests.support.polish_bundle import BUNDLE",
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_polish_bundle.py",)


def test_a_changed_support_package_init_selects_importers_of_submodules() -> None:
    result = select_test_files(
        ["tests/support/__init__.py"],
        existing_tests={
            "tests/test_polish_bundle.py",
            "tests/test_support_root.py",
            "tests/test_strip.py",
        },
        test_sources={
            "tests/support/__init__.py": "",
            "tests/support/polish_bundle.py": "BUNDLE = {}",
            "tests/test_polish_bundle.py": "from tests.support.polish_bundle import BUNDLE",
            "tests/test_support_root.py": "import tests.support",
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_polish_bundle.py", "tests/test_support_root.py")


def test_a_changed_acquisition_control_selects_direct_and_indirect_consumers() -> None:
    result = select_test_files(
        ["acquisition-controls/legacy-bundles.json"],
        existing_tests={
            "tests/test_asset_acquire.py",
            "tests/test_final_polish.py",
            "tests/test_final_polish_cli.py",
            "tests/test_strip.py",
        },
        test_sources=_acquisition_control_test_sources(),
    )

    assert result.kind == "selected"
    assert result.files == (
        "tests/test_asset_acquire.py",
        "tests/test_final_polish.py",
        "tests/test_final_polish_cli.py",
    )


def test_a_test_source_that_cannot_be_read_is_skipped_not_raised() -> None:
    """C4: missing test source is skipped when resolving support-module consumers."""
    result = select_test_files(
        ["tests/final_polish_harness.py"],
        existing_tests={
            "tests/test_final_polish.py",
            "tests/test_unreadable.py",
        },
        test_sources={
            "tests/test_final_polish.py": "from tests.final_polish_harness import helper",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_final_polish.py",)


def test_a_changed_conftest_selects_the_whole_suite() -> None:
    result = select_test_files(["tests/conftest.py"], existing_tests=set())

    assert result.kind == "whole_suite"


def test_a_changed_pytest_ini_selects_the_whole_suite() -> None:
    result = select_test_files(["pytest.ini"], existing_tests=set())

    assert result.kind == "whole_suite"


def test_a_changed_requirements_txt_selects_the_whole_suite() -> None:
    result = select_test_files(["requirements.txt"], existing_tests=set())

    assert result.kind == "whole_suite"


def test_a_changed_package_json_selects_the_whole_suite() -> None:
    result = select_test_files(["package.json"], existing_tests=set())

    assert result.kind == "whole_suite"


def test_a_changed_asset_file_selects_the_whole_suite() -> None:
    result = select_test_files(
        ["assets/dwarf/idle/strip.png"], existing_tests=set()
    )

    assert result.kind == "whole_suite"


def test_a_changed_gate_controls_file_selects_the_whole_suite() -> None:
    result = select_test_files(
        ["gate-controls/reviews/swing/packet.json"], existing_tests=set()
    )

    assert result.kind == "whole_suite"


def test_an_unmapped_path_falls_back_to_the_whole_suite() -> None:
    result = select_test_files([".github/workflows/ci.yml"], existing_tests=set())

    assert result.kind == "whole_suite"


def test_a_changed_doc_selects_only_the_tests_that_read_it() -> None:
    result = select_test_files(
        ["docs/strip-acquisition-contract.md"],
        existing_tests={"tests/test_final_polish.py", "tests/test_corpus.py"},
        test_sources={
            "tests/test_final_polish.py": (
                'text = (ROOT / "docs" / "strip-acquisition-contract.md").read_text()'
            ),
            "tests/test_corpus.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_final_polish.py",)


def test_a_changed_doc_no_test_reads_selects_nothing() -> None:
    result = select_test_files(
        ["docs/agents/code-style.md"],
        existing_tests={"tests/test_corpus.py"},
        test_sources={"tests/test_corpus.py": "from pipeline.strip import coherence_report"},
    )

    assert result.kind == "nothing"


def test_a_changed_doc_alongside_a_module_adds_to_the_selection() -> None:
    result = select_test_files(
        ["pipeline/strip.py", "docs/strip-acquisition-contract.md"],
        existing_tests={"tests/test_strip.py", "tests/test_final_polish.py"},
        test_sources={
            "tests/test_final_polish.py": '"docs" / "strip-acquisition-contract.md"',
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_final_polish.py", "tests/test_strip.py")


def test_a_mapping_with_no_existing_test_file_falls_back_to_the_whole_suite() -> None:
    result = select_test_files(
        ["pipeline/brand_new_module.py"],
        existing_tests={"tests/test_strip.py"},
    )

    assert result.kind == "whole_suite"


def test_any_whole_suite_trigger_wins_even_alongside_a_mapped_change() -> None:
    result = select_test_files(
        ["pipeline/strip.py", "requirements.txt"],
        existing_tests={"tests/test_strip.py"},
    )

    assert result.kind == "whole_suite"


def test_multiple_mapped_changes_selection_is_deduped_and_sorted() -> None:
    result = select_test_files(
        ["pipeline/strip.py", "tests/test_asset_pack.py"],
        existing_tests={
            "tests/test_strip.py",
            "tests/test_asset_pack.py",
        },
    )

    assert result.kind == "selected"
    assert result.files == ("tests/test_asset_pack.py", "tests/test_strip.py")


def test_a_changed_legacy_bundles_json_selects_acquisition_control_companions() -> None:
    result = select_test_files(
        ["acquisition-controls/legacy-bundles.json"],
        existing_tests=set(_ACQUISITION_CONTROL_COMPANIONS),
        test_sources=_acquisition_control_test_sources(),
    )

    assert result.kind == "selected"
    assert result.files == _ACQUISITION_CONTROL_COMPANIONS


def test_a_changed_attempts_jsonl_selects_acquisition_control_companions() -> None:
    result = select_test_files(
        ["acquisition-controls/attempts.jsonl"],
        existing_tests=set(_ACQUISITION_CONTROL_COMPANIONS),
        test_sources=_acquisition_control_test_sources(),
    )

    assert result.kind == "selected"
    assert result.files == _ACQUISITION_CONTROL_COMPANIONS


def test_a_changed_acquisition_control_markdown_selects_companions() -> None:
    result = select_test_files(
        ["acquisition-controls/readme.md"],
        existing_tests=set(_ACQUISITION_CONTROL_COMPANIONS),
        test_sources=_acquisition_control_test_sources(),
    )

    assert result.kind == "selected"
    assert result.files == _ACQUISITION_CONTROL_COMPANIONS


def test_acquisition_control_companions_dedupe_with_other_mapped_changes() -> None:
    result = select_test_files(
        ["acquisition-controls/legacy-bundles.json", "pipeline/strip.py"],
        existing_tests={
            *_ACQUISITION_CONTROL_COMPANIONS,
            "tests/test_strip.py",
        },
        test_sources={
            **_acquisition_control_test_sources(),
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == (
        "tests/test_asset_acquire.py",
        "tests/test_final_polish.py",
        "tests/test_final_polish_cli.py",
        "tests/test_strip.py",
    )


def test_a_changed_final_polish_harness_selects_its_consumers() -> None:
    result = select_test_files(
        ["tests/final_polish_harness.py"],
        existing_tests=set(_FINAL_POLISH_HARNESS_CONSUMERS),
        test_sources={
            "tests/test_final_polish.py": "from tests.final_polish_harness import helper",
            "tests/test_final_polish_cli.py": "import tests.final_polish_harness",
        },
    )

    assert result.kind == "selected"
    assert result.files == _FINAL_POLISH_HARNESS_CONSUMERS


def test_pr_240_changed_paths_select_companions_without_widening() -> None:
    result = select_test_files(
        list(_PR_240_CHANGED_PATHS),
        existing_tests={
            *_ACQUISITION_CONTROL_COMPANIONS,
            "tests/test_strip.py",
        },
        test_sources={
            **_acquisition_control_test_sources(),
            "tests/test_final_polish.py": (
                'from tests.final_polish_harness import helper\n'
                'text = (ROOT / "docs" / "strip-acquisition-contract.md").read_text()'
            ),
            "tests/test_strip.py": "from pipeline.strip import coherence_report",
        },
    )

    assert result.kind == "selected"
    assert result.files == _ACQUISITION_CONTROL_COMPANIONS
