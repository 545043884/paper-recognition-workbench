import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from paddleocr import PPStructureV3
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("paper-ocr-service")

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILES = int(os.getenv("OCR_MAX_FILES", "20"))
MAX_FILE_SIZE = int(os.getenv("OCR_MAX_FILE_SIZE_MB", "15")) * 1024 * 1024
DEVICE = os.getenv("OCR_DEVICE", "gpu")
GRAPH_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploads" / "graphs"
GRAPH_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Paper OCR Service",
    version="0.1.0",
    description="Extracts layout, text, coordinates and draft questions from exam paper images.",
)
default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174"
allowed_origins = os.getenv("OCR_ALLOWED_ORIGINS", default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads/graphs", StaticFiles(directory=GRAPH_UPLOAD_ROOT), name="graph-images")


@app.post("/api/v1/assets")
async def upload_asset(file: UploadFile = File(...)) -> dict[str, str]:
    """Store a user-added question/option image in the same format as OCR crops."""
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="只支持 JPG、PNG 或 WEBP 图片")
    data = await file.read()
    if not data or len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="图片不能为空且不能超过文件大小限制")
    try:
        from io import BytesIO
        image = Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="上传文件不是有效图片") from exc

    asset_id = uuid.uuid4().hex
    folder = GRAPH_UPLOAD_ROOT / asset_id
    folder.mkdir(parents=True, exist_ok=False)
    filename = f"manual-{uuid.uuid4().hex}.jpg"
    image.save(folder / filename, format="JPEG", quality=94, optimize=True)
    return {"path": f"/uploads/graphs/{asset_id}/{filename}"}

_pipeline: PPStructureV3 | None = None
_pipeline_lock = Lock()


def get_pipeline() -> PPStructureV3:
    """Load models once. The first call downloads official model weights if absent."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                logger.info("Loading PP-StructureV3 on %s", DEVICE)
                pipeline_options: dict[str, Any] = {
                    "device": DEVICE,
                    "layout_detection_model_name": os.getenv(
                        "OCR_LAYOUT_MODEL", "PP-DocLayout-S" if DEVICE == "cpu" else "PP-DocLayout_plus-L"
                    ),
                    "formula_recognition_model_name": os.getenv(
                        "OCR_FORMULA_MODEL", "PP-FormulaNet-S" if DEVICE == "cpu" else "PP-FormulaNet_plus-L"
                    ),
                    "text_detection_model_name": os.getenv(
                        "OCR_TEXT_DET_MODEL", "PP-OCRv5_mobile_det" if DEVICE == "cpu" else "PP-OCRv5_server_det"
                    ),
                    "text_recognition_model_name": os.getenv(
                        "OCR_TEXT_REC_MODEL", "PP-OCRv5_mobile_rec" if DEVICE == "cpu" else "PP-OCRv5_server_rec"
                    ),
                    "use_doc_orientation_classify": True,
                    "use_doc_unwarping": os.getenv("OCR_USE_DOC_UNWARPING", "0" if DEVICE == "cpu" else "1") == "1",
                    "use_textline_orientation": True,
                    "use_table_recognition": False,
                    "use_formula_recognition": True,
                }
                if DEVICE == "cpu":
                    # PaddleX otherwise enables oneDNN for CPU pipelines by default.
                    # PaddlePaddle 3.x cannot currently lower every PP-StructureV3
                    # PIR attribute through that executor, which raises an
                    # unimplemented ConvertPirAttribute2RuntimeAttribute error.
                    pipeline_options["enable_mkldnn"] = False
                    pipeline_options["cpu_threads"] = int(os.getenv("OCR_CPU_THREADS", "2"))
                _pipeline = PPStructureV3(
                    **pipeline_options,
                )
    return _pipeline


def to_json_value(value: Any) -> Any:
    """Convert Paddle/Numpy result values into response-safe JSON primitives."""
    if hasattr(value, "tolist"):
        return to_json_value(value.tolist())
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def result_to_dict(result: Any) -> dict[str, Any]:
    """PaddleOCR 3.x result objects expose JSON; retain it without losing coordinates."""
    raw_json = getattr(result, "json", None)
    if callable(raw_json):
        raw_json = raw_json()
    if isinstance(raw_json, str):
        return to_json_value(json.loads(raw_json))
    if isinstance(raw_json, dict):
        return to_json_value(raw_json)
    if hasattr(result, "to_dict"):
        return to_json_value(result.to_dict())
    return to_json_value(dict(result))


def find_text_lines(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Read PP-Structure global OCR lines while tolerating minor Paddle result changes."""
    candidates = [payload, payload.get("res", {})]
    for candidate in candidates:
        ocr = candidate.get("overall_ocr_res", {}) if isinstance(candidate, dict) else {}
        texts = ocr.get("rec_texts") or ocr.get("rec_text") or []
        boxes = ocr.get("dt_polys") or ocr.get("rec_boxes") or []
        scores = ocr.get("rec_scores") or ocr.get("rec_score") or []
        if isinstance(texts, str):
            texts = [texts]
        if texts:
            return [
                {
                    "text": text,
                    "bbox": boxes[index] if index < len(boxes) else None,
                    "confidence": scores[index] if index < len(scores) else None,
                }
                for index, text in enumerate(texts)
            ]
    return []


