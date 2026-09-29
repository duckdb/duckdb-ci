# extension-bump

Bumps an extension to a DuckDB commit: moves the `duckdb` and `extension-ci-tools` submodules,
applies the duckdb patches it's given, and creates or updates one PR from `duckdb-bump/<branch>`.
Commits pushed to that branch by hand are rebased onto each new bump.

The same script runs three ways:

    # by hand, from the extension's root (commits only; add --make-pr to push and open the PR)
    python3 ../extension_bump.py --duckdb <sha|tag> [--patches a.patch,b.patch]

    # from duckdb-automations, for every extension
    python3 release/extensions/extension_util.py --current-base v1.5.5 --release-type major extension-bump

    # in CI, from the extension's .github/workflows/BumpDuckDB.yml
    - uses: duckdb/duckdb-ci/extension-bump@main
      with:
        duckdb: ${{ inputs.duckdb }}
        patches: ${{ inputs.patches }}
        token: ${{ secrets.DUCKDB_BUMP_TOKEN }}

The bump never edits a workflow file. Remove `duckdb_version` from `MainDistributionPipeline.yml`
(the build then uses the submodule), and name the extension-ci-tools branch there once when a
release branch is created.
