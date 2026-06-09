# How Disks and File Systems Actually Work — Built From Scratch in Python

## 1. Why I Wrote This

Last month, I was studying for my AZ-900 certification and kept hitting the same wall: I understood _what_ cloud block storage was (EBS volumes, Azure Managed Disks), but I had no idea _why_ it was designed that way. Why are there blocks? Why do inodes exist? Why can't I just store a file as a single chunk?

So I did what any curious engineer does—I built it from scratch. In ~350 lines of Python, I created a fully functional virtual disk and file system. No external libraries. No magic. Just the essential concepts that make real systems like NTFS, ext4, and cloud storage work.

The result surprised me. Once I understood the _why_ behind each piece—the bitmap, the inode table, the concept of blocks—everything clicked. Suddenly, `ls -i` in Linux made sense. AWS EBS seemed less magical. And worst of all (for my study schedule), I realized I could explain this to anyone.

This post walks through that implementation. Whether you're preparing for a systems design interview, writing storage code, or just curious about what happens under the hood when you save a file, you'll see exactly how it works.

---

## 2. The Big Picture: Two Layers

A file system isn't one thing—it's two. Think of a building with a ground floor and upper floors.

**The Ground Floor: The Disk Layer** is the raw hardware. It's a massive sequence of bytes. It knows nothing about files or folders. It just reads and writes 4,096-byte chunks (blocks) in response to requests like "give me bytes 8192-12288." In our system, this is the `VirtualDisk` class.

**The Upper Floor: The File System Layer** is where you, the human, live. It organizes those blocks into files and folders. It remembers that block 5 and block 7 belong to your "notes.txt" file. It knows that "hello.txt" lives in a folder called "documents." This is the `FileSystem` class.

The two layers barely talk to each other. The file system says "write this data," and the disk says "I'll put it in block 3." The file system remembers that mapping. Next time, the file system asks for block 3, and the disk finds it instantly.

| Concept               | Our Code         | NTFS (Windows)        | ext4 (Linux)         | Cloud (AWS/Azure)                                |
| --------------------- | ---------------- | --------------------- | -------------------- | ------------------------------------------------ |
| **Raw storage**       | VirtualDisk      | Physical disk sectors | Physical disk blocks | EBS volume (virtual disk on shared storage)      |
| **Block size**        | 4,096 bytes      | 4,096 bytes           | 4,096 bytes          | 4,096 bytes (EBS blocks)                         |
| **File metadata**     | Inode dict       | MFT record            | Inode structure      | Inode + block pointers (stored in metadata tier) |
| **Block tracking**    | Bitmap array     | $Bitmap file          | Block group bitmap   | Bitmap in metadata tier                          |
| **File organization** | FileSystem class | NTFS driver           | ext4 driver          | Storage layer API                                |

---

## 3. Part 1: The Virtual Disk

### What is a Disk, and What is a Virtual Disk?

Imagine a warehouse with a million identical 4KB shelves. A **physical disk** is a real warehouse—the SSD in your laptop or the hard drive in a server. A **virtual disk** is a photograph of that warehouse. It's a file—in our case, a `.bin` file—that contains all the same information. From the file system's perspective, there's no difference.

When you use AWS EBS or Azure Managed Disks, you're using a virtual disk. It's not a physical drive on your machine. It's a file (called an "image") stored on shared storage hardware in a data center. The operating system communicates with it over a network, but it behaves exactly like a local disk. The cloud provider's software layer translates your requests into the actual hardware.

In our system, we create this virtual disk as a `.bin` file:

```python
self.diskname = diskname + ".bin"
self.disksize = disksize_mb * 1024 * 1024  # Convert MB to bytes
self.total_blocks = self.disksize // self.BLOCK_SIZE  # How many 4KB blocks fit?
```

That's it. A 6 MB virtual disk becomes a 6 MB `.bin` file on disk. When we initialize it, we write a few metadata structures and fill the rest with zeros, mimicking a freshly formatted drive.

