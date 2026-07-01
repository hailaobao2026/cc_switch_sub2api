from __future__ import annotations

import hashlib
import json
import platform
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__


RELEASE_LAYOUT_MD = r'''# Release Layout

- `bin/`：规范化命名后的可执行文件副本（如存在）
- `dist/`：原始打包产物
- `config/`：示例配置文件
- `scripts/`：安装/打包/辅助脚本
- `services/`：三端服务模板
- `docs/`：项目文档与安装说明
- `metadata/`：manifest / requirements / pyproject / 校验信息

推荐交付流程：

1. 编辑 `config/config.sidecar.example.json` 为实际配置
2. 优先分发 `bin/` 中的规范化可执行文件
3. 按系统执行对应安装脚本
4. 如需对外发布，可分发压缩包与 `SHA256SUMS.txt`
'''

INSTALL_WINDOWS_MD = r'''# Install on Windows

## 推荐顺序

1. 编辑 `config\config.sidecar.example.json`
2. 使用 `bin\cc-usage-reporter-gui.exe` 进行桌面配置
3. 如需后台服务，执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install_winsw.ps1 -ConfigPath "$env:USERPROFILE\.config\cc-switch\usage_reporter.json"
```

## 可执行文件

- `bin\cc-usage-reporter.exe`：CLI / daemon
- `bin\cc-usage-reporter-gui.exe`：GUI
'''

INSTALL_LINUX_MD = r'''# Install on Linux

## 推荐顺序

1. 编辑 `config/config.sidecar.example.json`
2. 运行 GUI 或 daemon：

```bash
./bin/cc-usage-reporter-gui
# 或
./bin/cc-usage-reporter daemon --config ~/.config/cc-switch/usage_reporter.json
```

3. 如需 systemd 用户服务：

```bash
bash ./scripts/linux/install_systemd_user.sh ~/.config/cc-switch/usage_reporter.json
```
'''

INSTALL_MACOS_MD = r'''# Install on macOS

## 推荐顺序

1. 编辑 `config/config.sidecar.example.json`
2. 运行 GUI 或 daemon：

```bash
./bin/cc-usage-reporter-gui
# 或
./bin/cc-usage-reporter daemon --config "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
```

3. 如需 launchd：

```bash
bash ./scripts/macos/install_launchd.sh "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
```
'''

POSIX_INSTALL_SH = r'''#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Release dir: $BASE_DIR"
echo "Read docs in $BASE_DIR/docs/INSTALL_LINUX.md or INSTALL_MACOS.md"
echo "Main binaries: $BASE_DIR/bin/"
'''

LINUX_INSTALL_SH = r'''#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$BASE_DIR/scripts/linux/install_systemd_user.sh"
bash "$BASE_DIR/scripts/linux/install_systemd_user.sh" "$HOME/.config/cc-switch/usage_reporter.json"
'''

MACOS_INSTALL_SH = r'''#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$BASE_DIR/scripts/macos/install_launchd.sh"
bash "$BASE_DIR/scripts/macos/install_launchd.sh" "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
'''

WINDOWS_INSTALL_PS1 = r'''$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Release dir: $BaseDir"
Write-Host "Read docs\INSTALL_WINDOWS.md"
Write-Host "Main binaries are in bin\"
Write-Host "To install WinSW service:"
Write-Host "powershell -ExecutionPolicy Bypass -File $BaseDir\scripts\windows\install_winsw.ps1 -ConfigPath \"$env:USERPROFILE\.config\cc-switch\usage_reporter.json\""
'''


def _copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _normalized_bin_name(name: str) -> str:
    lower = name.lower()
    if "gui" in lower:
        return "cc-usage-reporter-gui.exe" if lower.endswith('.exe') else "cc-usage-reporter-gui"
    return "cc-usage-reporter.exe" if lower.endswith('.exe') else "cc-usage-reporter"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _pack_release(outdir: Path) -> list[Path]:
    artifacts: list[Path] = []
    parent = outdir.parent
    base = outdir.name

    zip_path = parent / f"{base}.zip"
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in outdir.rglob('*'):
            zf.write(path, path.relative_to(parent))
    artifacts.append(zip_path)

    tgz_path = parent / f"{base}.tar.gz"
    with tarfile.open(tgz_path, 'w:gz') as tf:
        tf.add(outdir, arcname=outdir.name)
    artifacts.append(tgz_path)

    return artifacts


