#!/bin/sh
# 本机没有 gcc/cc 且无 sudo：用 zig 充当 C 编译器与链接器（pip install --user cargo-zigbuild ziglang）
exec "$HOME/.local/bin/cargo-zigbuild" zig cc -- -target x86_64-linux-gnu.2.35 "$@"
