import base64

from django.core.management.base import BaseCommand
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class Command(BaseCommand):
    help = "Generate one VAPID key pair for INPROFIC Web Push environment variables."

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
        public_raw = private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write("Generate once, then store these in Render Environment:")
        self.stdout.write(f"WEB_PUSH_VAPID_PUBLIC_KEY={_b64url(public_raw)}")
        self.stdout.write(f"WEB_PUSH_VAPID_PRIVATE_KEY={_b64url(private_raw)}")
        self.stdout.write("WEB_PUSH_VAPID_SUBJECT=mailto:your-admin-email@example.com")
        self.stdout.write(self.style.WARNING("Keep the private key secret and stable. Rotating it requires devices to subscribe again."))
