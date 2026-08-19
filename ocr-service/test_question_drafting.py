import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import app as app_module

from app import (
    crop_bbox,
    draft_questions_from_document,
    draft_questions_from_structured_blocks,
    find_structured_blocks,
    persist_question_images,
    suggest_question_type,
)


class QuestionDraftingRegressionTest(unittest.TestCase):
    def test_fill_in_page_keeps_all_eight_question_numbers(self):
        fixture = Path(__file__).parent / "fixtures" / "ui-paper-response.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))["pages"][0]["raw_result"]

        drafts = draft_questions_from_document(payload)

        self.assertEqual([draft["number"] for draft in drafts], [str(number) for number in range(1, 9)])
        self.assertNotIn("2.", drafts[0]["stem"])

    def test_choice_options_are_separate_from_stem_and_keep_visual_options(self):
        fixture = Path(__file__).parent / "fixtures" / "choice-paper-response.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))["pages"][0]["raw_result"]

        drafts = draft_questions_from_document(payload)

        self.assertEqual([option["label"] for option in drafts[1]["options"]], ["A", "B"])
        self.assertNotIn("A.", drafts[1]["stem"])
        self.assertEqual([option["label"] for option in drafts[2]["options"]], ["A", "B"])
        self.assertTrue(all(option.get("requires_visual_review") for option in drafts[2]["options"]))
        self.assertEqual([option["label"] for option in drafts[3]["options"]], ["A", "B", "C"])

    def test_question_type_suggestions_cover_the_supported_types(self):
        choices = [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}]
        self.assertEqual(suggest_question_type("下列各项中，正确的是（ ）", choices)[0], 0)
        self.assertEqual(suggest_question_type("多选：下列说法正确的是（ ）", choices)[0], 1)
        self.assertEqual(suggest_question_type("把分数化成最简分数是（ ）", [])[0], 2)
        self.assertEqual(suggest_question_type("判断：这个说法是否正确", [])[0], 3)
        self.assertEqual(suggest_question_type("计算下列各题", [])[0], 4)


    def test_crop_bbox_persists_graph_region(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "graph.jpg"
            image = Image.new("RGB", (120, 90), "white")

            self.assertTrue(crop_bbox(image, [20, 15, 80, 65], destination))
            self.assertTrue(destination.exists())
            self.assertGreater(destination.stat().st_size, 0)

    def test_split_figure_strip_into_individual_option_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "paper.png"
            image = Image.new("RGB", (420, 180), "white")
            draw = ImageDraw.Draw(image)
            for index in range(4):
                x = 20 + index * 95
                draw.rectangle((x, 45, x + 55, 120), fill="black")
            image.save(image_path)

            questions = [
                {
                    "number": "1",
                    "stem": "选择下列图像对应的选项",
                    "options": [
                        {"label": "A", "content": "", "requires_visual_review": True},
                        {"label": "B", "content": "", "requires_visual_review": True},
                        {"label": "C", "content": "", "requires_visual_review": True},
                        {"label": "D", "content": "", "requires_visual_review": True},
                    ],
                    "figure_bboxes": [[0, 30, 420, 150]],
                }
            ]

            original_root = app_module.GRAPH_UPLOAD_ROOT
            app_module.GRAPH_UPLOAD_ROOT = Path(temp_dir) / "graphs"
            try:
                persist_question_images(image_path, questions, "testsplit")
            finally:
                app_module.GRAPH_UPLOAD_ROOT = original_root

            self.assertFalse(questions[0]["image_paths"])
            self.assertTrue(all(option["image_paths"] for option in questions[0]["options"]))

    def test_unnumbered_stems_after_options_start_new_questions(self):
        blocks = [
            {"block_label": "text", "block_content": "2. 二次函数 y=ax^2+bx+c 的图象如右图，则点 M 在（ ）", "block_bbox": [0, 80, 300, 140]},
            {"block_label": "text", "block_content": "A.第一象限 B.第二象限 C.第三象限 D.第四象限", "block_bbox": [0, 150, 300, 180]},
            {"block_label": "text", "block_content": "已知二次函数 y=ax^2+bx+c，且 a<0，则一定有（ ）", "block_bbox": [0, 200, 300, 230]},
            {"block_label": "text", "block_content": "A.b^2-4ac>0 B.b^2-4ac=0 C.b^2-4ac<0 D.b^2-4ac<=0", "block_bbox": [0, 245, 300, 275]},
            {"block_label": "text", "block_content": "把抛物线 y=x^2+bx+c 向右平移 3 个单位，则有（ ）", "block_bbox": [0, 290, 300, 340]},
            {"block_label": "text", "block_content": "A.b=3,c=7 B.b=-9,c=-15 C.b=3,c=3 D.b=-9,c=21", "block_bbox": [0, 360, 300, 390]},
        ]

        drafts = draft_questions_from_structured_blocks(blocks, [])

        self.assertEqual(["2", "3", "4"], [question["number"] for question in drafts])
        self.assertEqual([4, 4, 4], [len(question["options"]) for question in drafts])

    def test_visual_option_slots_are_created_from_four_part_figure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "paper.png"
            image = Image.new("RGB", (440, 140), "white")
            draw = ImageDraw.Draw(image)
            for left in (10, 120, 230, 340):
                draw.line((left + 10, 90, left + 80, 20), fill="black", width=3)
                draw.line((left + 10, 90, left + 80, 90), fill="black", width=3)
                draw.line((left + 45, 15, left + 45, 105), fill="black", width=2)
            image.save(image_path)

            questions = [
                {
                    "number": "5",
                    "stem": "下面所示各图是在同一直角坐标系内，正确的是（ ）",
                    "options": [],
                    "figure_bboxes": [[0, 0, 440, 130]],
                }
            ]

            original_root = app_module.GRAPH_UPLOAD_ROOT
            app_module.GRAPH_UPLOAD_ROOT = Path(temp_dir) / "graphs"
            try:
                persist_question_images(image_path, questions, "testautoslots")
            finally:
                app_module.GRAPH_UPLOAD_ROOT = original_root

            self.assertFalse(questions[0]["image_paths"])
            self.assertEqual(["A", "B", "C", "D"], [option["label"] for option in questions[0]["options"]])
            self.assertTrue(all(option["image_paths"] for option in questions[0]["options"]))

    def test_visual_option_slots_ignore_question_text_above_the_graph_strip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "paper.png"
            image = Image.new("RGB", (480, 220), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 480, 40), fill="black")
            for left in (20, 130, 240, 350):
                draw.rectangle((left, 90, left + 60, 170), fill="black")
            image.save(image_path)

            questions = [
                {
                    "number": "5",
                    "stem": "閫夋嫨涓嬪垪鍥惧儚瀵瑰簲鐨勯€夐」",
                    "options": [],
                    "figure_bboxes": [[0, 0, 480, 180]],
                }
            ]

            original_root = app_module.GRAPH_UPLOAD_ROOT
            app_module.GRAPH_UPLOAD_ROOT = Path(temp_dir) / "graphs"
            try:
                persist_question_images(image_path, questions, "testvisualtrim")
            finally:
                app_module.GRAPH_UPLOAD_ROOT = original_root

            option_a = next(option for option in questions[0]["options"] if option["label"] == "A")
            self.assertTrue(option_a["image_paths"])
            saved = Path(temp_dir) / "graphs" / "testvisualtrim" / "question-1-option-A.jpg"
            cropped = Image.open(saved).convert("L")
            top_band = sum(1 for x in range(cropped.width) if cropped.getpixel((x, 0)) < 200)
            self.assertLess(top_band, cropped.width // 5)

    def test_structured_blocks_deduplicate_nearly_identical_image_boxes(self):
        payload = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "image", "block_bbox": [16, 498, 463, 562], "block_content": ""}
                ],
                "layout_det_res": {
                    "boxes": [
                        {
                            "label": "image",
                            "coordinate": [16.8, 498.2, 463.5, 562],
                        }
                    ]
                },
            }
        }

        image_blocks = [block for block in find_structured_blocks(payload) if block["block_label"] == "image"]

        self.assertEqual(1, len(image_blocks))

    def test_layout_image_is_attached_to_question_above_not_last_question(self):
        payload = {
            "res": {
                "parsing_res_list": [
                    {
                        "block_label": "text",
                        "block_content": "1. Choose the correct graph ( )",
                        "block_bbox": [10, 10, 400, 30],
                        "block_order": 1,
                    },
                    {
                        "block_label": "text",
                        "block_content": "2. The y-intercept of y=x+3 is ( )",
                        "block_bbox": [10, 200, 400, 230],
                        "block_order": 2,
                    },
                    {
                        "block_label": "text",
                        "block_content": "A. (-3,0) B. (3,0) C. (0,3) D. (0,-3)",
                        "block_bbox": [10, 240, 400, 260],
                        "block_order": 3,
                    },
                ],
                "layout_det_res": {
                    "boxes": [
                        {
                            "label": "image",
                            "coordinate": [10, 60, 400, 150],
                        }
                    ]
                },
            }
        }

        drafts = draft_questions_from_document(payload)

        self.assertEqual([1, 0], [len(question.get("figure_bboxes", [])) for question in drafts])


if __name__ == "__main__":
    unittest.main()
