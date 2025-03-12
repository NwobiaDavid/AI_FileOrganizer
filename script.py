import os
import shutil
import argparse
from collections import defaultdict
import re
from typing import Set, List, Dict, Tuple
import logging
from tqdm import tqdm
import concurrent.futures
import difflib

def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def sanitize_folder_name(folder_name: str) -> str:
    """
    Sanitize folder names by removing invalid characters.
    
    Args:
        folder_name: The original folder name to sanitize
        
    Returns:
        A sanitized folder name safe for file systems
    """
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', " ", folder_name)
    # Replace multiple spaces with a single space
    sanitized = re.sub(r"\s+", " ", sanitized)
    # Remove leading/trailing spaces
    sanitized = sanitized.strip()
    # Capitalize each word for readability
    sanitized = ' '.join(word.capitalize() for word in sanitized.split())
    
    if not sanitized or len(sanitized) > 255:
        return "Group_" + str(hash(folder_name) % 10000)
    return sanitized

def get_file_base_name(filename: str) -> str:
    """Extract base name without extension and normalize for comparison."""
    base_name = os.path.splitext(filename)[0]
    # Remove digits and special chars for better matching
    # normalized = re.sub(r'[\d_\-\s()]+', ' ', base_name.lower()).strip()
    normalized = re.sub(r'[\d_\-\s()\[\]@#$%^&*!~+=|{}:;\'"<>?/,]+', ' ', base_name.lower()).strip()
    return normalized

def find_similar_files(file_names: List[str], similarity_threshold: float = 0.7) -> Dict[str, List[str]]:
    """
    Find groups of similar files based on filename similarity.
    
    Args:
        file_names: List of filenames to compare
        similarity_threshold: Threshold for considering files similar (0.0-1.0)
        
    Returns:
        Dictionary mapping group identifiers to lists of similar filenames
    """
    # Extract base names for better comparison
    base_names = {file: get_file_base_name(file) for file in file_names}
    
    # Group by similar base names
    similarity_groups = defaultdict(list)
    processed = set()
    
    # First pass - exact matches after normalization
    name_groups = defaultdict(list)
    for file, base in base_names.items():
        if base:  # Skip empty base names
            name_groups[base].append(file)
    
    # Create groups from exact matches
    for base, files in name_groups.items():
        if len(files) >= 2:
            group_key = min(files)
            similarity_groups[group_key] = files
            processed.update(files)
    
    # Second pass - sequence matching for remaining files
    remaining = [f for f in file_names if f not in processed]
    
    for i, file1 in enumerate(remaining):
        # Skip if this file is already in a group
        if file1 in processed:
            continue
            
        current_group = [file1]
        base1 = base_names[file1]
        
        for file2 in remaining[i+1:]:
            if file2 in processed:
                continue
                
            base2 = base_names[file2]
            
            # Skip comparison if base names are too different in length
            if abs(len(base1) - len(base2)) > min(len(base1), len(base2)):
                continue
                
            similarity = difflib.SequenceMatcher(None, base1, base2).ratio()
            
            if similarity >= similarity_threshold:
                current_group.append(file2)
                processed.add(file2)
        
        if len(current_group) > 1:
            group_key = min(current_group)
            similarity_groups[group_key] = current_group
            processed.add(file1)
    
    return similarity_groups

