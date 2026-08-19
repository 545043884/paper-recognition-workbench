import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const app = await readFile(new URL('../src/App.vue', import.meta.url), 'utf8')

assert.match(
  app,
  /v-html="renderMathText\(question\.stem\)"/,
  '题干必须提供数学公式预览，而不是只用 textarea 显示原始 LaTeX'
)
assert.match(
  app,
  /v-html="renderMathText\(option\.text\)"/,
  '选项必须提供数学公式预览，而不是只用 input 显示原始 LaTeX'
)
assert.match(
  app,
  /v-if="question\.editing"/,
  '题干的原始 LaTeX 编辑框默认必须收起'
)
assert.match(
  app,
  /v-if="option\.editing"/,
  '选项的原始 LaTeX 编辑框默认必须收起'
)
