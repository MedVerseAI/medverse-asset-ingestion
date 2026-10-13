import os
import zipfile
import tarfile

def extract_dataset(archive_path: str, extract_to: str, delete_archive: bool = False) -> bool:
    """
    Extracts .zip or .tar.gz archives into the target directory.
    Optionally deletes the original archive to save hard drive space.
    """
    if not os.path.exists(archive_path):
        print(f"[Extraction] Error: Archive not found at {archive_path}")
        return False

    # Ensure the destination folder (data/interim) exists
    os.makedirs(extract_to, exist_ok=True)
    print(f"[Extraction] Unpacking {archive_path} into {extract_to}...")

    try:
        # Handle standard Zip files
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
                
        # Handle Tarballs (common in scientific/medical datasets)
        elif archive_path.endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_to)
                
        else:
            print(f"[Extraction] Unsupported file format: {archive_path}")
            return False

        print(f"[Extraction] SUCCESS: Files extracted to {extract_to}")

        # Storage management logic
        if delete_archive:
            os.remove(archive_path)
            print(f"[Extraction] Cleaned up original archive to save space: {archive_path}")

        return True

    except (zipfile.BadZipFile, tarfile.ReadError) as e:
        print(f"[Extraction] FATAL ERROR: Archive is corrupted or incomplete. {e}")
        return False