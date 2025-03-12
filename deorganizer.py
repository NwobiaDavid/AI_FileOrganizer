import os
import shutil
import argparse
from pathlib import Path
import logging
from tqdm import tqdm

def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def get_unique_filename(destination_path: str) -> str:
    """
    Generate a unique filename if a duplicate exists.
    
    Args:
        destination_path: The target file path
        
    Returns:
        A unique file path that doesn't exist yet
    """
    if not os.path.exists(destination_path):
        return destination_path
        
    directory, filename = os.path.split(destination_path)
    name, extension = os.path.splitext(filename)
    
    counter = 1
    while True:
        new_filename = f"{name} ({counter}){extension}"
        new_path = os.path.join(directory, new_filename)
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def flatten_directory(directory_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    """
    Moves all files from subdirectories to the main directory.
    
    Args:
        directory_path: Path to the directory to flatten
        dry_run: If True, only show what would be done without making changes
        verbose: Whether to print detailed logging information
    """
    setup_logging(verbose)
    
    # Convert to absolute path
    directory_path = os.path.abspath(directory_path)
    
    if not os.path.exists(directory_path):
        logging.error(f"Error: Directory '{directory_path}' does not exist!")
        return
    
    if not os.path.isdir(directory_path):
        logging.error(f"Error: '{directory_path}' is not a directory!")
        return
    
    # Find all files in subdirectories
    total_files = 0
    files_to_move = []
    
    logging.info(f"Scanning directory: {directory_path}")
    for root, dirs, files in os.walk(directory_path):
        # Skip the main directory itself
        if root == directory_path:
            continue
        
        for filename in files:
            source_path = os.path.join(root, filename)
            dest_path = os.path.join(directory_path, filename)
            files_to_move.append((source_path, dest_path))
            total_files += 1
    
    if total_files == 0:
        print("No files found in subdirectories. Nothing to do.")
        return
    
    print(f"\nFound {total_files} files in subdirectories to move to the main directory.")
    
    if dry_run:
        print("\nDRY RUN: No files will be moved.")
        if verbose:
            for source, dest in files_to_move[:10]:
                print(f"Would move: {source} -> {dest}")
            if len(files_to_move) > 10:
                print(f"... and {len(files_to_move) - 10} more files")
        return
    
    # Move all files to the main directory
    print("\nMoving files to the main directory...")
    
    moved_files = 0
    skipped_files = 0
    failed_files = 0
    
    with tqdm(total=total_files, disable=not verbose) as pbar:
        for source_path, dest_path in files_to_move:
            try:
                # Handle duplicates by creating a unique filename
                if os.path.exists(dest_path):
                    unique_dest_path = get_unique_filename(dest_path)
                    if verbose:
                        logging.info(f"Duplicate detected, renaming: {dest_path} -> {unique_dest_path}")
                    dest_path = unique_dest_path
                
                # Move the file
                shutil.move(source_path, dest_path)
                moved_files += 1
                
                if verbose:
                    rel_source = os.path.relpath(source_path, start=directory_path)
                    rel_dest = os.path.relpath(dest_path, start=directory_path)
                    logging.info(f"Moved: {rel_source} -> {rel_dest}")
            
            except (shutil.Error, OSError) as e:
                failed_files += 1
                logging.error(f"Failed to move {source_path}: {str(e)}")
            
            pbar.update(1)
    
    # Remove empty directories
    print("\nRemoving empty directories...")
    dirs_removed = 0
    
    for root, dirs, files in os.walk(directory_path, topdown=False):
        if root == directory_path:
            continue
        
        try:
            # Check if directory is empty
            if not os.listdir(root):
                os.rmdir(root)
                rel_path = os.path.relpath(root, start=directory_path)
                logging.info(f"Removed empty directory: {rel_path}")
                dirs_removed += 1
        except OSError as e:
            logging.error(f"Failed to remove directory {root}: {str(e)}")
    
    # Summary
    print("\n✅ Flattening complete!")
    print(f"Moved {moved_files} files to the main directory")
    print(f"Removed {dirs_removed} empty directories")
    
    if failed_files > 0:
        print(f"Failed to move {failed_files} files (see log for details)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flatten a directory structure by moving all files to the parent directory")
    parser.add_argument("directory", help="Directory path to flatten")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    try:
        flatten_directory(
            args.directory,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()