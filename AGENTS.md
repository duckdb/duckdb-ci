# GitHub
- Use gh CLI to access github.

## workflow or action changes
- Run `actionlint` directly to test workflow/action changes.

# Docker images

## Install packages for different distributions

- Add suffix `# manylinux` or `# alpine` to use a specific package names per
  linux distribution. Without the suffix, the package name is used for both
  distributions.

## Packages are tracked in `docker/*_packages.txt` files
- `docker/*_packages.txt` files are used when building docker images.
- Verify that `docker/packages.py` can query a version when adding a new
  explicit version check for a package.
- Never add version checks in the docker files. Only perform version checks in packages.py.