def extract_common_patterns(file_names: List[str], min_length: int = 3) -> List[Tuple[str, float]]:
    """
    Extract common patterns from file names with relevance scoring.
    
    Args:
        file_names: List of file names to analyze
        min_length: Minimum length of patterns to consider
        
    Returns:
        List of (pattern, relevance_score) tuples sorted by relevance
    """
    # Extract words and phrases from filenames
    patterns = defaultdict(int)
    
    for name in file_names:
        base_name = os.path.splitext(name)[0].lower()
        
        # Extract words
        words = re.findall(r'\b\w{%d,}\b' % min_length, base_name)
        for word in words:
            patterns[word] += 1
        
        # Extract phrases (consecutive words)
        phrases = re.findall(r'\b(\w+\s+\w+(?:\s+\w+){0,3})\b', base_name)
        for phrase in phrases:
            if len(phrase) >= min_length:
                patterns[phrase] += 1
                
        # Extract sequential patterns (with connecting chars)
        sequences = re.findall(r'([a-z0-9]{%d,}(?:[_\-\s]+[a-z0-9]+){1,3})' % min_length, base_name)
        for seq in sequences:
            patterns[seq] += 1
    
    # Calculate relevance scores
    relevance_scores = []
    for pattern, count in patterns.items():
        if count >= 2 and len(pattern) >= min_length:
            # Score based on pattern length, frequency, and specificity
            specificity = len(pattern) / 20  # Normalize length
            frequency = min(count / len(file_names), 0.5)  # Cap at 0.5 to prevent domination
            score = specificity * frequency * count
            relevance_scores.append((pattern, score))
    
    # Sort by relevance score (higher is better)
    relevance_scores.sort(key=lambda x: x[1], reverse=True)
    return relevance_scores

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
        
        
def process_file(file_info: tuple, folder_path: str, dry_run: bool) -> tuple:
    """Process a single file for grouping."""
    file_name, group_folder_name = file_info
    source_path = os.path.join(folder_path, file_name)
    
    if not group_folder_name:
        group_folder_name = "Miscellaneous"
    
    group_folder = os.path.join(folder_path, group_folder_name)
    dest_path = os.path.join(group_folder, file_name)
    
    # Handle duplicate file names
    # if os.path.exists(dest_path) and source_path != dest_path:
    #     filename, ext = os.path.splitext(file_name)
    #     dest_path = os.path.join(group_folder, f"{filename}_copy{ext}")
    if os.path.exists(dest_path) and source_path != dest_path:
        dest_path = get_unique_filename(dest_path)
    
    if not dry_run and source_path != dest_path:
        try:
            # Create directory with a try-except to handle race condition
            try:
                os.makedirs(group_folder, exist_ok=True)
            except FileExistsError:
                # This is fine, the directory already exists
                pass
                
            shutil.move(source_path, dest_path)
            return (file_name, group_folder_name, True)
        except (OSError, shutil.Error) as e:
            return (file_name, group_folder_name, f"Error: {str(e)}")
    
    return (file_name, group_folder_name, "Skipped (dry run)" if dry_run else "No action needed")

def create_group_name_from_files(files: List[str]) -> str:
    """Generate a descriptive group name from a list of files."""
    if not files:
        return "Miscellaneous"
        
    # Extract common words/patterns
    common_parts = []
    for file in files:
        base_name = os.path.splitext(file)[0]
        # Remove numbers and special chars
        cleaned = re.sub(r'[\d_\-\s()]+', ' ', base_name)
        parts = cleaned.split()
        common_parts.extend(parts)
    
    # Count occurrences
    word_counts = defaultdict(int)
    for word in common_parts:
        if len(word) >= 3:
            word_counts[word.lower()] += 1
    
    if not word_counts:
        return os.path.splitext(min(files))[0][:30]
    
    # Get most common words
    common_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Use top words for the group name (limit to 3)
    name_parts = [word.title() for word, _ in common_words[:3]]
    group_name = "_".join(name_parts)
    
    return group_name[:50]  # Limit length

