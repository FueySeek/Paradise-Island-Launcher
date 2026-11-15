"""鏋勫缓鍗曟枃浠?Windows exe銆?
鐢ㄦ硶:
    python build_exe.py

浜х墿: dist/Paradise Island Launcher.exe
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "Paradise Island Launcher"
ICON = os.path.join(ROOT, "static", "images", "icon.ico")
SPLASH = os.path.join(ROOT, "static", "images", "splash.png")

EXCLUDES = (
    "unittest", "doctest", "pydoc", "pydoc_data", "lib2to3", "sqlite3",
    "distutils", "setuptools", "pip", "ensurepip", "venv", "idlelib",
    "xmlrpc", "curses", "test", "turtle", "turtledemo",
)


def main():
    if not os.path.isfile(ICON):
        raise SystemExit("缂哄皯鍥炬爣: " + ICON + "锛岃鍏堣繍琛?python tools/make_assets.py")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--icon", ICON,
        "--add-data", os.path.join(ROOT, "static") + os.pathsep + "static",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    if os.path.isfile(SPLASH):
        args += ["--splash", SPLASH]
    # 鎸囧畾鍙啓鐨勮В鍘嬬洰褰曪紝閬垮厤绯荤粺 TEMP 鏃犳潈闄愭椂 onefile 鍚姩澶辫触
    args += ["--runtime-tmpdir", "."]
    args.append(os.path.join(ROOT, "app.py"))
    print(" ".join(args))
    subprocess.run(args, check=True)
    exe = os.path.join(ROOT, "dist", NAME + ".exe")
    if os.path.isfile(exe):
        print("鏋勫缓瀹屾垚:", exe, "(%.1f MB)" % (os.path.getsize(exe) / 1024 / 1024))
    else:
        raise SystemExit("鏋勫缓澶辫触锛氭湭鎵惧埌 exe")


if __name__ == "__main__":
    main()

