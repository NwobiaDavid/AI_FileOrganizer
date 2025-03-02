import os
import shutil

def gather_files(folder_path):
    """Move all files from subfolders to the root folder and delete empty subfolders."""
    if not os.path.exists(folder_path):
        print("Error: Folder does not exist!")
        return

    # Iterate through subdirectories
    for subfolder in os.listdir(folder_path):
        subfolder_path = os.path.join(folder_path, subfolder)
        
        if os.path.isdir(subfolder_path):
            for file_name in os.listdir(subfolder_path):
                file_path = os.path.join(subfolder_path, file_name)
                if os.path.isfile(file_path):
                    shutil.move(file_path, os.path.join(folder_path, file_name))
                    print(f"Moved: {file_name} → {folder_path}/")
            
            # Remove subfolder if empty
            if not os.listdir(subfolder_path):
                os.rmdir(subfolder_path)
                print(f"Deleted empty folder: {subfolder_path}")

if __name__ == "__main__":
    folder_to_gather = input("Enter the folder path to gather files: ")
    gather_files(folder_to_gather)
    print("✅ Files gathered successfully!")
