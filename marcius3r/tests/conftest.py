import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.mkdtemp(prefix="m3r-test-")
os.environ.setdefault("MARCIUS3R_DATA", _tmp)
os.environ.setdefault("MARCIUS3R_SECRETS", os.path.join(_tmp, "secrets"))
