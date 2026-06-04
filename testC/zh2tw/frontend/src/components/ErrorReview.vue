<template>
  <div class="review-box">
    <div class="review-header">
      <span v-if="errorGroups.length === 0" class="no-error">✓ 未检测到易错字</span>
      <span v-else class="has-error">⚠ 检测到 {{ errorGroups.length }} 组易错字，请逐组确认</span>
    </div>
    <div v-for="group in errorGroups" :key="group.char" class="error-group">
      <div class="group-header">
        <span class="group-char">【{{ group.char }}】</span>
        <span class="group-count">出现 {{ group.items.length }} 处</span>
        <div class="group-candidates">
          <span class="label">批量设为：</span>
          <button v-for="c in group.candidates" :key="c" class="btn-candidate" @click="setGroupDefault(group, c)">{{ c }}</button>
          <button class="btn-set-all" @click="setAll(group)">全部设为「{{ group.defaultCandidate || '…' }}」</button>
        </div>
      </div>
      <div v-for="item in group.items" :key="item.position" class="error-item">
        <span class="item-context" v-html="highlightContext(item)"></span>
        <div class="item-candidates">
          <button
            v-for="c in group.candidates" :key="c"
            class="btn-candidate"
            :class="{ selected: item.selected === c }"
            @click="selectItem(item, c)"
          >{{ c }}</button>
        </div>
      </div>
    </div>
    <div v-if="errorGroups.length > 0" class="global-actions">
      <button class="btn btn-confirm" @click="confirmAll">確認所有替換</button>
      <button class="btn btn-undo" @click="undo" :disabled="!canUndo">撤銷上一次</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  errorChecks: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue', 'update:errorChecks'])

const errorGroups = ref([])
const history = ref(null)
const canUndo = ref(false)

watch(() => props.errorChecks, (checks) => {
  const map = {}
  for (const item of checks) {
    if (!map[item.char]) {
      map[item.char] = {
        char: item.char,
        candidates: item.candidates,
        defaultCandidate: null,
        items: []
      }
    }
    map[item.char].items.push({ ...item, selected: null, current: item.char })
  }
  errorGroups.value = Object.values(map)
  history.value = null
  canUndo.value = false
}, { immediate: true })

function highlightContext(item) {
  const display = item.current || item.char
  return item.context.replace(`【${item.char}】`, `<span class="hl">${display}</span>`)
}

function setGroupDefault(group, candidate) {
  group.defaultCandidate = candidate
  for (const item of group.items) {
    if (item.selected === null) {
      item.selected = candidate
      item.current = candidate
    }
  }
}

function setAll(group) {
  if (!group.defaultCandidate) return
  for (const item of group.items) {
    item.selected = group.defaultCandidate
    item.current = group.defaultCandidate
  }
}

function selectItem(item, candidate) {
  item.selected = candidate
  item.current = candidate
}

function confirmAll() {
  history.value = {
    resultText: props.modelValue,
    errorChecks: JSON.parse(JSON.stringify(props.errorChecks))
  }
  canUndo.value = true
  let text = props.modelValue
  const allItems = []
  for (const group of errorGroups.value) {
    for (const item of group.items) {
      if (item.selected !== null) allItems.push(item)
    }
  }
  allItems.sort((a, b) => b.position - a.position)
  for (const item of allItems) {
    text = text.slice(0, item.position) + item.selected + text.slice(item.position + item.char.length)
  }
  emit('update:modelValue', text)
  for (const group of errorGroups.value) {
    for (const item of group.items) {
      item.selected = null
      item.current = item.char
    }
    group.defaultCandidate = null
  }
}

function undo() {
  if (!history.value) return
  emit('update:modelValue', history.value.resultText)
  emit('update:errorChecks', history.value.errorChecks)
  history.value = null
  canUndo.value = false
}
</script>

<style scoped>
.review-box { margin-top: 20px; background: #fff; border-radius: 8px; border: 1px solid #dee2e6; padding: 16px; }
.review-header { font-size: 14px; margin-bottom: 16px; font-weight: 500; }
.no-error { color: #2d6a4f; }
.has-error { color: #e67e00; }
.error-group { border: 1px solid #e9ecef; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; background: #f8f9fa; }
.group-header { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.group-char { font-size: 16px; font-weight: bold; color: #5c4db1; }
.group-count { font-size: 13px; color: #6c757d; }
.group-candidates { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.label { font-size: 13px; color: #6c757d; }
.btn-candidate { background: #fff; color: #5c4db1; border: 1px solid #5c4db1; border-radius: 4px; padding: 2px 10px; font-size: 13px; cursor: pointer; }
.btn-candidate:hover { background: #ede9f8; }
.btn-candidate.selected { background: #5c4db1; color: #fff; }
.btn-set-all { background: #e9ecef; color: #495057; border: 1px solid #ced4da; border-radius: 4px; padding: 2px 10px; font-size: 13px; cursor: pointer; }
.btn-set-all:hover { background: #dee2e6; }
.error-item { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-top: 1px solid #e9ecef; gap: 12px; }
.item-context { font-size: 16px; color: #343a40; flex: 1; line-height: 1.6; }
.item-candidates { display: flex; gap: 6px; flex-shrink: 0; }
:deep(.hl) { background: #fff3cd; color: #212529; border-radius: 3px; padding: 0 3px; font-weight: bold; }
.global-actions { display: flex; gap: 12px; margin-top: 16px; padding-top: 16px; border-top: 1px solid #dee2e6; }
.btn { padding: 10px 28px; border: none; border-radius: 8px; font-size: 15px; cursor: pointer; }
.btn-confirm { background: #5c4db1; color: #fff; font-weight: bold; }
.btn-confirm:hover { background: #4a3d9a; }
.btn-undo { background: #fff; color: #dc3545; border: 1px solid #dc3545; padding: 10px 28px; }
.btn-undo:hover { background: #fff5f5; }
.btn-undo:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
