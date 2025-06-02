import argparse
import json
import os
import shutil
import time
import re
import hashlib
from datetime import datetime, timedelta
import subprocess

# --- Constants for Metadata ---
METADATA_FILE = ".superhxpro_metadata.json"

# --- Helper Functions ---

def _normalize_path(path):
    """
    Normalizes a path to ensure it's absolute and handles current directory '.' correctly.
    This helps in consistently identifying folder paths for metadata.
    """
    if path == "" or path == ".":
        return os.getcwd()
    return os.path.abspath(path)

def _load_metadata(folder_path):
    """
    Loads metadata from a hidden JSON file in the specified folder.
    Returns an empty dictionary if the file doesn't exist or is corrupted.
    """
    normalized_folder_path = _normalize_path(folder_path)
    metadata_path = os.path.join(normalized_folder_path, METADATA_FILE)
    
    if not os.path.exists(metadata_path):
        return {}

    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
            else:
                print(f"[WARNING] Metadata file '{metadata_path}' is empty. Returning empty dict.")
                # If the file is empty, it should be deleted on next save if metadata remains empty.
                return {}
    except json.JSONDecodeError:
        print(f"[ERROR] Metadata file '{metadata_path}' is corrupted. Returning empty dict and attempting to back up/reset.")
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copy2(metadata_path, f"{metadata_path}.corrupted_{timestamp}.bak")
            print(f"[INFO] Backed up corrupted metadata file to '{metadata_path}.corrupted_{timestamp}.bak'")
        except Exception as e:
            print(f"[ERROR] Failed to back up corrupted metadata file: {e}")
        return {}
    except IOError as e:
        print(f"[ERROR] Reading metadata from '{metadata_path}': {e}")
        return {}
    except Exception as e:
        print(f"[ERROR] Unexpected error loading metadata from '{metadata_path}': {e}")
        return {}
    
def _save_metadata(folder_path, metadata):
    """
    Saves metadata to a hidden JSON file in the specified folder.
    Ensures the target directory exists before saving.
    IMPORTANT: Only saves the file if 'metadata' is not empty.
               Deletes the file if 'metadata' is empty and the file exists.
    """
    normalized_folder_path = _normalize_path(folder_path)
    metadata_path = os.path.join(normalized_folder_path, METADATA_FILE)

    if not metadata: # Check if the dictionary is empty (e.g., {})
        if os.path.exists(metadata_path): # If it's empty, and the file exists, delete it
            try:
                os.remove(metadata_path)
                print(f"[INFO] Deleted empty metadata file: '{metadata_path}'.")
            except OSError as e:
                print(f"[ERROR] Failed to delete empty metadata file '{metadata_path}': {e}")
        return # In either case (empty metadata, no file, or just deleted file), we're done.

    # If metadata is NOT empty, proceed to save it
    try:
        os.makedirs(normalized_folder_path, exist_ok=True) # Use normalized path here
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4)
        # print(f"[INFO] Metadata successfully saved to '{metadata_path}'.") 
    except PermissionError:
        print(f"Error: Permission denied. Cannot save metadata to '{metadata_path}'.")
    except IOError as e:
        print(f"Error saving metadata to '{metadata_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving metadata to '{metadata_path}': {e}")

