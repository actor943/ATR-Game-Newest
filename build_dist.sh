#!/bin/zsh
# -*- coding: utf-8 -*-
#
# ATR Game 分发构建脚本
# =====================
#
# 用法：
#   ./build_dist.sh apk      # 打 Android 安装包（输出 dist/ATR Game-release.apk）
#   ./build_dist.sh aab      # 打 Google Play 用的 aab
#   ./build_dist.sh app      # 打 macOS 应用（输出 dist/ATR Game.app）
#   ./build_dist.sh ipa      # 打 iOS 安装包（需要 Apple 开发者账号签名）
#   ./build_dist.sh all      # apk + app + ipa 全打
#
# 首次构建会自动下载并安装所需工具链（放在用户目录，不污染项目）：
#   Flutter   → ~/flutter/<版本>          （约 1 GB）
#   JDK 17    → ~/java/17.0.13+11         （仅 Android 需要）
#   AndroidSDK→ ~/Android/sdk             （仅 Android 需要）
# macOS 的 .app 与 iOS 的 .ipa 还需要完整 Xcode（App Store 安装，约 10 GB）。
#
# 国内网络如果下载 Flutter 很慢，可先手动装好再跑本脚本：
#   mkdir -p ~/flutter/3.41.7
#   curl -o /tmp/flutter.zip \
#     "https://storage.flutter-io.cn/flutter_infra_release/releases/stable/macos/flutter_macos_arm64_3.41.7-stable.zip"
#   unzip -q /tmp/flutter.zip -d /tmp/flutter_dl && mv /tmp/flutter_dl/flutter/* ~/flutter/3.41.7/
#
set -euo pipefail

cd "$(dirname "$0")"

PY="./venv/bin/python"
[ -x "$PY" ] || { echo "找不到 $PY，请确认在项目根目录运行（venv 需要用 pyproject.toml 装一次）"; exit 1; }

# flet 的命令行入口（venv 里的 flet 脚本 shebang 可能失效，直接用模块调）
flet() { "$PY" -c "import sys; sys.argv[0]='flet'; from flet.cli import main; main()" "$@"; }

target="${1:-all}"

echo "==> 目标：$target   应用：ATR Game 0.4.8"
echo "==> 输出目录：$(pwd)/dist"

case "$target" in
  apk|aab|app|ipa)
    flet build "$target" --yes
    ;;
  all)
    flet build apk --yes
    flet build app --yes
    flet build ipa --yes
    ;;
  *)
    echo "未知目标：$target（可选 apk / aab / app / ipa / all）"
    exit 1
    ;;
esac

echo
echo "完成，产物在 dist/："
ls -lh dist 2>/dev/null || true
