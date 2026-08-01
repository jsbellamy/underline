"""Unit tests for the changed-file -> test-file mapping (issue #193, C6).

The mapping is exercised as a pure function of a synthetic changed-file list
and a synthetic existing-test-file set — no git subprocess, no filesystem
scan. One test per `## Contract` C2 row, plus the C3 whole-suite fallback.
"""

from __future__ import annotations

from scripts.select_changed_tests import Selection, select_test_files


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