QUESTION_PATTERN = re.compile(r"^\s*(\d{1,3})\s*[\.．、]\s*(.*)$")
OPTION_PATTERN = re.compile(r"^\s*([A-DＡ-Ｄ])\s*[\.．、]\s*(.*)$")
# A scanned row can be either `A. 2 B. 3` or `A.17B.18`; do not require spaces.
INLINE_OPTION_PATTERN = re.compile(r"([A-DＡ-Ｄ])\s*[\.．、]\s*")
OPTION_LABEL_TRANSLATION = str.maketrans("ＡＢＣＤ", "ABCD")


VISUAL_OPTION_LABELS = ["A", "B", "C", "D"]


def suggest_question_type(stem: str, options: list[dict[str, Any]]) -> tuple[int | None, float]:
    """Suggest a question-bank type; the user can always override it in the UI."""
    text = re.sub(r"\s+", "", stem or "")
    if options:
        if re.search(r"多选|不定项|可多选|下列.*?(都|全部|所有).*(正确|符合)", text):
            return 1, 0.92
        return 0, 0.82
    if re.search(r"判断|对错|正确.*?错误|√|×", text):
        return 3, 0.88
    if re.search(r"填空|\(\s*\)|（\s*）|_{2,}|横线上|空格", stem or ""):
        return 2, 0.88
    if re.search(r"简答|解答|计算|证明|作图|说明|写出|求.*?(值|面积|体积|周长)", text):
        return 4, 0.72
    return None, 0.0


def enrich_question_type(question: dict[str, Any]) -> dict[str, Any]:
    question_type, confidence = suggest_question_type(question.get("stem", ""), question.get("options", []))
    question["suggested_question_type"] = question_type
    question["type_confidence"] = confidence
    return question


def draft_questions(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create editable question drafts. Results are intentionally not database-ready."""
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        text = str(line["text"]).strip()
        if not text:
            continue
        question_match = QUESTION_PATTERN.match(text)
        option_match = OPTION_PATTERN.match(text)
        if question_match:
            current = {
                "number": question_match.group(1),
                "stem": question_match.group(2),
                "options": [],
                "figure_bboxes": [],
                "source_bbox": line["bbox"],
                "confidence": line["confidence"],
                "review_status": "pending",
            }
            questions.append(current)
        elif option_match and current is not None:
            current["options"].append(
                {
                    "label": option_match.group(1).upper(),
                    "content": option_match.group(2),
                    "source_bbox": line["bbox"],
                    "confidence": line["confidence"],
                }
            )
        elif current is not None:
            current["stem"] = f"{current['stem']} {text}"

    return [enrich_question_type(question) for question in questions]


def find_structured_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Use PP-Structure's reading-order blocks instead of reassembling loose OCR lines."""
    candidates = [payload, payload.get("res", {})]
    parsed_blocks: list[dict[str, Any]] = []
    for candidate in candidates:
        blocks = candidate.get("parsing_res_list", []) if isinstance(candidate, dict) else []
        if blocks:
            for index, block in enumerate(blocks):
                parsed_block = to_json_value(block)
                parsed_block.setdefault("_source_index", index)
                parsed_blocks.append(parsed_block)
    extra_blocks = find_layout_image_blocks(payload)
    if not parsed_blocks and not extra_blocks:
        return []
    for block in extra_blocks:
        if block.get("block_order") is None:
            inferred_order = infer_layout_image_order(block, parsed_blocks)
            if inferred_order is not None:
                block["block_order"] = inferred_order
    merged = parsed_blocks + extra_blocks
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[Any, ...] | None]] = set()
    for block in merged:
        bbox = block.get("block_bbox")
        key = (str(block.get("block_label")), tuple(bbox) if isinstance(bbox, list) else None)
        if key in seen:
            continue
        if any(is_duplicate_block(block, existing) for existing in deduped):
            continue
        seen.add(key)
        deduped.append(block)
    deduped.sort(key=block_sort_key)
    return deduped


