# Virtual Filesystem Implementation

A from-scratch implementation of a filesystem to learn about how operating systems manage files, directories, and disk storage.

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Installation & Usage](#installation--usage)
- [API Reference](#api-reference)
- [File Format](#file-format)
- [Example Usage](#example-usage)

---

## Project Overview

This project implements a complete filesystem with the following features:

- **Virtual Disk Management:** Create virtual disks with configurable sizes
- **File Operations:** Create, read, update, and delete files
- **Directory Management:** Create folders and navigate the filesystem
- **Block Allocation:** Automatic block allocation with free space tracking
- **Inode System:** File metadata management using inode tables
- **Web Interface:** Flask-based UI to interact with virtual disks
- **Persistence:** Save and load filesystems from disk

**Technology Stack:**

- Python 3
- Flask (for web interface)
- JSON (for serialization)

---

## Architecture

The project consists of two main classes:

### 1. VirtualDisk

Manages the physical disk storage, block allocation, and metadata.

### 2. FileSystem

Manages file and directory operations, built on top of VirtualDisk.

```
┌─────────────────────────────────────────┐
│   FileSystem (High-level API)           │
│  - create_file, open_file, mkdir, etc.  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│   VirtualDisk (Low-level operations)    │
│  - read_block, write_block, etc.        │
└────────────────┬────────────────────────┘
                 │
        ┌────────▼────────┐
        │  disk.bin file  │
        │  (persistent)   │
        └─────────────────┘
```

---

## Installation & Usage

### Prerequisites

```bash
python >= 3.8
flask >= 2.0
```

### Setup

1. **Install dependencies:**

   ```bash
   pip install flask
   ```

2. **Run the web server:**

   ```bash
   python app.py
   ```

3. **Access the interface:**
   Open your browser and navigate to `http://localhost:5000`

### Creating Your First Disk (Programmatic)

```python
from virtualDisk import VirtualDisk, FileSystem

# Create a 6MB virtual disk
disk = VirtualDisk("mydisk", 6)

# Initialize the filesystem
fs = FileSystem(disk)

# Create a file
fs.create_file("hello.txt", "Hello, World!")

# Create a directory
fs.mkdir("documents")
```

---

## API Reference

### VirtualDisk Class

#### Constructor: `__init__(diskname: str, disksize_mb: int)`

**Purpose:** Creates a new virtual disk and initializes the filesystem structures.

**Parameters:**

- `diskname` (str): Name of the disk (extension `.bin` added automatically)
- `disksize_mb` (int): Disk size in megabytes

**What it does:**

1. Calculates total blocks based on block size (4KB)
2. Creates metadata containing filesystem information
3. Initializes a bitmap to track free/used blocks
4. Creates an empty inode table
5. Writes all structures to the `.bin` file

**Example:**

```python
disk = VirtualDisk("my_disk", 5)  # Creates a 5MB disk
```

---

#### Class Method: `load(diskname: str) → VirtualDisk`

**Purpose:** Opens an existing disk without overwriting it.

**Parameters:**

- `diskname` (str): Filename of the `.bin` file to load

**Returns:** A VirtualDisk object with loaded metadata, bitmap, and inode table

**What it does:**

1. Reads the metadata from block 0
2. Loads the bitmap from block 1
3. Loads the inode table from block 2
4. Restores all in-memory structures

**Example:**

```python
disk = VirtualDisk.load("my_disk.bin")
```

---

#### Method: `offset(block_number: int) → int`

**Purpose:** Calculates the byte offset for a given block number.

**Formula:** `block_number × BLOCK_SIZE` (where BLOCK_SIZE = 4096)

**Why it matters:** Hard drives store data at specific byte positions. This converts logical block numbers to physical file offsets.

**Example:**

```python
offset = disk.offset(5)  # Returns 20480 (5 × 4096)
```

---

#### Method: `write_block(data: str) → tuple(block_number, size)`

**Purpose:** Writes data to the first available free block.

**Parameters:**

- `data` (str): The content to write

**Returns:** Tuple of (block_number where data was written, size of data written)

**What it does:**

1. Finds the first free block in the bitmap (first `0`)
2. Marks that block as used in the bitmap (sets to `1`)
3. Seeks to the block's offset in the file
4. Writes the data
5. Updates disk metadata

**Example:**

```python
block_num, size = disk.write_block("Hello World")
# Returns: (3, 11)  # Written to block 3, 11 bytes
```

---

#### Method: `update_block(data: str, block_number: int) → tuple(block_number, size)`

**Purpose:** Overwrites data in an existing block.

**Parameters:**

- `data` (str): New content
- `block_number` (int): Block to overwrite

**Returns:** Tuple of (block_number, size of data)

**What it does:**

1. Seeks to the block's offset
2. Overwrites the existing data
3. Updates disk metadata

**Note:** Unlike `write_block`, this doesn't allocate a new block. It replaces content in an existing block.

**Example:**

```python
disk.update_block("New content", 3)
```

---

#### Method: `read_block(block_number: int) → bytes`

**Purpose:** Reads the entire contents of a block.

**Parameters:**

- `block_number` (int): Block to read

**Returns:** Raw bytes from the block (padded to BLOCK_SIZE with null bytes)

**What it does:**

1. Seeks to the block's offset
2. Reads BLOCK_SIZE bytes
3. Returns the raw data

**Example:**

```python
data = disk.read_block(3)  # Returns 4096 bytes
content = data.decode().strip('\0')  # Convert to string
```

---

#### Method: `clear_block(block_number: int)`

**Purpose:** Erases a block and marks it as free.

**Parameters:**

- `block_number` (int): Block to clear

**What it does:**

1. Writes null bytes to fill the block
2. Marks block as free in bitmap (sets to `0`)
3. Updates disk metadata

**Example:**

```python
disk.clear_block(3)  # Block 3 is now available for reuse
```

---

#### Method: `update_disk_metadata()`

**Purpose:** Syncs all in-memory changes back to disk.

**What it does:**

1. Clears blocks 0-2 (reserved for metadata)
2. Recalculates used/free block counts
3. Writes updated metadata to block 0
4. Writes updated bitmap to block 1
5. Writes updated inode table to block 2

**Important:** This is called automatically by most operations, but you can call it manually if needed.

---

### FileSystem Class

#### Constructor: `__init__(disk: VirtualDisk)`

**Purpose:** Initializes the filesystem on a new disk.

**Parameters:**

- `disk` (VirtualDisk): The disk to initialize

**What it does:**

1. Creates a root directory (special folder that contains all others)
2. Allocates space for the root directory
3. Creates an inode for root
4. Sets the current working directory to "root"

**Example:**

```python
fs = FileSystem(disk)
```

---

#### Class Method: `load(disk: VirtualDisk) → FileSystem`

**Purpose:** Opens the filesystem on an existing disk.

**Parameters:**

- `disk` (VirtualDisk): A loaded disk

**Returns:** A FileSystem object ready for operations

**What it does:**

1. Restores the filesystem state
2. Sets working directory to root

**Example:**

```python
disk = VirtualDisk.load("my_disk.bin")
fs = FileSystem.load(disk)
```

---

#### Method: `inode_hash(name: str) → str`

**Purpose:** Generates a unique identifier for a file/folder based on its name.

**Parameters:**

- `name` (str): Name of the file or folder

**Returns:** String in format `"inode" + hash_number`

**How it works:**

1. Converts each character to its ASCII value
2. Multiplies by its position (1-indexed)
3. Sums all values
4. Applies modulo BLOCK_SIZE for consistent size

**Why consistent hashing?** A filename always produces the same inode ID, allowing reliable lookups.

**Example:**

```python
inode_id = fs.inode_hash("document.txt")
# Returns: "inode1234"  (deterministic)
```

---

#### Method: `cwd() → str`

**Purpose:** Returns the current working directory name (not the full path).

**Returns:** String name of the current directory

**Example:**

```python
fs.cwd()  # Returns "documents" (if in /root/documents)
```

---

#### Method: `create_inode(name: str, blocks_used: list, size: int, type_: str)`

**Purpose:** Creates and stores an inode for a file or directory.

**Parameters:**

- `name` (str): Name of the file/directory
- `blocks_used` (list): List of block numbers containing the data
- `size` (int): Total size of the file in bytes
- `type_` (str): Either "file" or "dir"

**What it does:**

1. Generates unique inode ID using `inode_hash`
2. Creates inode object with block list, size, and type
3. Stores in the disk's inode table
4. Updates disk metadata

**Example:**

```python
fs.create_inode("myfile.txt", [3, 4], 500, "file")
```

---

#### Method: `create_file(name: str, content: str)`

**Purpose:** Creates a new file with the given content.

**Parameters:**

- `name` (str): Filename
- `content` (str): File content

**What it does:**

1. Splits content into BLOCK_SIZE chunks
2. Writes each chunk to a free block
3. Creates an inode tracking all blocks
4. Registers file in parent directory
5. Updates metadata

**Example:**

```python
fs.create_file("essay.txt", "Once upon a time...")
```

---

#### Method: `open_file(name: str) → str`

**Purpose:** Reads and returns the complete contents of a file.

**Parameters:**

- `name` (str): Filename to read

**Returns:** Complete file content as string

**What it does:**

1. Looks up file in current directory
2. Retrieves its inode
3. Finds all blocks containing its data
4. Reads and assembles blocks in order
5. Returns complete content

**Example:**

```python
content = fs.open_file("essay.txt")
print(content)
```

---

#### Method: `delete_file(name: str)`

**Purpose:** Deletes a file and frees its blocks.

**Parameters:**

- `name` (str): Filename to delete

**What it does:**

1. Finds file's inode
2. Retrieves all blocks it uses
3. Clears each block and marks as free in bitmap
4. Removes file entry from parent directory
5. Deletes inode from inode table
6. Updates metadata

**Example:**

```python
fs.delete_file("oldfile.txt")
```

---

#### Method: `update_entry(name: str, content: str)`

**Purpose:** Overwrites the content of an existing file or directory.

**Parameters:**

- `name` (str): File/directory name
- `content` (str): New content

**What it does:**

1. Retrieves inode of the entry
2. Frees all old blocks
3. Allocates new blocks for new content
4. Updates inode with new blocks and size
5. Updates metadata

**Example:**

```python
fs.update_entry("config.json", '{"updated": true}')
```

---

#### Method: `open_entry(name: str) → str`

**Purpose:** Low-level method to read any entry (file or directory).

**Parameters:**

- `name` (str): Entry name

**Returns:** Raw content as string

**What it does:**

1. Looks up inode
2. Retrieves all blocks
3. Assembles and returns content

**Note:** Used internally by `open_file` and `mkdir`. For directories, this returns JSON-formatted content.

---

#### Method: `create_entry(name: str, content: str, type_: str)`

**Purpose:** Low-level method to create any entry (file or directory).

**Parameters:**

- `name` (str): Entry name
- `content` (str): Entry content
- `type_` (str): "file" or "dir"

**What it does:**

1. Allocates blocks for content
2. Creates inode
3. Registers in parent directory
4. Updates metadata

**Note:** Used internally by `create_file` and `mkdir`.

---

#### Method: `delete_entry(name: str)`

**Purpose:** Low-level method to delete any entry.

**Parameters:**

- `name` (str): Entry name

**What it does:**

1. Retrieves inode
2. Frees all blocks
3. Removes from parent directory
4. Deletes inode
5. Updates metadata

---

#### Method: `mkdir(name: str)`

**Purpose:** Creates a new directory/folder.

**Parameters:**

- `name` (str): Directory name

**What it does:**

1. Creates a special directory inode
2. Initializes directory content with `.` and `..` entries (current and parent)
3. Registers in parent directory
4. Updates metadata

**Example:**

```python
fs.mkdir("documents")
```

---

#### Method: `rmdir(name: str)`

**Purpose:** Recursively deletes a directory and all contents.

**Parameters:**

- `name` (str): Directory name to delete

**What it does:**

1. Reads directory contents
2. Recursively deletes all files and subdirectories
3. Changes to parent directory
4. Deletes the now-empty directory

**Example:**

```python
fs.rmdir("documents")
```

---

#### Method: `cd(folder_name: str)`

**Purpose:** Changes the current working directory.

**Parameters:**

- `folder_name` (str): Name of folder to enter
  - `"."` = stay in current directory
  - `".."` = go to parent directory
  - Any other string = enter that subfolder

**What it does:**

1. Validates the folder exists (if not `.` or `..`)
2. Updates the `self.path` string

**Example:**

```python
fs.cd("documents")    # Enter documents folder
fs.cd("..")          # Go back to parent
fs.cd(".")           # Stay in current (no-op)
```

---

#### Method: `ls() → dict`

**Purpose:** Lists contents of current directory.

**Returns:** Dictionary mapping names to inode IDs

**What it does:**

1. Reads the current directory's content
2. Parses JSON mapping
3. Returns dictionary

**Output includes:**

- `"."` - Current directory
- `".."` - Parent directory
- File and folder names

**Example:**

```python
contents = fs.ls()
# Returns: {".": "inode100", "..": "inode50", "file.txt": "inode201"}
```

---

#### Method: `file_exists(name: str) → bool`

**Purpose:** Checks if a file or folder exists in current directory.

**Parameters:**

- `name` (str): Name to check

**Returns:** True if exists, False otherwise

**Example:**

```python
if fs.file_exists("document.txt"):
    print("File found!")
```

---

#### Method: `tree(name: str = "root", prefix: str = "", is_root: bool = True)`

**Purpose:** Prints a visual tree representation of the directory structure.

**Parameters:**

- `name` (str): Starting directory (default: root)
- `prefix` (str): Indentation prefix (auto-managed)
- `is_root` (bool): Whether this is the root of the tree

**What it does:**

1. Recursively traverses all directories
2. Prints formatted tree with branches and folders
3. Shows file/folder distinction with `/` suffix on folders

**Example:**

```python
fs.tree()
# Output:
# root/
# ├── documents/
# │   ├── essay.txt
# │   └── notes.txt
# └── images/
#     └── photo.jpg
```

---

## File Format

Virtual disks are stored in binary `.bin` files with the following structure:

```
Byte Offset          Size         Content
──────────────────────────────────────────
0                    4096 bytes   Metadata (JSON)
4096                 4096 bytes   Bitmap (JSON)
8192                 4096 bytes   Inode Table (JSON)
12288                ...          File Data Blocks
```

### Block 0: Metadata (Super Block)

```json
{
  "magic": "MYFSYS",
  "disksize": 5242880,
  "total_blocks": 1280,
  "super_block": 0,
  "bitmap_block": 1,
  "inode_table": 2,
  "data_block": 3,
  "free_blocks": 1277,
  "used_blocks": 3,
  "size": 12288
}
```

### Block 1: Bitmap

```json
[1, 1, 1, 0, 0, 1, 0, 0, 1, ...]
```

1 = Block used, 0 = Block free

### Block 2: Inode Table

```json
{
  "inode201": {
    "blocks_used": [3, 4],
    "size": 8500,
    "type": "file"
  },
  "inode100": {
    "blocks_used": [5],
    "size": 256,
    "type": "dir"
  }
}
```

### Blocks 3+: Data Blocks

Raw file and directory contents.

---

## Example Usage

### Complete Workflow Example

```python
from virtualDisk import VirtualDisk, FileSystem

# Create a new 10MB disk
disk = VirtualDisk("workspace", 10)
fs = FileSystem(disk)

# Create directory structure
fs.mkdir("projects")
fs.mkdir("archive")
fs.cd("projects")

# Create files
fs.create_file("README.md", "# My Project\nThis is my project.")
fs.create_file("notes.txt", "Important notes...")

# Read a file
content = fs.open_file("README.md")
print(content)

# View directory
contents = fs.ls()
print(contents)

# Display tree structure
fs.cd("..")
fs.tree()

# Delete a file
fs.cd("projects")
fs.delete_file("notes.txt")

# Go back and delete entire directory
fs.cd("..")
fs.rmdir("archive")

# View final state
fs.tree()
```

### Loading and Using Existing Disk

```python
from virtualDisk import VirtualDisk, FileSystem

# Load existing disk
disk = VirtualDisk.load("workspace.bin")
fs = FileSystem.load(disk)

# Continue working
fs.cd("projects")
fs.create_file("report.txt", "Final report")

print(fs.open_file("report.txt"))
```

### Web Interface Usage

1. Open `http://localhost:5000`
2. **Create Disk:** Enter name and size (MB)
3. **Browse Disk:** Click on disk name to view contents
4. **Create File:** Enter filename and content
5. **Create Folder:** Enter folder name
6. **Navigate:** Click folder names to enter, use breadcrumb to navigate
7. **View File:** Click file name to view contents
8. **Delete:** Click delete button on file or folder

---

## Disk Structure Visualization

```
Disk File (workspace.bin)
│
├─ Block 0: Metadata (Super Block)
│  ├─ Magic: "MYFSYS"
│  ├─ Disk Size: 10 MB
│  ├─ Total Blocks: 2560
│  ├─ Used: 5, Free: 2555
│  └─ Block Locations of Bitmap, Inode Table, etc.
│
├─ Block 1: Bitmap
│  └─ [1,1,1,1,1,0,0,0,...]  (tracks block usage)
│
├─ Block 2: Inode Table
│  ├─ inode100 → root (directory)
│  ├─ inode201 → projects (directory)
│  └─ inode350 → README.md (file)
│
└─ Blocks 3+: Data Storage
   ├─ Block 3: {".", "..": inode100, "projects": inode201}
   ├─ Block 4: {".", "..": inode201, "README.md": inode350}
   └─ Block 5: "# My Project\nThis is my project."
```

---

## Performance Characteristics

| Operation        | Complexity | Notes                            |
| ---------------- | ---------- | -------------------------------- |
| Create File      | O(n)       | n = number of blocks needed      |
| Read File        | O(n)       | n = number of blocks to read     |
| Delete File      | O(n)       | n = number of blocks to clear    |
| Find Free Block  | O(m)       | m = total blocks (linear search) |
| Create Directory | O(1)       | Creates empty directory          |
| List Directory   | O(1)       | Reads single directory block\*   |

\*Assumes directory fits in one block (4096 bytes)

---

## Limitations & Future Improvements

### Current Limitations

- ❌ No hard links
- ❌ No symbolic links
- ❌ No file permissions
- ❌ No timestamps
- ❌ No user/group ownership
- ❌ Linear block search (inefficient bitmap)
- ❌ Fixed 4KB block size
- ❌ Simple JSON serialization (not optimized for size)

### Possible Enhancements

- ✅ Implement extent-based allocation (allocate contiguous blocks)
- ✅ Add B-tree for faster inode lookups
- ✅ Implement file permissions and ownership
- ✅ Add timestamps (creation, modification, access times)
- ✅ Support file hard links
- ✅ Add journaling for crash recovery
- ✅ Compress metadata with binary format
- ✅ Support multiple block sizes
- ✅ Implement defragmentation

---

## Learning Resources

This implementation is inspired by real filesystems:

- **ext4** (Linux): Similar block/inode structure
- **NTFS** (Windows): Master File Table (MFT) instead of inodes
- **APFS** (macOS): Modern copy-on-write filesystem
- **FAT32** (USB): Simple File Allocation Table

Study this code if you want to understand:

- How data is physically stored on disks
- How files are organized and located
- How free space is tracked
- How deletion works
- The relationship between logical names and physical locations

---

## Contributing

This is a learning project. Feel free to:

- Extend with new features
- Optimize existing code
- Add error handling
- Implement improvements

---

## License

Free to use and modify for educational purposes.
