-- One-time setup for the paper-recognition test tenant.
-- Run this against the pb_data MySQL database before enabling question writes.
-- It is safe to re-run: an active department with the same name is reused.

START TRANSACTION;

SET @department_name = '试卷识别测试部';
SET @operator_name = 'ceshi01';
SET @test_department_id = NULL;

SELECT dept_id
INTO @test_department_id
FROM fire_dept
WHERE dept_name = @department_name
  AND del_flag = '0'
ORDER BY dept_id
LIMIT 1;

INSERT INTO fire_dept (
  parent_id,
  ancestors,
  dept_name,
  order_num,
  leader,
  email,
  status,
  del_flag,
  create_by,
  create_time,
  update_by,
  update_time,
  org_id
)
SELECT
  0,
  '0',
  @department_name,
  999,
  @operator_name,
  NULL,
  '0',
  '0',
  @operator_name,
  NOW(),
  @operator_name,
  NOW(),
  0
WHERE @test_department_id IS NULL;

SET @test_department_id = COALESCE(@test_department_id, LAST_INSERT_ID());

COMMIT;

SELECT
  @test_department_id AS dept_id,
  'ceshi01' AS codeid,
  'ceshi01' AS create_by,
  @department_name AS dept_name;
