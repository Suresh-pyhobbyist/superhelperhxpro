import argparse
import json
import os
import shutil
import time
import re
import hashlib
from datetime import datetime, timedelta

# --- Constants for Metadata ---
METADATA_FILE = ".superhxpro_metadata.json"

# --- Helper Functions ---

def _load_metadata(folder_path):
    """
    Loads metadata from a hidden JSON file in the specified folder.
    Returns an empty dictionary if the file doesn't exist, is empty, or is corrupted.
    """
    metadata_path = os.path.join(folder_path, METADATA_FILE)
    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                # Read content first to check if file is empty
                content = f.read().strip()
                if content: # Only attempt to load JSON if there's content
                    return json.loads(content)
                else:
                    # File exists but is empty
                    print(f"Info: Metadata file '{metadata_path}' is empty. Returning empty dictionary.")
                    return {}
        except json.JSONDecodeError:
            # File exists but contains invalid JSON
            print(f"Warning: Corrupted metadata file '{metadata_path}'. Returning empty dictionary to start fresh.")
            # Consider adding logic here to back up or delete the corrupted file
            return {}
        except IOError as e:
            # General I/O error (e.g., permissions)
            print(f"Error reading metadata from '{metadata_path}': {e}. Returning empty dictionary.")
            return {}
        except Exception as e:
            # Catch any other unexpected errors
            print(f"An unexpected error occurred while loading metadata from '{metadata_path}': {e}. Returning empty dictionary.")
            return {}
            
    # File does not exist
    return {}

def _save_metadata(folder_path, metadata):
    """
    Saves metadata to a hidden JSON file in the specified folder.
    Ensures the target directory exists before saving.
    """
    metadata_path = os.path.join(folder_path, METADATA_FILE)
    try:
        # Ensure the directory exists. `exist_ok=True` prevents error if dir already exists.
        os.makedirs(folder_path, exist_ok=True)
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4) # Use indent for readable JSON
        # print(f"Debug: Metadata successfully saved to '{metadata_path}'.") # Uncomment for debugging
    except PermissionError:
        print(f"Error: Permission denied. Cannot save metadata to '{metadata_path}'.")
    except IOError as e:
        print(f"Error saving metadata to '{metadata_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving metadata to '{metadata_path}': {e}")



