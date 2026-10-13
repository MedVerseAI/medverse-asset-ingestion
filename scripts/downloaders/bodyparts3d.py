import os
import sys
import argparse
from pathlib import Path

# Dynamically add the root repository folder to Python's path so it can find the 'src' module
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.medverse.validation import verify_file
from src.medverse.download import download_dataset
from src.medverse.extraction import extract_dataset

def main():
    parser = argparse.ArgumentParser(description="Automate the download, validation, and extraction of the BodyParts3D dataset.")
    
    # Define the command-line arguments
    parser.add_argument("--url", required=True, help="Direct URL to the dataset archive (.zip or .tar.gz).")
    parser.add_argument("--raw-dest", default="data/raw/bodyparts3d.zip", help="Path to save the downloaded archive.")
    parser.add_argument("--extract-to", default="data/interim/bodyparts3d/", help="Directory to unpack the 3D meshes into.")
    parser.add_argument("--expected-hash", default=None, help="Expected SHA-256 hash for strict validation.")
    parser.add_argument("--keep-archive", action="store_true", help="Keep the massive .zip file after extraction (default is to delete it).")
    
    args = parser.parse_args()
    
    print("\n=== MedVerse Dataset Ingestion Pipeline ===")
    
    # STEP 1: Local Check (Idempotency)
    needs_download = True
    if os.path.exists(args.raw_dest):
        print(f"[Orchestrator] Found existing archive at {args.raw_dest}. Inspecting...")
        if verify_file(args.raw_dest, args.expected_hash):
            print("[Orchestrator] Existing archive is valid. Skipping network request.")
            needs_download = False
        else:
            print("[Orchestrator] Existing archive is corrupted. Preparing to re-download...")
            
    # STEP 2 & 3: Network Fetch & Post-Download Validation
    if needs_download:
        print("[Orchestrator] Initiating network fetch...")
        if not download_dataset(args.url, args.raw_dest):
            print("[Orchestrator] FATAL: Pipeline aborted due to network failure.")
            sys.exit(1)
            
        print("[Orchestrator] Validating newly downloaded file...")
        if not verify_file(args.raw_dest, args.expected_hash):
            print("[Orchestrator] FATAL: Pipeline aborted due to hash mismatch on new download.")
            sys.exit(1)

    # STEP 4: Extraction & Cleanup
    print("[Orchestrator] Initiating extraction phase...")
    # If the user didn't explicitly pass --keep-archive, we delete it to save space
    should_delete = not args.keep_archive 
    
    if extract_dataset(args.raw_dest, args.extract_to, delete_archive=should_delete):
        print("=== Pipeline Completed Successfully ===\n")
    else:
        print("=== Pipeline Failed During Extraction ===\n")
        sys.exit(1)

if __name__ == "__main__":
    main()