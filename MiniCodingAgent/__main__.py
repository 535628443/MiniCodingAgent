import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from MiniCodingAgent.main import main
else:
    from .main import main

if __name__ == "__main__":
    main()