def folder_mood_get(folder, recursive=False, mood_filter_name=None):
    """
    Gets the emotional label for a specific folder, or recursively scans folders
    to find those matching a specified mood name.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    # Handle single folder check (non-recursive, no filter)
    if not recursive and mood_filter_name is None:
        metadata = _load_metadata(folder)
        if "__folder__" in metadata and "mood" in metadata["__folder__"]:
            mood_info = metadata["__folder__"]["mood"]
            mood_value = mood_info.get("value", "N/A")
            print(f"{folder} - {mood_value}")
        else:
            print(f"No mood set for folder '{folder}'.")
        return

    # Handle recursive or filtered scan
    found_matches = False

    for root, dirs, files in os.walk(folder):
        current_folder_path = root

        # Filter out the metadata file itself from traversal if it's treated as a file by os.walk (though it shouldn't be)
        if METADATA_FILE in files:
            files.remove(METADATA_FILE) 
        
        # Filter out the metadata file from subdirectories if it somehow gets listed as one
        # This is primarily for robust `os.walk` behavior, less common for actual dirs.
        if METADATA_FILE.strip('.') in dirs:
            dirs.remove(METADATA_FILE.strip('.'))


        try:
            metadata = _load_metadata(current_folder_path)

            # Check if the folder has a mood and matches the filter
            if "__folder__" in metadata and "mood" in metadata["__folder__"]:
                mood_info = metadata["__folder__"]["mood"]
                mood_value = mood_info.get("value", "N/A")
                mood_name = mood_info.get("name", "N/A")

                filter_lower = mood_filter_name.lower() if mood_filter_name else None

                if filter_lower is None or \
                   (mood_value and filter_lower in mood_value.lower()) or \
                   (mood_name and filter_lower in mood_name.lower()):
                    print(f"{current_folder_path} - {mood_value}")
                    found_matches = True

        except Exception as e:
            # print(f"Warning: Error processing metadata for '{current_folder_path}': {e}") 
            pass # Suppress errors for clean output

    if not found_matches:
        print("No matching moods found for the specified criteria.")


def get_file_hash(filepath, hash_algo=hashlib.sha256, chunk_size=65536):
    """Calculates the SHA256 hash of a file."""
    hasher = hash_algo()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except IOError as e:
        print(f"Error reading file '{filepath}' for hashing: {e}")
        return None

def _is_file_older_than(filepath, days):
    """Checks if a file is older than a given number of days."""
    try:
        stat = os.stat(filepath)
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        return datetime.now() - mod_time > timedelta(days=days)
    except OSError as e:
        print(f"Error accessing file '{filepath}': {e}")
        return False

def _get_file_size(filepath):
    """Returns the size of a file in bytes."""
    try:
        return os.stat(filepath).st_size
    except OSError as e:
        print(f"Error accessing file '{filepath}': {e}")
        return 0

# --- Core SuperHelperXPro Commands ---

def visualize_folder(folder, max_depth, current_depth=0, prefix=""):
    """
    Recursively visualizes the folder structure.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    if current_depth > max_depth:
        return

    try:
        items = os.listdir(folder)
        # Filter out the metadata file itself from the listing
        items = [item for item in items if item != METADATA_FILE]
        
        # Sort items: directories first, then files, alphabetically
        items.sort(key=lambda x: (not os.path.isdir(os.path.join(folder, x)), x.lower()))

        for i, item in enumerate(items):
            path = os.path.join(folder, item)
            connector = "├── " if i < len(items) - 1 else "└── "
            item_type = "(Dir)" if os.path.isdir(path) else "(File)"
            print(f"{prefix}{connector}{item} {item_type}")

            if os.path.isdir(path):
                extension = "│   " if i < len(items) - 1 else "    "
                visualize_folder(path, max_depth, current_depth + 1, prefix + extension)
    except OSError as e:
        print(f"Error accessing folder '{folder}': {e}")