def infer_layout_image_order(image_block: dict[str, Any], parsed_blocks: list[dict[str, Any]]) -> float | None:
    """Place layout-only image blocks between surrounding text blocks.

    PP-Structure often gives text blocks a reading order but layout images only coordinates.
    If image blocks are sorted after all text, diagrams get attached to the last question.
    """
    bbox = image_block.get("block_bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    image_top = float(bbox[1])
    preceding_orders: list[float] = []
    following_orders: list[float] = []
    for block in parsed_blocks:
        block_bbox = block.get("block_bbox")
        if not isinstance(block_bbox, list) or len(block_bbox) != 4:
            continue
        order = block.get("block_order")
        if order is None:
            order = block.get("_source_index")
        if order is None:
            continue
        order_value = float(order)
        block_bottom = float(block_bbox[3])
        block_top = float(block_bbox[1])
        if block_bottom <= image_top:
            preceding_orders.append(order_value)
        elif block_top >= image_top:
            following_orders.append(order_value)
    if preceding_orders and following_orders:
        before = max(preceding_orders)
        after = min(following_orders)
        if after > before:
            return before + (after - before) / 2
    if preceding_orders:
        return max(preceding_orders) + 0.5
    if following_orders:
        return min(following_orders) - 0.5
    return None


def bbox_iou(first: Any, second: Any) -> float:
    if not isinstance(first, list) or not isinstance(second, list) or len(first) != 4 or len(second) != 4:
        return 0.0
    left = max(float(first[0]), float(second[0]))
    top = max(float(first[1]), float(second[1]))
    right = min(float(first[2]), float(second[2]))
    bottom = min(float(first[3]), float(second[3]))
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, float(first[2]) - float(first[0])) * max(0.0, float(first[3]) - float(first[1]))
    second_area = max(0.0, float(second[2]) - float(second[0])) * max(0.0, float(second[3]) - float(second[1]))
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def is_duplicate_block(block: dict[str, Any], existing: dict[str, Any]) -> bool:
    if block.get("block_label") != existing.get("block_label"):
        return False
    return bbox_iou(block.get("block_bbox"), existing.get("block_bbox")) >= 0.92


def find_layout_image_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [payload, payload.get("res", {})]
    for candidate in candidates:
        layout = candidate.get("layout_det_res", {}) if isinstance(candidate, dict) else {}
        boxes = layout.get("boxes", []) if isinstance(layout, dict) else []
        if not boxes:
            continue
        image_blocks: list[dict[str, Any]] = []
        for index, box in enumerate(boxes):
            label = box.get("label")
            coordinate = box.get("coordinate")
            if label != "image" or not isinstance(coordinate, list) or len(coordinate) != 4:
                continue
            image_blocks.append(
                {
                    "block_label": "image",
                    "block_content": "",
                    "block_bbox": to_json_value(coordinate),
                    "block_id": f"layout-image-{index}",
                    "block_order": None,
                }
            )
        if image_blocks:
            return image_blocks
    return []


def block_sort_key(block: dict[str, Any]) -> tuple[int, float, float]:
    order = block.get("block_order")
    bbox = block.get("block_bbox")
    top = float(bbox[1]) if isinstance(bbox, list) and len(bbox) == 4 else 0.0
    left = float(bbox[0]) if isinstance(bbox, list) and len(bbox) == 4 else 0.0
    source_index = block.get("_source_index")
    if order is not None:
        return (0, float(order), left)
    if source_index is not None:
        return (0, float(source_index), left)
    return (1, top, left)


