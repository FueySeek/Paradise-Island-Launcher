import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "Paradise Island Launcher"
ICON = os.path.join(ROOT, "static", "images", "icon.ico")
STATIC = os.path.join(ROOT, "static")

EXCLUDES = (
    "pygame", "numpy", "pandas", "matplotlib", "scipy", "cv2", "torch", "tensorflow",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "jupyter", "notebook", "nbformat",
    "lib2to3", "idlelib", "turtle", "turtledemo", "test",
)


def main():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--icon", ICON,
        "--add-data", STATIC + os.pathsep + "static",
        "--collect-all", "customtkinter",
        "--hidden-import", "PIL._tkinter_finder",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
        "--runtime-tmpdir", ".",
    ]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    args.append(os.path.join(ROOT, "launcher.py"))
    subprocess.run(args, check=True)
    exe = os.path.join(ROOT, "dist", NAME + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("build failed")
    print(exe, "%.1f MB" % (os.path.getsize(exe) / 1024 / 1024))


if __name__ == "__main__":
    main()