def batch_rename(folder, regex_pattern, replacement, recursive):
    """
    Renames many files at once using regex.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Starting batch rename in '{folder}' (recursive: {recursive})...")
    renamed_count = 0

    for root, _, files in os.walk(folder):
        if not recursive and root != folder:
            continue

        # Filter out the metadata file from processing
        files_to_process = [f for f in files if f != METADATA_FILE]

        for filename in files_to_process:
            try:
                original_path = os.path.join(root, filename)
                new_filename = re.sub(regex_pattern, replacement, filename)

                if new_filename != filename:
                    new_path = os.path.join(root, new_filename)
                    if os.path.exists(new_path):
                        print(f"  Skipping '{original_path}': Target '{new_path}' already exists.")
                        continue
                    os.rename(original_path, new_path)
                    print(f"  Renamed: '{filename}' -> '{new_filename}'")
                    renamed_count += 1
            except re.error as e:
                print(f"Error with regex pattern '{regex_pattern}': {e}")
                return
            except OSError as e:
                print(f"Error renaming '{filename}': {e}")

    print(f"Finished. Total files renamed: {renamed_count}")

def deep_clone(src, dest):
    """
    Copies a whole folder and its contents.
    """
    if not os.path.isdir(src):
        print(f"Error: Source folder '{src}' not found.")
        return
    if os.path.exists(dest):
        print(f"Error: Destination '{dest}' already exists. Please remove it first or choose a different name.")
        return

    print(f"Deep cloning '{src}' to '{dest}'...")
    try:
        shutil.copytree(src, dest)
        # After cloning, clean up any empty metadata files that might have been copied
        for root, dirs, files in os.walk(dest):
            # Ensure proper folder path for _load_metadata for newly cloned directories
            normalized_root = _normalize_path(root)
            metadata_path = os.path.join(normalized_root, METADATA_FILE)

            if os.path.exists(metadata_path):
                metadata = _load_metadata(normalized_root)
                if not metadata: # If the loaded metadata is empty, delete the file
                    try:
                        os.remove(metadata_path)
                        print(f"[INFO] Deleted empty metadata file in cloned folder: '{metadata_path}'.")
                    except OSError as e:
                        print(f"[ERROR] Failed to delete empty metadata file in cloned folder '{metadata_path}': {e}")

        print("Clone successful!")
    except Exception as e:
        print(f"An error occurred during cloning: {e}")

def conditional_move_copy(src, dest, condition_type, value, is_copy):
    """
    Moves or copies files based on rules (e.g., age, size).
    """
    if not os.path.isdir(src):
        print(f"Error: Source folder '{src}' not found.")
        return
    if not os.path.exists(dest):
        try:
            os.makedirs(dest)
        except OSError as e:
            print(f"Error creating destination folder '{dest}': {e}")
            return

    action = "copying" if is_copy else "moving"
    print(f"{action.capitalize()} files from '{src}' to '{dest}' based on condition '{condition_type}' with value '{value}'...")
    processed_count = 0

    for filename in os.listdir(src):
        filepath = os.path.join(src, filename)
        if not os.path.isfile(filepath) or filename == METADATA_FILE: # Skip metadata file
            continue

        perform_action = False
        try:
            if condition_type.lower() == "agedays":
                if _is_file_older_than(filepath, int(value)):
                    perform_action = True
            elif condition_type.lower() == "sizegt": # Size Greater Than (bytes)
                if _get_file_size(filepath) > int(value):
                    perform_action = True
            elif condition_type.lower() == "sizelt": # Size Less Than (bytes)
                if _get_file_size(filepath) < int(value):
                    perform_action = True
            else:
                print(f"Warning: Unknown condition type '{condition_type}'. Skipping file '{filename}'.")
                continue

            if perform_action:
                dest_path = os.path.join(dest, filename)
                if os.path.exists(dest_path):
                    print(f"  Skipping '{filename}': Target '{dest_path}' already exists.")
                    continue

                if is_copy:
                    shutil.copy2(filepath, dest_path)
                    print(f"  Copied: '{filename}' to '{dest}'")
                else:
                    # When moving, also consider moving/updating metadata if relevant
                    # Ensure folder paths are normalized for _load_metadata and _save_metadata
                    normalized_src = _normalize_path(src)
                    normalized_dest = _normalize_path(dest)

                    src_metadata = _load_metadata(normalized_src)
                    dest_metadata = _load_metadata(normalized_dest)
                    
                    if filename in src_metadata:
                        dest_metadata[filename] = src_metadata.pop(filename) # Move metadata entry
                        _save_metadata(normalized_src, src_metadata) # Save changes to src metadata (might delete if empty)
                    
                    shutil.move(filepath, dest_path)
                    _save_metadata(normalized_dest, dest_metadata) # Save changes to dest metadata (might create/update)
                    print(f"  Moved: '{filename}' to '{dest}'")
                processed_count += 1
        except ValueError:
            print(f"Error: Invalid value '{value}' for condition type '{condition_type}'.")
            return
        except OSError as e:
            print(f"Error {action}ing file '{filename}': {e}")

    print(f"Finished. Total files {action}ed: {processed_count}")

def auto_cleanup(folder, criteria, value):
    """
    Deletes old or unwanted files based on criteria.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Cleaning up '{folder}' based on criteria '{criteria}' with value '{value}'...")
    deleted_count = 0

    for root, _, files in os.walk(folder):
        normalized_root = _normalize_path(root) # Normalize root for metadata operations
        metadata = _load_metadata(normalized_root)
        
        # Make a copy of files list to allow modification during iteration if a file is deleted
        for filename in list(files): 
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath) or filename == METADATA_FILE:
                continue

            perform_delete = False
            try:
                if criteria.lower() == "agedays":
                    if _is_file_older_than(filepath, int(value)):
                        perform_delete = True
                elif criteria.lower() == "emptyfile":
                    if _get_file_size(filepath) == 0:
                        perform_delete = True
                else:
                    print(f"Warning: Unknown cleanup criteria '{criteria}'. Skipping file '{filename}'.")
                    continue

                if perform_delete:
                    os.remove(filepath)
                    print(f"  Deleted: '{filepath}'")
                    deleted_count += 1
                    # Also remove its metadata entry if it exists
                    if filename in metadata:
                        del metadata[filename]
                        _save_metadata(normalized_root, metadata) # Save updated metadata (might delete if empty)
            except ValueError:
                print(f"Error: Invalid value '{value}' for criteria '{criteria}'.")
                return
            except OSError as e:
                print(f"Error deleting '{filepath}': {e}")

    print(f"Finished. Total files deleted: {deleted_count}")

