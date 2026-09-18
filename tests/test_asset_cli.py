"""asset_tool CLI 雛形のテスト（Phase 2-1）。パーサ・TOMLマージ・出力検証・終了コード。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import asset_tool.cli as cli
from asset_tool.config import Config


class TestParserDefaults(unittest.TestCase):
    def _parse(self, argv):
        return cli.build_parser().parse_args(argv)

    def test_defaults(self):
        args = self._parse(["--input", "in", "--output", "out"])
        self.assertEqual(args.format, None)      # CLI未指定 → TOML/既定へ委譲
        self.assertIsNone(args.sort)
        self.assertIsNone(args.order)
        self.assertIsNone(args.recursive)       # CLI未指定 → TOML/既定へ委譲
        self.assertFalse(args.with_hash)
        self.assertFalse(args.detail)
        self.assertFalse(args.dry_run)

    def test_no_recursive(self):
        args = self._parse(["--input", "in", "--output", "out", "--no-recursive"])
        self.assertFalse(args.recursive)

    def test_all_options_accepted(self):
        args = self._parse([
            "--input", "in", "--output", "out", "--format", "html",
            "--sort", "size", "--order", "desc", "--recursive",
            "--with-hash", "--detail", "--exclude-pattern", "tmp",
            "--log-file", "a.log", "--log-level", "DEBUG", "--dry-run"])
        self.assertEqual(args.format, "html")
        self.assertEqual(args.sort, "size")
        self.assertEqual(args.order, "desc")
        self.assertTrue(args.recursive)
        self.assertTrue(args.with_hash)
        self.assertTrue(args.detail)
        self.assertEqual(args.exclude_pattern, "tmp")
        self.assertEqual(args.log_file, "a.log")
        self.assertEqual(args.log_level, "DEBUG")
        self.assertTrue(args.dry_run)


class TestMergeAndToml(unittest.TestCase):
    def test_merge_cli_over_default(self):
        args = cli.build_parser().parse_args(
            ["--input", "in", "--output", "out", "--format", "md",
             "--sort", "files", "--order", "desc", "--no-recursive", "--detail"])
        cfg = cli._merge(args, Config())
        self.assertEqual(cfg.format, "md")
        self.assertEqual(cfg.sort, "files")
        self.assertEqual(cfg.order, "desc")
        self.assertFalse(cfg.recursive)
        self.assertTrue(cfg.detail)
        self.assertEqual(cfg.input_dir, Path("in"))
        self.assertEqual(cfg.output_dir, Path("out"))

    def test_toml_asset_section(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / "mytools.toml"
            toml_path.write_text(
                '[asset]\nformat = "html"\nsort = "mtime"\norder = "desc"\n',
                encoding="utf-8")
            data = cli._load_toml(str(toml_path))
            self.assertEqual(data.get("format"), "html")

            args = cli.build_parser().parse_args(
                ["--input", "in", "--output", "out", "--config", str(toml_path),
                 "--format", "csv"])  # CLI > TOML
            cfg = cli._merge(args, cli.from_dict(data))
            self.assertEqual(cfg.format, "csv")   # CLI優先
            self.assertEqual(cfg.sort, "mtime")   # TOML反映
            self.assertEqual(cfg.order, "desc")


class TestValidateOutput(unittest.TestCase):
    def test_file_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "out.csv"
            f.write_text("x", encoding="utf-8")
            self.assertIsNotNone(cli.validate_output(f))

    def test_suffixed_nonexistent_rejected(self):
        self.assertIsNotNone(cli.validate_output(Path("some/out.csv")))

    def test_dotted_dir_allowed(self):
        """v1.2 のようなドット付きフォルダ名は許可。"""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "v1.2"
            d.mkdir()
            self.assertIsNone(cli.validate_output(d))

    def test_plain_dir_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(cli.validate_output(Path(td)))


class TestMainExitCodes(unittest.TestCase):
    def _run_main(self, argv):
        import io
        import contextlib
        buf_err, buf_out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(buf_err), contextlib.redirect_stdout(buf_out):
            code = cli.main(argv)
        return code, buf_err.getvalue(), buf_out.getvalue()

    def test_missing_input_dir(self):
        with tempfile.TemporaryDirectory() as td:
            code, err, _ = self._run_main(
                ["--input", str(Path(td) / "nope"), "--output", str(td)])
            self.assertEqual(code, 1)
            self.assertIn("入力フォルダが見つかりません", err)

    def test_core_run_succeeds(self):
        """Phase 3 実装後は core.run が正常動作し exit 0。"""
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in"
            inp.mkdir()
            out = Path(td) / "out"
            out.mkdir()
            code, _, out_txt = self._run_main(
                ["--input", str(inp), "--output", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("asset-tool 開始", out_txt)

    def test_log_file_default_created(self):
        """ログ既定パス asset_*.log が生成される（スタブ実行時）。"""
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in"
            inp.mkdir()
            out = Path(td) / "out"
            out.mkdir()
            cli.main(["--input", str(inp), "--output", str(out)])
            logs = list(out.glob("asset_*.log"))
            self.assertEqual(len(logs), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)