from flask import Flask, render_template,request,redirect,jsonify
from virtualDisk import VirtualDisk, FileSystem
import os
import json
app = Flask(__name__)
metadata = {}
diskname = ""

def load_fs(disk_name, folder_path=None):
    """Load disk and filesystem, navigate to folder_path. Returns (disk, fs)."""
    disk = VirtualDisk.load(disk_name)
    fs = FileSystem.load(disk)
    if folder_path and folder_path != "root":
        folders = folder_path.split("/")
        if folders[0] == "root":
            folders = folders[1:]
        for folder in folders:
            fs.cd(folder)
    return disk, fs

def redirect_to_disk(disk_name, fs):
    """Redirect to the current fs.path."""
    if fs.path == "root":
        return redirect(f"/disk/{disk_name}")
    return redirect(f"/disk/{disk_name}/{fs.path}")

@app.route("/")
def home():
    disks = []
    for entry in os.scandir(os.getcwd()):
        if entry.is_file() and entry.name.endswith(".bin"):
            d = VirtualDisk.load(entry.name)
            used_kb = round(d.metadata["used_blocks"] * d.BLOCK_SIZE / 1024, 1)
            size = d.metadata["size"] // 1024
            disks.append({"name": entry.name, "used_kb": size,"total_kb": round(d.metadata["total_blocks"] * d.BLOCK_SIZE / 1024, 1)})

    return render_template("index.html",disks=disks,metadata=metadata,diskname=diskname)


@app.route("/create-disk",methods = ['POST'])
def create_disk():
    disk_name = request.form.get("diskName")
    disk_size = int(request.form.get("diskSize"))

    vd = VirtualDisk(disk_name,disk_size)
    fs=FileSystem(vd)
    
    return redirect("/")

@app.route("/read-disk-metadata",methods = ["POST"])
def read_disk_metadata():
    global metadata
    global diskname
    diskname = request.form.get("disk-name")
    disk = VirtualDisk.load(diskname)
    metadata = disk.metadata
    return redirect("/")

@app.route("/disk/<string:disk_name>")
@app.route("/disk/<string:disk_name>/<path:folder_path>")
def disk(disk_name, folder_path="root"):
    disk, fs = load_fs(disk_name, folder_path)

    entries_dict = fs.ls()
    files = []
    for name, inode_hash in entries_dict.items():
        if name in [".", ".."]:
            continue
        inode = disk.inode_table.get(inode_hash, {})
        files.append({
            "name": name,
            "size": inode.get("size", 0),
            "type": inode.get("type", "file")
        })

    free_space = disk.metadata["free_blocks"] * disk.BLOCK_SIZE
    return render_template("disk.html", files=files, diskname=disk_name, free_space=free_space, folder_path=fs.path)
    
@app.route("/open-file")
def open_file():
    disk_name = request.args.get("disk")
    filename = request.args.get("filename")
    disk = VirtualDisk.load(disk_name)
    fs = FileSystem.load(disk)
    content = fs.open_entry(filename)
    return jsonify({"filename": filename, "content": content})

@app.route("/create-file",methods = ["POST"])
def create_file():
    diskname = request.form.get("diskname")
    filename = request.form.get("filename")
    file_content = str(request.form.get("file-content")).strip()
    folder_path = request.form.get("folder_path", "root")
    disk, fs = load_fs(diskname, folder_path)
    fs.create_file(filename, file_content)
    return redirect_to_disk(diskname, fs)

@app.route("/delete-disk",methods = ["POST"])
def delete_disk():
    diskname = request.form.get("disk-name")
    if os.path.isfile(diskname):
        os.remove(diskname)
    return redirect("/")

@app.route("/delete-file",methods = ["POST"])
def delete_file():
    diskname = request.form.get("disk-name")
    filename = request.form.get("file-name")
    folder_path = request.form.get("folder_path", "root")
    disk, fs = load_fs(diskname, folder_path)
    fs.delete_file(filename)
    return redirect_to_disk(diskname, fs)

@app.route("/mkdir",methods = ["POST"])
def mkdir():
    diskname = request.form.get("diskname")
    foldername = request.form.get("foldername")
    folder_path = request.form.get("folder_path", "root")
    disk, fs = load_fs(diskname, folder_path)
    fs.mkdir(foldername)
    return redirect_to_disk(diskname, fs)

@app.route("/rmdir",methods = ["POST"])
def rmdir():
    diskname = request.form.get("disk-name")
    foldername = request.form.get("folder-name")
    folder_path = request.form.get("folder_path", "root")
    disk, fs = load_fs(diskname, folder_path)
    fs.rmdir(foldername)
    return redirect_to_disk(diskname, fs)

if __name__ == "__main__":
    app.run(debug=True)