def deduplicate(folder, dry_run):
    """
    Finds and removes duplicate files using SHA256 hashes.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Searching for duplicate files in '{folder}' (dry run: {dry_run})...")
    hashes = {}
    duplicates_found = 0
    deleted_count = 0

    for root, _, files in os.walk(folder):
        normalized_root = _normalize_path(root) # Normalize root for metadata operations
        current_folder_metadata = _load_metadata(normalized_root)
        
        # Create a list of files to iterate, excluding metadata file
        files_to_process = [f for f in files if f != METADATA_FILE]

        for filename in files_to_process:
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath):
                continue

            file_hash = get_file_hash(filepath)
            if file_hash:
                if file_hash in hashes:
                    duplicates_found += 1
                    print(f"  Duplicate found: '{filepath}' (original: '{hashes[file_hash]}')")
                    if not dry_run:
                        try:
                            os.remove(filepath)
                            print(f"    Deleted: '{filepath}'")
                            deleted_count += 1
                            # Remove metadata entry for the deleted duplicate
                            if filename in current_folder_metadata:
                                del current_folder_metadata[filename]
                                _save_metadata(normalized_root, current_folder_metadata) # Save updated metadata (might delete if empty)
                        except OSError as e:
                            print(f"    Error deleting duplicate '{filepath}': {e}")
                else:
                    hashes[file_hash] = filepath
    
    print(f"Finished. Found {duplicates_found} duplicate(s). {'Deleted' if not dry_run else 'Would delete'} {deleted_count} file(s).")


def tag_file(file_path, add_tags_str, remove_tags_str, recursive):
    """
    Adds or removes tags on files. Tags are stored in a hidden JSON metadata file.
    """
    if not os.path.exists(file_path):
        print(f"Error: Path '{file_path}' not found.")
        return

    if os.path.isfile(file_path):
        target_paths = [file_path]
    elif os.path.isdir(file_path):
        if recursive:
            target_paths = [os.path.join(r, f) for r, _, files in os.walk(file_path) for f in files if f != METADATA_FILE]
        else:
            target_paths = [os.path.join(file_path, f) for f in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, f)) and f != METADATA_FILE]
    else:
        print(f"Error: '{file_path}' is neither a file nor a directory.")
        return

    add_tags = {tag.strip() for tag in add_tags_str.split(',') if tag.strip()}
    remove_tags = {tag.strip() for tag in remove_tags_str.split(',') if tag.strip()}

    processed_count = 0
    for path in target_paths:
        if not os.path.isfile(path) or os.path.basename(path) == METADATA_FILE:
            continue

        # Correctly determine the folder for metadata, handling current directory
        folder = os.path.dirname(path)
        if folder == "": # If file is in current directory, dirname returns ""
            folder = "." # Represent current directory as '.'
        
        normalized_folder = _normalize_path(folder) # Normalize for consistency
        metadata = _load_metadata(normalized_folder)
        
        file_key = os.path.basename(path)
        
        # Initialize tags if not present
        if file_key not in metadata:
            metadata[file_key] = {"tags": []}
        elif "tags" not in metadata[file_key]:
            metadata[file_key]["tags"] = []
        
        current_tags = set(metadata[file_key]["tags"])
        
        updated_tags = (current_tags.union(add_tags)).difference(remove_tags)
        
        # Only save if there's a real change to avoid unnecessary writes
        if updated_tags != current_tags:
            metadata[file_key]["tags"] = sorted(list(updated_tags))
            _save_metadata(normalized_folder, metadata) # Pass the corrected/normalized folder
            print(f"  Updated tags for '{path}': {', '.join(metadata[file_key]['tags']) if metadata[file_key]['tags'] else '[No tags]'}")
            processed_count += 1
        else:
            print(f"  No tag changes for '{path}'. Current tags: {', '.join(current_tags) if current_tags else '[No tags]'}")

    print(f"Finished tagging. Processed {processed_count} file(s).")


def search_tag(folder, tag):
    """
    Finds files with a specific tag.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Searching for files with tag '{tag}' in '{folder}'...")
    found_count = 0

    for root, _, files in os.walk(folder):
        normalized_root = _normalize_path(root) # Normalize root for metadata operations
        metadata = _load_metadata(normalized_root)
        for filename in files:
            if filename == METADATA_FILE:
                continue
            
            file_key = filename
            if file_key in metadata and "tags" in metadata[file_key]:
                if tag in metadata[file_key]["tags"]: # This looks for an exact tag match
                    print(f"  Found: {os.path.join(root, filename)} (Tags: {', '.join(metadata[file_key]['tags'])})")
                    found_count += 1
    print(f"Finished. Found {found_count} file(s) with tag '{tag}'.")

