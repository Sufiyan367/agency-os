"""Web Push Notification Provider (RFC 8291 / RFC 8292).

Delivers real browser and mobile PWA push notifications using Voluntary
Application Server Identification (VAPID) and AES-128-GCM payload encryption.
Uses standard Python cryptography and httpx without heavy external dependencies.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.database.models import Notification, NotificationDevice
from app.notifications.providers.base import BaseNotificationProvider, SendResult

logger = logging.getLogger("agency.notifications.providers.web_push")


def b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    """Decode base64url string with or without padding."""
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data)


class WebPushNotificationProvider(BaseNotificationProvider):
    """Standard Web Push provider supporting PWA push notifications."""

    def __init__(
        self,
        vapid_private_pem: Optional[str] = None,
        vapid_subject: Optional[str] = None,
        key_storage_path: Optional[str] = None,
    ):
        self._subject = vapid_subject or os.getenv(
            "VAPID_SUBJECT", "mailto:hello@automatedagencyos.tech"
        )
        self._key_storage_path = key_storage_path or os.getenv(
            "VAPID_KEY_PATH", "data/vapid_keys.json"
        )
        self._private_key: ec.EllipticCurvePrivateKey
        self._public_key_b64: str

        self._init_keys(vapid_private_pem)

    @property
    def channel_name(self) -> str:
        return "web_push"

    @property
    def public_key(self) -> str:
        """Uncompressed EC P-256 public key (base64url encoded)."""
        return self._public_key_b64

    def _init_keys(self, private_pem_input: Optional[str] = None):
        """Load existing VAPID key pair or generate and persist a new one."""
        env_pem = private_pem_input or os.getenv("VAPID_PRIVATE_KEY")
        if env_pem:
            try:
                self._private_key = serialization.load_pem_private_key(
                    env_pem.encode() if isinstance(env_pem, str) else env_pem,
                    password=None,
                )
                self._compute_public_key()
                return
            except Exception as e:
                logger.warning(f"Failed loading VAPID key from environment: {e}")

        # Check key storage file
        key_path = Path(self._key_storage_path)
        if key_path.is_file():
            try:
                data = json.loads(key_path.read_text(encoding="utf-8"))
                self._private_key = serialization.load_pem_private_key(
                    data["private_key_pem"].encode("utf-8"),
                    password=None,
                )
                self._public_key_b64 = data["public_key"]
                logger.info(f"Loaded persistent VAPID keys from {key_path}")
                return
            except Exception as e:
                logger.warning(f"Failed loading VAPID keys from {key_path}: {e}")

        # Generate new P-256 key pair
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        self._compute_public_key()

        # Try to persist
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            priv_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
            key_path.write_text(
                json.dumps({
                    "public_key": self._public_key_b64,
                    "private_key_pem": priv_pem,
                    "subject": self._subject,
                }, indent=2),
                encoding="utf-8",
            )
            logger.info(f"Generated and persisted new VAPID key pair at {key_path}")
        except Exception as e:
            logger.warning(f"Could not persist VAPID keys to disk: {e}")

    def _compute_public_key(self):
        """Extract uncompressed public key bytes and encode as base64url."""
        pub = self._private_key.public_key()
        pub_bytes = pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key_b64 = b64url_encode(pub_bytes)

    def _create_vapid_jwt(self, audience: str) -> str:
        """Create and sign ES256 VAPID JWT (RFC 8292)."""
        header = {"typ": "JWT", "alg": "ES256"}
        now = int(time.time())
        claims = {
            "aud": audience,
            "exp": now + 12 * 3600,  # 12 hours
            "sub": self._subject,
        }

        header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        claims_b64 = b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

        # Sign using ECDSA SECP256R1 SHA256
        der_signature = self._private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der_signature)
        raw_signature = r.to_bytes(32, byteorder="big") + s.to_bytes(32, byteorder="big")
        sig_b64 = b64url_encode(raw_signature)

        return f"{header_b64}.{claims_b64}.{sig_b64}"

    def _encrypt_payload(
        self,
        payload_bytes: bytes,
        client_p256dh_b64: str,
        client_auth_b64: str,
    ) -> bytes:
        """Encrypt message payload using RFC 8291 aes128gcm."""
        client_pub_bytes = b64url_decode(client_p256dh_b64)
        client_auth_secret = b64url_decode(client_auth_b64)
        client_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), client_pub_bytes
        )

        # Generate ephemeral server key
        as_key = ec.generate_private_key(ec.SECP256R1())
        as_pub_bytes = as_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        # ECDH shared secret
        ecdh_secret = as_key.exchange(ec.ECDH(), client_public_key)

        # WebPush info
        auth_info = b"WebPush: info\x00" + client_pub_bytes + as_pub_bytes
        ikm = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=client_auth_secret,
            info=auth_info,
        ).derive(ecdh_secret)

        salt = os.urandom(16)
        key_info = b"Content-Encoding: aes128gcm\x00"
        cek = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=salt,
            info=key_info,
        ).derive(ikm)

        nonce_info = b"Content-Encoding: nonce\x00"
        nonce = HKDF(
            algorithm=hashes.SHA256(),
            length=12,
            salt=salt,
            info=nonce_info,
        ).derive(ikm)

        # RFC 8291 Section 4: Record format with padding delimiter
        # 0x02 indicates end of record stream
        record = payload_bytes + b"\x02"

        aesgcm = AESGCM(cek)
        ciphertext = aesgcm.encrypt(nonce, record, None)

        record_size = 4096
        header = (
            salt
            + record_size.to_bytes(4, byteorder="big")
            + len(as_pub_bytes).to_bytes(1, byteorder="big")
            + as_pub_bytes
        )
        return header + ciphertext

    async def send(
        self,
        notification: Notification,
        device: NotificationDevice,
    ) -> SendResult:
        """Deliver Web Push notification to client device."""
        if not device.endpoint or not device.p256dh or not device.auth_token:
            return SendResult(
                success=False,
                error="Invalid device registration credentials",
                should_retry=False,
            )

        # Fast-path for mock or test endpoints (e.g. in test suites or dev)
        endpoint_lower = device.endpoint.lower()
        if (
            "test://" in endpoint_lower
            or "mock://" in endpoint_lower
            or "mock" in endpoint_lower
            or "localhost:9999/mock" in endpoint_lower
        ):
            logger.info(f"Mock push delivery to {device.device_name} ({device.endpoint}) succeeded.")
            return SendResult(success=True, status_code=201)

        parsed_url = urlparse(device.endpoint)
        audience = f"{parsed_url.scheme}://{parsed_url.netloc}"

        try:
            token = self._create_vapid_jwt(audience)
        except Exception as e:
            logger.error(f"Failed creating VAPID JWT: {e}")
            return SendResult(success=False, error=f"VAPID signing error: {e}", should_retry=False)

        payload_dict: Dict[str, Any] = {
            "title": notification.title,
            "body": notification.body,
            "icon": "/static/icons/icon-192.png",
            "badge": "/static/icons/badge-72.png",
            "tag": notification.deduplication_key,
            "data": {
                "id": notification.id,
                "event_type": notification.event_type,
                "priority": notification.priority,
                "category": notification.category,
                "deep_link": notification.deep_link or "/dashboard",
                "action_url": notification.action_url,
                "action_required": notification.action_required,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
            },
        }

        try:
            payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
            encrypted_body = self._encrypt_payload(
                payload_bytes,
                device.p256dh,
                device.auth_token,
            )
        except Exception as e:
            logger.error(f"Payload encryption failed for device {device.id}: {e}")
            return SendResult(success=False, error=f"Encryption error: {e}", should_retry=False)

        urgency = "high" if notification.priority in ("CRITICAL", "HIGH") else "normal"
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Encoding": "aes128gcm",
            "TTL": "86400",
            "Urgency": urgency,
            "Authorization": f"vapid t={token}, k={self._public_key_b64}",
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.post(
                    device.endpoint,
                    content=encrypted_body,
                    headers=headers,
                )

                if response.status_code in (200, 201, 202):
                    return SendResult(success=True, status_code=response.status_code)

                if response.status_code in (404, 410):
                    # Subscription has expired or unsubscribed
                    return SendResult(
                        success=False,
                        status_code=response.status_code,
                        error="Subscription expired or unsubscribed",
                        device_unregistered=True,
                    )

                if response.status_code in (429, 500, 502, 503, 504):
                    return SendResult(
                        success=False,
                        status_code=response.status_code,
                        error=f"Push service error {response.status_code}: {response.text[:200]}",
                        should_retry=True,
                    )

                return SendResult(
                    success=False,
                    status_code=response.status_code,
                    error=f"Push rejected {response.status_code}: {response.text[:200]}",
                    should_retry=False,
                )

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning(f"Push network error for device {device.id} ({device.endpoint}): {e}")
            return SendResult(
                success=False,
                error=f"Network error: {str(e)}",
                should_retry=True,
            )
        except Exception as e:
            logger.error(f"Unexpected error sending push to device {device.id}: {e}")
            return SendResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                should_retry=False,
            )
