"""Print a new Ed25519 private key (hex) for COLLECTOR_PRIVATE_KEY. Put it in .env — never commit it."""
import nacl.signing

if __name__ == "__main__":
    print(nacl.signing.SigningKey.generate().encode().hex())
