"""Σημείο εισόδου για το PyInstaller (.exe στα Windows, .app στο macOS)."""
import sys

from uniwa_notifier.launcher.app import main

if __name__ == "__main__":
    sys.exit(main())
