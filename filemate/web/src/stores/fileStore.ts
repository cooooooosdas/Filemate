import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProcessingSession } from '../types'

export const useFileStore = defineStore('file', () => {
  // 状态
  const files = ref<ProcessingSession[]>([])
  const currentFile = ref<ProcessingSession | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 当前文件列表
  const fileList = ref<{ id: string; name: string; status: string }[]>([])

  // 添加文件
  function addFile(session: ProcessingSession) {
    files.value.push(session)
    if (!currentFile.value) {
      currentFile.value = session
    }
  }

  // 设置当前文件
  function setCurrentFile(session: ProcessingSession | null) {
    currentFile.value = session
  }

  // 更新文件
  function updateFile(session: ProcessingSession) {
    const index = files.value.findIndex(f => f.session_id === session.session_id)
    if (index >= 0) {
      files.value[index] = session
    } else {
      files.value.push(session)
    }
    if (currentFile.value?.session_id === session.session_id) {
      currentFile.value = session
    }
  }

  // 清空文件
  function clearFiles() {
    files.value = []
    currentFile.value = null
    error.value = null
  }

  return {
    files,
    currentFile,
    loading,
    error,
    fileList,
    addFile,
    setCurrentFile,
    updateFile,
    clearFiles
  }
})