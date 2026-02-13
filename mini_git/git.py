import sys,os,struct
from pathlib import Path
import zlib,hashlib,time
from typing import Dict, Tuple
import urllib.request



class git:
    DIR_MODE = 40000
    FILE_MODE = 100644
    
    def hash_blob(self, content, obj_type="blob"):
        try:
            header = f"{obj_type} {len(content)}\0".encode()
            content = header + content
            hash_val = hashlib.sha1(content).hexdigest()
            os.makedirs(f".git/objects/{hash_val[:2]}", exist_ok=True)
            with open(f".git/objects/{hash_val[:2]}/{hash_val[2:]}", "wb") as wb:
                wb.write(zlib.compress(content))
            return hash_val
        except OSError as e:
            raise RuntimeError(f"Failed to write object: {e}")

    def write_blob(self,file_path):
        try:
            with open(file_path, "rb") as f:
                return self.hash_blob(f.read())
        except (OSError, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to read file {file_path}: {e}")

    def encode_mode(self,mode, name, hash_val) -> bytes:
        try:
            return f"{mode} {name}".encode() + b"\0" + bytes.fromhex(hash_val)
        except ValueError as e:
            raise RuntimeError(f"Invalid hash for {name}: {e}")

    def write_tree(self,root="."):
        hash_map = {}
        try:
            for entry in os.scandir(root):
                if entry.name.startswith((".", "_")):  
                    if entry.name == ".git":
                        continue
                if entry.is_file(follow_symlinks=False):
                    hash_val = self.write_blob(os.path.join(root, entry.name))
                    hash_map[entry.name] = self.encode_mode(self.FILE_MODE, entry.name, hash_val)
                elif entry.is_dir(follow_symlinks=False):
                    hash_val = self.write_tree(os.path.join(root, entry.name))
                    hash_map[entry.name] = self.encode_mode(self.DIR_MODE, entry.name, hash_val)
        except OSError as e:
            raise RuntimeError(f"Failed to scan directory {root}: {e}")
        hash_list = [v for k, v in sorted(hash_map.items())]
        content = b"".join(hash_list)
        return self.hash_blob(content, "tree")
    
    def commit_tree(self,tree_sha, parent_sha=None, message=""):
        ts = int(time.time())
        content_parts = [f"tree {tree_sha}"]
        if parent_sha:
            content_parts.append(f"parent {parent_sha}")
        content_parts.extend([f"author auth <auth_email@gmail.com> {ts} +0000", f"committer committer <comit_email@gmail.com> {ts} +0000", "", message])
        content = "\n".join(content_parts).encode()
        return self.hash_blob(content, "commit")



class clone:
    def init_repo(self,parent):
        (parent / ".git").mkdir(parents=True, exist_ok=True)
        (parent / ".git" / "objects").mkdir(parents=True, exist_ok=True)
        (parent / ".git" / "refs").mkdir(parents=True, exist_ok=True)
        (parent / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (parent / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    def fetch_refs(self,url):
        try:
            req = urllib.request.Request(f"{url}/info/refs?service=git-upload-pack")
            with urllib.request.urlopen(req) as f:
                data = f.read().decode('utf-8', errors='ignore')
                refs = {}
                for i in data.split('\n'):
                    if i and not i.startswith('#'):
                        parts = i.split()
                        if len(parts) >= 2:  
                            refs[parts[1]] = parts[0]
                return refs
        except Exception as e:
            raise RuntimeError(f"Ref fetch failed: {e}")
        
    def download_pack(self,url, refs) :
        body = b"0011command=fetch0001000fno-progress" + b"".join(b"0032want " + ref.encode() + b"\n" for ref in refs.values()) + b"0009done\n0000"
        try:
            req = urllib.request.Request(f"{url}/git-upload-pack", data=body, headers={"Git-Protocol": "version=2"})
            with urllib.request.urlopen(req) as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Pack download failed: {e}")

    def parse_pack_header(self,pack) :
        if len(pack) < 12 or not pack.startswith(b"PACK"):
            raise ValueError("Invalid or empty pack")
        v, n_objs =struct.unpack("!II", pack[4:12])
        if v != 2:
            raise ValueError(f"Unsupported pack version: {v}")
        return n_objs, pack[12:]

    def next_size_type(self,data) :
        byte = data[0]
        obj_type = {1: "commit", 2: "tree", 3: "blob", 4: "tag", 6: "ofs_delta", 7: "ref_delta"}.get((byte & 0b_0111_0000) >> 4, "unknown")
        size = byte & 0b_0000_1111
        i, shift = 1, 4
        while byte & 0b_1000_0000 and i < len(data):
            byte = data[i]
            size |= (byte & 0b_0111_1111) << shift
            shift += 7
            i += 1
        return obj_type, size, data[i:]

    def unpack_objects(self,parent, pack, n_objs):
        for _ in range(n_objs):
            obj_type, _, pack = self.next_size_type(pack)
            if obj_type in ["commit", "tree", "blob", "tag"]:
                dec = zlib.decompressobj()
                content = dec.decompress(pack)
                pack = dec.unused_data
                self.write_object(parent, obj_type, content)
            elif obj_type == "ref_delta":
                base_sha = pack[:20].hex()
                pack = pack[20:]
                dec = zlib.decompressobj()
                delta = dec.decompress(pack)
                pack = dec.unused_data
                base_ty, base_content = self.read_object(parent, base_sha)
                self.write_object(parent, base_ty, base_content)  
            else:
                raise RuntimeError(f"Unsupported type: {obj_type}")

    def write_object(self,parent, ty, content):
        full = ty.encode() + b" " + f"{len(content)}".encode() + b"\0" + content
        sha = hashlib.sha1(full, usedforsecurity=False).hexdigest()
        c = zlib.compress(full, level=zlib.Z_BEST_SPEED)
        path = parent / ".git" / "objects" / sha[:2] / sha[2:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(c)
        return sha

    def read_object(self,parent, sha):
        path = parent / ".git" / "objects" / sha[:2] / sha[2:]
        full = zlib.decompress(path.read_bytes())
        ty, content = full.split(b"\0", maxsplit=1)
        return ty.decode(), content

    def render_tree(self,parent, tree_sha, target) :
        _, tree = self.read_object(parent, tree_sha)
        while tree:
            me = tree.find(b" ")
            if me == -1: break
            mode = tree[:me]
            tree = tree[me + 1:]
            ne = tree.find(b"\0")
            name = tree[:ne]
            sha = tree[ne + 1 : ne + 21].hex()
            tree = tree[ne + 21:]
            if mode == b"40000":
                self.render_tree(parent, sha, target / name.decode())
            elif mode in [b"100644", b"100755"]:
                _, content = self.read_object(parent, sha)
                (target / name.decode()).write_bytes(content)

    def clone_repo(self,url, target_dir):
        parent = Path(target_dir)
        self.init_repo(parent)
        refs = self.fetch_refs(url)
        for ref, sha in refs.items():
            (parent / ".git" / ref).write_text(sha + "\n")
        pack = self.download_pack(url, refs)
        n_objs, pack = self.parse_pack_header(pack)
        self.unpack_objects(parent, pack, n_objs)
        head_sha = refs.get("HEAD")
        if head_sha:
            _, commit = self.read_object(parent, head_sha)
            tree_sha = commit.split(b"\n")[0].split()[1].decode()
            self.render_tree(parent, tree_sha, parent)



def main():
    if len(sys.argv) < 2:
        raise RuntimeError("Usage: python script.py <command> [args]") 
    command = sys.argv[1]
    try:
        if command == "init":
            os.makedirs(".git/objects", exist_ok=True)
            os.makedirs(".git/refs", exist_ok=True)
            with open(".git/HEAD", "w") as f:
                f.write("ref: refs/heads/main\n")
            print("Initialized git directory")
        
        elif command == "cat-file":
            if len(sys.argv) < 4:
                raise RuntimeError("Usage: cat-file -p <hash>")
            param, hash_val = sys.argv[2], sys.argv[3]
            if param == "-p":
                try:
                    with open(f".git/objects/{hash_val[:2]}/{hash_val[2:]}", "rb") as f:
                        c = f.read()
                        dec = zlib.decompress(c)
                        obj_type, rest = dec.split(b"\0", maxsplit=1)
                        if obj_type.startswith(b"blob"):
                            print(rest.decode("utf-8"), end="")
                        else:
                            raise RuntimeError("cat-file -p only supports blobs")
                except (OSError, zlib.error, ValueError) as e:
                    raise RuntimeError(f"Failed to read object {hash_val}: {e}")
        
        elif command == "hash-object":
            if len(sys.argv) < 4 or sys.argv[2] != "-w":
                raise RuntimeError("Usage: hash-object -w <file>")
            file_path = sys.argv[3]
            print(git.write_blob(file_path))
        
        elif command == "ls-tree":
            if len(sys.argv) < 4 or sys.argv[2] != "--name-only":
                raise RuntimeError("Usage: ls-tree --name-only <hash>")
            hash_val = sys.argv[3]
            try:
                with open(f".git/objects/{hash_val[:2]}/{hash_val[2:]}", "rb") as f:
                    data = zlib.decompress(f.read())
                    obj_type, bd = data.split(b"\0", maxsplit=1)
                    if not obj_type.startswith(b"tree"):
                        raise RuntimeError("ls-tree requires a tree object")
                    while len(bd) >= 21:  
                        mode_name, bd = bd.split(b"\0", maxsplit=1)
                        mode, name = mode_name.decode().split(" ", 1)
                        bd = bd[20:]  
                        print(name)
            except (OSError, zlib.error, ValueError) as e:
                raise RuntimeError(f"Failed to parse tree {hash_val}: {e}")
        
        elif command == "write-tree":
            print(git.write_tree())
        
        elif command == "commit-tree":
            if len(sys.argv) < 5 or sys.argv[3] != "-m":
                raise RuntimeError("Usage: commit-tree <tree_sha> [-p <parent_sha>] -m <message>")
            tree_sha = sys.argv[2]
            parent_sha = None
            message = sys.argv[4]
            if len(sys.argv) > 5 and sys.argv[4] == "-p":
                parent_sha = sys.argv[5]
                message = sys.argv[7] if len(sys.argv) > 7 else ""
            print(git.commit_tree(tree_sha, parent_sha, message))
            
        elif command=="clone":
            if(len(sys.argv)!=4):
                raise RuntimeError("Usage: python clone.py <repo_url> <target_dir>")
            try:
                clone.clone_repo(sys.argv[2],sys.argv[3])
                print("Cloned successfully.")
            except RuntimeError as e:
                print(f"Error: {e}")
                sys.exit(1)
                
        else:
            raise RuntimeError(f"Unknown command :{command}")
        
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)



if __name__ == "__main__":
    main()