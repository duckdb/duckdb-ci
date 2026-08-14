from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from matrix.matrix import (
    BuildJob,
    Matrices,
    MatrixError,
    TestJob as MatrixTestJob,
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


def load_repo_config() -> dict[str, Any]:
    return load_extensions_config(ROOT / "matrix" / "extensions.json")


def compute_core_matrices(*args: Any, **kwargs: Any) -> Matrices:
    kwargs.setdefault("groups", DUCKDB_CORE_GROUPS)
    return compute_matrices(*args, **kwargs)


def test_extensions_json_is_valid():
    config = load_repo_config()
    assert set(config) == {"linux", "osx", "windows", "wasm"}


def test_matrix_get_requires_exactly_one_match():
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")

    with pytest.raises(MatrixError) as ambiguous:
        matrices.build.linux.get(arch="linux_amd64")
    assert str(ambiguous.value) == (
        "expected exactly one matrix job matching arch='linux_amd64'; found 3"
    )

    with pytest.raises(MatrixError) as missing:
        matrices.build.linux.get(arch="linux_amd64", prefix="missing-extensions")
    assert str(missing.value) == (
        "expected exactly one matrix job matching arch='linux_amd64', "
        "prefix='missing-extensions'; found 0"
    )


def test_pull_request_auto_enables_reduced_ci(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="pull_request",
    )

    assert matrices.build.linux.archs == [
        "linux_amd64",
        "linux_amd64",
        "linux_amd64",
    ]
    assert matrices.test.linux.archs == ["linux_amd64"]
    assert matrices.build.windows.archs == ["windows_amd64", "windows_amd64"]
    assert matrices.test.windows.archs == ["windows_amd64"]
    assert [job.prefix for job in matrices.build.windows.includes] == [
        "main-extensions",
        "rust-extensions",
    ]
    assert matrices.build.wasm.archs == ["wasm_eh"]
    assert matrices.test.wasm.archs == ["wasm_eh"]
    assert matrices.build.macos.includes == []
    assert matrices.test.macos.includes == []


def test_push_auto_keeps_full_non_opt_in_matrix(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        reduced_ci_mode="auto",
        event_type="push",
    )

    assert "linux_arm64" in matrices.build.linux.archs
    assert "osx_amd64" in matrices.build.macos.archs
    assert "windows_amd64_mingw" in matrices.build.windows.archs
    assert "wasm_threads" in matrices.build.wasm.archs
    assert "windows_arm64" not in matrices.build.windows.archs


def test_explicit_reduced_ci_modes(tmp_path):
    enabled = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled", event_type="push")
    disabled = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled", event_type="pull_request")

    assert "linux_arm64" not in enabled.build.linux.archs
    assert "linux_arm64" in disabled.build.linux.archs


def test_exclude_and_opt_in_filters(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        exclude_archs="linux_amd64,wasm_eh",
        opt_in_archs="windows_arm64;linux_amd64_musl",
        reduced_ci_mode="disabled",
    )

    assert "linux_amd64" not in matrices.build.linux.archs
    assert "linux_amd64_musl" in matrices.build.linux.archs
    assert "windows_arm64" in matrices.build.windows.archs
    assert "wasm_eh" not in matrices.build.wasm.archs


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


def test_group_yaml_parser_accepts_scalar_config_and_rejects_invalid_fields():
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

    with pytest.raises(MatrixError, match="unsupported toolchain"):
        parse_groups(
            """custom:
  config: custom.cmake
  toolchain: unsupported
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

    assert matrices.build.linux.get(
        arch="linux_amd64", prefix="main-extensions"
    ).runner == [
        "namespace-profile-linux-x64"
    ]
    assert matrices.build.linux.get(
        arch="linux_arm64_musl", prefix="main-extensions"
    ).runner == [
        "self-hosted",
        "linux",
        "arm64",
    ]


def test_macos_output_key_maps_from_osx_config(tmp_path):
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled")

    job = matrices.build.macos.get(arch="osx_arm64", prefix="main-extensions")
    assert job.osx_build_arch == "arm64"
    test = matrices.test.macos.get(arch="osx_arm64")
    assert test.osx_build_arch == "arm64"


def test_linux_container_fields_use_fixed_image_owner_without_suffix(tmp_path):
    matrices = compute_core_matrices(
        load_repo_config(),
        image_version="20260528-fbcf3036",
        opt_in_archs="linux_arm64_musl",
        reduced_ci_mode="disabled",
    )

    main_job = matrices.build.linux.get(arch="linux_amd64", prefix="main-extensions")
    rust_job = matrices.build.linux.get(arch="linux_arm64", prefix="rust-extensions")
    assert main_job.container_name == "manylinux_2_28_amd64_main"
    assert main_job.container == (
        "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main:20260528-fbcf3036"
    )
    assert rust_job.container_name == "manylinux_2_28_aarch64_rust"
    linux_test = matrices.test.linux.get(arch="linux_arm64")
    assert linux_test.container_name == "manylinux_2_28_aarch64_test"
    assert linux_test.container == (
        "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_aarch64_test:20260528-fbcf3036"
    )
    alpine_test = matrices.test.linux.get(arch="linux_arm64_musl")
    assert alpine_test.container_name == "alpine_3_22_aarch64_test"
    assert alpine_test.container == (
        "ghcr.io/duckdb/duckdb-ci/alpine_3_22_aarch64_test:20260528-fbcf3036"
    )


def test_cuda_builds_select_cuda_test_container_and_aggregate_toolchains():
    matrices = compute_matrices(
        load_repo_config(),
        groups="""cuda:
  config: .github/config/cuda_extensions.cmake
  default_exclude_archs: linux_amd64_musl;linux_arm64_musl;osx_amd64;osx_arm64;windows_amd64;windows_arm64;windows_amd64_mingw;wasm_mvp;wasm_eh;wasm_threads
  toolchain: cuda
main:
  config: .github/config/in_tree_extensions.cmake
  toolchain: main
""",
        image_version="20260528-fbcf3036",
        reduced_ci_mode="disabled",
    )

    cuda_build = matrices.build.linux.get(
        arch="linux_amd64", prefix="cuda-extensions"
    )
    assert cuda_build.container_name == "manylinux_2_28_amd64_cuda"
    linux_test = matrices.test.linux.get(arch="linux_amd64")
    assert linux_test.toolchains == ("cuda", "main")
    assert linux_test.container_name == "manylinux_2_28_amd64_cuda"
    assert linux_test.container == (
        "ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_cuda:20260528-fbcf3036"
    )


def test_cuda_toolchain_rejects_unsupported_architectures():
    with pytest.raises(
        MatrixError,
        match="cuda toolchain does not support architecture 'osx_amd64'",
    ):
        compute_matrices(
            load_repo_config(),
            groups="""cuda:
  config: .github/config/cuda_extensions.cmake
  toolchain: cuda
""",
            reduced_ci_mode="disabled",
        )


def test_group_expansion_exposes_toolchain_and_config_paths():
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="disabled")

    main_job = matrices.build.linux.get(arch="linux_amd64", prefix="main-extensions")
    rust_job = matrices.build.linux.get(arch="linux_amd64", prefix="rust-extensions")
    external_job = matrices.build.linux.get(
        arch="linux_amd64", prefix="external-extensions"
    )
    assert "extra_toolchains" not in main_job.to_dict()
    assert main_job.to_dict()["artifact_prefix"] == "main-extensions"
    assert "prefix" not in main_job.to_dict()
    assert main_job.toolchain == "main"
    assert main_job.extension_config_paths == (
        ".github/config/in_tree_extensions.cmake",
        ".github/config/out_of_tree_extensions.cmake",
    )
    assert rust_job.toolchain == "rust"
    assert rust_job.extension_config_paths == (
        ".github/config/rust_based_extensions.cmake",
    )
    assert external_job.toolchain == "main"
    assert external_job.extension_config_paths == (
        ".github/config/external_extensions.cmake",
    )
    assert "linux_amd64_musl" not in [
        job.duckdb_arch
        for job in matrices.build.linux.includes
        if job.prefix == "rust-extensions"
    ]


def test_artifact_names_match_one_deduplicated_test_row_per_arch():
    matrices = compute_core_matrices(
        load_repo_config(),
        reduced_ci_mode="disabled",
    )

    build_jobs = [
        job
        for job in matrices.build.linux.includes
        if job.duckdb_arch == "linux_arm64"
    ]
    assert [job.artifact_name for job in build_jobs] == [
        "external-extensions-linux_arm64",
        "main-extensions-linux_arm64",
        "rust-extensions-linux_arm64",
    ]
    test_jobs = [
        job
        for job in matrices.test.linux.includes
        if job.duckdb_arch == "linux_arm64"
    ]
    assert test_jobs == [
        MatrixTestJob(
            artifact_pattern="*-extensions-linux_arm64",
            container_name="manylinux_2_28_aarch64_test",
            duckdb_arch="linux_arm64",
            runner=["ubuntu-24.04-arm"],
            toolchains=("main", "rust"),
            vcpkg_host_triplet="arm64-linux-release",
            vcpkg_target_triplet="arm64-linux-release",
        )
    ]


def test_arch_without_build_groups_has_no_test_row():
    matrices = compute_matrices(
        load_repo_config(),
        groups="""only:
  config: missing.cmake
  default_exclude_archs: linux_amd64;linux_arm64;linux_amd64_musl;linux_arm64_musl
  toolchain: main
""",
        reduced_ci_mode="disabled",
    )

    assert matrices.build.linux.includes == []
    assert matrices.test.linux.includes == []


def test_render_github_output_uses_exact_output_keys(tmp_path):
    matrices = compute_core_matrices(load_repo_config(), reduced_ci_mode="enabled")
    output = render_github_output(matrices)

    lines = output.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == [
        "build_linux",
        "test_linux",
        "build_macos",
        "test_macos",
        "build_windows",
        "test_windows",
        "build_wasm",
        "test_wasm",
    ]
    for line in lines:
        payload = json.loads(line.split("=", 1)[1])
        assert json.dumps(payload, separators=(",", ":"), sort_keys=True) == line.split("=", 1)[1]


def test_render_readable_matrix_log_includes_tables_details_and_empty_platforms():
    matrices = Matrices()
    matrices.build.linux.includes.append(
        BuildJob(
            duckdb_arch="linux_amd64",
            prefix="main-extensions",
            artifact_name="main-extensions-linux_amd64",
            runner=["ubuntu-24.04"],
            vcpkg_target_triplet="x64-linux-release",
            vcpkg_host_triplet="x64-linux-release",
            container_name="manylinux_2_28_amd64_main",
            container="ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_main:20260528-fbcf3036",
            toolchain="main",
            extension_config_paths=(
                ".github/config/in_tree_extensions.cmake",
                ".github/config/out_of_tree_extensions.cmake",
            ),
            exclude_archs="wasm_mvp;wasm_eh",
            opt_in_archs="",
        )
    )
    matrices.test.linux.includes.append(
        MatrixTestJob(
            duckdb_arch="linux_amd64",
            artifact_pattern="*-extensions-linux_amd64",
            runner=["ubuntu-24.04"],
            container_name="manylinux_2_28_amd64_test",
            container="ghcr.io/duckdb/duckdb-ci/manylinux_2_28_amd64_test:20260528-fbcf3036",
            toolchains=("main",),
            vcpkg_target_triplet="x64-linux-release",
            vcpkg_host_triplet="x64-linux-release",
        )
    )
    matrices.build.macos.includes.append(
        BuildJob(
            duckdb_arch="osx_arm64",
            prefix="main-extensions",
            artifact_name="main-extensions-osx_arm64",
            runner=["macos-15"],
            vcpkg_target_triplet="arm64-osx-release",
            vcpkg_host_triplet="arm64-osx-release",
            osx_build_arch="arm64",
            toolchain="main",
            extension_config_paths=(".github/config/in_tree_extensions.cmake",),
            exclude_archs="",
            opt_in_archs="osx_arm64",
        )
    )
    matrices.test.macos.includes.append(
        MatrixTestJob(
            duckdb_arch="osx_arm64",
            artifact_pattern="*-extensions-osx_arm64",
            runner=["macos-15"],
            osx_build_arch="arm64",
            toolchains=("main",),
            vcpkg_target_triplet="arm64-osx-release",
            vcpkg_host_triplet="arm64-osx-release",
        )
    )

    output = render_readable_matrix_log(matrices)

    assert "build_linux (1 job)" in output
    assert "test_linux (1 job)" in output
    assert "build_macos (1 job)" in output
    assert "test_macos (1 job)" in output
    assert "build_windows (0 jobs)\n  No jobs" in output
    assert "test_windows (0 jobs)\n  No jobs" in output
    assert "build_wasm (0 jobs)\n  No jobs" in output
    assert "test_wasm (0 jobs)\n  No jobs" in output
    assert "#  duckdb_arch" in output
    assert "linux_amd64" in output
    assert "main-extensions" in output
    assert "main-extensions-linux_amd64" in output
    assert "*-extensions-linux_amd64" in output
    assert "ubuntu-24.04" in output
    assert "x64-linux-release" in output
    assert "manylinux_2_28_amd64_main" in output
    assert "osx_build_arch" in output
    assert "  Job 1:" in output
    assert "    extension_config_paths: .github/config/in_tree_extensions.cmake,.github/config/out_of_tree_extensions.cmake" in output
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
    assert not stdout.startswith("build_linux={")


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
    assert not stdout.startswith("build_linux={")


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
