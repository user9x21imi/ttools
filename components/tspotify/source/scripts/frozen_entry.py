import sys

from tspotify import _worker
from tspotify.cli import main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_engine_worker":
        raise SystemExit(_worker.main(sys.argv[2:]))
    main()
