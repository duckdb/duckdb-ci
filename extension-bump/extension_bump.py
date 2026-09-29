#!/usr/bin/env python3
"""Bump the extension checked out in the current directory to a DuckDB commit.

Run it from the extension's root, by hand, from duckdb-automations' driver, or in CI through the
extension-bump action; all three do the same thing. The caller decides the DuckDB commit and
which of duckdb's patches to apply; everything else is read from the checkout. Without
--make-pr it only commits locally.

    python3 ../extension_bump.py --duckdb <sha|tag> [--duckdb-version v2.0.0] [--patches a.patch,b.patch] [--make-pr]
"""
import argparse
import os
import re
import subprocess
import shutil
import sys
import tempfile

DUCKDB_URL = "https://github.com/duckdb/duckdb"
CI_TOOLS_URL = "https://github.com/duckdb/extension-ci-tools"
PIPELINE_PATH = ".github/workflows/MainDistributionPipeline.yml"
# Some extensions' workflows check duckdb out at the commit in this file instead of the submodule
DUCKDB_VERSION_PATH = ".github/duckdb-version"
EXTENSION_CONFIG_PATH = "extension_config.cmake"
# Marks this script's commits: any other commit on the bump branch is a human's, and is kept
TRAILER = "Bumped-By: duckdb-ci extension-bump"
# Comments are consumed whole, as they can contain parentheses and argument names
EXTENSION_LOAD_BLOCK = re.compile(r'^[ \t]*duckdb_extension_load\(\s*(?P<name>\w+)(?P<body>(?:#[^\n]*|[^)#])*)\)', re.M)
GIT_TAG_ARG = re.compile(r'^(?P<lead>[ \t]*GIT_TAG[ \t]+)(?P<value>\S+)', re.M)
GIT_URL_ARG = re.compile(r'^[ \t]*GIT_URL[ \t]+(?P<value>\S+)', re.M)
CMAKE_COMMENT = re.compile(r'#[^\n]*')
OWN_SOURCE_DIR = re.compile(r'\bSOURCE_DIR\s+\$\{CMAKE_CURRENT_LIST_DIR\}')
CI_TOOLS_USES = re.compile(r'duckdb/extension-ci-tools/\.github/workflows/[\w.-]+\.ya?ml@(?P<ref>[\w./-]+)')
DUCKDB_VERSION_INPUT = re.compile(r'^[ \t]*duckdb_version:', re.M)


class BumpError(Exception):
    pass


def run(*cmd, check=True, data=None):
    res = subprocess.run(cmd, input=data, capture_output=True)
    if check and res.returncode != 0:
        raise BumpError(f"{' '.join(cmd)} failed: {res.stderr.decode(errors='replace').strip()}")
    return res


def git(*args, check=True):
    return run("git", *args, check=check).stdout.decode(errors="replace").strip()


def gh_api(*args, data=None):
    return run("gh", "api", *args, data=data).stdout.decode(errors="replace").strip()


def summary(line):
    """A line in the GitHub Actions job summary, when running there."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(line + "\n")


class DuckDB:
    """The duckdb commit being moved to, fetched shallowly into a scratch repository: it doesn't
    depend on the submodule's state, and `git show` gives patch files' exact bytes."""

    def __init__(self, ref):
        self.dir = tempfile.mkdtemp(prefix="duckdb-")
        git("init", "-q", "--bare", self.dir)
        res = run("git", "-C", self.dir, "fetch", "-q", "--depth", "1", DUCKDB_URL, ref, check=False)
        if res.returncode != 0:
            raise BumpError(f"cannot fetch {ref!r} from duckdb/duckdb (use a full 40-character SHA or a tag name)")
        self.sha = git("-C", self.dir, "rev-parse", "FETCH_HEAD^{commit}")

    def read(self, path):
        res = run("git", "-C", self.dir, "show", f"{self.sha}:{path}", check=False)
        return res.stdout if res.returncode == 0 else None

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def extension_name(override):
    """The extension's own name: the duckdb_extension_load whose SOURCE_DIR is this repository.
    In-tree duckdb extensions (json, parquet, ...) have no SOURCE_DIR, and other repositories'
    extensions have a GIT_URL instead."""
    if override:
        return override
    if not os.path.exists(EXTENSION_CONFIG_PATH):
        raise BumpError(f"no {EXTENSION_CONFIG_PATH} here: run from the extension's root, or pass --name")
    with open(EXTENSION_CONFIG_PATH) as f:
        content = f.read()
    # A config can load its own extension in both branches of an if()
    own = sorted({b.group("name") for b in EXTENSION_LOAD_BLOCK.finditer(content)
                  if OWN_SOURCE_DIR.search(CMAKE_COMMENT.sub("", b.group("body")))})
    if len(own) != 1:
        raise BumpError(f"expected one duckdb_extension_load with SOURCE_DIR ${{CMAKE_CURRENT_LIST_DIR}} in "
                        f"{EXTENSION_CONFIG_PATH}, found {own or 'none'}; pass --name")
    return own[0]


def target_branch(override):
    branch = override or git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise BumpError("HEAD is detached: check out the target branch, or pass --branch")
    return branch


def remote_branch_sha(remote, branch):
    out = git("ls-remote", remote, f"refs/heads/{branch}")
    return out.split()[0] if out else ""


def ci_tools_ref():
    """The extension-ci-tools branch the pipeline names: main, or e.g. v1.5-variegata on a
    release branch. Set once when the branch is created, so the bump never edits a workflow."""
    if not os.path.exists(PIPELINE_PATH):
        return "main"
    with open(PIPELINE_PATH) as f:
        match = CI_TOOLS_USES.search(f.read())
    return match.group("ref") if match else "main"


def bump_submodule(path, sha):
    """Point a submodule's gitlink at sha without fetching it."""
    entry = git("ls-files", "-s", path)
    if not entry.startswith("160000") or entry.split()[1] == sha:
        return False
    git("update-index", "--cacheinfo", f"160000,{sha},{path}")
    return True