def split_inline_options(content: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(INLINE_OPTION_PATTERN.finditer(content))
    if not matches:
        return content, []
    stem = content[: matches[0].start()].strip()
    options = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        options.append(
            {
                "label": match.group(1).translate(OPTION_LABEL_TRANSLATION).upper(),
                "content": content[match.end() : end].strip(),
            }
        )
    return stem, options


def next_question_number(questions: list[dict[str, Any]]) -> str:
    for question in reversed(questions):
        number = str(question.get("number", "")).strip()
        if number.isdigit():
            return str(int(number) + 1)
    return str(len(questions) + 1)


def looks_like_unnumbered_question_stem(content: str, current: dict[str, Any] | None) -> bool:
    if current is None or len(current.get("options", [])) < 2:
        return False
    text = re.sub(r"\s+", "", content or "")
    if len(text) < 10 or INLINE_OPTION_PATTERN.match(text):
        return False
    return bool(
        re.search(
            r"(\(\)|（）|（\)|\(）|则有|正确的是|下列|已知|把.*?平移|求|判断|计算|证明)",
            text,
        )
    )


def new_question(number: str, stem: str, block: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "number": number,
        "stem": stem,
        "options": [],
        "figure_bboxes": [],
        "source_bbox": block.get("block_bbox"),
        "confidence": average_block_confidence(block.get("block_bbox"), lines),
        "review_status": "pending",
    }


def add_options_to_question(
    question: dict[str, Any], options: list[dict[str, str]], block: dict[str, Any], lines: list[dict[str, Any]]
) -> None:
    """Attach parsed option blocks to the preceding question, preserving their source area."""
    for option in options:
        option["source_bbox"] = block.get("block_bbox")
        option["confidence"] = average_block_confidence(block.get("block_bbox"), lines)
        if not option["content"]:
            option["requires_visual_review"] = True
        question["options"].append(option)


def average_block_confidence(block_bbox: Any, lines: list[dict[str, Any]]) -> float | None:
    if not isinstance(block_bbox, list) or len(block_bbox) != 4:
        return None
    _, top, _, bottom = block_bbox
    scores = []
    for line in lines:
        bbox = line.get("bbox")
        score = line.get("confidence")
        if not bbox or score is None:
            continue
        line_top = min(point[1] for point in bbox)
        line_bottom = max(point[1] for point in bbox)
        if line_bottom >= top and line_top <= bottom:
            scores.append(float(score))
    return round(sum(scores) / len(scores), 4) if scores else None


def draft_questions_from_structured_blocks(
    blocks: list[dict[str, Any]], lines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for block in blocks:
        block_label = block.get("block_label")
        if block_label == "image":
            # Diagram choices are emitted as an image after an `A.`/`B.` text block.
            if current is not None:
                bbox = block.get("block_bbox")
                if current["options"] and not current["options"][-1]["content"]:
                    option = current["options"][-1]
                    option["requires_visual_review"] = True
                    option["source_bbox"] = bbox
                    option.setdefault("image_bboxes", []).append(bbox)
                else:
                    current.setdefault("figure_bboxes", []).append(bbox)
            continue
        if block_label not in {"text", "paragraph_title"}:
            continue
        content = " ".join(str(block.get("block_content", "")).split())
        match = QUESTION_PATTERN.match(content)
        if match:
            stem, options = split_inline_options(match.group(2).strip())
            current = new_question(match.group(1), stem, block, lines)
            add_options_to_question(current, options, block, lines)
            questions.append(current)
        elif current is not None and content:
            stem, options = split_inline_options(content)
            if not options and looks_like_unnumbered_question_stem(content, current):
                current = new_question(next_question_number(questions), content, block, lines)
                questions.append(current)
                continue
            if options:
                add_options_to_question(current, options, block, lines)
            else:
                current["stem"] = f"{current['stem']} {content}".strip()
    return [enrich_question_type(question) for question in questions]


def draft_questions_from_document(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer PP-Structure blocks; use loose lines only when structure is unavailable."""
    lines = find_text_lines(payload)
    structured_drafts = draft_questions_from_structured_blocks(find_structured_blocks(payload), lines)
    return structured_drafts or draft_questions(lines)


def crop_bbox(image: Image.Image, bbox: Any, destination: Path) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    left, top, right, bottom = (int(float(value)) for value in bbox)
    padding = 8
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    if right <= left or bottom <= top:
        return False
    image.crop((left, top, right, bottom)).convert("RGB").save(destination, "JPEG", quality=92)
    return True


def split_bbox_by_whitespace(image: Image.Image, bbox: Any) -> list[list[int]]:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return []
    left, top, right, bottom = (int(float(value)) for value in bbox)
    padding = 4
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    if right <= left or bottom <= top:
        return []

    crop = image.crop((left, top, right, bottom)).convert("L")
    width, height = crop.size
    if width < 24 or height < 24:
        return [[left, top, right, bottom]]

    pixels = crop.load()
    column_ink = []
    row_ink = []
    dark_threshold = 240
    active_column_threshold = max(1, int(height * 0.03))
    active_row_threshold = max(1, int(width * 0.03))

    for x in range(width):
        count = 0
        for y in range(height):
            if pixels[x, y] < dark_threshold:
                count += 1
        column_ink.append(count)
    for y in range(height):
        count = 0
        for x in range(width):
            if pixels[x, y] < dark_threshold:
                count += 1
        row_ink.append(count)

    def spans(values: list[int], threshold: int) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        start: int | None = None
        for index, value in enumerate(values):
            if value >= threshold:
                if start is None:
                    start = index
            elif start is not None:
                result.append((start, index - 1))
                start = None
        if start is not None:
            result.append((start, len(values) - 1))
        return result

    column_spans = spans(column_ink, active_column_threshold)
    row_spans = spans(row_ink, active_row_threshold)

    if len(column_spans) > 1 and len(column_spans) >= len(row_spans):
        segments = []
        for start, end in column_spans:
            if end - start + 1 < 8:
                continue
            segments.append([left + start, top, left + end + 1, bottom])
        return segments or [[left, top, right, bottom]]

    if len(row_spans) > 1:
        segments = []
        for start, end in row_spans:
            if end - start + 1 < 8:
                continue
            segments.append([left, top + start, right, top + end + 1])
        return segments or [[left, top, right, bottom]]

    return [[left, top, right, bottom]]


def split_bbox_into_equal_parts(bbox: list[int], parts: int) -> list[list[int]]:
    if parts <= 1:
        return [bbox]
    left, top, right, bottom = bbox
    width = right - left
    if width <= 0:
        return [bbox]
    step = width / parts
    segments = []
    for index in range(parts):
        seg_left = int(round(left + step * index))
        seg_right = int(round(left + step * (index + 1)))
        if index == 0:
            seg_left = left
        if index == parts - 1:
            seg_right = right
        if seg_right > seg_left:
            segments.append([seg_left, top, seg_right, bottom])
    return segments or [bbox]


def bbox_ink_score(image: Image.Image, bbox: list[int]) -> int:
    left, top, right, bottom = bbox
    crop = image.crop((left, top, right, bottom)).convert("L")
    pixels = crop.load()
    score = 0
    for y in range(crop.height):
        for x in range(crop.width):
            if pixels[x, y] < 240:
                score += 1
    return score


def choose_dominant_bbox_part(image: Image.Image, parts: list[list[int]]) -> list[int] | None:
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    scored_parts = [(bbox_ink_score(image, part), part) for part in parts]
    scored_parts.sort(key=lambda item: (item[0], (item[1][3] - item[1][1]) * (item[1][2] - item[1][0])), reverse=True)
    return scored_parts[0][1]


def normalized_bbox(image: Image.Image, bbox: Any, padding: int = 4) -> list[int] | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    left, top, right, bottom = (int(float(value)) for value in bbox)
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def should_create_visual_option_slots(question: dict[str, Any], bbox: Any, part_bboxes: list[list[int]]) -> bool:
    if question.get("options"):
        return False
    normalized = re.sub(r"\s+", "", question.get("stem", ""))
    looks_like_choice = bool(re.search(r"(\(\)|（）|（\)|\(）|正确的是|下列|选择)", normalized))
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    width = float(bbox[2]) - float(bbox[0])
    height = float(bbox[3]) - float(bbox[1])
    is_wide_option_strip = height > 0 and width / height >= 2.5
    return is_wide_option_strip and (looks_like_choice or len(part_bboxes) >= 1)


def is_near_duplicate_bbox(bbox: Any, seen_bboxes: list[list[int]], threshold: float = 0.92) -> bool:
    return any(bbox_iou(bbox, seen_bbox) >= threshold for seen_bbox in seen_bboxes)


def persist_question_images(path: Path, questions: list[dict[str, Any]], recognition_id: str) -> None:
    destination_dir = GRAPH_UPLOAD_ROOT / recognition_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        for question_index, question in enumerate(questions, start=1):
            question_paths: list[str] = []
            processed_bboxes: list[list[int]] = []
            option_slots = [
                option
                for option in question.get("options", [])
                if not str(option.get("content", "")).strip() or option.get("requires_visual_review")
            ]
            for image_index, bbox in enumerate(question.pop("figure_bboxes", []), start=1):
                if is_near_duplicate_bbox(bbox, processed_bboxes):
                    continue
                if isinstance(bbox, list) and len(bbox) == 4:
                    processed_bboxes.append([int(float(value)) for value in bbox])
                part_bboxes = [bbox]
                if should_create_visual_option_slots(question, bbox, part_bboxes):
                    question["options"] = [
                        {"label": label, "content": "", "requires_visual_review": True}
                        for label in VISUAL_OPTION_LABELS
                    ]
                    option_slots = question["options"]
                    normalized = normalized_bbox(image, bbox)
                    split_parts = split_bbox_by_whitespace(image, normalized if normalized is not None else bbox)
                    dominant_part = choose_dominant_bbox_part(image, split_parts)
                    if dominant_part is None:
                        dominant_part = normalized if normalized is not None else [int(float(value)) for value in bbox]
                    part_bboxes = split_bbox_into_equal_parts(dominant_part, len(option_slots))
                elif option_slots:
                    part_bboxes = split_bbox_by_whitespace(image, bbox)
                    if len(part_bboxes) == 1 and len(option_slots) >= 3:
                        part_bboxes = split_bbox_into_equal_parts(part_bboxes[0], len(option_slots))
                if len(part_bboxes) > 1 and len(part_bboxes) == len(option_slots):
                    for option, part_bbox in zip(option_slots, part_bboxes):
                        filename = f"question-{question_index}-option-{option.get('label', 'X')}.jpg"
                        if crop_bbox(image, part_bbox, destination_dir / filename):
                            option.setdefault("image_paths", []).append(
                                f"/uploads/graphs/{recognition_id}/{filename}"
                            )
                    continue
                for part_index, part_bbox in enumerate(part_bboxes, start=1):
                    filename = f"question-{question_index}-figure-{image_index}-{part_index}.jpg"
                    if crop_bbox(image, part_bbox, destination_dir / filename):
                        question_paths.append(f"/uploads/graphs/{recognition_id}/{filename}")
            question["image_paths"] = question_paths

            for option_index, option in enumerate(question.get("options", []), start=1):
                option_paths: list[str] = list(option.get("image_paths", []))
                for image_index, bbox in enumerate(option.pop("image_bboxes", []), start=1):
                    for part_index, part_bbox in enumerate(split_bbox_by_whitespace(image, bbox), start=1):
                        filename = f"question-{question_index}-option-{option_index}-{image_index}-{part_index}.jpg"
                        if crop_bbox(image, part_bbox, destination_dir / filename):
                            option_paths.append(f"/uploads/graphs/{recognition_id}/{filename}")
                option["image_paths"] = option_paths


async def save_upload(upload: UploadFile, directory: Path, page_number: int) -> Path:
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {upload.content_type}")
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"File {upload.filename} is empty")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File {upload.filename} exceeds the size limit")
    suffix = Path(upload.filename or "image.jpg").suffix.lower() or ".jpg"
    path = directory / f"page-{page_number}{suffix}"
    path.write_bytes(content)
    return path


def recognize_page(path: Path, page_number: int, recognition_id: str) -> dict[str, Any]:
    pipeline = get_pipeline()
    results = list(pipeline.predict(str(path)))
    if not results:
        return {"page_number": page_number, "lines": [], "draft_questions": [], "raw_result": {}}
    raw_result = result_to_dict(results[0])
    lines = find_text_lines(raw_result)
    questions = draft_questions_from_document(raw_result)
    persist_question_images(path, questions, recognition_id)
    return {
        "page_number": page_number,
        "lines": lines,
        "draft_questions": questions,
        "raw_result": raw_result,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "device": DEVICE, "model_loaded": _pipeline is not None}


@app.post("/api/v1/recognitions")
async def recognize(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FILES} images are accepted")

    recognition_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="paper-ocr-") as temp_dir:
        temp_path = Path(temp_dir)
        uploaded_paths = [
            await save_upload(upload, temp_path, page_number)
            for page_number, upload in enumerate(files, start=1)
        ]
        pages = [
            await asyncio.to_thread(recognize_page, path, page_number, recognition_id)
            for page_number, path in enumerate(uploaded_paths, start=1)
        ]

    return {
        "status": "completed",
        "recognition_id": recognition_id,
        "page_count": len(pages),
        "pages": pages,
        "notice": "draft_questions must be confirmed by a user before writing to nine_question_bank.",
    }
