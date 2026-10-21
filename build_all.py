"""
Flet 应用多平台打包脚本
用法：python build_all.py
根据当前操作系统自动构建可生成的平台包。
入口默认 main.py，全部项目文件默认包含。
"""
import subprocess
import sys
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
ENTRY_FILE = PROJECT_ROOT / "main.py"

# 需要确保被包含的文件/目录（Flet 默认会包含项目文件，此处显式声明以防遗漏）
INCLUDE_ITEMS = ["assets", "*.json", "*.txt", "*.csv"]  # 按需修改

def run_build(target: str, extra_args: list = None):
    """执行 flet build 命令"""
    cmd = ["flet", "build", target, str(PROJECT_ROOT)]
    
    # 确保包含关键资源
    for item in INCLUDE_ITEMS:
        if (PROJECT_ROOT / item.replace("*", "")).exists() or any(PROJECT_ROOT.glob(item)):
            cmd.extend(["--include", item])
    
    if extra_args:
        cmd.extend(extra_args)
    
    print(f"\n{'='*60}")
    print(f"正在构建: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[失败] {target} 构建返回码: {result.returncode}")
        return False
    print(f"[成功] {target} 构建完成")
    return True

def main():
    if not ENTRY_FILE.exists():
        print(f"错误：未找到入口文件 {ENTRY_FILE}")
        print("请确保 main.py 位于项目根目录。")
        sys.exit(1)
    
    system = platform.system()  # Windows / Darwin / Linux
    print(f"当前操作系统: {system}")
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"入口文件: {ENTRY_FILE}")
    
    builds = []
    
    if system == "Windows":
        builds.append(("windows", None))
    elif system == "Darwin":
        builds.append(("macos", None))
    elif system == "Linux":
        # Linux 可构建 Linux 桌面版，但不是你要求的 win/mac
        pass
    
    # Android 在三个平台均可构建
    builds.append(("apk", ["--split-per-abi"]))  # 按 CPU 架构拆分，减小单个包体积
    
    if not builds:
        print(f"当前系统 {system} 无法构建 windows 或 macos 包。")
        print("请在各对应系统上运行此脚本，或使用 GitHub Actions 跨平台构建。")
        sys.exit(1)
    
    success_count = 0
    for target, args in builds:
        if run_build(target, args):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"构建结束: {success_count}/{len(builds)} 个平台成功")
    print(f"产物位置: {PROJECT_ROOT / 'build'}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()