def bump_duckdb_version_file(sha):
    if not os.path.exists(DUCKDB_VERSION_PATH):
        return
    with open(DUCKDB_VERSION_PATH) as f:
        original = f.read()
    if original.strip() == sha:
        return
    # Keep the file's trailing newline, or lack of one, as it was
    with open(DUCKDB_VERSION_PATH, "w") as f:
        f.write(sha + original[len(original.rstrip()):])
    git("add", DUCKDB_VERSION_PATH)


def normalized_git_url(url):
    return url.rstrip("/").removesuffix(".git").lower()


def applies_patches(cmake_body):
    return bool(re.search(r'\bAPPLY_PATCHES\b', CMAKE_COMMENT.sub('', cmake_body)))


def duckdb_extension_pin(duckdb, name):
    """(git_url, git_tag, applies_patches) duckdb builds extension `name` with, or None."""
    data = duckdb.read(f".github/config/extensions/{name}.cmake")
    if data is None:
        return None
    content = data.decode(errors="replace")
    url, tag = GIT_URL_ARG.search(content), GIT_TAG_ARG.search(content)
    if not url or not tag:
        return None
    return url.group("value"), tag.group("value"), applies_patches(content)


def bump_extension_config_pins(duckdb):
    """Move the other duckdb extensions extension_config.cmake builds to duckdb's pins for them:
    after a bump, an older commit of e.g. httpfs can stop compiling against the new duckdb."""
    if not os.path.exists(EXTENSION_CONFIG_PATH):
        return
    with open(EXTENSION_CONFIG_PATH) as f:
        original = f.read()

    def bump_block(block):
        name, body = block.group("name"), block.group("body")
        url, tag = GIT_URL_ARG.search(body), GIT_TAG_ARG.search(body)
        if not url or not tag:
            return block.group(0)
        pin = duckdb_extension_pin(duckdb, name)
        if pin is None:
            return block.group(0)
        pin_url, pin_tag, pin_applies_patches = pin
        # A pin of some other repository, e.g. a fork, is deliberate and not ours to move
        if normalized_git_url(url.group("value")) != normalized_git_url(pin_url):
            return block.group(0)
        if pin_applies_patches and not applies_patches(body):
            print(f"::warning::duckdb applies patches to {name} at {pin_tag[:10]}, {EXTENSION_CONFIG_PATH} does not")
        if tag.group("value") == pin_tag:
            return block.group(0)
        new_body = body[:tag.start("value")] + pin_tag + body[tag.end("value"):]
        return block.group(0).replace(body, new_body, 1)

    content = EXTENSION_LOAD_BLOCK.sub(bump_block, original)
    if content != original:
        with open(EXTENSION_CONFIG_PATH, "w") as f:
            f.write(content)
        git("add", EXTENSION_CONFIG_PATH)


def commit(message):
    """Commit what's staged, marked as this script's. False if nothing is staged."""
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git("commit", "-q", "-m", message, "-m", TRAILER)
    return True


