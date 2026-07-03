from __future__ import annotations

import json
from pathlib import Path

import pytest

from matrix.matrix import (
    MatrixError,
    compute_matrices,
    detect_event_type_from_file,
    load_extensions_config,
    parse_groups,
    render_github_output,
    render_readable_matrix_log,
    split_list,
)
from matrix.main import main as matrix_main


ROOT = Path(__file__).resolve().parents[1]

DUCKDB_CORE_GROUPS = """external:
  config: .github/config/external_extensions.cmake
  default_exclude_archs: wasm_mvp;wasm_eh;wasm_threads;windows_amd64_mingw;windows_amd64;linux_amd64_musl
  toolchain: main
main:
  config:
    - .github/config/in_tree_extensions.cmake
    - .github/config/out_of_tree_extensions.cmake
  toolchain: main
rust:
  config: .github/config/rust_based_extensions.cmake
  default_exclude_archs: wasm_mvp;wasm_eh;wasm_threads;windows_amd64_rtools;windows_amd64_mingw;linux_amd64_musl
  toolchain: rust
"""


def load_repo_config():
    return load_extensions_config(ROOT / "matrix" / "extensions.json")


def compute_core_matrices(*args, **kwargs):
    kwargs.setdefault("groups", DUCKDB_CORE_GROUPS)
    return compute_matrices(*args, **kwargs)


def archs(matrix):
    return [entry["duckdb_arch"] for entry in matrix["include"]]


def by_arch_and_group(matrix, duckdb_arch, artifact_prefix):
    for entry in matrix["include"]:
        if entry["duckdb_arch"] == duckdb_arch and entry["artifact_prefix"] == artifact_prefix:
            return entry
    raise AssertionError(f"missing {duckdb_arch} {artifact_prefix}")


def test_extensions_json_is_valid():
    config = load_repo_config()
    assert set(config) == {"linux", "osx", "windows", "wasm"}


def test_pull_request_auto_enables_reduced_ci(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="pull_request",
    )

    assert archs(matrices["linux"]) == ["linux_amd64", "linux_amd64", "linux_amd64"]
    assert archs(matrices["windows"]) == ["windows_amd64", "windows_amd64"]
    assert [
        entry["artifact_prefix"] for entry in matrices["windows"]["include"]
    ] == ["main-extensions", "rust-extensions"]
    assert archs(matrices["wasm"]) == ["wasm_eh"]
    assert matrices["macos"]["include"] == []


def test_push_auto_keeps_full_non_opt_in_matrix(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="push",
    )

    assert "linux_arm64" in archs(matrices["linux"])
    assert "osx_amd64" in archs(matrices["macos"])
    assert "windows_amd64_mingw" in archs(matrices["windows"])
    assert "wasm_threads" in archs(matrices["wasm"])
    assert "windows_arm64" not in archs(matrices["windows"])


def test_explicit_reduced_ci_modes(tmp_path):
    enabled = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled", event_type="push")
    disabled = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled", event_type="pull_request")

    assert "linux_arm64" not in archs(enabled["linux"])
    assert "linux_arm64" in archs(disabled["linux"])


def test_exclude_and_opt_in_filters(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        exclude_archs="linux_amd64,wasm_eh",
        opt_in_archs="windows_arm64;linux_amd64_musl",
        reduced_ci_mode="disabled",
    )

    assert "linux_amd64" not in archs(matrices["linux"])
    assert "linux_amd64_musl" in archs(matrices["linux"])
    assert "windows_arm64" in archs(matrices["windows"])
    assert "wasm_eh" not in archs(matrices["wasm"])


def test_split_list_accepts_commas_semicolons_and_deduplicates():
    assert split_list(" linux_amd64,linux_arm64; linux_amd64;;") == ["linux_amd64", "linux_arm64"]


def test_default_groups_parse_in_sorted_order():
    groups = parse_groups(DUCKDB_CORE_GROUPS)

    assert [group.key for group in groups] == ["external", "main", "rust"]
    assert [group.toolchain for group in groups] == ["main", "main", "rust"]
    assert groups[1].config_paths == (
        ".github/config/in_tree_extensions.cmake",
        ".github/config/out_of_tree_extensions.cmake",
    )


