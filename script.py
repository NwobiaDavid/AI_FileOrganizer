import os
import shutil
import mimetypes

# Define categories and file extensions
FILE_CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"],
    "Videos": [".mp4", ".mkv", ".flv", ".avi", ".mov"],
    "Documents": [".pdf", ".docx", ".txt", ".xlsx", ".pptx"],
    "Audio": [".mp3", ".wav", ".aac", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Code": [".py", ".js", ".html", ".css", ".java", ".cpp"]
}

def get_file_category(file_name):
    """Determine file category based on extension."""
    ext = os.path.splitext(file_name)[1].lower()
    for category, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return category
    return "Others"  # Default category if no match

def organize_folder(folder_path):
    """Organize files into categorized subfolders."""
    if not os.path.exists(folder_path):
        print("Error: Folder does not exist!")
        return

    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)

        if os.path.isfile(file_path):  # Ignore directories
            category = get_file_category(file_name)
            category_path = os.path.join(folder_path, category)

            # Create category folder if not exists
            os.makedirs(category_path, exist_ok=True)

            # Move file to its category folder
            shutil.move(file_path, os.path.join(category_path, file_name))
            print(f"Moved: {file_name} → {category}/")

if __name__ == "__main__":
    folder_to_organize = input("Enter the folder path to organize: ")
    organize_folder(folder_to_organize)
    print("✅ Folder organization complete!")