def search_meta(folder, json_query_str):
    """
    Finds files by size, date, type, using extended metadata.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    try:
        query = json.loads(json_query_str)
    except json.JSONDecodeError:
        print("Error: Invalid JSON query for search-meta.")
        return

    print(f"Searching for files in '{folder}' with metadata query: {json.dumps(query, indent=2)}...")
    found_count = 0

    for root, _, files in os.walk(folder):
        normalized_root = _normalize_path(root) # Normalize root for metadata operations
        metadata_from_file = _load_metadata(normalized_root)
        
        for filename in files:
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath) or filename == METADATA_FILE:
                continue

            try:
                stat = os.stat(filepath)
                file_size = stat.st_size
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                file_type = os.path.splitext(filename)[1].lstrip('.').lower()

                # Combine stat info with stored metadata
                file_metadata = {
                    "name": filename,
                    "path": filepath,
                    "size": file_size,
                    "type": file_type,
                    "last_modified": mod_time.isoformat(),
                    "tags": metadata_from_file.get(filename, {}).get("tags", []),
                    "mood": metadata_from_file.get(filename, {}).get("mood", {}).get("value"),
                    "mood_name": metadata_from_file.get(filename, {}).get("mood", {}).get("name")
                }

                # Evaluate conditions
                match = True
                if "type" in query and file_metadata["type"] != query["type"].lower():
                    match = False
                
                if "size" in query:
                    if "gt" in query["size"] and not (file_size > query["size"]["gt"]):
                        match = False
                    if "lt" in query["size"] and not (file_size < query["size"]["lt"]):
                        match = False
                
                if "ageDays" in query:
                    required_age = int(query["ageDays"])
                    if not _is_file_older_than(filepath, required_age):
                        match = False

                if "tags" in query:
                    if isinstance(query["tags"], list):
                        if not all(tag in file_metadata["tags"] for tag in query["tags"]):
                            match = False
                    elif isinstance(query["tags"], str) and query["tags"] not in file_metadata["tags"]:
                             match = False
                
                if "mood" in query and file_metadata.get("mood") != query["mood"].lower():
                    match = False
                
                if "mood_name" in query and file_metadata.get("mood_name") != query["mood_name"]:
                    match = False

                if match:
                    print(f"  Found: {filepath} (Size: {file_size} bytes, Modified: {mod_time.strftime('%Y-%m-%d')}, Type: .{file_type}, Tags: {', '.join(file_metadata['tags'])})")
                    found_count += 1

            except OSError as e:
                print(f"Error accessing file '{filepath}': {e}")
            except ValueError:
                print(f"Error processing query for '{filepath}'. Check query values.")

    print(f"Finished. Found {found_count} file(s) matching criteria.")

def exec_script(script_path, args):
    """
    Runs custom scripts (e.g., Python, Node.js).
    """
    if not os.path.exists(script_path):
        print(f"Error: Script '{script_path}' not found.")
        return

    script_extension = os.path.splitext(script_path)[1].lower()
    command = []

    if script_extension == ".js":
        command = ["node", script_path]
    elif script_extension == ".py":
        command = ["python", script_path]
    else:
        print(f"Error: Unsupported script type for '{script_path}'. Only .js and .py are supported.")
        return

    if args:
        command.extend(args)

    print(f"Executing script: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print("\n--- Script Output ---")
        print(result.stdout)
        if result.stderr:
            print("\n--- Script Errors ---")
            print(result.stderr)
        print("--- Script Finished ---")
    except FileNotFoundError:
        print(f"Error: Interpreter not found for script type '{script_extension}'. Make sure 'node' or 'python' is in your PATH.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Script execution failed with exit code {e.returncode}")
        print("--- Script Output ---")
        print(e.stdout)
        if e.stderr:
            print("\n--- Script Errors ---")
            print(e.stderr)
    except Exception as e:
        print(f"An unexpected error occurred during script execution: {e}")

def health_check(folder):
    """
    Checks data consistency (e.g., inaccessible files, broken symlinks).
    This is a basic check. More advanced checks would involve file content validation,
    checksum verification against a manifest, etc.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Performing health check on '{folder}'...")
    issues_found = 0

    for root, dirs, files in os.walk(folder):
        # Remove the metadata file from the list of files to check
        if METADATA_FILE in files:
            files.remove(METADATA_FILE)

        # Check directories
        for d in dirs:
            dir_path = os.path.join(root, d)
            if not os.path.isdir(dir_path):
                print(f"  Issue: Directory '{dir_path}' found in listing but not accessible or is not a directory.")
                issues_found += 1
            elif os.path.islink(dir_path) and not os.path.exists(os.readlink(dir_path)):
                print(f"  Issue: Broken symlink to directory: '{dir_path}' -> '{os.readlink(dir_path)}'")
                issues_found += 1

        # Check files
        for f in files:
            file_path = os.path.join(root, f)
            if not os.path.isfile(file_path):
                print(f"  Issue: File '{file_path}' found in listing but not accessible or is not a regular file.")
                issues_found += 1
            elif os.path.islink(file_path) and not os.path.exists(os.readlink(file_path)):
                print(f"  Issue: Broken symlink to file: '{file_path}' -> '{os.readlink(file_path)}'")
                issues_found += 1
            # Add checks for empty files, zero-size files, etc.
            try:
                if os.path.getsize(file_path) == 0:
                    print(f"  Warning: Empty file found: '{file_path}'")
            except OSError:
                print(f"  Issue: Cannot get size of '{file_path}'. Possible permissions issue or corruption.")
                issues_found += 1

    if issues_found == 0:
        print("Health check completed: No significant issues found.")
    else:
        print(f"Health check completed: Found {issues_found} issue(s).")