**Real-world parallel:** An AWS EBS volume is similarly a virtual disk image stored in Amazon's data centers. Azure Managed Disks work the same way. The cloud provider's storage software handles the physical placement, but your operating system issues the same read/write commands it would to a local SSD.

### What is a Block?

A **block** is a fixed-size chunk—4,096 bytes, or 4KB. It's the atomic unit of storage. The disk doesn't read individual bytes; it reads entire blocks. The file system doesn't allocate individual bytes; it allocates blocks.

Why? Imagine a hotel with rooms of different sizes. Guests could arrive and say "I need 47 bytes of space," but then you'd waste the remaining bytes in the room and fragment the building. Instead, rooms are standardized: "This is a room; it fits exactly one guest; no splitting." Blocks work the same way. One data allocation = one or more full blocks. No fragmentation within a block. The entire disk is a grid of blocks.

Here's the math:

```python
BLOCK_SIZE = 4096  # 4 kilobytes
total_blocks = disksize // BLOCK_SIZE
```

A 6 MB disk has `6,291,456 / 4096 = 1536` blocks. Each one is identified by its block number: 0, 1, 2, ..., 1535.

Real systems use the same sizes:

- **NTFS**: 4,096 bytes per cluster (NTFS's term for block)
- **ext4**: 4,096 bytes per block (configurable, but 4K is standard)
- **EBS**: 4,096 bytes per block (AWS's standard)

The 4KB size is a sweet spot chosen by decades of systems research. It's small enough to avoid wasting space on tiny files, but large enough to amortize the overhead of metadata and network I/O.

**Real-world parallel:** Just as physical disk sectors are typically 4,096 bytes (a standard agreed upon by the industry), virtual disks use the same block size. Your OS assumes 4K blocks; the cloud provider delivers 4K blocks. The abstraction is seamless.

### Disk Layout: The First Three Blocks

When we create a virtual disk, the first three blocks are reserved for metadata. They're like the building plans, the vacancy board, and the inventory ledger for our warehouse.

**Block 0 is the Superblock.** It's a JSON file containing:

- `magic`: A signature ("MYFSYS") so we can recognize our format
- `disksize`: Total size in bytes
- `total_blocks`: How many blocks exist
- `free_blocks` and `used_blocks`: The running count
- Pointers to the other reserved blocks

The superblock is the floor plan. If the disk got corrupted, we'd read block 0 to understand its structure.

**Block 1 is the Bitmap.** This is a list of 1s and 0s: `[1, 1, 1, 0, 0, 1, 0, ...]`. Each entry corresponds to a block. A `1` means the block is in use; a `0` means it's free. It's a vacancy board. When you want to write a file, you scan through this list to find the first 0, then flip it to 1. It's staggeringly efficient—one integer per block tells you the entire state of the disk.

**Block 2 is the Inode Table.** This is a dictionary mapping inode identifiers to file metadata:

```json
{
  "inode1021": { "blocks_used": [3, 4], "size": 7500, "type": "file" },
  "inode942": { "blocks_used": [5], "size": 2048, "type": "dir" }
}
```

It's an inventory ledger. Each file has an entry describing which blocks hold its data.

Here's the initialization code:

```python
self.metadata = {
    "magic": "MYFSYS",
    "disksize": self.disksize,
    "total_blocks": self.total_blocks,
    "super_block": 0,
    "bitmap_block": 1,
    "inode_table": 2,
    "data_block": 3,
    "free_blocks": self.total_blocks - 3,
    "used_blocks": 3
}
self.bitmap = [0] * self.total_blocks
for i in range(3):
    self.bitmap[i] = 1  # Mark the first 3 blocks as used
```

Then we write these to disk:

```python
with open(self.diskname, "wb") as f:
    f.seek(self.offset(0))
    f.write(json.dumps(self.metadata, separators=COMPACT).encode())
    f.seek(self.offset(1))
    f.write(json.dumps(self.bitmap, separators=COMPACT).encode())
    f.seek(self.offset(2))
    f.write(json.dumps(self.inode_table, separators=COMPACT).encode())
```

**Real-world parallel:**

- **ext4**: The superblock is in block 0 and contains similar information (filesystem UUID, creation time, mount count, block size, etc.). Block groups also have their own superblock copies for redundancy.
- **NTFS**: The Master Boot Record (MBR) and Master File Table ($MFT) serve similar roles. The $Bitmap file tracks allocation.
- **Cloud**: EBS volumes have metadata tiers that store superblock-like structures in low-numbered blocks. Azure Managed Disks do the same.

### The Bitmap in Action

The bitmap is the heartbeat of the disk. Every time you write a file, the file system asks the disk: "Which block is free?" The disk scans the bitmap, finds a 0, and claims it.

Here's the write method in action. Let's say you're writing a 100-byte file. The disk needs to find one free block.

```python
def write_block(self, data: str):
    data_block = self.metadata["data_block"]
    free_block = self.bitmap.index(0, data_block)  # Find first 0 starting from block 3
    self.bitmap[free_block] = 1  # Claim it
    with open(self.diskname, "rb+") as f:
        f.seek(self.offset(free_block))
        f.write(data.encode())
    self.update_disk_metadata()
    return free_block, len(data)
```

Step by step:

1. **Search the bitmap** for the first 0 starting from block 3 (where data begins). Let's say it's block 5.
2. **Flip it to 1**: `self.bitmap[5] = 1`.
3. **Write the data** at byte position `5 * 4096 = 20480`.
4. **Persist**: Update the metadata (superblock, bitmap, inode table) back to disk.
5. **Return**: Tell the file system that the data is in block 5.

The file system receives block 5 and remembers it in the inode: "This file's data is in blocks [5]."

Later, when reading, the file system asks, "Where's this file?" The disk responds, "Block 5." The file system then asks the disk, "Read block 5," and the disk knows exactly where to look: byte 20480, for 4096 bytes.

**Real-world parallel:** ext4 and NTFS both use bitmaps internally. When you write a large file in Linux, the kernel scans the bitmap to find free blocks, marks them as allocated, and writes the inode. The bitmap is updated. On the next block write, the kernel skips already-used blocks. AWS EBS does the same at the storage layer—each EBS volume has an internal bitmap tracking block allocation across its virtual storage array.

### How Reading and Writing Find the Right Spot: The Offset Function

Here's a question: if block 7 contains data, and the disk is a file, where exactly in that file do we write?

The answer is the `offset()` function:

```python
def offset(self, block_number):
    return int(block_number) * self.BLOCK_SIZE
```

Block 7 lives at byte `7 * 4096 = 28,672`. Block 3 lives at byte `3 * 4096 = 12,288`.

This is how the disk translates block numbers into file positions. When the file system says "read block 5," the disk computes the offset, seeks to that byte position, and reads 4,096 bytes.

```python
def read_block(self, block_number: int):
    with open(self.diskname, "rb") as f:
        f.seek(self.offset(block_number))
        return f.read(self.BLOCK_SIZE)
```

This concept, multiplying block number by block size to find a byte position, is called **Logical Block Addressing (LBA)**. Every disk, every SSD, every EBS volume uses this. The storage device receives a block number, computes the physical address, and accesses it.

**Real-world parallel:** SSDs and physical hard drives use LBA to map logical block addresses to physical locations on the medium. When your OS asks the SSD, "Read block 1000," the SSD's firmware computes the offset, accesses the NAND flash (or spinning platter), and returns 4,096 bytes. Virtual disks in the cloud do the same translation. AWS EBS firmware maps your block request to the shared storage backend. The abstraction is perfect.

---

## 4. Part 2: The File System

### Inodes: The File's ID Card

Here's a problem: your file "notes.txt" is 12,000 bytes. That's three 4KB blocks. The disk can store it, but how does the system remember that these three blocks belong to _one_ file?

That's what inodes are for.

An **inode** is an entry in a database that describes a file. It says: "This file uses blocks [3, 5, 7]. It's 12,000 bytes total. It's a regular file (not a directory)." Think of it as your file's ID card. Every file gets an inode. Every directory gets an inode. The inode stores _metadata_ about the file, including which blocks hold the file's data.

Here's an inode in our system:

```python
inode = {
    "blocks_used": [3, 5, 7],
    "size": 12000,
    "type": "file"
}
```

Now, here's something crucial: **the filename is NOT stored in the inode.** The inode doesn't know it's called "notes.txt." Instead, the _parent directory_ (the folder containing the file) stores that mapping:

```python
parent_folder_entries = {
    "notes.txt": "inode1021",
    "draft.txt": "inode942"
}
```

Why separate them? Because this design enables **hard links**. In Linux, you can say `ln notes.txt links-to-notes.txt`, and suddenly two different filenames point to the same inode. They're the same file, with two names. Modifying one modifies the other. If filenames were stored in the inode, this wouldn't be possible.

Inodes are identified by a hash of the filename (in our simple implementation). In real systems, they're numbered sequentially:

```python
def inode_hash(self, name: str):
    inode_hash_number = sum([ord(c)*i for i,c in enumerate(name,1)]) % self.disk.BLOCK_SIZE
    return "inode" + str(inode_hash_number)
```

When you run `ls -i` in a Linux terminal, those numbers you see are inode numbers. Each one represents a file or directory in the current folder.

**Real-world parallel:**

- **ext4**: Inodes are fixed-size structures (256 bytes) stored in inode tables. The `ls -i` command shows the inode number. You can inspect an inode with `stat filename`, which shows the block pointers, size, permissions, and timestamps.
- **NTFS**: NTFS uses MFT (Master File Table) records instead of inodes. Each MFT record describes a file, including which clusters hold the data. The concept is identical; the name is different.
- **Cloud**: EBS volumes use similar metadata structures. The volume's metadata tier stores inode-like records describing which blocks belong to which file.

### Creating a File: A Story in Three Acts

Creating a file is a three-step dance between the disk layer and the file system layer. Let me tell it as a story.

**Act 1: Writing the Data**

You call `fs.create_file("hello.txt", "Hello, world!")`. The file system springs into action. First, it needs to _write_ the content to disk. The file is small (13 bytes), so it fits in one 4KB block. The file system calls `disk.write_block(content)`.

The disk scans its bitmap for a free block. It finds block 7 is free (bitmap[7] = 0). It flips the bitmap (bitmap[7] = 1), seeks to byte 28,672 (7 \* 4096), and writes "Hello, world!" to disk. It returns block 7 to the file system.

**Act 2: Creating the Inode**

The file system now knows the data is in block 7. It creates an inode and stores it in the inode table:

```python
inode = {
    "blocks_used": [7],
    "size": 13,
    "type": "file"
}
self.disk.inode_table["inode4829"] = inode  # "inode4829" is the hash of "hello.txt"
```

**Act 3: Updating the Parent Directory**

Finally, the file system needs to tell the parent folder about this new file. The parent folder is also a file (directories are files!). It contains a JSON dictionary:

```python
# Current contents of the "root" directory block
{
    ".": "inode0",
    "..": "inode0"
}
```

The file system reads this block, adds an entry for "hello.txt", and writes it back:

```python
{
    ".": "inode0",
    "..": "inode0",
    "hello.txt": "inode4829"
}
```

Here's the code orchestrating this:

```python
def create_entry(self, name: str, content: str, type_: str):
    # Act 1: Write data to disk
    blocks_used = []
    size = 0
    for chunk in range((len(content) // self.disk.BLOCK_SIZE) + 1):
        block, chunk_size = self.disk.write_block(content[chunk*self.disk.BLOCK_SIZE:(chunk+1)*self.disk.BLOCK_SIZE])
        blocks_used.append(block)
        size += chunk_size

    # Act 2: Create inode
    self.create_inode(name, blocks_used, size, type_)

    # Act 3: Update parent directory
    parent_folder = self.path.split("/")[-1]
    parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
    parent_folder_lookup[name] = self.inode_hash(name)
    self.update_entry(parent_folder, json.dumps(parent_folder_lookup, separators=COMPACT))

    # Update parent's size in its inode
    parent_folder_inode = self.disk.inode_table[self.inode_hash(parent_folder)]
    parent_folder_inode["size"] += size
    self.disk.metadata["size"] += size
    self.disk.update_disk_metadata()
```

This exact pattern—write data, create inode, update parent directory—is how ext4 creates files. The specifics differ (ext4 uses different data structures), but the three-act structure is universal.

**Real-world parallel:** When you run `touch myfile.txt` in Linux on an ext4 filesystem, the kernel performs these exact three steps. First, it allocates blocks for the file (even if empty, the directory entry takes space). Second, it creates an inode. Third, it updates the parent directory's block to include the new filename-to-inode mapping. The difference is that ext4 uses a more complex directory format (B-trees for large directories) and adds permissions, timestamps, and links count to the inode. But the essence is identical.

### Directories Are Just Files

Here's a mind-bending insight: directories are not a special kind of storage. They're files. They just happen to contain a specific format—a dictionary mapping names to inode numbers.

When you create a directory, you're creating a file whose content is JSON:

```python
def mkdir(self, name: str):
    folder_inode = self.inode_hash(name)
    # The directory's "content" is a JSON dict
    self.create_entry(name, json.dumps({
        ".": folder_inode,
        "..": folder_inode
    }), "dir")
```

That's it. A directory is a file of type "dir" with special formatting.

Let me trace through a concrete example. We start with an empty disk. We run:

```python
fs.mkdir("documents")
fs.cd("documents")
fs.create_file("hello.txt", "Hello, world!")
fs.create_file("notes.txt", "Project notes...")
fs.mkdir("drafts")
```

**After `mkdir("documents")`:**

The root directory block now contains:

```json
{
  ".": "inode0",
  "..": "inode0",
  "documents": "inode3472"
}
```

The new "documents" directory block contains:

```json
{
  ".": "inode3472",
  "..": "inode0"
}
```

(The ".." entry points back to root, identified as "inode0".)

**After `create_file("hello.txt", ...)`:**

Our current path is "root/documents". The "documents" block is updated:

```json
{
  ".": "inode3472",
  "..": "inode0",
  "hello.txt": "inode5821"
}
```

Blocks on disk:

- Block 0: Superblock (metadata)
- Block 1: Bitmap
- Block 2: Inode table
- Block 3: Root directory JSON
- Block 4: Documents directory JSON
- Block 5: hello.txt data ("Hello, world!")
- Block 6: notes.txt data ("Project notes...")
- Block 7: drafts directory JSON

The inode table in block 2 looks like:

```json
{
    "inode0": { "blocks_used": [3], "size": ..., "type": "dir" },
    "inode3472": { "blocks_used": [4], "size": ..., "type": "dir" },
    "inode5821": { "blocks_used": [5], "size": 13, "type": "file" },
    "inode..." : { ... }
}
```

When we call `fs.ls()`, the file system reads the current directory's block, decodes the JSON, and prints the entries:

```python
def ls(self):
    current_folder = self.path.split("/")[-1]  # "documents"
    content = self.open_entry(current_folder)  # Read the directory block
    print(json.loads(content.strip()))
    # Output:
    # {
    #   ".": "inode3472",
    #   "..": "inode0",
    #   "hello.txt": "inode5821",
    #   "notes.txt": "inode8934",
    #   "drafts": "inode2109"
    # }
```

The "." and ".." entries are standard in real file systems. "." points to the current directory (so `cd .` is a no-op). ".." points to the parent, allowing `cd ..` to go up.

**Real-world parallel:** In ext4 and NTFS, directories are stored differently (ext4 uses a linked list or hash tree; NTFS uses a B-tree), but the concept is identical. Each directory entry maps a filename to an inode (or MFT record). Accessing a file requires traversing the directory tree. When you run `find . -type f`, the filesystem recursively reads directory blocks, descends through the tree, and collects all files.

### Navigating the Tree

Here's a beautiful simplification: navigating the directory tree—`cd`—involves _no disk I/O_.

```python
def cd(self, folder_name: str):
    if folder_name == ".":
        return
    elif folder_name == "..":
        cwd = self.cwd()
        if cwd == "root":
            return
        path = self.path.split("/")[:-1]
        self.path = ""
        for p in path:
            self.path = self.path + "/" + p
        return
    else:
        self.path = self.path + "/" + folder_name
```

We're just manipulating a string. The path "root/documents/drafts" is stored in memory. The disk is untouched until you call `ls()`, `create_file()`, or `delete_file()`.

The disk is only read when:

- **Listing**: `ls()` reads the current directory block
- **Creating**: `create_file()` reads the parent directory to add an entry
- **Deleting**: `delete_entry()` reads the parent directory to remove an entry

This is why navigating a massive directory tree is fast, even with millions of files. You're just manipulating a path string. The real work—finding blocks on disk—happens only when you actually interact with files.

### Deleting a File: Erasing the Trail

Deleting a file reverses the three-act creation process.

**Act 1: Clear the Data Blocks**

We start by reading the inode to learn which blocks hold the file:

```python
inode = self.disk.inode_table[self.inode_hash(name)]
blocks_used = inode["blocks_used"]  # e.g., [5, 6, 7]
for block in blocks_used:
    self.disk.clear_block(block)
```

`clear_block()` is crucial. It wipes the block clean (writes 4,096 zeros over it) and marks it as free in the bitmap:

```python
def clear_block(self, block_number: int):
    with open(self.diskname, "rb+") as f:
        f.seek(self.offset(block_number))
        f.write(b"\0" * self.BLOCK_SIZE)
    self.bitmap[block_number] = 0  # Mark as free
    self.update_disk_metadata()
```

**Act 2: Remove the Inode**

We delete the entry from the inode table:

```python
self.disk.inode_table.pop(self.inode_hash(name), None)
```

**Act 3: Remove the Directory Entry**

We read the parent directory, remove the filename entry, and write it back:

```python
parent_folder = self.path.split("/")[-1]
parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
if name in parent_folder_lookup:
    del parent_folder_lookup[name]
    self.update_entry(parent_folder, json.dumps(parent_folder_lookup, separators=COMPACT))
```

Here's the full deletion code:

```python
def delete_entry(self, name: str):
    inode = self.disk.inode_table[self.inode_hash(name)]
    blocks_used = inode["blocks_used"]
    size = inode["size"]

    # Act 1: Clear data blocks
    for block in blocks_used:
        self.disk.clear_block(block)

    # Act 2: Remove inode
    self.disk.inode_table.pop(self.inode_hash(name), None)

    # Act 3: Remove directory entry
    parent_folder = self.path.split("/")[-1]
    parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
    if name in parent_folder_lookup:
        del parent_folder_lookup[name]
        self.update_entry(parent_folder, json.dumps(parent_folder_lookup, separators=COMPACT))

    # Update parent's size
    self.disk.inode_table[self.inode_hash(parent_folder)]["size"] -= size
    self.disk.metadata["size"] -= size
    self.disk.update_disk_metadata()
```

Here's the critical insight: **Our implementation performs a secure delete—we overwrite the data blocks with zeros.** Most real file systems _don't_ do this. They just remove the inode and directory entry. The blocks are marked as free, but the data is still physically there, just invisible to the system.

This is why data recovery tools work. When you delete a file in ext4 or NTFS, the blocks are freed (the bitmap/allocation table is updated), but the file's data remains on disk. A recovery tool can scan the disk, find blocks that _look_ like they contain valid data, and reconstruct files. It's forensically perfect for recovering accidentally deleted files.

Our system erases the data, making recovery impossible. This is more like a "secure delete" feature you'd find in Windows (Cipher /w) or Linux (shred).

**Real-world parallel:** ext4 and NTFS both leave data on disk when you delete a file. The block allocation bitmap is updated (marking blocks as free), but the file's data bytes are untouched. This is a design choice—leaving data on disk is slightly faster and wastes no CPU cycles overwriting. It's also convenient for recovery. NTFS can even recover files if you simply undo a deletion before the system reuses the blocks. In contrast, secure delete tools overwrite the data, similar to our implementation.

---

## 5. Part 3: Connecting to the Cloud

When you spin up an EBS volume on AWS or a Managed Disk on Azure, what are you actually getting?

You're getting our `VirtualDisk` in the cloud.

Here's the abstraction:

| Our Implementation                                | Cloud Storage                                                                       |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `VirtualDisk` (a .bin file)                       | EBS volume (virtual disk image on shared SSDs)                                      |
| Blocks stored in the .bin file                    | Blocks replicated across multiple SSDs in a data center                             |
| `read_block(5)` seeks to offset, reads 4096 bytes | AWS firmware maps block 5 to physical location, returns 4096 bytes over the network |
| Bitmap tracks free/used blocks locally            | EBS metadata tier tracks allocation across the volume                               |
| Inode table stored in block 2                     | Volume metadata tier stores inode-like structures                                   |

When you SSH into an EC2 instance and run `touch myfile.txt`, you're issuing the same three-act file creation sequence we implemented. The Linux kernel's ext4 driver reads the inode table (stored in EBS blocks), finds free blocks using the bitmap, writes data, and updates the directory. The difference is that every block access goes over the network to AWS's storage tier. But the logic is identical.

Why are blocks important in the cloud?

**1. Fixed-size allocation prevents fragmentation.** If you could allocate arbitrary byte ranges, you'd have scattered data and slow seeks. With fixed 4KB blocks, data is aligned and efficient.

**2. Scattered blocks are tracked via inodes.** A large file spans many blocks across the disk. The inode stores the list of block numbers. Without inodes, the system would have no way to know which blocks belong to which file. In the cloud, this mapping is critical—blocks might be physically located on different SSDs in different racks.

**3. Efficient I/O alignment.** SSDs and network I/O are optimized for 4KB requests. If your file system issued requests for random byte ranges (3- bytes here, 7 bytes there), it would be a disaster. Standardizing on 4KB blocks means every I/O operation is aligned, predictable, and efficient.

**4. The bitmap prevents collisions.** Without tracking free/used blocks, the system might allocate the same block twice, corrupting both files. The bitmap ensures each block is used by at most one file.

**5. Distributed reliability.** In the cloud, blocks can be replicated across multiple SSDs. If one fails, another copy is available. The inode points to all replicas. The system automatically handles replication and failure detection.

The abstraction is so successful that your operating system doesn't need to know it's running on cloud storage. It issues the same read/write block commands it would for a local SSD. The cloud provider's storage layer translates those commands into actual hardware operations. Perfect encapsulation.

---

## 6. Limitations: Our Simple Design vs. Real Systems

Our implementation is educational. Real file systems are far more sophisticated. Here's how they differ:

| Our Implementation                                                    | Real File Systems (ext4/NTFS)                                    | Solution                                                                    |
| --------------------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **Bitmap** is a JSON array of 1,000,000+ integers                     | **Bitmap** is a packed bit array (1 bit per block)               | Saves 99% of space. A 100 GB disk needs only 3 MB for bitmap, not 300 MB    |
| **Inode table** is a single block, all in one place                   | **Inode table** split into block groups                          | If one block corrupts, you lose the entire table. Real systems replicate.   |
| **Sequential inode numbering** in our simple hash                     | **ext4 inodes** numbered sequentially within block groups        | Enables better caching and recovery; supports hard links naturally          |
| **No journaling** — if power fails mid-write, disk state is undefined | **Journaling** writes changes to a log first                     | Power failures leave the disk in a consistent state. Recovery is automatic. |
| **No permissions** — anyone can read/write any file                   | **POSIX permissions** (user, group, other; read, write, execute) | Security. Multiple users on one system.                                     |
| **Single-threaded** — one operation at a time                         | **Concurrent operations** with fine-grained locking              | Supports multithreaded systems and network access.                          |
| **No timestamps** — files don't remember creation/modification time   | **Timestamps** for every file (atime, mtime, ctime)              | Audit trails. Recovery. Incremental backups.                                |
| **No compression** — files stored as-is                               | **Optional compression** for larger files                        | Saves disk space; trade-off with CPU.                                       |
| **No deduplication** — identical blocks stored separately             | **Deduplication** (in some systems)                              | Cloud storage uses this heavily to save space                               |

The most important missing feature is **journaling**. Real file systems write changes to a journal (a log) before applying them to the main filesystem. If power fails mid-write, the system replays the journal on restart. Our implementation has no journal. If the `.bin` file is corrupted mid-write, the disk is unrecoverable.

Real-world systems also use **B-trees** or **hash tables** for large directories instead of flat arrays. As a directory grows to millions of files, a linear scan becomes catastrophically slow. ext4 uses hash trees; NTFS uses B-trees. Our simple dictionary works for educational purposes but doesn't scale.

---

## 7. Try It Yourself

Here's a runnable example. Create a disk, make directories, create files, and visualize the structure:

```python
# Create a 6 MB virtual disk
disk = VirtualDisk("example", 6)
fs = FileSystem(disk)

# Create folders
fs.mkdir("documents")
fs.mkdir("projects")

# Enter documents folder
fs.cd("documents")
fs.create_file("notes.txt", "My project notes\nLine 2\nLine 3")

# Create a subfolder
fs.mkdir("archive")
fs.cd("archive")
fs.create_file("old-notes.txt", "Archived notes from last year")

# Go back to documents
fs.cd("..")
fs.cd("..")  # Back to root

# Enter projects
fs.cd("projects")
fs.create_file("README.md", "# My Project\nThis is a project.")
fs.mkdir("src")
fs.cd("src")
fs.create_file("main.py", "print('Hello, world!')")

# Visualize the entire tree
fs.cd("/")  # Root
fs.tree()

# Output:
# root/
# ├── documents/
# │   ├── notes.txt
# │   └── archive/
# │       └── old-notes.txt
# ├── projects/
# │   ├── README.md
# │   └── src/
# │       └── main.py
```

You can also inspect the disk state:

```python
# See all inodes
print(fs.disk.inode_table)

# Read a file
content = fs.open_file("notes.txt")
print(content)

# Delete a file
fs.delete_file("notes.txt")

# Check what blocks are free
free_blocks = [i for i, bit in enumerate(fs.disk.bitmap) if bit == 0]
print(f"Free blocks: {free_blocks}")
print(f"Used: {sum(fs.disk.bitmap)} blocks, Free: {len(free_blocks)} blocks")
```

---

## 8. Key Takeaways

1. **Disks work in fixed-size blocks (4 KB), not individual bytes.** This prevents fragmentation and enables efficient, aligned I/O. The file system requests "read block N," and the disk computes the byte position using `offset = N * BLOCK_SIZE`.

2. **The bitmap tracks which blocks are free and which are used.** A simple array of bits (or in our case, integers) tells the system the allocation state. Scanning the bitmap finds free blocks for new files.

3. **Inodes store file metadata and the list of blocks holding the file's data.** A file might span multiple blocks (e.g., blocks [3, 5, 7]). The inode remembers this mapping. The filename is stored in the parent directory, not the inode, enabling hard links.

4. **Directories are just files containing a dictionary of {filename: inode} mappings.** There's no special directory storage. Navigating the file tree (`cd`) just updates a path string until you actually interact with files.

5. **The cloud uses the same structure.** An EBS volume is a virtual disk image on shared SSDs. AWS translates your block requests into physical I/O. Blocks enable efficient allocation, replication, and failure recovery. The abstraction is seamless—your OS doesn't know (and doesn't care) if the disk is local or in the cloud.

File systems are one of computing's great achievements—a universal language spoken by every operating system, every device, every cloud provider. Understanding their structure demystifies storage, making system design, performance optimization, and debugging far clearer. Now when you hear "inode," "block," or "bitmap," you know exactly what's happening under the hood.

---

_Built in Python as a learning project. ~350 lines. No external dependencies. Full source available on GitHub._
