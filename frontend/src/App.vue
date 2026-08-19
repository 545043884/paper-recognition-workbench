<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const fileInput = ref(null)
const files = ref([])
const activePage = ref(0)
const isRecognizing = ref(false)
const saved = ref(false)
const toast = ref('')
const recognitionError = ref('')
const uploadingImageTarget = ref('')

/* ---- 题目关联信息弹窗 ---- */
const showRelaDialog = ref(false)
const relaForm = ref({ stageId: null, gradeId: null, subjectId: null, xueqiId: 1 })
const availableGrades = computed(() =>
  relaForm.value.stageId ? GRADES.filter((g) => g.stageId === relaForm.value.stageId) : []
)

const OCR_API_URL = import.meta.env.VITE_OCR_API_URL || 'http://127.0.0.1:8000'
const QUESTION_API_URL = import.meta.env.VITE_QUESTION_API_URL || ''

const questionTypeNames = ['单选题', '多选题', '填空题', '判断题', '简答题']
const difficultyLevels = { 简单: 0, 一般: 1, 中等: 2, 困难: 3, 特难: 4 }

/* ---- 学段/年级/学科 静态数据（与 nine_grade / nine_subject 表同步） ---- */
const STAGES = [
  { id: 1, name: '小学' },
  { id: 2, name: '初中' },
  { id: 3, name: '高中' }
]

const GRADES = [
  { id: 1, name: '一年级', stageId: 1 },
  { id: 2, name: '二年级', stageId: 1 },
  { id: 3, name: '三年级', stageId: 1 },
  { id: 4, name: '四年级', stageId: 1 },
  { id: 5, name: '五年级', stageId: 1 },
  { id: 6, name: '六年级', stageId: 1 },
  { id: 7, name: '七年级', stageId: 2 },
  { id: 8, name: '八年级', stageId: 2 },
  { id: 9, name: '九年级', stageId: 2 },
  { id: 10, name: '高一', stageId: 3 },
  { id: 11, name: '高二', stageId: 3 },
  { id: 12, name: '高三', stageId: 3 }
]

const SUBJECTS = [
  { id: 1, name: '语文' },
  { id: 2, name: '数学' },
  { id: 3, name: '英语' },
  { id: 4, name: '物理' },
  { id: 5, name: '化学' },
  { id: 6, name: '生物' },
  { id: 7, name: '政治' },
  { id: 8, name: '地理' },
  { id: 9, name: '历史' },
  { id: 10, name: '科学' },
  { id: 11, name: '道德与法治' }
]

const questions = ref([
  {
    number: '01',
    typeCode: 0,
    confidence: 96,
    stem: '小明有 24 支铅笔，平均分给 6 个同学，每人可以分到多少支？',
    imagePaths: [],
    options: [
      { label: 'A', text: '3 支', imagePaths: [], requiresVisualReview: false },
      { label: 'B', text: '4 支', imagePaths: [], requiresVisualReview: false },
      { label: 'C', text: '5 支', imagePaths: [], requiresVisualReview: false },
      { label: 'D', text: '6 支', imagePaths: [], requiresVisualReview: false }
    ],
    answer: 'B',
    difficulty: '一般',
    status: '待确认',
    editing: false
  }
])

const confirmedCount = computed(() => questions.value.filter((item) => item.status === '已确认').length)
const pendingCount = computed(() => questions.value.length - confirmedCount.value)

function showToast(message, delay = 2600) {
  toast.value = message
  window.setTimeout(() => {
    if (toast.value === message) toast.value = ''
  }, delay)
}

function resolveOcrAsset(path) {
  if (!path) return ''
  return /^https?:\/\//.test(path) ? path : `${OCR_API_URL}${path}`
}

function normalizeImagePaths(value) {
  return Array.isArray(value) ? value.filter(Boolean) : []
}