def apply_patches(duckdb, name, patches, branch, restore):
    """Apply patches on the commit duckdb pins for this extension (they're authored against it),
    then carry the result onto the branch tip. Returns the patches that changed something."""
    if not patches:
        return []
    pin = duckdb_extension_pin(duckdb, name)
    if pin is None:
        raise BumpError(f"duckdb {duckdb.sha[:10]} has no config with a GIT_TAG for {name}")
    pinned = pin[1]
    applied, patched = [], None
    patch_dir = tempfile.mkdtemp(prefix="duckdb-patches-")
    git("checkout", "-q", "--detach", pinned)
    try:
        for patch in patches:
            data = duckdb.read(f".github/patches/extensions/{name}/{patch}")
            if data is None:
                raise BumpError(f"duckdb {duckdb.sha[:10]} has no patch {patch} for {name}")
            # git apply rejects a patch whose final line has no newline as corrupt
            if not data.endswith(b"\n"):
                data += b"\n"
            with open(os.path.join(patch_dir, patch), "wb") as f:
                f.write(data)
            if run("git", "apply", "--index", f.name, check=False).returncode == 0:
                applied.append(patch)
                continue
            if run("git", "apply", "--check", "--reverse", f.name, check=False).returncode == 0:
                continue  # already in the extension at the pinned commit
            err = run("git", "apply", "--check", f.name, check=False).stderr.decode(errors="replace").strip()
            raise BumpError(f"patch {patch} does not apply to {name} at {pinned[:10]}: {err}")
        if commit(f"Apply patches from duckdb {duckdb.sha[:10]}"):
            patched = git("rev-parse", "HEAD")
    finally:
        # Back to exactly where the run started: the branch it was on, or the detached commit
        git("checkout", "-q", "--force", restore)
        shutil.rmtree(patch_dir, ignore_errors=True)
    if patched is None:
        return []
    if run("git", "cherry-pick", patched, check=False).returncode != 0:
        conflicted = git("diff", "--name-only", "--diff-filter=U")
        run("git", "cherry-pick", "--abort", check=False)
        if conflicted:
            raise BumpError(f"duckdb's patches for {name} conflict with {branch} in: {conflicted.replace(chr(10), ', ')}")
        return []  # empty on the tip: the branch already carries everything the patches do
    return applied


def carry_human_commits(bump_branch, branch):
    """Replay commits a human pushed to the bump branch onto the fresh bump.

    Returns (old_sha, conflict): old_sha is the remote bump branch's tip, or "" if it doesn't
    exist. A commit that has become empty (its fix is now upstream) is dropped."""
    old = remote_branch_sha("origin", bump_branch)
    if not old:
        return "", False
    git("fetch", "-q", "origin", f"refs/heads/{bump_branch}")
    base = git("merge-base", "FETCH_HEAD", f"origin/{branch}")
    for sha in git("rev-list", "--reverse", "--no-merges", f"{base}..FETCH_HEAD").split():
        if TRAILER in git("log", "-1", "--format=%B", sha):
            author, committer = git("log", "-1", "--format=%ae|%ce", sha).split("|")
            if author != committer:
                print(f"::warning::{sha[:10]} is a bump commit that {committer} changed; that change is dropped "
                      "by this bump -- push it again as a commit of its own")
            continue
        if run("git", "cherry-pick", sha, check=False).returncode == 0:
            continue
        if git("diff", "--name-only", "--diff-filter=U"):
            run("git", "cherry-pick", "--abort", check=False)
            return old, True
        run("git", "cherry-pick", "--skip", check=False)
    return old, False


def repo_slug():
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug
    match = re.search(r'github\.com[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?$', git("remote", "get-url", "origin"))
    if not match:
        raise BumpError("origin is not a GitHub repository")
    return match.group("slug")


def open_pr_number(slug, bump_branch, branch):
    owner = slug.split("/")[0]
    return gh_api(f"repos/{slug}/pulls?state=open&base={branch}&head={owner}:{bump_branch}",
                  "--jq", '.[0].number // ""')


def comment_once(slug, number, marker, text):
    bodies = gh_api(f"repos/{slug}/issues/{number}/comments", "--paginate", "--jq", ".[].body")
    if marker in bodies:
        return
    gh_api(f"repos/{slug}/issues/{number}/comments", "-f", f"body={marker}\n{text}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duckdb", required=True, help="DuckDB commit (full SHA) or tag to move to")
    parser.add_argument("--duckdb-version", default="", help="Label for commit and PR titles, e.g. v2.0.0 (default: the short SHA)")
    parser.add_argument("--patches", default="", help="Comma-separated duckdb patch file names to apply")
    parser.add_argument("--make-pr", action="store_true", help="Push duckdb-bump/<branch> and create or edit its PR")
    parser.add_argument("--name", default="", help="Extension name, when it can't be read from extension_config.cmake")
    parser.add_argument("--branch", default="", help="Target branch, when HEAD is detached")
    args = parser.parse_args()

    name = extension_name(args.name)
    branch = target_branch(args.branch)
    if git("status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"):
        raise BumpError("the checkout has uncommitted changes")
    start = git("rev-parse", "HEAD")
    restore = git("symbolic-ref", "-q", "--short", "HEAD", check=False) or start

    duckdb = DuckDB(args.duckdb)
    try:
        return bump(args, name, branch, start, restore, duckdb)
    finally:
        duckdb.cleanup()


