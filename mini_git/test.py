#Taken from gpt to test the git.py
import unittest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from git import git, clone  

class TestGit(unittest.TestCase):    
    def setUp(self):
        self.g = git()
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)  
        os.makedirs('.git/objects', exist_ok=True)  

    def tearDown(self):
        os.chdir('/')  
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hash_blob_basic(self):
        content = b"test content"
        hash_val = self.g.hash_blob(content)
        self.assertEqual(len(hash_val), 40)  
        self.assertTrue(os.path.exists(f".git/objects/{hash_val[:2]}/{hash_val[2:]}"))  

    def test_hash_blob_empty(self):
        content = b""
        hash_val = self.g.hash_blob(content)
        self.assertEqual(len(hash_val), 40)

    def test_write_blob_file_exists(self):
        with open("test.txt", "w") as f:
            f.write("hello world")
        hash_val = self.g.write_blob("test.txt")
        self.assertEqual(len(hash_val), 40)
        self.assertTrue(os.path.exists(f".git/objects/{hash_val[:2]}/{hash_val[2:]}"))

    def test_write_blob_file_not_found(self):
        with self.assertRaises(RuntimeError):
            self.g.write_blob("nonexistent.txt")

    def test_write_tree_empty_dir(self):
        hash_val = self.g.write_tree()
        self.assertEqual(len(hash_val), 40)

    def test_write_tree_with_files(self):
        with open("file1.txt", "w") as f:
            f.write("content1")
        with open("file2.txt", "w") as f:
            f.write("content2")
        hash_val = self.g.write_tree()
        self.assertEqual(len(hash_val), 40)

    def test_commit_tree_basic(self):
        tree_sha = "abcd1234567890abcdef1234567890abcdef"  
        commit_sha = self.g.commit_tree(tree_sha, message="Test commit")
        self.assertEqual(len(commit_sha), 40)

    def test_commit_tree_with_parent(self):
        tree_sha = "abcd1234567890abcdef1234567890abcdef"
        parent_sha = "1234567890abcdef1234567890abcdef12"
        commit_sha = self.g.commit_tree(tree_sha, parent_sha, "Test with parent")
        self.assertEqual(len(commit_sha), 40)

class TestClone(unittest.TestCase):
    
    def setUp(self):
        self.c = clone()
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_repo(self):
        self.c.init_repo(self.temp_dir)
        self.assertTrue((self.temp_dir / ".git").exists())
        self.assertTrue((self.temp_dir / ".git" / "objects").exists())
        self.assertTrue((self.temp_dir / ".git" / "refs" / "heads").exists())
        self.assertEqual((self.temp_dir / ".git" / "HEAD").read_text(), "ref: refs/heads/main\n")

    @patch('urllib.request.urlopen')
    def test_fetch_refs_valid(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"001e# service=git-upload-pack\n00000000capabilities^{}0000\n"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        refs = self.c.fetch_refs("https://github.com/user/repo.git")
        self.assertIsInstance(refs, dict)
        mock_urlopen.assert_called_once()

    def test_fetch_refs_invalid_url(self):
        with self.assertRaises(RuntimeError):
            self.c.fetch_refs("invalid-url")

    @patch('urllib.request.urlopen')
    def test_download_pack(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"PACK\x00\x00\x00\x02\x00\x00\x00\x00"  
        mock_urlopen.return_value.__enter__.return_value = mock_response
        refs = {"HEAD": "abcd1234"}
        pack = self.c.download_pack("https://github.com/user/repo.git", refs)
        self.assertIsInstance(pack, bytes)
        mock_urlopen.assert_called_once()

    def test_parse_pack_header(self):
        pack = b"PACK\x00\x00\x00\x02\x00\x00\x00\x02rest"  
        n_objs, remaining = self.c.parse_pack_header(pack)
        self.assertEqual(n_objs, 2)
        self.assertEqual(remaining, b"rest")

    def test_parse_pack_header_invalid(self):
        with self.assertRaises(ValueError):
            self.c.parse_pack_header(b"INVALID")


if __name__ == '__main__':
    unittest.main()