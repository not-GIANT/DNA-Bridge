import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class EncryptionManager:
    def __init__(self, pairing_code: str):
        # Use a static salt for the MVP, though a dynamic one shared during pairing would be better.
        salt = b'dna-bridge-salt-v1' 
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(pairing_code.encode()))
        self.fernet = Fernet(key)

    def encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception:
            return None
