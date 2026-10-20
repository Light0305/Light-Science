"""支持 `python -m light_literature ...` 调用。"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
