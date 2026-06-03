import json
import os

COMPACT = (",",":")


class VirtualDisk:
    def __init__(self,diskname,disksize_mb):
        self.BLOCK_SIZE = 4096 # 4KB
        extension = ""
        if ".bin" not in diskname:
            extension = ".bin"

        self.diskname = diskname + extension
        self.disksize = disksize_mb*1024*1024 #from MB to bytes
        self.total_blocks = self.disksize // self.BLOCK_SIZE

        self.metadata ={
            "magic":"MYFSYS",
            "disksize":self.disksize,
            "total_blocks":self.total_blocks,
            "super_block":0,
            "bitmap_block":1,
            "inode_table":2,
            "data_block":3,
            "free_blocks":self.total_blocks - 3,
            "used_blocks":3
        }

        self.bitmap = [0]*self.total_blocks 

        # Mark reserved blocks as used
        for i in range(3):
            self.bitmap[i] = 1

        metadata_b = json.dumps(self.metadata,
                                separators=COMPACT).encode()

        bitmap_b = json.dumps(self.bitmap,
                              separators=COMPACT).encode()

        self.inode_table = {}

        inode_table_b = json.dumps(
            self.inode_table,
            separators=COMPACT
        ).encode()

        with open(self.diskname, "wb") as f:

            f.seek(self.offset(0))
            f.write(metadata_b)

            f.seek(self.offset(1))
            f.write(bitmap_b)

            f.seek(self.offset(2))
            f.write(inode_table_b)

            f.seek(self.disksize - 1)
            f.write(b"\0")

        print(f"Disk created with name {self.diskname}")
        print(f"Size of disk: {self.disksize // 1024} KB")
        print(f"Total block: {self.total_blocks}")
    
    def offset(self, block_number):
        return int(block_number) * self.BLOCK_SIZE
    
    def update_disk_metadata(self):

    # Clear reserved blocks on disk before rewriting them
        for block in range(3):
            with open(self.diskname, "rb+") as f:
                f.seek(self.offset(block))
                f.write(b"\0" * self.BLOCK_SIZE)

        # Ensure reserved blocks stay marked as used in bitmap
        for i in range(3):
            self.bitmap[i] = 1

        self.metadata["used_blocks"] = sum(self.bitmap)

        self.metadata["free_blocks"] = self.metadata["total_blocks"] - self.metadata["used_blocks"]
        
        with open(self.diskname, "rb+") as f:

            f.seek(0)
            f.write(json.dumps(self.metadata,separators=COMPACT).encode())
            f.seek(self.offset(self.metadata["bitmap_block"]))
            f.write(json.dumps(self.bitmap,separators=COMPACT).encode())

            f.seek(self.offset(self.metadata["inode_table"]))
            f.write(json.dumps(self.inode_table,separators=COMPACT).encode())

    @classmethod
    def load(cls, diskname):
        """Open an existing .bin disk without overwriting it."""

        disk = object._new_(cls)
        disk.BLOCK_SIZE = 4096
        disk.diskname = diskname

        with open(diskname, "rb") as f:

            disk.metadata = json.loads(f.read(disk.BLOCK_SIZE).strip(b"\0").decode())

            f.seek(disk.metadata["bitmap_block"] * disk.BLOCK_SIZE)
            disk.bitmap = json.loads(f.read(disk.BLOCK_SIZE).decode().strip("\0"))

            f.seek(disk.metadata["inode_table"] * disk.BLOCK_SIZE)
            disk.inode_table = json.loads(f.read(disk.BLOCK_SIZE).strip(b"\0").decode())

        disk.disksize = disk.metadata["disksize"]
        disk.total_blocks = disk.metadata["total_blocks"]

        return disk
    
    def write_block(self,data:str):
        data_block = self.metadata["data_block"]
        free_block = self.bitmap.index(0, data_block)
        self.bitmap[free_block] = 1
        with open(self.diskname, "rb+") as f:
            f.seek(self.offset(free_block))
            f.write(data.encode())
        self.update_disk_metadata()
        return free_block, len(data)
    
    def update_block(self,data:str,block_number:int):
        with open(self.diskname, "rb+") as f:
            f.seek(self.offset(block_number))
            f.write(data.encode())
        self.update_disk_metadata()
        return block_number, len(data)
    
    def read_block(self, block_number:int):
        with open(self.diskname, "rb") as f:
            f.seek(self.offset(block_number))
            return f.read(self.BLOCK_SIZE)
    
    def clear_block(self, block_number:int):
        with open(self.diskname, "rb+") as f:
            f.seek(self.offset(block_number))
            f.write(b"\0" * self.BLOCK_SIZE)
        self.bitmap[block_number] = 0
        self.update_disk_metadata()
        return 
    
    def print_block(self, block_number:int):
        data = self.read_block(block_number)
        print(f"Block {block_number} content:")
        print(data.decode().strip("\0"))


