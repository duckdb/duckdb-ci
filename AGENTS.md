# GitHub
- Use gh CLI to access github.

## workflow or action changes
- Run `actionlint` directly to test workflow/action changes.

# Docker images

## Packages are tracked in `docker/*_packages.txt` files
- `docker/*_packages.txt` files are used when building docker images.
- Verify that `docker/packages.py` can query a tool version when adding a new
  explicit version check for a package.