def export_map(folder, json_file):
    """
    Creates a JSON catalog of your files with basic metadata.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Exporting folder map of '{folder}' to '{json_file}'...")
    file_map = {}

    for root, dirs, files in os.walk(folder):
        normalized_root = _normalize_path(root) # Normalize root for metadata operations
        relative_path = os.path.relpath(normalized_root, _normalize_path(folder))
        if relative_path == ".":
            relative_path = "" # For the root folder itself

        folder_data = {"files": [], "subdirectories": []}

        # Load folder-specific metadata
        folder_metadata = _load_metadata(normalized_root)
        if "__folder__" in folder_metadata: # Check directly if key exists
            if "mood" in folder_metadata["__folder__"]:
                folder_data["mood"] = folder_metadata["__folder__"]["mood"]
        
        # Filter out the metadata file directory if it somehow gets listed as a directory
        dirs[:] = [d for d in dirs if d != METADATA_FILE.strip('.')] # Modify dirs in place for os.walk
        for d in dirs:
            folder_data["subdirectories"].append(d)

        # Filter out the metadata file from the files list
        files_to_process = [f for f in files if f != METADATA_FILE]
        for f in files_to_process:
            filepath = os.path.join(root, f)
            try:
                stat = os.stat(filepath)
                file_info = {
                    "name": f,
                    "size": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "type": os.path.splitext(f)[1].lstrip('.').lower(),
                }
                # Add stored metadata
                if f in folder_metadata:
                    file_info.update(folder_metadata[f])
                folder_data["files"].append(file_info)
            except OSError as e:
                print(f"Warning: Could not get info for '{filepath}': {e}")

        # Store the folder data using its relative path as key
        # Only store if there's actual data for the folder (files, subdirs, or folder mood)
        if folder_data["files"] or folder_data["subdirectories"] or "mood" in folder_data:
            file_map[relative_path if relative_path else "/"] = folder_data

    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(file_map, f, indent=4)
        print(f"Folder map exported successfully to '{json_file}'.")
    except IOError as e:
        print(f"Error exporting folder map to '{json_file}': {e}")


def apply_rules(folder):
    """
    Runs automation rules. This is a conceptual command.
    In a real scenario, you'd define rules in a separate configuration file
    (e.g., YAML, JSON) and this function would parse and execute them.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Applying automation rules to '{folder}' (conceptual)...")
    print("This command requires a separate 'rules engine' and configuration.")
    print("Example: Automatically moving images to 'Photos' folder, or compressing old archives.")
    print("For now, manually run other commands like 'conditional-move-copy' or 'auto-cleanup'.")

def schedule_command(name, delay_ms, command_args):
    """
    Schedules a command to run later.
    This is conceptual for a single-file script.
    Real scheduling requires persistent tasks (cron on Linux/macOS, Task Scheduler on Windows)
    or a dedicated Python scheduling library (e.g., `APScheduler`, `schedule`).
    """
    delay_seconds = delay_ms / 1000
    print(f"Scheduling command '{' '.join(command_args)}' with name '{name}' to run in {delay_seconds:.2f} seconds...")
    print("Note: This is a conceptual scheduling. For real-world use, consider:")
    print("  - Linux/macOS: cron jobs")
    print("  - Windows: Task Scheduler")
    print("  - Python libraries: 'schedule' or 'APScheduler' (requires a running process)")


def undo_actions(steps):
    """
    Reverts last actions.
    This is highly complex and requires a sophisticated logging/journaling system
    that records all file operations and their reversal capabilities.
    """
    print(f"Attempting to undo the last {steps} actions (conceptual)...")
    print("True undo functionality requires a robust transaction log and reversal logic for every command.")
    print("This feature is beyond the scope of a simple CLI script.")
    print("For now, please be cautious with commands that modify files irreversibly.")