# Assuming _load_metadata is defined elsewhere and works correctly.
def folder_mood_get(folder, recursive=False, mood_filter_name=None):
    """
    Gets the emotional label for a specific folder, or recursively scans folders
    to find those matching a specified mood name.

    Args:
        folder (str): The path to the folder to check or start the scan from.
        recursive (bool): If True, scans all subfolders recursively.
        mood_filter_name (str, optional): If provided, only shows folders
                                         whose mood's 'value' OR 'name' property contains this string
                                         (case-insensitive).
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
            # Show full path for single folder check
            print(f"{folder} - {mood_value}")
        else:
            print(f"No mood set for folder '{folder}'.")
        return

    # Handle recursive or filtered scan
    found_matches = False

    for root, dirs, files in os.walk(folder):
        current_folder_path = root

        try:
            metadata = _load_metadata(current_folder_path)

            # Check if the folder has a mood and matches the filter
            if "__folder__" in metadata and "mood" in metadata["__folder__"]:
                mood_info = metadata["__folder__"]["mood"]
                mood_value = mood_info.get("value", "N/A")
                mood_name = mood_info.get("name", "N/A")

                # Corrected filter logic (from last turn)
                filter_lower = mood_filter_name.lower() if mood_filter_name else None

                if filter_lower is None or \
                   (mood_value and filter_lower in mood_value.lower()) or \
                   (mood_name and filter_lower in mood_name.lower()):
                    # Show full path for recursive scan
                    print(f"{current_folder_path} - {mood_value}")
                    found_matches = True

        except Exception as e:
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
        # Sort items: directories first, then files, alphabetically
        items.sort(key=lambda x: (not os.path.isdir(os.path.join(folder, x)), x.lower()))

        for i, item in enumerate(items):
            path = os.path.join(folder, item)
            connector = "├── " if i < len(items) - 1 else "└── "
            item_type = "(Dir)" if os.path.isdir(path) else "(File)"
            print(f"{prefix}{connector}{item} {item_type}")

            if os.path.isdir(path) and item != METADATA_FILE: # Avoid endless recursion on metadata file if it somehow becomes a dir
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

        for filename in files:
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
        if not os.path.isfile(filepath):
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
                    shutil.move(filepath, dest_path)
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
        for filename in files:
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
                # Add more criteria here (e.g., "filetype:txt", "contains:temp")
                else:
                    print(f"Warning: Unknown cleanup criteria '{criteria}'. Skipping file '{filename}'.")
                    continue

                if perform_delete:
                    os.remove(filepath)
                    print(f"  Deleted: '{filepath}'")
                    deleted_count += 1
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
        for filename in files:
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
                        except OSError as e:
                            print(f"    Error deleting duplicate '{filepath}': {e}")
                else:
                    hashes[file_hash] = filepath
    
    print(f"Finished. Found {duplicates_found} duplicate(s). {'Deleted' if not dry_run else 'Would delete'} {deleted_count} file(s).")


def tag_file(file_path, add_tags_str, remove_tags_str, recursive):
    """
    Adds or removes tags on files. Tags are stored in a hidden JSON metadata file.
    Note: 'recursive' is not directly applicable to a single file,
    but can be extended to tag all files in a directory if the path is a folder.
    For this implementation, it will apply to the specified file or all files in a directory.
    """
    if not os.path.exists(file_path):
        print(f"Error: Path '{file_path}' not found.")
        return

    if os.path.isfile(file_path):
        target_paths = [file_path]
    elif os.path.isdir(file_path):
        if recursive:
            target_paths = [os.path.join(r, f) for r, _, files in os.walk(file_path) for f in files]
        else:
            target_paths = [os.path.join(file_path, f) for f in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, f))]
    else:
        print(f"Error: '{file_path}' is neither a file nor a directory.")
        return

    add_tags = {tag.strip() for tag in add_tags_str.split(',') if tag.strip()}
    remove_tags = {tag.strip() for tag in remove_tags_str.split(',') if tag.strip()}

    processed_count = 0
    for path in target_paths:
        if not os.path.isfile(path) or os.path.basename(path) == METADATA_FILE:
            continue

        folder = os.path.dirname(path)
        metadata = _load_metadata(folder)
        
        file_key = os.path.basename(path)
        if file_key not in metadata:
            metadata[file_key] = {"tags": []}
        
        current_tags = set(metadata[file_key].get("tags", []))
        
        updated_tags = (current_tags.union(add_tags)).difference(remove_tags)
        
        if updated_tags != current_tags:
            metadata[file_key]["tags"] = sorted(list(updated_tags))
            _save_metadata(folder, metadata)
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
        metadata = _load_metadata(root)
        for filename in files:
            if filename == METADATA_FILE:
                continue
            
            file_key = filename
            if file_key in metadata and "tags" in metadata[file_key]:
                if tag in metadata[file_key]["tags"]:
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
        metadata_from_file = _load_metadata(root) # Load internal metadata
        
        for filename in files:
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath) or filename == METADATA_FILE:
                continue

            try:
                stat = os.stat(filepath)
                file_size = stat.st_size
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                file_type = os.path.splitext(filename)[1].lstrip('.').lower() # e.g., 'jpg', 'pdf'

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
        # Use subprocess.run for simple execution and waiting
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

import subprocess

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
                if os.path.getsize(file_path) == 0 and f != METADATA_FILE:
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
        relative_path = os.path.relpath(root, folder)
        if relative_path == ".":
            relative_path = "" # For the root folder itself

        folder_data = {"files": [], "subdirectories": []}

        # Load folder-specific metadata
        folder_metadata = _load_metadata(root)
        if "mood" in folder_metadata.get("__folder__", {}):
            folder_data["mood"] = folder_metadata["__folder__"]["mood"]
        
        for d in dirs:
            # Skip hidden metadata folder if it was a directory
            if d == METADATA_FILE.strip('.'):
                continue
            folder_data["subdirectories"].append(d)

        for f in files:
            if f == METADATA_FILE:
                continue

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
    metadata = _load_metadata(folder)
    
    # Special key for folder-level metadata
    if "__folder__" not in metadata:
        metadata["__folder__"] = {}
    
    metadata["__folder__"]["mood"] = {"value": mood, "name": name if name else None}
    
    _save_metadata(folder, metadata)
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
        help="Condition type (e.g., 'ageDays', 'sizeGT' in bytes, 'sizeLT' in bytes).",
    )
    conditional_parser.add_argument("value", type=int, help="Condition value (e.g., 180 for ageDays, 5000000 for sizeGT).")
    conditional_parser.add_argument(
        "is_copy",
        type=lambda x: x.lower() == "true",
        nargs="?",
        default=False,
        help="Set to 'true' to copy instead of move. Default: false (move).",
    )

    # auto-cleanup
    auto_cleanup_parser = subparsers.add_parser(
        "auto-cleanup", help="Delete old or unwanted files."
    )
    auto_cleanup_parser.add_argument("folder", help="The folder to clean up.")
    auto_cleanup_parser.add_argument(
        "criteria", choices=["ageDays", "emptyFile"], help="Criteria for cleanup ('ageDays', 'emptyFile')."
    )
    auto_cleanup_parser.add_argument(
        "value", type=int, nargs="?", help="Value for criteria (e.g., 7 for ageDays). Not needed for 'emptyFile'."
    )

    # deduplicate
    deduplicate_parser = subparsers.add_parser(
        "deduplicate", help="Find and remove duplicate files."
    )
    deduplicate_parser.add_argument("folder", help="The folder to deduplicate.")
    deduplicate_parser.add_argument(
        "--dryRun",
        type=lambda x: x.lower() == "true",
        default=True,
        help="Set to 'false' to delete duplicates. Default is dry run.",
    )

    # tag
    tag_parser = subparsers.add_parser("tag", help="Add or remove tags on files.")
    tag_parser.add_argument("path", help="The file or folder to tag.")
    tag_parser.add_argument(
        "add_tags", help="Comma-separated tags to add. Use '' if none."
    )
    tag_parser.add_argument(
        "remove_tags", help="Comma-separated tags to remove. Use '' if none."
    )
    tag_parser.add_argument(
        "recursive",
        type=lambda x: x.lower() == "true",
        nargs="?",
        default=False,
        help="If path is a folder, whether to tag recursively (true/false). Default: false.",
    )

    # search-tag
    search_tag_parser = subparsers.add_parser(
        "search-tag", help="Find files with a specific tag."
    )
    search_tag_parser.add_argument("folder", help="The folder to search in.")
    search_tag_parser.add_argument("tag", help="The tag to search for.")

    # search-meta
    search_meta_parser = subparsers.add_parser(
        "search-meta", help="Find files by size, date, type, or custom tags/moods."
    )
    search_meta_parser.add_argument("folder", help="The folder to search in.")
    search_meta_parser.add_argument(
        "json_query", help="JSON string for metadata query (e.g., '{\"type\":\"image\",\"size\":{\"gt\":5000000}, \"tags\":[\"urgent\"], \"mood\":\"happy\"}')."
    )

    # exec-script
    exec_script_parser = subparsers.add_parser(
        "exec-script", help="Run custom JavaScript (.js) or Python (.py) scripts."
    )
    exec_script_parser.add_argument("script_path", help="Path to the script (.js or .py).")
    exec_script_parser.add_argument(
        "args", nargs=argparse.REMAINDER, help="Arguments to pass to the script."
    )

    # health-check
    health_check_parser = subparsers.add_parser(
        "health-check", help="Check data consistency (e.g., broken links, inaccessible files)."
    )
    health_check_parser.add_argument("folder", help="The folder to health check.")

    # export-map
    export_map_parser = subparsers.add_parser(
        "export-map", help="Create a JSON catalog of your files with metadata."
    )
    export_map_parser.add_argument("folder", help="The folder to map.")
    export_map_parser.add_argument("json_file", help="The output JSON file.")

    # apply-rules
    apply_rules_parser = subparsers.add_parser(
        "apply-rules", help="Run automation rules defined in a configuration (conceptual)."
    )
    apply_rules_parser.add_argument("folder", help="The folder to apply rules to.")

    # schedule
    schedule_parser = subparsers.add_parser("schedule", help="Schedule a command to run later (conceptual for a single-file script).")
    schedule_parser.add_argument("name", help="Name of the scheduled task.")
    schedule_parser.add_argument(
        "delay", type=int, help="Delay in milliseconds before running the command."
    )
    schedule_parser.add_argument("command_args", nargs=argparse.REMAINDER, help="The command to schedule (e.g., 'auto-cleanup Temp').")


    # undo
    undo_parser = subparsers.add_parser("undo", help="Revert last actions (conceptual and highly complex).")
    undo_parser.add_argument(
        "steps", type=int, nargs="?", default=1, help="Number of steps to undo (default: 1)."
    )

    # --- Consolidated folder-mood command ---
    folder_mood_parser = subparsers.add_parser(
        "folder-mood", help="Set or get emotional labels for folders."
    )
    folder_mood_subparsers = folder_mood_parser.add_subparsers(
        dest="mood_action", help="Folder mood actions", required=True
    )

    # folder-mood set
    folder_mood_set_subparser = folder_mood_subparsers.add_parser(
        "set", help="Set the mood of a folder."
    )
    folder_mood_set_subparser.add_argument("folder", help="The folder to set mood for.")
    folder_mood_set_subparser.add_argument(
        "--mood", required=True, help="The mood to set (e.g., 'happy', 'stressful')."
    )
    folder_mood_set_subparser.add_argument(
        "--name", help="An optional name for the mood (e.g., 'Vacation', 'WorkProject')."
    )

    # folder-mood get - UPDATED HERE
    folder_mood_get_subparser = folder_mood_subparsers.add_parser(
        "get", help="Get the mood of a folder (or recursively for subfolders, with optional filtering)."
    )
    folder_mood_get_subparser.add_argument("folder", help="The folder to get mood from.")
    folder_mood_get_subparser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan and display moods for all subfolders recursively."
    )
    folder_mood_get_subparser.add_argument(
        "--mood-name",
        help="Search for moods with a specific name/description (case-insensitive partial match).",
        default=None
    )
    # --- End of consolidated folder-mood command ---


    # --- Parse Arguments ---
    args = parser.parse_args()

    # --- Execute Commands based on parsed arguments ---
    if args.command == "visualize":
        visualize_folder(args.folder, args.max_depth)
    elif args.command == "batch-rename":
        batch_rename(args.folder, args.regex, args.replacement, args.recursive)
    elif args.command == "deep-clone":
        deep_clone(args.src, args.dest)
    elif args.command == "conditional-move-copy":
        conditional_move_copy(
            args.src, args.dest, args.type, args.value, args.is_copy
        )
    elif args.command == "auto-cleanup":
        if args.criteria == "ageDays" and args.value is None:
            parser.error("The 'value' argument is required for 'ageDays' criteria.")
        auto_cleanup(args.folder, args.criteria, args.value)
    elif args.command == "deduplicate":
        deduplicate(args.folder, args.dryRun)
    elif args.command == "tag":
        tag_file(args.path, args.add_tags, args.remove_tags, args.recursive)
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
    elif args.command == "schedule":
        scheduled_command = " ".join(args.command_args)
        schedule_command(args.name, args.delay, scheduled_command)
    elif args.command == "undo":
        undo_actions(args.steps)
    elif args.command == "folder-mood": # Handles both 'set' and 'get' actions
        if args.mood_action == "set":
            folder_mood_set(args.folder, args.mood, args.name)
        elif args.mood_action == "get":
            # Pass all relevant arguments to folder_mood_get
            folder_mood_get(args.folder, recursive=args.recursive, mood_filter_name=args.mood_name)

    # else: # required=True on subparsers means this else block might not be needed
    #     parser.print_help()

# def main():
#     parser = argparse.ArgumentParser(
#         description="SuperHelperXPro: Your smart file assistant that helps you sort, fix, and manage your files with simple commands!"
#     )

#     subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

#     # visualize
#     visualize_parser = subparsers.add_parser("visualize", help="See the folder tree.")
#     visualize_parser.add_argument("folder", help="The folder to visualize.")
#     visualize_parser.add_argument(
#         "max_depth", type=int, nargs="?", default=1, help="Max depth for visualization (default: 1)."
#     )

#     # batch-rename
#     batch_rename_parser = subparsers.add_parser("batch-rename", help="Rename many files at once.")
#     batch_rename_parser.add_argument("folder", help="The folder to perform renaming in.")
#     batch_rename_parser.add_argument("regex", help="The regular expression to match. Use raw string for patterns (e.g., r'(IMG_)(\d+)').")
#     batch_rename_parser.add_argument("replacement", help="The replacement string.")
#     batch_rename_parser.add_argument(
#         "recursive",
#         type=lambda x: x.lower() == "true",
#         nargs="?",
#         default=False,
#         help="Whether to rename recursively (true/false). Default: false.",
#     )

#     # deep-clone
#     deep_clone_parser = subparsers.add_parser(
#         "deep-clone", help="Copy a whole folder and contents."
#     )
#     deep_clone_parser.add_argument("src", help="Source folder.")
#     deep_clone_parser.add_argument("dest", help="Destination folder.")

#     # conditional-move-copy
#     conditional_parser = subparsers.add_parser(
#         "conditional-move-copy", help="Move or copy files by rules."
#     )
#     conditional_parser.add_argument("src", help="Source folder.")
#     conditional_parser.add_argument("dest", help="Destination folder.")
#     conditional_parser.add_argument(
#         "type",
#         choices=["ageDays", "sizeGT", "sizeLT"],
#         help="Condition type (e.g., 'ageDays', 'sizeGT' in bytes, 'sizeLT' in bytes).",
#     )
#     conditional_parser.add_argument("value", type=int, help="Condition value (e.g., 180 for ageDays, 5000000 for sizeGT).")
#     conditional_parser.add_argument(
#         "is_copy",
#         type=lambda x: x.lower() == "true",
#         nargs="?",
#         default=False,
#         help="Set to 'true' to copy instead of move. Default: false (move).",
#     )

#     # auto-cleanup
#     auto_cleanup_parser = subparsers.add_parser(
#         "auto-cleanup", help="Delete old or unwanted files."
#     )
#     auto_cleanup_parser.add_argument("folder", help="The folder to clean up.")
#     auto_cleanup_parser.add_argument(
#         "criteria", choices=["ageDays", "emptyFile"], help="Criteria for cleanup ('ageDays', 'emptyFile')."
#     )
#     auto_cleanup_parser.add_argument(
#         "value", type=int, nargs="?", help="Value for criteria (e.g., 7 for ageDays). Not needed for 'emptyFile'."
#     )

#     # deduplicate
#     deduplicate_parser = subparsers.add_parser(
#         "deduplicate", help="Find and remove duplicate files."
#     )
#     deduplicate_parser.add_argument("folder", help="The folder to deduplicate.")
#     deduplicate_parser.add_argument(
#         "--dryRun",
#         type=lambda x: x.lower() == "true",
#         default=True,
#         help="Set to 'false' to delete duplicates. Default is dry run.",
#     )

#     # tag
#     tag_parser = subparsers.add_parser("tag", help="Add or remove tags on files.")
#     tag_parser.add_argument("path", help="The file or folder to tag.")
#     tag_parser.add_argument(
#         "add_tags", help="Comma-separated tags to add. Use '' if none."
#     )
#     tag_parser.add_argument(
#         "remove_tags", help="Comma-separated tags to remove. Use '' if none."
#     )
#     tag_parser.add_argument(
#         "recursive",
#         type=lambda x: x.lower() == "true",
#         nargs="?",
#         default=False,
#         help="If path is a folder, whether to tag recursively (true/false). Default: false.",
#     )

#     # search-tag
#     search_tag_parser = subparsers.add_parser(
#         "search-tag", help="Find files with a specific tag."
#     )
#     search_tag_parser.add_argument("folder", help="The folder to search in.")
#     search_tag_parser.add_argument("tag", help="The tag to search for.")

#     # search-meta
#     search_meta_parser = subparsers.add_parser(
#         "search-meta", help="Find files by size, date, type, or custom tags/moods."
#     )
#     search_meta_parser.add_argument("folder", help="The folder to search in.")
#     search_meta_parser.add_argument(
#         "json_query", help="JSON string for metadata query (e.g., '{\"type\":\"image\",\"size\":{\"gt\":5000000}, \"tags\":[\"urgent\"], \"mood\":\"happy\"}')."
#     )

#     # exec-script
#     exec_script_parser = subparsers.add_parser(
#         "exec-script", help="Run custom JavaScript (.js) or Python (.py) scripts."
#     )
#     exec_script_parser.add_argument("script_path", help="Path to the script (.js or .py).")
#     exec_script_parser.add_argument(
#         "args", nargs=argparse.REMAINDER, help="Arguments to pass to the script."
#     )

#     # health-check
#     health_check_parser = subparsers.add_parser(
#         "health-check", help="Check data consistency (e.g., broken links, inaccessible files)."
#     )
#     health_check_parser.add_argument("folder", help="The folder to health check.")

#     # export-map
#     export_map_parser = subparsers.add_parser(
#         "export-map", help="Create a JSON catalog of your files with metadata."
#     )
#     export_map_parser.add_argument("folder", help="The folder to map.")
#     export_map_parser.add_argument("json_file", help="The output JSON file.")

#     # apply-rules
#     apply_rules_parser = subparsers.add_parser(
#         "apply-rules", help="Run automation rules defined in a configuration (conceptual)."
#     )
#     apply_rules_parser.add_argument("folder", help="The folder to apply rules to.")

#     # schedule
#     schedule_parser = subparsers.add_parser("schedule", help="Schedule a command to run later (conceptual for a single-file script).")
#     schedule_parser.add_argument("name", help="Name of the scheduled task.")
#     schedule_parser.add_argument(
#         "delay", type=int, help="Delay in milliseconds before running the command."
#     )
#     schedule_parser.add_argument("command_args", nargs=argparse.REMAINDER, help="The command to schedule (e.g., 'auto-cleanup Temp').")


#     # undo
#     undo_parser = subparsers.add_parser("undo", help="Revert last actions (conceptual and highly complex).")
#     undo_parser.add_argument(
#         "steps", type=int, nargs="?", default=1, help="Number of steps to undo (default: 1)."
#     )

#     # folder-mood get
#     folder_mood_get_parser = folder_mood_subparsers.add_parser(
#         "get", help="Get the mood of a folder."
#     )
#     folder_mood_get_parser.add_argument("folder", help="The folder to get mood from.")
#     # Add this new argument:
#     folder_mood_get_parser.add_argument(
#         "--recursive",
#         action="store_true", # This makes it a boolean flag
#         help="Scan and display moods for all subfolders recursively."
#     )

#     # folder-mood (set)
#     folder_mood_set_parser = subparsers.add_parser(
#         "folder-mood", help="Set or get emotional labels for folders."
#     )
#     folder_mood_set_parser.add_argument("folder", help="The folder to set/get mood for.")
    
#     # Use mutually exclusive group for --set and --get
#     mood_group = folder_mood_set_parser.add_mutually_exclusive_group(required=True)
#     mood_group.add_argument(
#         "--set", action="store_true", help="Specify this flag to set a mood."
#     )
#     mood_group.add_argument(
#         "--get", action="store_true", help="Specify this flag to get the mood."
#     )
    
#     folder_mood_set_parser.add_argument("--mood", help="The mood to set (e.g., 'happy', 'stressful'). Required with --set.")
#     folder_mood_set_parser.add_argument(
#         "--name", help="An optional name for the mood (e.g., 'Vacation', 'WorkProject')."
#     )


#     args = parser.parse_args()

#     # Execute commands based on parsed arguments
#     if args.command == "visualize":
#         visualize_folder(args.folder, args.max_depth)
#     elif args.command == "batch-rename":
#         batch_rename(args.folder, args.regex, args.replacement, args.recursive)
#     elif args.command == "deep-clone":
#         deep_clone(args.src, args.dest)
#     elif args.command == "conditional-move-copy":
#         conditional_move_copy(
#             args.src, args.dest, args.type, args.value, args.is_copy
#         )
#     elif args.command == "auto-cleanup":
#         # Ensure value is provided if criteria is ageDays
#         if args.criteria == "ageDays" and args.value is None:
#             parser.error("The 'value' argument is required for 'ageDays' criteria.")
#         auto_cleanup(args.folder, args.criteria, args.value)
#     elif args.command == "deduplicate":
#         deduplicate(args.folder, args.dryRun)
#     elif args.command == "tag":
#         tag_file(args.path, args.add_tags, args.remove_tags, args.recursive)
#     elif args.command == "search-tag":
#         search_tag(args.folder, args.tag)
#     elif args.command == "search-meta":
#         search_meta(args.folder, args.json_query)
#     elif args.command == "exec-script":
#         exec_script(args.script_path, args.args)
#     elif args.command == "health-check":
#         health_check(args.folder)
#     elif args.command == "export-map":
#         export_map(args.folder, args.json_file)
#     elif args.command == "apply-rules":
#         apply_rules(args.folder)
#     elif args.command == "schedule":
#         # Reconstruct the original command from command_args
#         scheduled_command = " ".join(args.command_args)
#         schedule_command(args.name, args.delay, scheduled_command)
#     elif args.command == "undo":
#         undo_actions(args.steps)
#     elif args.command == "folder-mood":
#         if args.set:
#             if not args.mood:
#                 parser.error("The '--mood' argument is required when using '--set'.")
#             folder_mood_set(args.folder, args.mood, args.name)
#         elif args.get:
#             folder_mood_get(args.folder)
#     else:
#         parser.print_help()

if __name__ == "__main__":
    main()