def group_files_by_similarity(
    folder_path: str, 
    min_pattern_length: int = 3,
    similarity_threshold: float = 0.7,
    max_groups: int = 50,
    min_files_per_group: int = 2,
    dry_run: bool = False,
    verbose: bool = False
):
    """
    Organize files into folders based on filename similarities.
    
    Args:
        folder_path: Path to the folder containing files to organize
        min_pattern_length: Minimum length of patterns to consider
        similarity_threshold: Threshold for considering files similar
        max_groups: Maximum number of groups to create
        min_files_per_group: Minimum files required to form a group
        dry_run: If True, only show what would be done without making changes
        verbose: Whether to print detailed logging information
    """
    setup_logging(verbose)
    
    if not os.path.exists(folder_path):
        logging.error(f"Error: Folder '{folder_path}' does not exist!")
        return
    
    # Get all file names in the folder (excluding subfolders)
    file_names = [f for f in os.listdir(folder_path) 
                 if os.path.isfile(os.path.join(folder_path, f))]
    
    if not file_names:
        logging.warning(f"No files found in '{folder_path}'")
        return
    
    logging.info(f"Found {len(file_names)} files to organize")
    
    # Find similar files based on filename
    logging.info("Finding similar files...")
    similarity_groups = find_similar_files(file_names, similarity_threshold)
    
    # Find common patterns for remaining files
    processed_files = set()
    for group_files in similarity_groups.values():
        processed_files.update(group_files)
    
    remaining_files = [f for f in file_names if f not in processed_files]
    
    if remaining_files:
        logging.info(f"Finding patterns in {len(remaining_files)} remaining files...")
        patterns = extract_common_patterns(remaining_files, min_pattern_length)
        
        # Apply patterns to remaining files
        pattern_groups = defaultdict(list)
        remaining_processed = set()
        
        for pattern, _ in patterns[:max_groups]:
            for file in remaining_files:
                if file in remaining_processed:
                    continue
                if pattern in file.lower():
                    sanitized_pattern = sanitize_folder_name(pattern)
                    if sanitized_pattern:
                        pattern_groups[sanitized_pattern].append(file)
                        remaining_processed.add(file)
        
        # Keep only groups with enough files
        pattern_groups = {k: v for k, v in pattern_groups.items() 
                         if len(v) >= min_files_per_group}
        
        # Add pattern groups to similarity groups
        for pattern, files in pattern_groups.items():
            if files:
                similarity_groups[pattern] = files
    
    # Create better group names for groups based on representative files
    final_groups = {}
    for key, files in similarity_groups.items():
        if len(files) >= min_files_per_group:
            # Use the key as the folder name if it's a pattern, otherwise create name from files
            if key in file_names:
                # This is a similarity-based group, create a descriptive name
                group_name = sanitize_folder_name(create_group_name_from_files(files))
            else:
                # This is a pattern-based group, use the sanitized pattern
                group_name = sanitize_folder_name(key)
                
            final_groups[group_name] = files
    
    # Assign remaining files to Miscellaneous
    all_grouped_files = set()
    for files in final_groups.values():
        all_grouped_files.update(files)
    
    misc_files = [f for f in file_names if f not in all_grouped_files]
    if misc_files:
        final_groups["Miscellaneous"] = misc_files
        
    group_counters = defaultdict(int)
    unique_groups = {}
    
    # Display the grouping plan
    print("\nProposed file grouping:")
    for group_name, files in sorted(final_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n{group_name} ({len(files)} files)")
        print(f"  Example files: {', '.join(files[:3])}")
        base_group_name = group_name
        group_counters[base_group_name] += 1
        
        # If we have a duplicate group name, add a number
        if group_counters[base_group_name] > 1:
            group_name = f"{base_group_name} {group_counters[base_group_name]}"
            
        unique_groups[group_name] = files
    
    print("\nProposed file grouping:")
    for group_name, files in sorted(unique_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n{group_name} ({len(files)} files)")
        print(f"  Example files: {', '.join(files[:3])}")
    
    # Create all group directories first to avoid race conditions
    # if not dry_run:
    #     print("\nCreating group directories...")
    #     for group_name in final_groups.keys():
    #         group_folder = os.path.join(folder_path, group_name)
    #         try:
    #             os.makedirs(group_folder, exist_ok=True)
    #         except Exception as e:
    #             logging.error(f"Error creating directory '{group_name}': {str(e)}")
    if not dry_run:
        print("\nCreating group directories...")
        for group_name in unique_groups.keys():
            group_folder = os.path.join(folder_path, group_name)
            try:
                os.makedirs(group_folder, exist_ok=True)
            except Exception as e:
                logging.error(f"Error creating directory '{group_name}': {str(e)}")
    
    # Process files
    if not dry_run:
        print("\nOrganizing files...")
    
    with tqdm(total=len(file_names), disable=not verbose) as pbar:
        # Process files in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            file_infos = []
            for group_name, files in final_groups.items():
                for file in files:
                    file_infos.append((file, group_name))
            
            futures = []
            for file_info in file_infos:
                future = executor.submit(
                    process_file, file_info, folder_path, dry_run
                )
                futures.append(future)
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                file_name, group, status = future.result()
                if verbose:
                    logging.info(f"Processed: {file_name} → {group}/ ({status})")
                pbar.update(1)
    
    # Summary
    print("\n✅ Organization " + ("simulation" if dry_run else "process") + " complete!")
    print(f"Created {len(final_groups) - (1 if 'Miscellaneous' in final_groups else 0)} groups")
    if "Miscellaneous" in final_groups:
        print(f"{len(final_groups['Miscellaneous'])} files placed in 'Miscellaneous'")
    
    if dry_run:
        print("\nThis was a dry run. No files were actually moved.")
        print("Run without --dry-run to apply the changes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organize files into groups based on filename similarities")
    parser.add_argument("folder", help="Folder path to organize")
    parser.add_argument("--min-length", type=int, default=3, help="Minimum pattern length to consider")
    parser.add_argument("--similarity", type=float, default=0.7, help="Similarity threshold (0.0-1.0)")
    parser.add_argument("--max-groups", type=int, default=50, help="Maximum number of groups to create")
    parser.add_argument("--min-files", type=int, default=2, help="Minimum files required to form a group")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    try:
        group_files_by_similarity(
            args.folder,
            min_pattern_length=args.min_length,
            similarity_threshold=args.similarity,
            max_groups=args.max_groups,
            min_files_per_group=args.min_files,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()