def folder_mood_set(folder, mood, name):
    """
    Sets emotional labels for folders, stored in the folder's metadata file.
    """
    if not os.path.isdir(folder):
        print(f"Error: Folder '{folder}' not found.")
        return

    print(f"Setting mood for folder '{folder}': Mood='{mood}', Name='{name}'...")
    normalized_folder = _normalize_path(folder) # Normalize folder for metadata operations
    metadata = _load_metadata(normalized_folder)
    
    # Special key for folder-level metadata
    if "__folder__" not in metadata:
        metadata["__folder__"] = {}
    
    metadata["__folder__"]["mood"] = {"value": mood, "name": name if name else None}
    
    _save_metadata(normalized_folder, metadata) # Pass the normalized folder
    print(f"Mood '{mood}' ({name if name else 'No name'}) set for folder '{folder}'.")


# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(
        description="SuperHelperXPro: Your smart file assistant that helps you sort, fix, and manage your files with simple commands!"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # visualize
    visualize_parser = subparsers.add_parser("visualize", help="See the folder tree.")
    visualize_parser.add_argument("folder", help="The folder to visualize.")
    visualize_parser.add_argument(
        "max_depth", type=int, nargs="?", default=1, help="Max depth for visualization (default: 1)."
    )

    # batch-rename
    batch_rename_parser = subparsers.add_parser("batch-rename", help="Rename many files at once.")
    batch_rename_parser.add_argument("folder", help="The folder to perform renaming in.")
    batch_rename_parser.add_argument("regex", help="The regular expression to match. Use raw string for patterns (e.g., r'(IMG_)(\d+)').")
    batch_rename_parser.add_argument("replacement", help="The replacement string.")
    batch_rename_parser.add_argument(
        "recursive",
        type=lambda x: x.lower() == "true",
        nargs="?",
        default=False,
        help="Whether to rename recursively (true/false). Default: false.",
    )

    # deep-clone
    deep_clone_parser = subparsers.add_parser(
        "deep-clone", help="Copy a whole folder and contents."
    )
    deep_clone_parser.add_argument("src", help="Source folder.")
    deep_clone_parser.add_argument("dest", help="Destination folder.")

    # conditional-move-copy
    conditional_parser = subparsers.add_parser(
        "conditional-move-copy", help="Move or copy files by rules."
    )
    conditional_parser.add_argument("src", help="Source folder.")
    conditional_parser.add_argument("dest", help="Destination folder.")
    conditional_parser.add_argument(
        "type",
        choices=["ageDays", "sizeGT", "sizeLT"],
        help="Condition type (ageDays, sizeGT, sizeLT).",
    )
    conditional_parser.add_argument("value", help="Value for the condition (e.g., 30 for ageDays, 1024 for sizeGT).")
    conditional_parser.add_argument(
        "--copy", action="store_true", help="Perform a copy instead of a move."
    )

    # auto-cleanup
    cleanup_parser = subparsers.add_parser("auto-cleanup", help="Delete old or unwanted files.")
    cleanup_parser.add_argument("folder", help="The folder to clean up.")
    cleanup_parser.add_argument(
        "criteria",
        choices=["ageDays", "emptyFile"],
        help="Cleanup criteria (ageDays, emptyFile).",
    )
    cleanup_parser.add_argument("value", nargs="?", help="Value for the criteria (e.g., 30 for ageDays).")

    # deduplicate
    deduplicate_parser = subparsers.add_parser("deduplicate", help="Find and remove duplicate files.")
    deduplicate_parser.add_argument("folder", help="The folder to deduplicate.")
    deduplicate_parser.add_argument(
        "--dry-run", action="store_true", help="Just find duplicates, don't delete them."
    )

    # tag-file
    tag_parser = subparsers.add_parser("tag-file", help="Add or remove tags on files.")
    tag_parser.add_argument("file_path", help="The file or folder to tag.")
    tag_parser.add_argument(
        "--add", default="", help="Comma-separated tags to add."
    )
    tag_parser.add_argument(
        "--remove", default="", help="Comma-separated tags to remove."
    )
    tag_parser.add_argument(
        "--recursive", action="store_true", help="Apply to all files in subfolders if a folder is specified."
    )

    # search-tag
    search_tag_parser = subparsers.add_parser("search-tag", help="Find files with a specific tag.")
    search_tag_parser.add_argument("folder", help="The folder to search in.")
    search_tag_parser.add_argument("tag", help="The tag to search for.")

    # search-meta
    search_meta_parser = subparsers.add_parser("search-meta", help="Find files by size, date, type, using extended metadata. Query as JSON string (e.g., '{\"type\": \"txt\", \"size\": {\"gt\": 1024}}').")
    search_meta_parser.add_argument("folder", help="The folder to search in.")
    search_meta_parser.add_argument("json_query", help="JSON string for the query.")

    # exec-script
    exec_script_parser = subparsers.add_parser("exec-script", help="Run custom scripts (e.g., Python, Node.js).")
    exec_script_parser.add_argument("script_path", help="Path to the script file.")
    exec_script_parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to the script.")

    # health-check
    health_check_parser = subparsers.add_parser("health-check", help="Check data consistency.")
    health_check_parser.add_argument("folder", help="The folder to check.")

    # export-map
    export_map_parser = subparsers.add_parser("export-map", help="Create a JSON catalog of your files with basic metadata.")
    export_map_parser.add_argument("folder", help="The folder to map.")
    export_map_parser.add_argument("json_file", help="The output JSON file path.")

    # apply-rules (conceptual)
    apply_rules_parser = subparsers.add_parser("apply-rules", help="Run automation rules (conceptual).")
    apply_rules_parser.add_argument("folder", help="The folder to apply rules to.")

    # schedule-command (conceptual)
    schedule_parser = subparsers.add_parser("schedule-command", help="Schedule a command to run later (conceptual).")
    schedule_parser.add_argument("name", help="A name for the scheduled command.")
    schedule_parser.add_argument("delay_ms", type=int, help="Delay in milliseconds before execution.")
    schedule_parser.add_argument("command_args", nargs=argparse.REMAINDER, help="The command and its arguments to schedule.")

    # undo-actions (conceptual)
    undo_parser = subparsers.add_parser("undo-actions", help="Revert last actions (conceptual).")
    undo_parser.add_argument("steps", type=int, nargs="?", default=1, help="Number of steps to undo (default: 1).")
    
    # folder-mood-set
    folder_mood_set_parser = subparsers.add_parser("folder-mood-set", help="Set an emotional label for a folder.")
    folder_mood_set_parser.add_argument("folder", help="The folder to set the mood for.")
    folder_mood_set_parser.add_argument("mood", help="The mood value (e.g., 'Happy', 'Work', 'Archived').")
    folder_mood_set_parser.add_argument("--name", help="An optional name for the mood (e.g., 'Project Alpha Progress').", default=None)

    # folder-mood-get
    folder_mood_get_parser = subparsers.add_parser("folder-mood-get", help="Get the emotional label for a folder or search by mood.")
    folder_mood_get_parser.add_argument("folder", help="The folder to check or start scanning from.")
    folder_mood_get_parser.add_argument("--recursive", action="store_true", help="Scan subfolders recursively.")
    folder_mood_get_parser.add_argument("--filter-mood", help="Filter folders by mood name or value (case-insensitive).", default=None)


    args = parser.parse_args()

    # --- Command Execution Logic ---
    if args.command == "visualize":
        visualize_folder(args.folder, args.max_depth)
    elif args.command == "batch-rename":
        batch_rename(args.folder, args.regex, args.replacement, args.recursive)
    elif args.command == "deep-clone":
        deep_clone(args.src, args.dest)
    elif args.command == "conditional-move-copy":
        conditional_move_copy(args.src, args.dest, args.type, args.value, args.copy)
    elif args.command == "auto-cleanup":
        auto_cleanup(args.folder, args.criteria, args.value)
    elif args.command == "deduplicate":
        deduplicate(args.folder, args.dry_run)
    elif args.command == "tag-file":
        tag_file(args.file_path, args.add, args.remove, args.recursive)
    elif args.command == "search-tag":
        search_tag(args.folder, args.tag)
    elif args.command == "search-meta":
        search_meta(args.folder, args.json_query)
    elif args.command == "exec-script":
        exec_script(args.script_path, args.args)
    elif args.command == "health-check":
        health_check(args.folder)
    elif args.command == "export-map":
        export_map(args.folder, args.json_file)
    elif args.command == "apply-rules":
        apply_rules(args.folder)
    elif args.command == "schedule-command":
        schedule_command(args.name, args.delay_ms, args.command_args)
    elif args.command == "undo-actions":
        undo_actions(args.steps)
    elif args.command == "folder-mood-set":
        folder_mood_set(args.folder, args.mood, args.name)
    elif args.command == "folder-mood-get":
        folder_mood_get(args.folder, args.recursive, args.filter_mood)

if __name__ == "__main__":
    main()
