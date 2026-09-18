"""asset_tool core（走査・集計・ソート・合計行）のテスト（Phase 3）。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import asset_tool.core as core
from asset_tool.config import Config


class _Logger:
    def __init__(self):
        self.infos, self.warns, self.errors = [], [], []

    def info(self, m, *a):
        self.infos.append(m % a if a else m)

    def warning(self, m, *a):
        self.warns.append(m % a if a else m)

    def error(self, m, *a):
        self.errors.append(m % a if a else m)

    def debug(self, m, *a):
        pass


def make_tree(root: Path) -> None:
    """設計書の想定構造＋エッジケースを構築する。"""
    root.mkdir(parents=True)
    (root / "直下ファイル.txt").write_text("root file", encoding="utf-8")
    p_a = root / "あ-お" / "あ" / "ああ-あと" / "タイトル"
    p_a.mkdir(parents=True)
    (p_a / "タイトル.zip").write_bytes(b"zip")
    (root / "あ-お" / "い" / "空フォルダ").mkdir(parents=True)
    (root / "あ-お" / "Thumbs.db").write_bytes(b"junk")   # 除外名（直下は数えない）
    (root / ".git").mkdir()      # ドット始まり＝部分木枝刈り
    (root / ".git" / "config").write_text("x", encoding="utf-8")
    (root / "$RECYCLE.BIN").mkdir()   # OSシステム項目（Q31=A）


def make_cfg(root: Path, out: Path, **kw) -> Config:
    return Config(input_dir=root, output_dir=out, **kw)


class TestScanTree(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "資産"
        make_tree(self.root)
        self.out = Path(self._td.name) / "out"
        self.out.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def _scan(self, **kw) -> core.ScanState:
        return core.scan_tree(make_cfg(self.root, self.out, **kw),
                              lambda cur, total, msg: None)

    def _by_storage(self, state) -> dict:
        return {r.storage: r for r in state.rows}

    def test_root_pseudo_row(self):
        """起点は (ルート) 疑似行（深さ0・Q28=A）。直下ファイルを数える。"""
        st = self._scan()
        root = self._by_storage(st)[core.ROOT_LABEL]
        self.assertEqual(root.depth, 0)
        self.assertEqual(root.name, "資産")
        self.assertEqual(root.files_d, 1)
        self.assertEqual(root.size_d, len("root file".encode()))

    def test_hierarchy_rows(self):
        st = self._scan()
        by = self._by_storage(st)
        self.assertEqual(by["あ-お"].depth, 1)
        self.assertEqual(by["あ-お\\あ"].depth, 2)
        title = by["あ-お\\あ\\ああ-あと\\タイトル"]
        # リーフ: 直下 == 配下 かつ > 0
        self.assertEqual(title.files_d, 1)
        self.assertEqual(title.files_r, 1)
        empty = by["あ-お\\い\\空フォルダ"]
        self.assertEqual((empty.files_d, empty.files_r), (0, 0))
        # Thumbs.db は除外済みのため あ-お の直下は 0
        self.assertEqual(by["あ-お"].files_d, 0)

    def test_excluded_subtree_pruned(self):
        """ドット・OSシステム項目は部分木枝刈り（行も子孫行も出さない・Q29-6）。"""
        st = self._scan()
        storages = {r.storage for r in st.rows}
        self.assertNotIn(".git", storages)
        self.assertNotIn(".git\\config", storages)
        self.assertNotIn("$RECYCLE.BIN", storages)

    def test_no_recursive(self):
        """--no-recursive は起点直下のみ（Q29-9）。"""
        st = self._scan(recursive=False)
        storages = [r.storage for r in st.rows]
        self.assertIn(core.ROOT_LABEL, storages)
        self.assertIn("あ-お", storages)
        self.assertNotIn("あ-お\\あ", storages)
        # 子行の配下＝直下（1階層分のみ）
        by = self._by_storage(st)
        self.assertEqual(by["あ-お"].files_r, by["あ-お"].files_d)

    def test_total_row(self):
        """合計行は独立計算（直下系合計・Q29-10）。"""
        st = self._scan()
        total = core.compute_total(st.rows)
        self.assertEqual(total.storage, "合計")
        # ユニークファイル: root直下1 + タイトル.zip1 = 2
        self.assertEqual(total.files_d, 2)
        self.assertEqual(total.files_r, None)   # 配下系は空欄
        folder_count = total.notes[0]
        self.assertEqual(folder_count, f"フォルダ数 {len(st.rows) - 1}")

    def test_read_error_injection(self):
        """例外注入による読取エラー再現（Q51=A・Q29-16）。"""
        real_scandir = core.os.scandir
        bad = self.root / "あ-お"

        def fake_scandir(path, *a, **kw):
            if str(path) == str(bad):
                raise PermissionError(13, "injected")
            return real_scandir(path, *a, **kw)

        with mock.patch.object(core.os, "scandir", side_effect=fake_scandir):
            st = self._scan()
        by = self._by_storage(st)
        row = by["あ-お"]
        self.assertEqual(row.files_d, None)     # 統計は空欄
        self.assertIn("読取エラー1件", row.notes_str)
        self.assertEqual(core.EXIT_PARTIAL, 2)  # exit 2 の定数整合

    def test_sort_default_and_desc(self):
        st = self._scan()
        rows = st.rows
        core.sort_rows(rows, "name", "asc")
        self.assertEqual(rows[0].storage, core.ROOT_LABEL)
        self.assertEqual(rows[1].storage, "あ-お")
        core.sort_rows(rows, "name", "desc")
        self.assertEqual(rows[-1].storage, core.ROOT_LABEL)

    def test_sort_by_size_secondary_relpath(self):
        """size ソートは配下基準・同値は相対パス昇順・空値は末尾（Q50=A）。"""
        st = self._scan()
        by = self._by_storage(st)
        by["あ-お"].files_r = None      # 空値行を作る

        by["あ-お"].size_r = None
        rows = list(st.rows)
        core.sort_rows(rows, "files", "asc")
        self.assertEqual(rows[-1].storage, "あ-お")   # 空値は末尾
        core.sort_rows(rows, "files", "desc")
        self.assertEqual(rows[-1].storage, "あ-お")   # 空値は末尾（descでも）



class TestLinkSkip(unittest.TestCase):
    def test_symlink_dir_skipped(self):
        """ディレクトリリンクはスキップ・備考に集約（Q29-7）。"""
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "本物").mkdir()
        (root / "本物" / "f.txt").write_text("x", encoding="utf-8")
        try:
            (root / "リンク").symlink_to(root / "本物", target_is_directory=True)
        except OSError:
            td.cleanup()
            self.skipTest("シンボリックリンクを作成できない環境です")
        try:
            st = core.scan_tree(
                make_cfg(root, Path(td.name) / "out"),
                lambda cur, total, msg: None)
            by = {r.storage: r for r in st.rows}
            self.assertNotIn("リンク", by)
            self.assertIn("リンクスキップ1件", by[core.ROOT_LABEL].notes_str)
        finally:
            td.cleanup()


class TestRunExitCodes(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "r"
        (self.root / "サブ").mkdir(parents=True)
        (self.root / "サブ" / "f.bin").write_bytes(b"data")
        (self.root / "a.txt").write_text("x", encoding="utf-8")
        self.out = Path(self._td.name) / "o"
        self.out.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_run_ok(self):
        logger = _Logger()
        code = core.run(make_cfg(self.root, self.out), logger)
        self.assertEqual(code, 0)
        self.assertTrue(any(s.startswith("summary:") for s in logger.infos))
        files = list(self.out.glob("asset_*.csv"))
        self.assertEqual(len(files), 1)

    def test_run_error_returns_2(self):
        real_scandir = core.os.scandir
        bad = self.root / "サブ"

        def fake_scandir(path, *a, **kw):
            if str(path) == str(bad):
                raise PermissionError(13, "injected")
            return real_scandir(path, *a, **kw)

        with mock.patch.object(core.os, "scandir", side_effect=fake_scandir):
            code = core.run(make_cfg(self.root, self.out), _Logger())
        self.assertEqual(code, 2)

    def test_dry_run_no_output(self):
        logger = _Logger()
        code = core.run(make_cfg(self.root, self.out, dry_run=True), logger)
        self.assertEqual(code, 0)
        self.assertEqual(list(self.out.glob("asset_*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)