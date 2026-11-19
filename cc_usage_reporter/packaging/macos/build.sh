#!/usr/bin/env bash
#
# 在 macOS 上打包。架构三选一：
#
#   bash packaging/macos/build.sh              # 本机架构
#   bash packaging/macos/build.sh arm64        # Apple Silicon
#   bash packaging/macos/build.sh x86_64       # Intel
#   bash packaging/macos/build.sh universal2   # 通用二进制（同时含 arm64 + x86_64）
#
# 也可以走环境变量（CI 里更方便）：
#   TARGET_ARCH=arm64 bash packaging/macos/build.sh
#
# 注意：PyInstaller 不能交叉编译。产物架构由「跑打包的那个 Python」决定：
#   * arm64 产物 -> 必须用 arm64 的 Python（Apple Silicon 原生，或
#     universal2 版 Python 在 arm64 上跑）
#   * x86_64 产物 -> 必须用 x86_64 的 Python（Intel 机器，或 arm64 机器上
#     Rosetta 里跑的 x86_64 Python）
#   * universal2 -> 必须用 python.org 的 universal2 版 Python（架构经
#     CC_USAGE_TARGET_ARCH 传给 .spec，最终落到 EXE(target_arch=...)）；
#     否则只能分别在两种机器上各打一份。
set -euo pipefail

TARGET="${1:-${TARGET_ARCH:-$(uname -m)}}"
case "$TARGET" in
  arm64|x86_64|universal2) ;;
  *)
    echo "不支持的架构: $TARGET （可选 arm64 / x86_64 / universal2）" >&2
    exit 2
    ;;
esac

cd "$(dirname "$0")/../.."

PY_PLATFORM="$(python3 -c 'import sysconfig; print(sysconfig.get_platform())')"
echo "==> 主机: $(uname -m)   Python 平台: $PY_PLATFORM   目标架构: $TARGET"

# 先确认这个 Python 能不能产出目标架构，避免打出一份架构不对的包还以为是好的
case "$PY_PLATFORM" in
  *universal2*)
    : # universal2 版 Python 三种目标都能打
    ;;
  *"-$TARGET")
    : # 架构一致
    ;;
  *)
    if [ "$TARGET" = "universal2" ]; then
      echo "错误：打 universal2 需要 universal2 版 Python。" >&2
    else
      echo "错误：当前 Python 是 $PY_PLATFORM，无法交叉编译出 $TARGET 的 Mach-O。" >&2
    fi
    echo "      二选一：在 $TARGET 机器上打包；或安装 python.org 的 universal2 版 Python 后重试。" >&2
    echo "      分别在两种机器上各打一份也是可以的（发布目录会带上架构名）。" >&2
    exit 3
    ;;
esac

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
python3 -m cc_usage_reporter deps-check || echo "tray optional deps check failed; continue if you only need CLI/daemon"

# 架构交给 .spec 里的 EXE(target_arch=...) 处理：PyInstaller 从 .spec 构建时
# 会忽略命令行的 --target-arch，只有 spec 里的参数才真正生效。
export CC_USAGE_TARGET_ARCH="$TARGET"

pyinstaller --clean --noconfirm cc-usage-reporter.spec
pyinstaller --clean --noconfirm cc-usage-reporter-gui.spec

# 打包后自检真实架构：lipo -archs 才是事实，别只看命令行参数
for bin in dist/cc-usage-reporter dist/cc-usage-reporter-gui; do
  if [ ! -f "$bin" ]; then
    echo "缺少产物: $bin" >&2
    exit 4
  fi
  arches="$(lipo -archs "$bin" 2>/dev/null || echo unknown)"
  echo "    $bin -> $arches"
  case " $arches " in
    *" $TARGET "*) ;;
    *universal2*) ;;
    *)
      if [ "$TARGET" != "universal2" ]; then
        echo "警告：$bin 的实际架构是「$arches」，与目标「$TARGET」不一致。" >&2
      fi
      ;;
  esac
done

rm -rf dist/macos-package
mkdir -p dist/macos-package
cp -R dist/cc-usage-reporter dist/cc-usage-reporter-gui dist/macos-package/ 2>/dev/null || true
tar -czf "dist/cc-usage-reporter-macos-${TARGET}.tar.gz" -C dist macos-package
echo "Build complete: dist/cc-usage-reporter-macos-${TARGET}.tar.gz"

# 发布目录名与 manifest 里都写上架构，避免 arm64 / x86_64 两份混淆
CC_USAGE_RELEASE_ARCH="$TARGET" python3 -m cc_usage_reporter release-pack