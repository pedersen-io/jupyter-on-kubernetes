#!/usr/bin/env bash
set -euo pipefail

TEMPLATE_PATH="/opt/jupyter-templates/MLB_Data_Starter.ipynb"
TARGET_NAME="MLB_Data_Starter.ipynb"

for target_dir in "$HOME/work" "$HOME/assignments"; do
  if [[ -d "$target_dir" ]] && [[ ! -f "$target_dir/$TARGET_NAME" ]]; then
    cp "$TEMPLATE_PATH" "$target_dir/$TARGET_NAME"
  fi
done
