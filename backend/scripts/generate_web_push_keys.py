"""Generate a VAPID pair once; keep the private value in Render secrets only."""

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_keys() -> tuple[str, str]:
    private = ec.generate_private_key(ec.SECP256R1())
    private_raw = private.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return _encode(public_raw), _encode(private_raw)


if __name__ == "__main__":
    public_key, private_key = generate_keys()
    print(f"WEB_PUSH_VAPID_PUBLIC_KEY={public_key}")
    print(f"WEB_PUSH_VAPID_PRIVATE_KEY={private_key}")
