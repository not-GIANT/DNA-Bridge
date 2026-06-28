import asyncio
import websockets
import json
from client.encryption import EncryptionManager

async def test_relay():
    pairing_code = "TEST01"
    server_url = "ws://localhost:8000/ws/" + pairing_code
    
    encryptor_a = EncryptionManager(pairing_code)
    encryptor_b = EncryptionManager(pairing_code)
    
    test_message = "Hello from DNA Bridge!"
    
    # Connect Client B (receiver)
    async with websockets.connect(server_url) as ws_b:
        print("Client B connected")
        
        # Connect Client A (sender)
        async with websockets.connect(server_url) as ws_a:
            print("Client A connected")
            
            # Send encrypted message from A
            encrypted_a = encryptor_a.encrypt(test_message)
            await ws_a.send(encrypted_a)
            print(f"Client A sent: {test_message}")
            
            # Receive on B
            received_b = await asyncio.wait_for(ws_b.recv(), timeout=5.0)
            decrypted_b = encryptor_b.decrypt(received_b)
            print(f"Client B received: {decrypted_b}")
            
            assert decrypted_b == test_message
            print("Sync Test Passed!")

if __name__ == "__main__":
    # This script assumes the server is already running
    try:
        asyncio.run(test_relay())
    except Exception as e:
        print(f"Test Failed: {e}")
