# OCR Service

This service accepts photographed exam pages and returns PaddleOCR structural results plus editable draft questions. It does **not** write any result to MySQL.

## Run

From `D:\ShiBie\untitled`:

```powershell
.\.venv-ocr\Scripts\Activate.ps1
cd .\ocr-service
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` to test the API. The first recognition request downloads PaddleOCR model weights and can take several minutes.

## Endpoint

`POST /api/v1/recognitions`

Send one or more image files in the `files` multipart field. The response includes:

- `pages[].lines`: recognized text with source coordinates and confidence.
- `pages[].draft_questions`: rule-based question/option drafts for the Vue confirmation page.
- `pages[].raw_result`: unmodified structural result from PaddleOCR, retained for troubleshooting and future parsing improvements.

Only after user confirmation should Spring Boot insert the selected draft into `nine_question_bank` and `nine_question_option`.

## Test department for question writes

Before enabling database writes, run [init_test_department.sql](./init_test_department.sql) once against `pb_data`. It creates or reuses `试卷识别测试部` and prints its numeric `dept_id`.

For the current test setup, use `ceshi01` for `codeid`, `create_by`, and `update_by`; use the printed `dept_id` for every inserted question. The write API must use a transaction: insert into `nine_question_bank`, then insert its `nine_question_option` rows, and roll back if any step fails.
