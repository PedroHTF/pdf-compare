"""Lançador na raiz do projeto (usado também pelo PyInstaller)."""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