function normalizeOptions(options) {
  return (options || []).map((option, index) => ({
    label: String(option.label || String.fromCharCode(65 + index)).trim().toUpperCase(),
    text: option.content || option.text || '',
    imagePaths: normalizeImagePaths(option.image_paths || option.imagePaths),
    requiresVisualReview: Boolean(option.requires_visual_review || option.requiresVisualReview),
    editing: false
  })).sort((left, right) => left.label.localeCompare(right.label))
}

function sortOptions(question) {
  question.options = [...question.options].sort((left, right) => left.label.localeCompare(right.label))
}

async function uploadImages(event, target, targetKey) {
  const selected = Array.from(event.target.files || [])
  event.target.value = ''
  if (!selected.length) return
  uploadingImageTarget.value = targetKey
  try {
    for (const file of selected) {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`${OCR_API_URL}/api/v1/assets`, { method: 'POST', body: formData })
      if (!response.ok) throw new Error(await readErrorMessage(response, '图片上传失败'))
      const payload = await response.json()
      target.imagePaths = [...(target.imagePaths || []), payload.path]
    }
    showToast('图片已添加，可继续编辑或删除')
  } catch (error) {
    showToast(error.message || '图片上传失败')
  } finally {
    uploadingImageTarget.value = ''
  }
}

function removeImage(target, index) {
  target.imagePaths = (target.imagePaths || []).filter((_, imageIndex) => imageIndex !== index)
}

function nextOptionLabel(options) {
  const used = new Set((options || []).map((option) => option.label))
  for (let index = 0; index < 26; index += 1) {
    const label = String.fromCharCode(65 + index)
    if (!used.has(label)) return label
  }
  return ''
}

function addOption(question) {
  const label = nextOptionLabel(question.options)
  if (!label) return
  question.options.push({ label, text: '', imagePaths: [], requiresVisualReview: true, editing: true })
  sortOptions(question)
  question.editing = true
  saved.value = false
}

function removeOption(question, option) {
  question.options = question.options.filter((item) => item !== option)
  sortOptions(question)
  saved.value = false
}

function addQuestion() {
  const numbers = questions.value.map((question) => Number.parseInt(question.number, 10)).filter(Number.isFinite)
  const number = String((numbers.length ? Math.max(...numbers) : 0) + 1)
  questions.value.push({
    number,
    typeCode: 0,
    confidence: 0,
    stem: '',
    imagePaths: [],
    options: [
      { label: 'A', text: '', imagePaths: [], requiresVisualReview: true, editing: true },
      { label: 'B', text: '', imagePaths: [], requiresVisualReview: true, editing: true }
    ],
    answer: '',
    difficulty: '一般',
    status: '待确认',
    editing: true
  })
  saved.value = false
  showToast(`已添加第 ${number} 题，请填写题干和选项`)
}

function removeQuestion(question) {
  if (!window.confirm(`确定删除第 ${question.number} 题吗？`)) return
  questions.value = questions.value.filter((item) => item !== question)
  saved.value = false
  showToast(`已删除第 ${question.number} 题`)
}

function questionTypeLabel(code) {
  return code === null || code === undefined ? '确认题型' : questionTypeNames[Number(code)] || '确认题型'
}

function chooseFiles(event) {
  files.value.forEach((file) => URL.revokeObjectURL(file.url))
  const selected = Array.from(event.target.files || [])
  files.value = selected.map((file, index) => ({
    file,
    name: file.name,
    size: formatSize(file.size),
    page: index + 1,
    url: URL.createObjectURL(file)
  }))
  activePage.value = 0
  saved.value = false
  recognitionError.value = ''
}

function removeFile(index) {
  URL.revokeObjectURL(files.value[index].url)
  files.value.splice(index, 1)
  activePage.value = Math.min(activePage.value, Math.max(0, files.value.length - 1))
}

