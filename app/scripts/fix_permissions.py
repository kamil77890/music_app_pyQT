import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fix-music-permissions.sh"


def main() -> None:
    if not _SCRIPT_PATH.is_file():
        log.error("Script not found: %s", _SCRIPT_PATH)
        sys.exit(1)
    result = subprocess.run(["bash", str(_SCRIPT_PATH)])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
