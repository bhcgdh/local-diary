import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import (
    DiaryStore,
    acquire_single_instance_lock,
    build_evernote_enex,
    get_date_info,
    get_day_ganzhi,
    get_diary_header,
)


class DiaryStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = DiaryStore(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_save_read_and_month_marker(self):
        self.store.save("2026-06-04", "今天的日记")

        self.assertEqual(self.store.get("2026-06-04"), "今天的日记")
        self.assertEqual(self.store.dates_in_month(2026, 6), {"2026-06-04"})

    def test_save_exports_yearly_three_column_csv(self):
        self.store.save("2026-06-04", "农历和干支\n今天的日记")

        with self.store.year_table_path(2026).open(
            encoding="utf-8-sig", newline=""
        ) as table:
            rows = list(csv.reader(table))

        self.assertEqual(rows[0], ["id", "时间", "日志"])
        self.assertEqual(rows[1], ["155", "2026-06-04", "农历和干支\n今天的日记"])

    def test_close_exports_csv_files(self):
        self.store.save("2026-06-04", "Close export diary")
        self.store.save_todo("2026-06-04", "Close export todo")
        self.store.year_table_path(2026).unlink()
        self.store.todo_table_path().unlink()

        self.store.close()

        self.assertTrue(self.store.year_table_path(2026).exists())
        self.assertTrue(self.store.todo_table_path().exists())
        self.store = DiaryStore(Path(self.temp_dir.name) / "test.db")

    def test_year_rows_uses_same_three_column_structure(self):
        self.store.save("2026-06-04", "今天的日记")

        self.assertEqual(
            self.store.year_rows(2026),
            [(155, "2026-06-04", "今天的日记")],
        )

    def test_id_restarts_each_year_and_supports_leap_year(self):
        self.store.save("2026-01-01", "新年")
        self.store.save("2027-01-01", "新年")
        self.store.save("2028-12-31", "闰年最后一天")

        with self.store.year_table_path(2026).open(
            encoding="utf-8-sig", newline=""
        ) as table:
            rows_2026 = list(csv.reader(table))
        with self.store.year_table_path(2027).open(
            encoding="utf-8-sig", newline=""
        ) as table:
            rows_2027 = list(csv.reader(table))
        with self.store.year_table_path(2028).open(
            encoding="utf-8-sig", newline=""
        ) as table:
            rows_2028 = list(csv.reader(table))

        self.assertEqual(rows_2026[1][0], "1")
        self.assertEqual(rows_2027[1][0], "1")
        self.assertEqual(rows_2028[1][0], "366")

    def test_empty_content_deletes_entry(self):
        self.store.save("2026-06-04", "内容")
        self.store.save("2026-06-04", "   ")

        self.assertEqual(self.store.get("2026-06-04"), "")

    def test_stale_empty_diary_does_not_delete_longer_content(self):
        self.store.save("2026-06-04", "已经写好的长日记")

        saved = self.store.save("2026-06-04", "", expected_content="")

        self.assertFalse(saved)
        self.assertEqual(self.store.get("2026-06-04"), "已经写好的长日记")

    def test_stale_shorter_diary_does_not_overwrite_longer_content(self):
        self.store.save("2026-06-04", "旧内容")
        second_store = DiaryStore(Path(self.temp_dir.name) / "test.db")
        try:
            loaded = self.store.get("2026-06-04")
            second_store.save("2026-06-04", "这是另一个窗口写入的更长日记内容")

            saved = self.store.save(
                "2026-06-04", "短", expected_content=loaded
            )

            self.assertFalse(saved)
            self.assertEqual(
                self.store.get("2026-06-04"), "这是另一个窗口写入的更长日记内容"
            )
        finally:
            second_store.close()

    def test_intentional_shorter_diary_is_allowed_when_not_stale(self):
        self.store.save("2026-06-04", "较长的原始内容")
        loaded = self.store.get("2026-06-04")

        saved = self.store.save("2026-06-04", "短内容", expected_content=loaded)

        self.assertTrue(saved)
        self.assertEqual(self.store.get("2026-06-04"), "短内容")

    def test_setting_is_persisted(self):
        self.store.save_setting("theme", "薄荷绿")

        self.assertEqual(self.store.get_setting("theme", "奶油粉"), "薄荷绿")

    def test_todo_is_saved_marked_and_exported(self):
        self.store.save_todo("2026-06-04", "完成本地日记功能")

        self.assertEqual(self.store.get_todo("2026-06-04"), "完成本地日记功能")
        self.assertEqual(self.store.todo_dates_in_month(2026, 6), {"2026-06-04"})
        with self.store.todo_table_path().open(
            encoding="utf-8-sig", newline=""
        ) as table:
            rows = list(csv.reader(table))

        self.assertEqual(rows[0], ["时间", "农历", "年月日干支", "待办内容"])
        self.assertEqual(
            rows[1],
            [
                "2026-06-04",
                "二〇二六年四月十九",
                "丙午年  癸巳月  己酉日",
                "完成本地日记功能",
            ],
        )

    def test_empty_todo_deletes_entry(self):
        self.store.save_todo("2026-06-04", "待办")
        self.store.save_todo("2026-06-04", "  ")

        self.assertEqual(self.store.get_todo("2026-06-04"), "")

    def test_stale_empty_todo_does_not_delete_longer_content(self):
        self.store.save_todo("2026-06-04", "已经写好的待办")

        saved = self.store.save_todo("2026-06-04", "", expected_content="")

        self.assertFalse(saved)
        self.assertEqual(self.store.get_todo("2026-06-04"), "已经写好的待办")


class DateInfoTest(unittest.TestCase):
    def test_known_date(self):
        lunar, ganzhi, wuxing = get_date_info(date(2026, 6, 4))

        self.assertEqual(lunar, "二〇二六年四月十九")
        self.assertEqual(ganzhi, "丙午年  癸巳月  己酉日")
        self.assertEqual(wuxing, "年：天河水  月：长流水  日：大驿土")

    def test_diary_header_contains_lunar_and_ganzhi(self):
        header = get_diary_header(date(2026, 6, 4))

        self.assertEqual(
            header,
            "农历：二〇二六年四月十九　干支：丙午年  癸巳月  己酉日",
        )

    def test_day_ganzhi_uses_daily_stem_wuxing_color(self):
        ganzhi, stem_color, branch_color = get_day_ganzhi(date(2026, 6, 4))

        self.assertEqual(ganzhi, "己酉")
        self.assertEqual(stem_color, "#B8862B")
        self.assertEqual(branch_color, "#D4A017")


class EvernoteExportTest(unittest.TestCase):
    def test_enex_contains_rendered_table_and_escaped_chinese_content(self):
        enex = build_evernote_enex(
            2026, [(1, "2026-01-01", "第一行\n第二行 & 内容")]
        )

        self.assertIn("<title>2026年的日记</title>", enex)
        self.assertIn("<![CDATA[", enex)
        self.assertIn("<table", enex)
        self.assertIn("日记内容", enex)
        self.assertIn("第一行<br/>第二行 &amp; 内容", enex)
        self.assertIn("width:6%", enex)
        self.assertIn("width:16%", enex)
        self.assertIn("width:78%", enex)


class SingleInstanceTest(unittest.TestCase):
    def test_second_instance_lock_is_rejected(self):
        first_lock = acquire_single_instance_lock()
        self.assertIsNotNone(first_lock)
        try:
            second_lock = acquire_single_instance_lock()
            self.assertIsNone(second_lock)
        finally:
            first_lock.close()


if __name__ == "__main__":
    unittest.main()