function formatSize(size) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function renderMathText(value) {
  const source = String(value || '')
  const pattern = /\$([^$]+)\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g
  let cursor = 0
  let result = ''

  for (const match of source.matchAll(pattern)) {
    result += escapeHtml(source.slice(cursor, match.index))
    const expression = match[1] ?? match[2] ?? match[3]
    result += katex.renderToString(expression, { throwOnError: false, strict: 'ignore' })
    cursor = (match.index || 0) + match[0].length
  }

  return result + escapeHtml(source.slice(cursor))
}

async function readErrorMessage(response, fallback) {
  try {
    const payload = await response.json()
    return payload.detail || payload.message || payload.error || fallback
  } catch {
    return fallback
  }
}

function inferQuestionType(stem, options) {
  const compact = String(stem || '').replace(/\s+/g, '')
  if (options?.length) {
    return /多选|不定项|可多选|全部正确|所有.*正确/.test(compact) ? 1 : 0
  }
  if (/判断|对错|正确.*错误|√|×/.test(compact)) return 3
  if (/填空|\(\s*\)|（\s*）|_{2,}|横线|空格/.test(String(stem || ''))) return 2
  if (/简答|解答|计算|证明|作图|说明|写出|求/.test(compact)) return 4
  return null
}

async function runRecognition() {
  if (!files.value.length) {
    showToast('请先上传至少一张试卷图片', 2200)
    return
  }

  isRecognizing.value = true
  saved.value = false
  recognitionError.value = ''

  try {
    const formData = new FormData()
    files.value.forEach(({ file }) => formData.append('files', file))
    const response = await fetch(`${OCR_API_URL}/api/v1/recognitions`, {
      method: 'POST',
      body: formData
    })
    if (!response.ok) throw new Error(await readErrorMessage(response, '识别服务请求失败'))
    const payload = await response.json()

    const draftQuestions = (payload.pages || []).flatMap((page) => page.draft_questions || [])
    questions.value = draftQuestions.map((item, index) => {
      const options = normalizeOptions(item.options)
      const typeCode = item.suggested_question_type ?? inferQuestionType(item.stem, options)

      return {
        number: item.number || String(index + 1),
        typeCode,
        confidence: Math.round((item.confidence || item.type_confidence || 0) * 100),
        stem: item.stem || '',
        imagePaths: normalizeImagePaths(item.image_paths || item.imagePaths),
        options,
        answer: '',
        difficulty: '一般',
        status: '待确认',
        editing: false
      }
    })
    showToast(`识别完成：发现 ${questions.value.length} 道待确认题目`)
  } catch (error) {
    recognitionError.value = error.message
    showToast('识别失败，请检查 OCR 服务是否已启动')
  } finally {
    isRecognizing.value = false
  }
}

function beforeSaveQuestions() {
  recognitionError.value = ''
  if (questions.value.some((question) => question.typeCode === null || question.typeCode === undefined)) {
    showToast('请先确认所有题目的题型')
    return
  }
  showRelaDialog.value = true
}

