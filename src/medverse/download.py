import os
import requests

def download_dataset(url: str, dest_path: str, chunk_size: int = 5242880) -> bool:
    """
    Downloads massive datasets over HTTP using large network-optimized chunks.
    Default chunk_size is 5MB (5242880 bytes) to maximize bandwidth.
    """
    # Ensure the target directory (e.g., data/raw/) exists before writing
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    print(f"[Network] Initiating connection to {url}...")
    
    try:
        # stream=True is critical: it keeps the 5GB file out of the RAM
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status() # Instantly catch 404 or 500 errors
            
            # Extract file size from HTTP headers for the progress tracker
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            print(f"[Network] Connected. Downloading {total_size / (1024 * 1024):.2f} MB...")
            
            # Write to disk in 5 MB chunks
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Print a dynamic progress bar on a single terminal line
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r[Network] Progress: {percent:.1f}% ({downloaded / (1024*1024):.1f} MB)", end="")
            
            print("\n[Network] SUCCESS: Download complete.")
            return True
            
    except requests.exceptions.RequestException as e:
        print(f"\n[Network] FATAL ERROR: Connection failed. {e}")
        # Automatically delete the corrupted partial file to prevent false validations later
        if os.path.exists(dest_path):
            os.remove(dest_path)
            print(f"[Network] Cleaned up partial file: {dest_path}")
        return False