def bump(args, name, branch, start, restore, duckdb):
    label = args.duckdb_version or duckdb.sha[:10]
    patches = [p for p in args.patches.split(",") if p]

    applied = apply_patches(duckdb, name, patches, branch, restore)
    ci_ref = ci_tools_ref()
    ci_sha = remote_branch_sha(CI_TOOLS_URL, ci_ref)
    bump_submodule("duckdb", duckdb.sha)
    if ci_sha:
        bump_submodule("extension-ci-tools", ci_sha)
    else:
        print(f"::warning::extension-ci-tools has no branch {ci_ref}; leaving its submodule as it is")
    bump_duckdb_version_file(duckdb.sha)
    bump_extension_config_pins(duckdb)
    commit(f"Bump duckdb to {label}")

    if os.path.exists(PIPELINE_PATH) and DUCKDB_VERSION_INPUT.search(open(PIPELINE_PATH).read()):
        print(f"::warning::{PIPELINE_PATH} still sets duckdb_version, so builds ignore the submodule "
              "(duckdblabs/duckdb-internal#10944)")

    if git("rev-parse", "HEAD") == start:
        print(f"{name}: already at duckdb {duckdb.sha[:10]}, nothing to do")
        summary(f"{name}: nothing to do")
        return 0
    if not args.make_pr:
        print(f"{name}: committed locally on {branch} (patches applied: {', '.join(applied) or 'none'})")
        return 0

    bump_branch = f"duckdb-bump/{branch}"
    slug = repo_slug()
    number = open_pr_number(slug, bump_branch, branch)
    if number:
        old, conflict = carry_human_commits(bump_branch, branch)
    else:
        # No open PR: whatever is left on the bump branch (e.g. after a squash-merge) is stale,
        # so the branch starts over from this bump
        old, conflict = remote_branch_sha("origin", bump_branch), False
    if conflict:
        message = (f"DuckDB `{duckdb.sha[:10]}` ({label}) is available, but the commits pushed to this "
                   f"branch by hand don't rebase onto it. Resolve them, or remove them, to pick it up.")
        if number:
            comment_once(slug, number, f"<!-- bump:{duckdb.sha} -->", message)
        print(f"::warning::{name}: {message}")
        summary(f"{name}: not updated, manual commits conflict with {duckdb.sha[:10]}")
        return 0

    if old:
        git("fetch", "-q", "origin", f"refs/heads/{bump_branch}")
    if old and number and git("rev-parse", "HEAD^{tree}") == git("rev-parse", f"{old}^{{tree}}"):
        # Same content as the open PR already has: a push would only re-run its CI
        print(f"{name}: https://github.com/{slug}/pull/{number} already has duckdb {duckdb.sha[:10]}")
        summary(f"{name}: up to date")
        return 0
    git("push", "-q", f"--force-with-lease=refs/heads/{bump_branch}:{old}", "origin", f"HEAD:refs/heads/{bump_branch}")
    title = f"[AUTOMATED_BUMP] Bump duckdb to {label}"
    body = (f"Bumps the duckdb submodule to `{duckdb.sha[:10]}` ({label}) and extension-ci-tools to "
            f"`{ci_ref}`.\n\nPatches applied from duckdb: {', '.join(applied) or 'none'}\n\n"
            "Opened by duckdb-ci's extension-bump. Commits pushed to this branch by hand are kept: "
            "each new bump rebases them.")
    if number:
        gh_api("-X", "PATCH", f"repos/{slug}/pulls/{number}", "-f", f"title={title}", "-f", f"body={body}")
        url = f"https://github.com/{slug}/pull/{number}"
    else:
        url = gh_api(f"repos/{slug}/pulls", "-f", f"title={title}", "-f", f"head={bump_branch}",
                     "-f", f"base={branch}", "-f", f"body={body}", "--jq", ".html_url")
    print(f"{name}: {url}")
    summary(f"{name}: {url}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BumpError as e:
        print(f"::error::{e}")
        summary(f"**failed:** {e}")
        sys.exit(1)
