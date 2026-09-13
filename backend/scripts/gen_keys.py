from __future__ import annotations

import argparse
import secrets
import sys

from app.config import get_settings
from app.security import crypto, rotation


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate IdentiCare key material.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing KEK. Destroys access to every stored template.",
    )
    args = parser.parse_args()

    settings = get_settings()
    kek_path = settings.kek_file
    rot_path = settings.rotation_file
    kek_path.parent.mkdir(parents=True, exist_ok=True)

    if kek_path.exists() and not args.force:
        print(f"[=] KEK already exists at {kek_path} — keeping it.")
        kek = crypto.load_kek(kek_path)
    else:
        if kek_path.exists():
            print("[!] --force: overwriting the KEK. Existing templates become unreadable.")
        kek = crypto.generate_kek()
        kek_path.write_bytes(kek)
        print(f"[+] KEK written to {kek_path} ({len(kek)} bytes)")

    print(
        f"[*] Deriving {settings.face_embedding_dim}x{settings.face_embedding_dim} "
        "orthogonal rotation from the KEK (HKDF-seeded QR)..."
    )
    matrix = rotation.derive_rotation(kek, dim=settings.face_embedding_dim)
    rotation.save_rotation(matrix, rot_path)
    print(f"[+] Rotation matrix written to {rot_path}")

    import numpy as np

    identity_err = float(np.abs(matrix @ matrix.T - np.eye(matrix.shape[0])).max())
    print(f"[+] Orthogonality check: max|R.R^T - I| = {identity_err:.2e}")
    if identity_err > 1e-9:
        print("[!] FAILED — matrix is not orthogonal, cosine would not be preserved.")
        return 1

    if not (kek_path.parent / ".gitignore").exists():
        (kek_path.parent / ".gitignore").write_text("*\n", encoding="utf-8")

    print()
    print("[*] Suggested NIK_PEPPER for your .env (it must NOT live in the database):")
    print(f"    NIK_PEPPER={secrets.token_urlsafe(32)}")
    print()
    print("[!] Back up keys/kek.bin separately from any database backup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
