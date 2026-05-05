#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
	echo "Usage: $0 <alpine|manylinux> <packages_file>" >&2
	exit 1
fi

distro="$1"
packages_file="$2"

case "$distro" in
alpine | manylinux) ;;
*)
	echo "Unsupported distro: $distro" >&2
	exit 1
	;;
esac

awk -v distro="$distro" '
  /^[[:space:]]*($|#)/ { next }
  {
    if (distro == "alpine") {
      if ($0 ~ /#[[:space:]]*manylinux[[:space:]]*$/) next
      sub(/[[:space:]]*#[[:space:]]*alpine[[:space:]]*$/, "")
      print
      next
    }
    if ($0 ~ /#[[:space:]]*alpine[[:space:]]*$/) next
    sub(/[[:space:]]*#[[:space:]]*manylinux[[:space:]]*$/, "")
    print
  }
' "$packages_file" | tr '\n' ' '
