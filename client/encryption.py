import base64
import hashlib
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("Client")

class EncryptionManager:
    def __init__(self, pairing_code: str):
        # Use a static salt for the MVP, though a dynamic one shared during pairing would be better.
        salt = b'dna-bridge-salt-v1' 
        logger.debug(f"Deriving encryption key from pairing code using PBKDF2HMAC")
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(pairing_code.encode()))
            self.fernet = Fernet(key)
            logger.info("Encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise

    def encrypt(self, data: str) -> str:
        try:
            return self.fernet.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return ""

    def decrypt(self, encrypted_data: str) -> str:
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.debug(f"Decryption failed (likely invalid key or data): {e}")
            return None
