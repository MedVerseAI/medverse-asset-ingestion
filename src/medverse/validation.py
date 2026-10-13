import os
import hashlib

def verify_file(filepath: str, expected_hash: str = None) -> bool:
    """
    Checks if a file exists and optionally validates its SHA-256 checksum.
    Reads in binary chunks to prevent RAM overload on massive 3D datasets.
    """
    if not os.path.exists(filepath):
        print(f"[Validation] File not found: {filepath}")
        return False
    
    if not expected_hash:
        print(f"[Validation] File exists, skipping hash check: {filepath}")
        return True
        
    print(f"[Validation] Validating SHA-256 checksum for {filepath}...")
    
    sha256_hash = hashlib.sha256()
    
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
            
    calculated_hash = sha256_hash.hexdigest()
    
    if calculated_hash == expected_hash:
        print("[Validation] SUCCESS: File is perfectly intact.")
        return True
    else:
        print(f"[Validation] FAILURE: Hash mismatch.\nExpected: {expected_hash}\nGot:      {calculated_hash}")
        return False