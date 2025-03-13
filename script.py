import os
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import io
import sys
from contextlib import redirect_stdout

# Import the functionality from your existing script
# Assuming the code you provided is saved as file_organizer.py
# If it's in the same file, you can directly call the function

# Import your file organization function or copy it directly
# From the code you shared, I'm using the main function:
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
    verbose: bool = False,
    output_callback=None
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
        output_callback: Function to call with output strings for GUI display
    """
    # Custom print function to redirect output to GUI
    def print_output(text):
        if output_callback:
            output_callback(text + "\n")
        else:
            print(text)
    
    setup_logging(verbose)
    
    if not os.path.exists(folder_path):
        error_msg = f"Error: Folder '{folder_path}' does not exist!"
        print_output(error_msg)
        logging.error(error_msg)
        return
    
    # Get all file names in the folder (excluding subfolders)
    file_names = [f for f in os.listdir(folder_path) 
                 if os.path.isfile(os.path.join(folder_path, f))]
    
    if not file_names:
        warning_msg = f"No files found in '{folder_path}'"
        print_output(warning_msg)
        logging.warning(warning_msg)
        return
    
    print_output(f"Found {len(file_names)} files to organize")
    logging.info(f"Found {len(file_names)} files to organize")
    
    # Find similar files based on filename
    print_output("Finding similar files...")
    logging.info("Finding similar files...")
    similarity_groups = find_similar_files(file_names, similarity_threshold)
    
    # Find common patterns for remaining files
    processed_files = set()
    for group_files in similarity_groups.values():
        processed_files.update(group_files)
    
    remaining_files = [f for f in file_names if f not in processed_files]
    
    if remaining_files:
        print_output(f"Finding patterns in {len(remaining_files)} remaining files...")
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
    print_output("\nProposed file grouping:")
    for group_name, files in sorted(final_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print_output(f"\n{group_name} ({len(files)} files)")
        print_output(f"  Example files: {', '.join(files[:3])}")
        base_group_name = group_name
        group_counters[base_group_name] += 1
        
        # If we have a duplicate group name, add a number
        if group_counters[base_group_name] > 1:
            group_name = f"{base_group_name} {group_counters[base_group_name]}"
            
        unique_groups[group_name] = files
    
    print_output("\nProposed file grouping:")
    for group_name, files in sorted(unique_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print_output(f"\n{group_name} ({len(files)} files)")
        print_output(f"  Example files: {', '.join(files[:3])}")
    
    # Create all group directories first to avoid race conditions
    if not dry_run:
        print_output("\nCreating group directories...")
        for group_name in unique_groups.keys():
            group_folder = os.path.join(folder_path, group_name)
            try:
                os.makedirs(group_folder, exist_ok=True)
            except Exception as e:
                error_msg = f"Error creating directory '{group_name}': {str(e)}"
                print_output(error_msg)
                logging.error(error_msg)
    
    # Process files
    if not dry_run:
        print_output("\nOrganizing files...")
    
    # Custom tqdm-like progress tracking for GUI
    total_files = len(file_names)
    processed_count = 0
    
    # Process files
    file_infos = []
    for group_name, files in unique_groups.items():
        for file in files:
            file_infos.append((file, group_name))
    
    for file_info in file_infos:
        file_name, group_name = file_info
        file_name, group, status = process_file(file_info, folder_path, dry_run)
        
        processed_count += 1
        if verbose:
            log_msg = f"Processed: {file_name} → {group}/ ({status})"
            print_output(log_msg)
            logging.info(log_msg)
        
        # Update progress every 10 files or at the end
        if processed_count % 10 == 0 or processed_count == total_files:
            print_output(f"Progress: {processed_count}/{total_files} files")
    
    # Summary
    print_output("\n✅ Organization " + ("simulation" if dry_run else "process") + " complete!")
    print_output(f"Created {len(final_groups) - (1 if 'Miscellaneous' in final_groups else 0)} groups")
    if "Miscellaneous" in final_groups:
        print_output(f"{len(final_groups['Miscellaneous'])} files placed in 'Miscellaneous'")
    
    if dry_run:
        print_output("\nThis was a dry run. No files were actually moved.")
        print_output("Run without --dry-run to apply the changes.")

# Create a custom logger that redirects to our text widget
class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""

    def write(self, string):
        self.buffer += string
        if '\n' in string:
            self.text_widget.insert(tk.END, self.buffer)
            self.text_widget.see(tk.END)
            self.buffer = ""

    def flush(self):
        if self.buffer:
            self.text_widget.insert(tk.END, self.buffer)
            self.text_widget.see(tk.END)
            self.buffer = ""
            

class FileOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Organizer")
        self.root.geometry("800x700")
        
        # Create a style
        self.style = ttk.Style()
        self.style.configure("TButton", padding=6, relief="flat")
        self.style.configure("TLabel", padding=6)
        self.style.configure("TFrame", padding=10)
        
        # Create the main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Directory selection
        dir_frame = ttk.Frame(main_frame)
        dir_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(dir_frame, text="Directory to Organize:").pack(side=tk.LEFT)
        
        self.dir_entry = ttk.Entry(dir_frame, width=50)
        self.dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        browse_btn = ttk.Button(dir_frame, text="Browse", command=self.browse_directory)
        browse_btn.pack(side=tk.LEFT)
        
        # Parameters frame
        params_frame = ttk.LabelFrame(main_frame, text="Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=10)
        
        # Parameters grid
        params_grid = ttk.Frame(params_frame)
        params_grid.pack(fill=tk.X)
        
        # Similarity threshold
        ttk.Label(params_grid, text="Similarity Threshold:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.similarity_var = tk.DoubleVar(value=0.7)
        similarity_scale = ttk.Scale(params_grid, from_=0.1, to=1.0, 
                                     variable=self.similarity_var, 
                                     orient=tk.HORIZONTAL, length=200)
        similarity_scale.grid(row=0, column=1, sticky=tk.W, pady=2)
        similarity_label = ttk.Label(params_grid, textvariable=tk.StringVar(value="0.7"))
        similarity_scale.configure(command=lambda val: similarity_label.configure(text=f"{float(val):.1f}"))
        similarity_label.grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # Min pattern length
        ttk.Label(params_grid, text="Min Pattern Length:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.min_length_var = tk.IntVar(value=3)
        ttk.Spinbox(params_grid, from_=1, to=10, textvariable=self.min_length_var, width=5).grid(
            row=1, column=1, sticky=tk.W, pady=2)
        
        # Max groups
        ttk.Label(params_grid, text="Max Groups:").grid(row=1, column=3, sticky=tk.W, pady=2)
        self.max_groups_var = tk.IntVar(value=50)
        ttk.Spinbox(params_grid, from_=1, to=100, textvariable=self.max_groups_var, width=5).grid(
            row=1, column=4, sticky=tk.W, pady=2)
        
        # Min files per group
        ttk.Label(params_grid, text="Min Files Per Group:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.min_files_var = tk.IntVar(value=2)
        ttk.Spinbox(params_grid, from_=1, to=10, textvariable=self.min_files_var, width=5).grid(
            row=2, column=1, sticky=tk.W, pady=2)
        
        # Dry run option
        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(params_grid, text="Dry Run (Preview Only)", variable=self.dry_run_var).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Verbose option
        self.verbose_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(params_grid, text="Verbose Output", variable=self.verbose_var).grid(
            row=3, column=3, columnspan=2, sticky=tk.W, pady=5)
        
        # Action buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        analyze_btn = ttk.Button(btn_frame, text="Analyze Files", command=self.run_analysis)
        analyze_btn.pack(side=tk.LEFT, padx=5)
        
        organize_btn = ttk.Button(btn_frame, text="Organize Files", command=self.run_organization)
        organize_btn.pack(side=tk.LEFT, padx=5)
        
        flatten_btn = ttk.Button(btn_frame, text="Flatten Directory", command=self.run_flatten)
        flatten_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = ttk.Button(btn_frame, text="Clear Output", command=self.clear_output)
        clear_btn.pack(side=tk.RIGHT, padx=5)
        
        # Output area
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding=10)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=20)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Set a default directory if available
        default_dir = os.path.expanduser("~/Downloads")
        if os.path.exists(default_dir):
            self.dir_entry.insert(0, default_dir)
    
    def browse_directory(self):
        """Open a file dialog to select a directory."""
        directory = filedialog.askdirectory(initialdir=self.dir_entry.get() or os.path.expanduser("~"))
        if directory:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, directory)
    
    def add_to_output(self, text):
        """Add text to the output area."""
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)
        self.output_text.update_idletasks()
    
    def clear_output(self):
        """Clear the output area."""
        self.output_text.delete(1.0, tk.END)
    
    def update_status(self, message):
        """Update the status bar message."""
        self.status_var.set(message)
        self.root.update_idletasks()
    
    def run_task(self, task_func, is_dry_run):
        """Run the file organization in a separate thread."""
        directory = self.dir_entry.get()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("Error", "Please select a valid directory.")
            return
        
        # If not is_dry_run, confirm before proceeding
        if not is_dry_run:
            if not messagebox.askyesno("Confirm", 
                "This will actually move files in your directory. Are you sure you want to proceed?"):
                return
        
        # Clear output
        self.clear_output()
        
        # Redirect stdout to our output widget
        original_stdout = sys.stdout
        sys.stdout = TextRedirector(self.output_text)
        
        # Update status
        self.update_status("Running..." + (" (Dry Run)" if is_dry_run else ""))
        
        try:
            # Run the task function
            task_func(
                directory,
                dry_run=is_dry_run,
                verbose=self.verbose_var.get(),
                output_callback=self.add_to_output
            )
            self.update_status("Completed" + (" (Dry Run)" if is_dry_run else ""))
        except Exception as e:
            self.add_to_output(f"ERROR: {str(e)}\n")
            import traceback
            self.add_to_output(traceback.format_exc())
            self.update_status("Error occurred")
        finally:
            # Restore stdout
            sys.stdout = original_stdout
    
    def run_analysis(self):
        """Run a dry-run analysis."""
        threading.Thread(target=self.run_task, args=(group_files_by_similarity, True), daemon=True).start()
    
    def run_organization(self):
        """Run the actual organization."""
        threading.Thread(target=self.run_task, args=(group_files_by_similarity, False), daemon=True).start()
    
    def run_flatten(self):
        """Run the flatten directory operation."""
        threading.Thread(target=self.run_task, args=(flatten_directory, self.dry_run_var.get()), daemon=True).start()

# Run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = FileOrganizerApp(root)
    root.mainloop()