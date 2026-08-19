# 试卷识别工作台 (Paper Vision)

拍照上传试卷 → OCR 识别题目 → 填写学段/年级/学科 → 写入题库

## 快速开始

### 1. 环境要求

- **MySQL** (自装，创建数据库并导入 pb_data.sql)
- **Java 17+** 或使用内置 JRE
- **Python 3.10+** 或使用内置 Python（仅 OCR 需要）

### 2. 启动

双击 `start.bat`，首次运行会提示配置数据库连接。

### 3. 使用

1. 上传试卷图片（支持多页）
2. 点击"开始识别"，等待 OCR 处理
3. 确认/编辑每道题的题型、选项、答案
4. 点击"确认并写入题库"
5. 弹窗中选择**学段、年级、学科、上下册**
6. 确认后写入数据库

## 项目结构

```
├── start.bat          # 一键启动脚本
├── build.bat          # 构建打包脚本
├── frontend/          # Vue.js 前端
├── ocr-service/       # Python OCR 服务 (PaddleOCR)
├── src/               # Java Spring Boot 后端
├── pom.xml            # Maven 配置
└── config.ini         # 数据库配置（首次运行生成）
```

## 端口

| 服务 | 端口 |
|------|------|
| 前端 + 后端 | 8080 |
| OCR 服务 | 8000 |
| MySQL | 3306 |

## 数据库表

- `nine_question_bank` — 题库表
- `nine_question_bank_rela` — 题目关联表（学段/年级/学科/版本/上下册）
- `nine_question_option` — 选择题选项表
- `nine_grade` — 年级字典
- `nine_subject` — 学科字典
