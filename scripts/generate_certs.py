"""Генерация self-signed TLS для nginx (docker compose)."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    print("Install: pip install cryptography")
    sys.exit(1)

CERT_DIR = Path(__file__).resolve().parent.parent / "deploy" / "nginx" / "certs"
CERT_DIR.mkdir(parents=True, exist_ok=True)

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
])
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
    .sign(key, hashes.SHA256())
)

(CERT_DIR / "key.pem").write_bytes(
    key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
(CERT_DIR / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print(f"Created {CERT_DIR / 'cert.pem'} and key.pem")