def _write_checksums(outdir: Path, artifacts: list[Path]) -> Path:
    lines = []
    for artifact in artifacts:
        lines.append(f"{_sha256_file(artifact)}  {artifact.name}")
    checksum_path = outdir / 'metadata' / 'SHA256SUMS.txt'
    _write_text(checksum_path, "\n".join(lines) + "\n")
    return checksum_path


def generate_release_dir(*, root: str | None = None, platform_name: str | None = None, pack: bool = False) -> Path:
    repo = Path(root).resolve() if root else Path(__file__).resolve().parent.parent
    plat = (platform_name or platform.system()).lower()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    version = __version__
    outdir = repo / "release" / f"cc-usage-reporter-v{version}-{plat}-{stamp}"

    docs_dir = outdir / "docs"
    config_dir = outdir / "config"
    scripts_dir = outdir / "scripts"
    services_dir = outdir / "services"
    metadata_dir = outdir / "metadata"
    dist_dir = outdir / "dist"
    bin_dir = outdir / "bin"

    for d in [docs_dir, config_dir, scripts_dir, services_dir, metadata_dir, dist_dir, bin_dir]:
        d.mkdir(parents=True, exist_ok=True)

    _copy_file(repo / "README.md", docs_dir / "README.md")
    _copy_file(repo / "config.example.json", config_dir / "config.example.json")
    _copy_file(repo / "config.sidecar.example.json", config_dir / "config.sidecar.example.json")
    _copy_file(repo / "requirements.txt", metadata_dir / "requirements.txt")
    _copy_file(repo / "pyproject.toml", metadata_dir / "pyproject.toml")

    manifest = {
        "name": "cc-usage-reporter",
        "version": version,
        "platform": plat,
        "generated_at": datetime.now().isoformat(),
        "layout": ["bin", "config", "scripts", "services", "docs", "metadata", "dist"],
        "normalized_bin": ["cc-usage-reporter", "cc-usage-reporter-gui"],
    }
    _write_text(metadata_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    for sub in ["linux", "macos", "windows"]:
        _copy_tree(repo / "service_templates" / sub, services_dir / sub)
        _copy_tree(repo / "packaging" / sub, scripts_dir / sub)

    repo_dist = repo / "dist"
    if repo_dist.exists():
        for item in repo_dist.iterdir():
            target = dist_dir / item.name
            if item.is_dir():
                _copy_tree(item, target)
            else:
                _copy_file(item, target)
                _copy_file(item, bin_dir / _normalized_bin_name(item.name))

    _write_text(docs_dir / "RELEASE_LAYOUT.md", RELEASE_LAYOUT_MD)
    _write_text(docs_dir / "INSTALL_WINDOWS.md", INSTALL_WINDOWS_MD)
    _write_text(docs_dir / "INSTALL_LINUX.md", INSTALL_LINUX_MD)
    _write_text(docs_dir / "INSTALL_MACOS.md", INSTALL_MACOS_MD)
    _generate_installers(outdir, plat)

    if pack:
        artifacts = _pack_release(outdir)
        _write_checksums(outdir, artifacts)

    return outdir


def _generate_installers(outdir: Path, plat: str) -> None:
    if plat == "windows":
        _write_text(outdir / "install.ps1", WINDOWS_INSTALL_PS1)
    else:
        _write_text(outdir / "install.sh", POSIX_INSTALL_SH)

    _write_text(outdir / "install-linux.sh", LINUX_INSTALL_SH)
    _write_text(outdir / "install-macos.sh", MACOS_INSTALL_SH)
    _write_text(outdir / "install-windows.ps1", WINDOWS_INSTALL_PS1)
