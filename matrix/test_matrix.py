from __future__ import annotations

import json
from pathlib import Path

import pytest

from matrix.matrix import (
    MatrixError,
    compute_matrices,
    detect_event_type_from_file,
    load_extensions_config,
    render_github_output,
    split_list,
)


ROOT = Path(__file__).resolve().parents[1]


def load_repo_config():
    return load_extensions_config(ROOT / "matrix" / "extensions.json")


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
    matrices = compute_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="pull_request",
        config_root=tmp_path,
    )

    assert archs(matrices["linux"]) == ["linux_amd64", "linux_amd64", "linux_amd64"]
    assert archs(matrices["windows"]) == ["windows_amd64", "windows_amd64"]
    assert [
        entry["artifact_prefix"] for entry in matrices["windows"]["include"]
    ] == ["main-extensions", "rust-based-extensions"]
    assert archs(matrices["wasm"]) == ["wasm_eh"]
    assert matrices["macos"]["include"] == []


def test_push_auto_keeps_full_non_opt_in_matrix(tmp_path):
    matrices = compute_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="push",
        config_root=tmp_path,
    )

    assert "linux_arm64" in archs(matrices["linux"])
    assert "osx_amd64" in archs(matrices["macos"])
    assert "windows_amd64_mingw" in archs(matrices["windows"])
    assert "wasm_threads" in archs(matrices["wasm"])
    assert "windows_arm64" not in archs(matrices["windows"])


def test_explicit_reduced_ci_modes(tmp_path):
    enabled = compute_matrices(load_repo_config(), reduced_ci_mode="enabled", event_type="push", config_root=tmp_path)
    disabled = compute_matrices(load_repo_config(), reduced_ci_mode="disabled", event_type="pull_request", config_root=tmp_path)

    assert "linux_arm64" not in archs(enabled["linux"])
    assert "linux_arm64" in archs(disabled["linux"])


def test_exclude_and_opt_in_filters(tmp_path):
    matrices = compute_matrices(
        load_repo_config(),
        exclude_archs="linux_amd64,wasm_eh",
        opt_in_archs="windows_arm64;linux_amd64_musl",
        reduced_ci_mode="disabled",
        config_root=tmp_path,
    )

    assert "linux_amd64" not in archs(matrices["linux"])
    assert "linux_amd64_musl" in archs(matrices["linux"])
    assert "windows_arm64" in archs(matrices["windows"])
    assert "wasm_eh" not in archs(matrices["wasm"])


def test_split_list_accepts_commas_semicolons_and_deduplicates():
    assert split_list(" linux_amd64,linux_arm64; linux_amd64;;") == ["linux_amd64", "linux_arm64"]


def test_runner_overrides_accept_strings_and_arrays(tmp_path):
    matrices = compute_matrices(
        load_repo_config(),
        runners=json.dumps(
            {
                "linux_x64": "namespace-profile-linux-x64",
                "linux_arm64": ["self-hosted", "linux", "arm64"],
            }
        ),
        opt_in_archs="linux_arm64_musl",
        reduced_ci_mode="disabled",
        config_root=tmp_path,
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
    matrices = compute_matrices(load_repo_config(), reduced_ci_mode="disabled", config_root=tmp_path)

    job = by_arch_and_group(matrices["macos"], "osx_arm64", "main-extensions")
    assert job["osx_build_arch"] == "arm64"
    assert "osx" not in matrices


def test_linux_container_fields_use_image_version_suffix_and_owner(tmp_path):
    matrices = compute_matrices(
        load_repo_config(),
        image_version="20260528-fbcf3036",
        image_suffix="_dev",
        repository_owner="duckdb",
        reduced_ci_mode="disabled",
        config_root=tmp_path,
    )

    main_job = by_arch_and_group(matrices["linux"], "linux_amd64", "main-extensions")
    rust_job = by_arch_and_group(matrices["linux"], "linux_arm64", "rust-based-extensions")
    assert main_job["container_name"] == "manylinux_2_28_amd64_main_dev"
    assert main_job["container"] == (
        "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main_dev:20260528-fbcf3036"
    )
    assert rust_job["container_name"] == "manylinux_2_28_aarch64_rust_dev"


def test_group_expansion_and_config_loading(tmp_path):
    config_dir = tmp_path / ".github" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "in_tree_extensions.cmake").write_text("set(IN_TREE 1)\n", encoding="utf-8")
    (config_dir / "out_of_tree_extensions.cmake").write_text("set(OUT_OF_TREE 1)\n", encoding="utf-8")
    (config_dir / "rust_based_extensions.cmake").write_text("set(RUST 1)\n", encoding="utf-8")
    (config_dir / "external_extensions.cmake").write_text("set(EXTERNAL 1)\n", encoding="utf-8")

    matrices = compute_matrices(load_repo_config(), reduced_ci_mode="disabled", config_root=tmp_path)

    main_job = by_arch_and_group(matrices["linux"], "linux_amd64", "main-extensions")
    rust_job = by_arch_and_group(matrices["linux"], "linux_amd64", "rust-based-extensions")
    external_job = by_arch_and_group(matrices["linux"], "linux_amd64", "external-extensions")
    assert main_job["extra_toolchains"] == "unixodbc;parser_tools"
    assert main_job["extension_config"] == "set(IN_TREE 1)\n\nset(OUT_OF_TREE 1)"
    assert rust_job["extension_config"] == "set(RUST 1)"
    assert external_job["extension_config"] == "set(EXTERNAL 1)"
    assert "linux_amd64_musl" not in [
        entry["duckdb_arch"]
        for entry in matrices["linux"]["include"]
        if entry["artifact_prefix"] == "rust-based-extensions"
    ]


def test_render_github_output_uses_exact_output_keys(tmp_path):
    matrices = compute_matrices(load_repo_config(), reduced_ci_mode="enabled", config_root=tmp_path)
    output = render_github_output(matrices)

    lines = output.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == ["linux", "macos", "windows", "wasm"]
    for line in lines:
        json.loads(line.split("=", 1)[1])


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


def test_invalid_reduced_ci_mode_errors(tmp_path):
    with pytest.raises(MatrixError):
        compute_matrices(load_repo_config(), reduced_ci_mode="sometimes", config_root=tmp_path)
