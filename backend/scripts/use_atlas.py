from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError

BACKEND = Path(__file__).resolve().parent.parent
ENV = BACKEND / ".env"
PLACEHOLDER = "REPLACE_WITH_CLUSTER_HOST"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    host = sys.argv[1].strip()
    m = re.match(r"mongodb\+srv://(?:[^@]+@)?([^/?]+)", host)
    if m:
        host = m.group(1)
    host = host.removeprefix("mongodb+srv://").rstrip("/")
    if not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9]+\.mongodb\.net", host):
        print(f"[!] That does not look like an Atlas host: {host}")
        print("    Expected something like  cluster0.ab12cd.mongodb.net")
        print("    Find it in Atlas: your cluster > Connect > Drivers.")
        return 2

    if not ENV.exists():
        print(f"[!] {ENV} not found. Copy .env.example to .env first.")
        return 1

    text = ENV.read_text(encoding="utf-8")
    line = re.search(r"^MONGO_URI=(.*)$", text, flags=re.M)
    if not line:
        print("[!] No MONGO_URI line in .env")
        return 1

    uri = line.group(1)
    if PLACEHOLDER in uri:
        uri = uri.replace(PLACEHOLDER, host)
    else:
        uri = re.sub(r"@[^/?]+", f"@{host}", uri, count=1)
        if not uri.startswith("mongodb+srv://"):
            print("[!] MONGO_URI is not an Atlas (mongodb+srv://) string; edit .env by hand.")
            return 1

    text = text[: line.start(1)] + uri + text[line.end(1) :]
    ENV.write_text(text, encoding="utf-8")
    print(f"[+] MONGO_URI now points at {host}")

    print("[*] Connecting to Atlas...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=15000)
        client.admin.command("ping")
    except ConfigurationError as exc:
        print(f"[!] Bad connection string: {exc}")
        return 1
    except OperationFailure as exc:
        if "auth" in str(exc).lower():
            print("[!] Authentication failed. Check the user name and password in .env")
            print("    (Atlas > Database Access). If you rotated the password, update .env.")
        else:
            print(f"[!] MongoDB refused: {exc}")
        return 1
    except ServerSelectionTimeoutError:
        print("[!] Could not reach the cluster. By far the most common cause:")
        print("    your current IP is not on the Atlas allowlist.")
        print("    Atlas > Network Access > Add IP Address > 'Allow access from anywhere'")
        print("    (0.0.0.0/0) is fine for development, and the only choice that survives")
        print("    a phone hotspot whose public IP changes.")
        return 1
    print("[+] Atlas reachable")

    py = sys.executable
    for script in ("bootstrap.py", "seed_peserta.py", "seed_articles.py"):
        path = BACKEND / "scripts" / script
        if not path.exists():
            print(f"[~] {script} not present, skipping")
            continue
        print(f"\n[*] {script}")
        rc = subprocess.call([py, str(path)], cwd=str(BACKEND))
        if rc != 0:
            print(f"[!] {script} failed (exit {rc})")
            return rc

    print("\n[+] Done. The backend now uses Atlas; Docker is no longer needed.")
    print("    Start it with:  backend\\start_backend.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