def test_group_yaml_parser_accepts_scalar_config_and_rejects_unknown_fields():
    groups = parse_groups(
        """custom:
  config: custom.cmake
  opt_in_archs: linux_amd64
  toolchain: main
"""
    )

    assert groups[0].key == "custom"
    assert groups[0].config_paths == ("custom.cmake",)
    assert groups[0].opt_in_archs == "linux_amd64"

    with pytest.raises(MatrixError):
        parse_groups(
            """custom:
  config: custom.cmake
  unknown: value
  toolchain: main
"""
        )


def test_runner_overrides_accept_strings_and_arrays(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        runners=json.dumps(
            {
                "linux_x64": "namespace-profile-linux-x64",
                "linux_arm64": ["self-hosted", "linux", "arm64"],
            }
        ),
        opt_in_archs="linux_arm64_musl",
        reduced_ci_mode="disabled",
    )

    assert by_arch_and_group(matrices["linux"], "linux_amd64", "main-extensions")["runner"] == [
        "namespace-profile-linux-x64"
    ]
    assert by_arch_and_group(matrices["linux"], "linux_arm64_musl", "main-extensions")["runner"] == [
        "self-hosted",
        "linux",
        "arm64",
    ]


def test_macos_output_key_maps_from_osx_config(tmp_path):
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled")

    job = by_arch_and_group(matrices["macos"], "osx_arm64", "main-extensions")
    assert job["osx_build_arch"] == "arm64"
    assert "osx" not in matrices


def test_linux_container_fields_use_fixed_image_owner_without_suffix(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        image_version="20260528-fbcf3036",
        reduced_ci_mode="disabled",
    )

    main_job = by_arch_and_group(matrices["linux"], "linux_amd64", "main-extensions")
    rust_job = by_arch_and_group(matrices["linux"], "linux_arm64", "rust-extensions")
    assert main_job["container_name"] == "manylinux_2_28_amd64_main"
    assert main_job["container"] == (
        "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main:20260528-fbcf3036"
    )
    assert rust_job["container_name"] == "manylinux_2_28_aarch64_rust"


def test_group_expansion_and_config_loading(tmp_path, monkeypatch):
    config_dir = tmp_path / ".github" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "in_tree_extensions.cmake").write_text("set(IN_TREE 1)\n", encoding="utf-8")
    (config_dir / "out_of_tree_extensions.cmake").write_text("set(OUT_OF_TREE 1)\n", encoding="utf-8")
    (config_dir / "rust_based_extensions.cmake").write_text("set(RUST 1)\n", encoding="utf-8")
    (config_dir / "external_extensions.cmake").write_text("set(EXTERNAL 1)\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled")

    main_job = by_arch_and_group(matrices["linux"], "linux_amd64", "main-extensions")
    rust_job = by_arch_and_group(matrices["linux"], "linux_amd64", "rust-extensions")
    external_job = by_arch_and_group(matrices["linux"], "linux_amd64", "external-extensions")
    assert "extra_toolchains" not in main_job
    assert main_job["extension_config"] == "set(IN_TREE 1)\n\nset(OUT_OF_TREE 1)"
    assert rust_job["extension_config"] == "set(RUST 1)"
    assert external_job["extension_config"] == "set(EXTERNAL 1)"
    assert "linux_amd64_musl" not in [
        entry["duckdb_arch"]
        for entry in matrices["linux"]["include"]
        if entry["artifact_prefix"] == "rust-extensions"
    ]


def test_render_github_output_uses_exact_output_keys(tmp_path):
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")
    output = render_github_output(matrices)

    lines = output.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == ["linux", "macos", "windows", "wasm"]
    for line in lines:
        payload = json.loads(line.split("=", 1)[1])
        assert json.dumps(payload, separators=(",", ":"), sort_keys=True) == line.split("=", 1)[1]


