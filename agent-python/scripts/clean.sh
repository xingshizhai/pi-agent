#!/usr/bin/env bash
# 清除 agent-python 下的临时文件与编译产物（不默认删除 .venv）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INCLUDE_VENV=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/clean.sh [options]

Options:
  --venv      同时删除 .venv 虚拟环境
  --dry-run   只打印将删除的内容，不实际删除
  -h, --help  显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv) INCLUDE_VENV=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

remove_path() {
  local target="$1"
  if [[ ! -e "$target" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would remove: $target"
  else
    rm -rf "$target"
    echo "removed: $target"
  fi
}

echo "Cleaning agent-python at: $ROOT"

# 顶层缓存与构建产物
for name in dist build .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage; do
  remove_path "$name"
done

# 临时目录（开发/调试残留）
for name in tmp tmp_wheel tmp_extract; do
  remove_path "$name"
done

# *.egg-info 目录
shopt -s nullglob
for path in *.egg-info src/*.egg-info; do
  remove_path "$path"
done
shopt -u nullglob

# __pycache__ 与字节码
if [[ "$DRY_RUN" -eq 1 ]]; then
  while IFS= read -r -d '' dir; do
    echo "would remove: $dir"
  done < <(find . -type d -name __pycache__ -not -path './.venv/*' -print0 2>/dev/null || true)
  while IFS= read -r -d '' file; do
    echo "would remove: $file"
  done < <(find . \( -name '*.pyc' -o -name '*.pyo' \) -not -path './.venv/*' -print0 2>/dev/null || true)
else
  find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
  find . \( -name '*.pyc' -o -name '*.pyo' \) -not -path './.venv/*' -delete 2>/dev/null || true
  echo "removed: __pycache__ / *.pyc / *.pyo (excluding .venv)"
fi

if [[ "$INCLUDE_VENV" -eq 1 ]]; then
  remove_path ".venv"
else
  echo "skipped: .venv (use --venv to remove)"
fi

echo "Done."