class FileSystem:
    def __init__(self, disk:VirtualDisk):
        self.disk = disk
        root_inode = self.inode_hash("root")
        root_folder_content = {
            ".": root_inode,
            "..": root_inode
        }

        block_used,size = self.disk.write_block(json.dumps(root_folder_content,separators=COMPACT))
        blocks_used = [block_used]
        self.create_inode("root",blocks_used,size,"dir")
        self.path = "root"
    
    def inode_hash(self, name:str):
        inode_hash_number = sum([ord(c)*i for i,c in enumerate(name,1)]) % self.disk.BLOCK_SIZE
        return "inode" + str(inode_hash_number)
    
    def cwd(self):
        return self.path.split("/")[-1]
    
    def create_inode(self,name:str,blocks_used:list,size:int,type_:str):
        '''Creates an inode for a file or directory.'''

        file_inode_hash = self.inode_hash(name)
        inode ={
            "blocks_used": blocks_used,
            "size": size,
            "type":type_
        }

        if self.disk.inode_table is None:
            inode_table = {}

        self.disk.inode_table[file_inode_hash] = inode
        self.disk.update_disk_metadata()
    
    @classmethod
    def load(cls, disk:VirtualDisk):
        fs = object._new_(cls)
        fs.disk = disk
        fs.path = "root"
        return fs
    
    def create_entry(self,name:str,content:str,type_:str):
        '''Creates file
        1. write content of file in disk
        2. create inode ands store in inode table of disk
        3. map file name and inode in folder block
        '''

        parent_folder = self.path.split("/")[-1]
        file_inode_hash = self.inode_hash(name)
        blocks_used = []
        size = 0
        for chunk in range((len(content)// self.disk.BLOCK_SIZE) + 1):
            block,chunk_size = self.disk.write_block(content[chunk*self.disk.BLOCK_SIZE:(chunk+1)*self.disk.BLOCK_SIZE])
            blocks_used.append(block)
            size += chunk_size
        
        self.create_inode(name, blocks_used, size, type_)
        parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
        parent_folder_lookup[name] = file_inode_hash
        self.update_entry(parent_folder, json.dumps(parent_folder_lookup,separators=COMPACT))
    
    def update_entry(self,name:str,content:str):
        '''Updates content of file or directory.'''
        inode = self.disk.inode_table[self.inode_hash(name)]
        blocks_used = inode["blocks_used"]
        for block in blocks_used:
            self.disk.clear_block(block)
        
        new_blocks_used = []
        size = 0
        for chunk in range((len(content)// self.disk.BLOCK_SIZE) + 1):
            block,chunk_size = self.disk.write_block(content[chunk*self.disk.BLOCK_SIZE:(chunk+1)*self.disk.BLOCK_SIZE])
            new_blocks_used.append(block)
            size += chunk_size
        
        inode["blocks_used"] = new_blocks_used
        inode["size"] = size
        self.disk.update_disk_metadata()
        return
    
    def open_entry(self,name:str):
        '''Reads content of file or directory.'''
        inode = self.disk.inode_table[self.inode_hash(name)]
        blocks_used = inode["blocks_used"]
        content = ""
        for block in blocks_used:
            content += self.disk.read_block(block).decode().strip("\0")
        return content
    
    def delete_entry(self,name:str):
        '''Deletes a file or directory.'''
        inode = self.disk.inode_table[self.inode_hash(name)]
        blocks_used = inode["blocks_used"]
        for block in blocks_used:
            self.disk.clear_block(block)
        
        self.disk.inode_table.pop(self.inode_hash(name), None)

        parent_folder = self.path.split("/")[-1]
        parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
        if name in parent_folder_lookup:
            del parent_folder_lookup[name]
            self.update_entry(parent_folder, json.dumps(parent_folder_lookup,separators=COMPACT))
        
        self.disk.update_disk_metadata()

        return
    
    def file_exists(self,name:str):
        '''Checks if a file or directory exists.'''
        parent_folder = self.path.split("/")[-1]
        parent_folder_lookup = json.loads(self.open_entry(parent_folder).strip())
        return name in parent_folder_lookup
    
    def create_file(self,name:str,content:str):
        self.create_entry(name, content, "file")

    def delete_file(self,name:str):
        if not self.file_exists(name):
            print(f"File {name} does not exist.")
            return
        self.delete_entry(name)
    
    def open_file(self,name:str):
        if not self.file_exists(name):
            print(f"File {name} does not exist.")
            return
        return self.open_entry(name)
    
    def mkdir(self,name:str):
        folder_inode = self.inode_hash(name)
        self.create_entry(name, json.dumps({".": folder_inode, "..": folder_inode},separators=COMPACT), "dir")
    
    def rmdir(self,name:str):
        entries = json.loads(self.open_entry(name).strip())
        for entry,inode in entries.items():
            if entry not in [".",".."]:
                type_ = self.disk.inode_table[inode]["type"]
                if type_ == "file":
                    self.delete_file(entry)
                elif type_ == "dir":
                    self.rmdir(entry)
        self.cd("..")
        self.delete_entry(name)
        return
    
    def ls(self):
        if self.path == "root":
            curent_folder = "root"
        else:
            curent_folder = self.path.split("/")[-1]
        
        content = self.open_entry(curent_folder)
        print("-"*20)
        print(self.path)
        return json.loads(content.strip())
    
    def cd(self,folder_name:str):
        if folder_name == ".":
            return
        elif folder_name == "..":
            cwd = self.cwd()
            if cwd == "root":
                return
            else:
                path = self.path.split("/")[:-1]
                self.path = ""
                for p in path:
                    self.path = self.path + "/" + p 
            return
        else:
            self.path = self.path + "/" + folder_name

    def tree(self,name="root",prefix="",is_root=True):
        if is_root:
            print(f"{name}/")
        entries = json.loads(self.open_entry(name).strip())
        items = [k for k in entries if k not in [".",".."]]
        for i,entry in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            inode = self.disk.inode_table[entries[entry]]
            type_label = "/" if inode["type"] == "dir" else ""
            print(f"{prefix}{connector}{entry}{type_label}")
            if inode["type"] == "dir":
                extension = "    " if is_last else "│   "
                self.tree(entry, prefix + extension, False)
    
if __name__ == "__main__":
    disk = VirtualDisk("disk", 2)
    fs = FileSystem(disk)
    fs.ls()
    fs.mkdir("docs")
    fs.cd("docs")
    fs.create_file("file1.txt", "Hello, World!")
    # fs.cd("root")
    print(fs.ls())
    fs.tree()

    