async function confirmSave() {
  const form = relaForm.value
  if (!form.stageId || !form.gradeId || !form.subjectId) {
    showToast('请完整填写学段、年级和学科')
    return
  }

  showRelaDialog.value = false
  isRecognizing.value = true
  try {
    const response = await fetch(`${QUESTION_API_URL}/api/question-bank/imports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        questions: questions.value.map((question) => ({
          content: question.stem,
          questionType: Number(question.typeCode),
          difficultyLevel: difficultyLevels[question.difficulty],
          correctAnswer: question.answer || null,
          imagePaths: question.imagePaths || [],
          options: question.options.map((option) => ({
            label: option.label,
            content: option.text || `[图形选项${option.imagePaths?.length ? '' : '待确认'}]`,
            imagePaths: option.imagePaths || []
          }))
        })),
        rela: {
          stageId: form.stageId,
          gradeId: form.gradeId,
          subjectId: form.subjectId,
          editionId: 0,
          xueqiId: form.xueqiId
        }
      })
    })
    if (!response.ok) throw new Error(await readErrorMessage(response, '题库写入失败'))
    const payload = await response.json()
    questions.value = []
    saved.value = false
    showToast(`已写入题库：${payload.insertedCount} 道题，右侧识别结果已清空`)
  } catch (error) {
    recognitionError.value = error.message
    showToast(error.message || '题库写入失败，未保存任何题目')
  } finally {
    isRecognizing.value = false
  }
}

function cancelRelaDialog() {
  showRelaDialog.value = false
}

onBeforeUnmount(() => {
  files.value.forEach((file) => URL.revokeObjectURL(file.url))
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">识</div>
        <div>
          <div class="brand-title">试卷识别工作台</div>
          <div class="brand-subtitle">Paper Vision · 题库录入</div>
        </div>
      </div>
      <div class="top-actions">
        <span class="environment-dot"></span>
        <span>开发环境</span>
        <div class="avatar">库</div>
      </div>
    </header>

    <main class="page">
      <div class="page-heading">
        <div>
          <div class="eyebrow">CONTENT INGESTION</div>
          <h1>上传并识别试卷</h1>
          <p>提取题干、选项、公式和函数图像，确认后写入 <code>nine_question_bank</code></p>
        </div>
        <div class="stepper">
          <div class="step active"><span>1</span> 上传图片</div>
          <div class="step-line"></div>
          <div class="step"><span>2</span> 识别确认</div>
          <div class="step-line"></div>
          <div class="step"><span>3</span> 写入题库</div>
        </div>
      </div>

      <section class="workspace-grid">
        <aside class="panel upload-panel">
          <div class="panel-title-row">
            <div>
              <div class="panel-kicker">STEP 01</div>
              <h2>试卷图片</h2>
            </div>
            <span class="count-pill">{{ files.length || 0 }} 页</span>
          </div>

          <input ref="fileInput" class="hidden-input" type="file" accept="image/*" multiple @change="chooseFiles" />
          <button class="dropzone" @click="fileInput?.click()">
            <span class="upload-icon">↑</span>
            <strong>点击选择试卷图片</strong>
            <span>支持 JPG、PNG，可一次选择多页</span>
          </button>

          <div v-if="files.length" class="file-list">
            <div
              v-for="(file, index) in files"
              :key="file.url"
              class="file-row"
              :class="{ selected: activePage === index }"
              @click="activePage = index"
            >
              <img :src="file.url" alt="" />
              <div class="file-meta">
                <strong>第 {{ file.page }} 页</strong>
                <span>{{ file.name }} · {{ file.size }}</span>
              </div>
              <button class="delete-button" aria-label="删除" @click.stop="removeFile(index)">×</button>
            </div>
          </div>
          <div v-else class="empty-files">
            <span class="empty-icon">□</span>
            <span>还没有上传图片</span>
          </div>

          <div class="tip-card">
            <span>✦</span>
            <div>
              <strong>拍摄建议</strong>
              <p>保持页面完整、光线均匀，函数图和选项图尽量不要被截断。</p>
            </div>
          </div>
        </aside>

        <section class="panel preview-panel">
          <div class="panel-title-row">
            <div>
              <div class="panel-kicker">PREVIEW</div>
              <h2>原图预览</h2>
            </div>
            <span v-if="files.length" class="preview-label">第 {{ activePage + 1 }} 页 / {{ files.length }}</span>
          </div>
          <div class="preview-stage">
            <img v-if="files.length" :src="files[activePage].url" alt="试卷预览" />
            <div v-else class="preview-placeholder">
              <div class="document-icon">□</div>
              <strong>上传图片后预览</strong>
              <span>识别结果会在右侧生成</span>
            </div>
          </div>
          <div class="preview-footer">
            <span>原图仅用于本次识别，确认后由后端保存题目图像地址</span>
            <span class="secure">安全处理</span>
          </div>
        </section>

        <section class="panel result-panel">
          <div class="panel-title-row">
            <div>
              <div class="panel-kicker">STEP 02</div>
              <h2>识别结果</h2>
            </div>
            <span class="result-status" :class="{ busy: isRecognizing, done: !isRecognizing && files.length }">
              <i></i>{{ isRecognizing ? '识别中' : files.length ? '识别完成' : '等待上传' }}
            </span>
          </div>

          <div class="result-summary">
            <div><strong>{{ questions.length }}</strong><span>检测题目</span></div>
            <div><strong>{{ confirmedCount }}</strong><span>已确认</span></div>
            <div><strong>{{ pendingCount }}</strong><span>待确认</span></div>
          </div>

          <div v-if="recognitionError" class="service-error">
            <strong>服务错误</strong><span>{{ recognitionError }}</span>
          </div>

          <div class="question-list">
            <article
              v-for="question in questions"
              :key="question.number"
              class="question-card"
              :class="{ warning: question.status !== '已确认' }"
            >
              <div class="question-head">
                <div class="question-number">{{ question.number }}</div>
                <select v-model="question.typeCode" class="type-select" aria-label="题型确认" @change="saved = false">
                  <option :value="null" disabled>确认题型</option>
                  <option v-for="(name, code) in questionTypeNames" :key="code" :value="Number(code)">
                    {{ name }}
                  </option>
                </select>
                <span class="confidence">置信度 {{ question.confidence }}%</span>
                <span class="question-status">{{ question.status }}</span>
                <button type="button" class="question-delete-button" @click="removeQuestion(question)">删除本题</button>
              </div>

              <div class="preview-row stem-preview">
                <div class="math-preview" v-html="renderMathText(question.stem)"></div>
                <button class="edit-formula-button" @click="question.editing = !question.editing">
                  {{ question.editing ? '收起编辑' : '编辑' }}
                </button>
              </div>
              <textarea
                v-if="question.editing"
                v-model="question.stem"
                class="stem-input"
                rows="2"
                aria-label="编辑题干原始内容"
              ></textarea>

              <div v-if="question.editing" class="image-edit-toolbar">
                <label class="image-upload-button">
                  {{ uploadingImageTarget === `question-${question.number}` ? '上传中…' : '添加题干图片' }}
                  <input type="file" accept="image/*" multiple :disabled="Boolean(uploadingImageTarget)" @change="uploadImages($event, question, `question-${question.number}`)" />
                </label>
                <span>可添加多张图片，已有图片可删除</span>
              </div>

              <div v-if="question.imagePaths?.length" class="question-images">
                <div v-for="(path, imageIndex) in question.imagePaths" :key="path" class="editable-image">
                  <img :src="resolveOcrAsset(path)" alt="题目中的函数图像" />
                  <button v-if="question.editing" type="button" class="remove-image-button" @click="removeImage(question, imageIndex)">×</button>
                </div>
              </div>

              <div v-if="question.options.length" class="options-grid">
                <div v-for="option in question.options" :key="option.label" class="option-row">
                  <b>{{ option.label }}</b>
                  <div class="option-editor">
                    <div v-if="option.imagePaths?.length" class="option-images">
                      <div v-for="(path, imageIndex) in option.imagePaths" :key="path" class="editable-image">
                        <img :src="resolveOcrAsset(path)" :alt="`选项 ${option.label} 图像`" />
                        <button v-if="option.editing" type="button" class="remove-image-button" @click="removeImage(option, imageIndex)">×</button>
                      </div>
                    </div>
                    <div v-else-if="option.requiresVisualReview && !option.text" class="missing-option-image">
                      图形待确认：OCR 没有返回该选项的图片路径
                    </div>

                    <div class="preview-row option-preview-row">
                      <div
                        v-if="option.text || option.editing || !option.imagePaths?.length"
                        class="math-preview option-preview"
                        v-html="renderMathText(option.text)"
                      ></div>
                      <button class="edit-formula-button" @click="option.editing = !option.editing">
                        {{ option.editing ? '收起编辑' : '编辑' }}
                      </button>
                      <button v-if="question.options.length > 1" type="button" class="remove-option-button preview-remove-option" @click="removeOption(question, option)">删除选项</button>
                    </div>
                    <input
                      v-if="option.editing"
                      v-model="option.text"
                      :placeholder="option.requiresVisualReview ? '图形选项，可填写文字说明' : '请输入选项内容'"
                      :aria-label="`编辑选项 ${option.label} 原始内容`"
                    />
                    <div v-if="option.editing" class="image-edit-toolbar option-image-toolbar">
                      <label class="image-upload-button">
                        {{ uploadingImageTarget === `option-${question.number}-${option.label}` ? '上传中…' : '添加选项图片' }}
                        <input type="file" accept="image/*" multiple :disabled="Boolean(uploadingImageTarget)" @change="uploadImages($event, option, `option-${question.number}-${option.label}`)" />
                      </label>
                      <span>支持多张图，已有图片可删除</span>
                    </div>
                  </div>
                  <span v-if="option.imagePaths?.length" class="visual-option-note">图片已识别</span>
                  <span v-else-if="option.requiresVisualReview" class="visual-option-note">图形待确认</span>
                </div>
              </div>

              <div v-if="question.typeCode !== null && Number(question.typeCode) <= 1" class="option-actions">
                <button type="button" class="add-option-button" :disabled="question.options.length >= 26" @click="addOption(question)">＋ 添加选项（可分别上传图片）</button>
              </div>

              <div class="answer-row">
                <label>
                  标准答案
                  <input v-model="question.answer" :placeholder="questionTypeLabel(question.typeCode) === '简答题' ? '可为空' : '请输入答案'" />
                </label>
                <label>
                  难度
                  <select v-model="question.difficulty">
                    <option>简单</option>
                    <option>一般</option>
                    <option>中等</option>
                    <option>困难</option>
                    <option>特难</option>
                  </select>
                </label>
              </div>
            </article>
          </div>

          <div class="result-actions">
            <button class="secondary-button add-question-button" :disabled="isRecognizing" @click="addQuestion">
              ＋ 手动添加题目
            </button>
            <button class="secondary-button" :disabled="isRecognizing" @click="runRecognition">
              {{ isRecognizing ? '识别处理中' : '开始识别' }}
            </button>
            <button class="primary-button" :disabled="isRecognizing" @click="beforeSaveQuestions">
              {{ saved ? '已保存到题库' : '确认并写入题库 →' }}
            </button>
          </div>
        </section>
      </section>
    </main>
    <!-- 题目关联信息弹窗 -->
    <div v-if="showRelaDialog" class="modal-overlay" @click.self="cancelRelaDialog">
      <div class="modal-card">
        <div class="modal-header">
          <h3>填写题目关联信息</h3>
          <p>请选择本题所属的学段、年级和学科，用于写入 nine_question_bank_rela</p>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>学段 <span class="required">*</span></label>
            <select v-model="relaForm.stageId" @change="relaForm.gradeId = null">
              <option :value="null" disabled>请选择学段</option>
              <option v-for="s in STAGES" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>年级 <span class="required">*</span></label>
            <select v-model="relaForm.gradeId" :disabled="!relaForm.stageId">
              <option :value="null" disabled>请选择年级</option>
              <option v-for="g in availableGrades" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>学科 <span class="required">*</span></label>
            <select v-model="relaForm.subjectId">
              <option :value="null" disabled>请选择学科</option>
              <option v-for="s in SUBJECTS" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>上下册</label>
            <select v-model="relaForm.xueqiId">
              <option :value="1">上册</option>
              <option :value="2">下册</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="secondary-button" @click="cancelRelaDialog">取消</button>
          <button class="primary-button" @click="confirmSave">确认并写入题库</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>
