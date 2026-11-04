from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tidy import organize


class TidyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def run_tidy(self, apply=False):
        with redirect_stdout(StringIO()):
            return organize(self.folder, apply)

    def test_preview_changes_nothing(self):
        photo = self.folder / "photo.jpg"
        photo.write_bytes(b"photo")
        self.assertEqual(self.run_tidy(), 1)
        self.assertEqual(list(self.folder.iterdir()), [photo])

    def test_move_preserves_contents_and_repeat_does_nothing(self):
        (self.folder / "photo.JPG").write_bytes(b"photo")
        self.assertEqual(self.run_tidy(True), 1)
        self.assertEqual((self.folder / "Images/photo.JPG").read_bytes(), b"photo")
        self.assertFalse((self.folder / "photo.JPG").exists())
        self.assertEqual(self.run_tidy(True), 0)

    def test_collision_preserves_both_files(self):
        (self.folder / "Images").mkdir()
        (self.folder / "Images/photo.jpg").write_bytes(b"old")
        (self.folder / "photo.jpg").write_bytes(b"new")
        self.assertEqual(self.run_tidy(True), 0)
        self.assertEqual((self.folder / "photo.jpg").read_bytes(), b"new")
        self.assertEqual((self.folder / "Images/photo.jpg").read_bytes(), b"old")

    def test_unknown_hidden_and_nested_files_stay_put(self):
        for name in ["script.py", ".hidden.jpg"]:
            (self.folder / name).touch()
        (self.folder / "nested").mkdir()
        (self.folder / "nested/photo.jpg").touch()
        self.assertEqual(self.run_tidy(True), 0)
        self.assertTrue((self.folder / "nested/photo.jpg").exists())

    def test_category_name_taken_by_file(self):
        (self.folder / "Images").touch()
        (self.folder / "photo.jpg").touch()
        self.assertEqual(self.run_tidy(True), 0)
        self.assertTrue((self.folder / "photo.jpg").exists())


if __name__ == "__main__":
    unittest.main()