def test_render_readable_matrix_log_includes_tables_details_and_empty_platforms():
    matrices = {
        "linux": {
            "include": [
                {
                    "duckdb_arch": "linux_amd64",
                    "artifact_prefix": "main-extensions",
                    "runner": ["ubuntu-24.04"],
                    "vcpkg_target_triplet": "x64-linux-release",
                    "vcpkg_host_triplet": "x64-linux-release",
                    "container_name": "manylinux_2_28_amd64_main",
                    "container": "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main:20260528-fbcf3036",
                    "extension_config": "set(IN_TREE 1)\n\nset(OUT_OF_TREE 1)",
                    "exclude_archs": "wasm_mvp;wasm_eh",
                    "opt_in_archs": "",
                }
            ]
        },
        "macos": {
            "include": [
                {
                    "duckdb_arch": "osx_arm64",
                    "artifact_prefix": "main-extensions",
                    "runner": ["macos-15"],
                    "vcpkg_target_triplet": "arm64-osx-release",
                    "vcpkg_host_triplet": "arm64-osx-release",
                    "osx_build_arch": "arm64",
                    "extension_config": "",
                    "exclude_archs": "",
                    "opt_in_archs": "osx_arm64",
                }
            ]
        },
        "windows": {"include": []},
        "wasm": {"include": []},
    }

    output = render_readable_matrix_log(matrices)

    assert "linux (1 job)" in output
    assert "macos (1 job)" in output
    assert "windows (0 jobs)\n  No jobs" in output
    assert "wasm (0 jobs)\n  No jobs" in output
    assert "#  duckdb_arch" in output
    assert "linux_amd64" in output
    assert "main-extensions" in output
    assert "ubuntu-24.04" in output
    assert "x64-linux-release" in output
    assert "manylinux_2_28_amd64_main" in output
    assert "osx_build_arch" in output
    assert "  Job 1:" in output
    assert "    extension_config:" in output
    assert "      set(IN_TREE 1)" in output
    assert "      \n      set(OUT_OF_TREE 1)" in output
    assert "    exclude_archs: wasm_mvp;wasm_eh" in output
    assert "    opt_in_archs: <empty>" in output
    assert (
        "    container: ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main:20260528-fbcf3036"
        in output
    )


def test_main_writes_github_output_file_and_prints_readable_log(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    output_path = tmp_path / "github-output.txt"

    assert (
        matrix_main(
            [
                "--extensions",
                str(ROOT / "matrix" / "extensions.json"),
                "--reduced-ci-mode",
                "enabled",
                "--groups",
                DUCKDB_CORE_GROUPS,
                "--out",
                str(output_path),
            ]
        )
        == 0
    )

    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")
    assert output_path.read_text(encoding="utf-8") == render_github_output(matrices)
    stdout = capsys.readouterr().out
    assert "linux (" in stdout
    assert "Details" in stdout
    assert not stdout.startswith("linux={")


def test_main_writes_github_output_env_and_prints_readable_log(tmp_path, capsys, monkeypatch):
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert (
        matrix_main(
            [
                "--extensions",
                str(ROOT / "matrix" / "extensions.json"),
                "--reduced-ci-mode",
                "enabled",
                "--groups",
                DUCKDB_CORE_GROUPS,
            ]
        )
        == 0
    )

    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")
    assert output_path.read_text(encoding="utf-8") == render_github_output(matrices)
    stdout = capsys.readouterr().out
    assert "linux (" in stdout
    assert "Details" in stdout
    assert not stdout.startswith("linux={")


def test_main_without_output_destination_preserves_github_output_stdout(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert (
        matrix_main(
            [
                "--extensions",
                str(ROOT / "matrix" / "extensions.json"),
                "--reduced-ci-mode",
                "enabled",
                "--groups",
                DUCKDB_CORE_GROUPS,
            ]
        )
        == 0
    )

    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")
    assert capsys.readouterr().out == render_github_output(matrices)


def test_detect_event_type_from_file(tmp_path):
    pull_request = tmp_path / "pull_request.json"
    push = tmp_path / "push.json"
    unknown = tmp_path / "unknown.json"
    pull_request.write_text('{"pull_request":{}}', encoding="utf-8")
    push.write_text('{"ref":"refs/heads/main"}', encoding="utf-8")
    unknown.write_text('{"workflow":"dispatch"}', encoding="utf-8")

    assert detect_event_type_from_file(pull_request) == "pull_request"
    assert detect_event_type_from_file(push) == "push"
    assert detect_event_type_from_file(unknown) == "unknown"
