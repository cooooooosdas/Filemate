import { safeDownloadName, writePickedFile } from '../preferences/file-save'

interface PickerWindow extends Window {
  showDirectoryPicker?: (options: { id: string; mode: string }) => Promise<FileSystemDirectoryHandle>
  showSaveFilePicker?: (options: { id: string; suggestedName: string; startIn: FileSystemDirectoryHandle }) => Promise<FileSystemFileHandle>
}
let folder: FileSystemDirectoryHandle | undefined
let loaded = false
let loadError = ''
const DB = 'filemate-download-preferences'
const STORE = 'preferences'
function rememberedFolder(): string | null {
  try { return localStorage.getItem('filemate-download-folder') } catch { return null }
}
function hasRememberedFolder(): boolean {
  return rememberedFolder() === 'selected'
}
function rememberFolder(selected: boolean): boolean {
  try {
    localStorage.setItem('filemate-download-folder', selected ? 'selected' : 'default')
    return true
  } catch { return false }
}

export function folderPickerAvailable(): boolean {
  const host = window as PickerWindow
  return isSecureContext && typeof host.showDirectoryPicker === 'function' && typeof host.showSaveFilePicker === 'function'
}

async function folderRecord(mode: 'read' | 'write' | 'remove', value?: FileSystemDirectoryHandle): Promise<FileSystemDirectoryHandle | undefined> {
  if (!globalThis.indexedDB) throw Error('当前浏览器无法记住目录，选择仅在本次打开期间生效。')
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = req.onblocked = () => reject(Error('目录偏好无法读取，请在设置中重新选择。'))
  })
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode === 'read' ? 'readonly' : 'readwrite')
      const store = tx.objectStore(STORE)
      const req = mode === 'read' ? store.get('folder') : mode === 'write' ? store.put(value, 'folder') : store.delete('folder')
      tx.oncomplete = () => resolve(mode === 'read' ? req.result : value)
      tx.onabort = tx.onerror = () => reject(Error('目录偏好保存失败，请重试。'))
    })
  } finally { db.close() }
}

export async function downloadLocation(): Promise<{ name: string; error: string }> {
  if (!loaded) {
    try { folder = rememberedFolder() === 'default' ? undefined : await folderRecord('read'); loadError = '' }
    catch (error) { loadError = error instanceof Error ? error.message : '目录偏好读取失败' }
    loaded = true
  }
  return { name: folder?.name || '', error: loadError }
}

export async function chooseDownloadFolder(): Promise<boolean> {
  if (!folderPickerAvailable()) throw Error('当前浏览器请通过下载设置选择保存位置。')
  let selected: FileSystemDirectoryHandle
  try { selected = await (window as PickerWindow).showDirectoryPicker!({ id: 'filemate-exports', mode: 'read' }) }
  catch (error) { if (error instanceof Error && error.name === 'AbortError') return false; throw error }
  // Only a handle is retained locally; no folder path or contents are sent to the server.
  folder = selected; loaded = true
  try {
    await folderRecord('write', selected)
    loadError = rememberFolder(true) ? '' : '目录已选中，浏览器未允许完整保存偏好；请在下次打开时核对目录。'
  }
  catch { loadError = '目录已选中，仅在本次打开期间生效；浏览器未允许记住目录。' }
  return true
}

export async function resetDownloadFolder(): Promise<void> {
  folder = undefined; loaded = true; loadError = ''
  // An explicit default prevents an undeletable old handle from returning after reload.
  const remembered = rememberFolder(false)
  try { await folderRecord('remove') }
  catch {
    if (!remembered) loadError = '已恢复浏览器默认下载，仅在本次打开期间生效；浏览器未允许记住设置。'
  }
}

export async function saveDownload(blob: Blob, filename: string): Promise<boolean> {
  const name = safeDownloadName(filename)
  try {
    await downloadLocation()
    if (folder) {
      if (!folderPickerAvailable()) throw Error('此浏览器无法使用已选目录，请在设置中改为浏览器默认下载。')
      const { ElMessageBox } = await import('./download-dialog')
      let picked: Promise<FileSystemFileHandle> | undefined
      try {
        await ElMessageBox.confirm(`文件：${name}\n大小：${Math.max(1, Math.ceil(blob.size / 1024))} KB\n建议文件夹：${folder.name}\n下一步可核对位置和文件名；覆盖同名文件由系统再次确认。`, '确认导出文件', {
          confirmButtonText: '选择并保存', cancelButtonText: '取消导出', distinguishCancelAndClose: true,
          beforeClose(action, _instance, done) {
            if (action === 'confirm') {
              picked = (window as PickerWindow).showSaveFilePicker!({ id: 'filemate-exports', suggestedName: name, startIn: folder! })
              void picked.catch(() => {})
            }
            done()
          },
        })
      } catch (error) { if (error === 'cancel' || error === 'close') return false; throw error }
      return await writePickedFile(blob, name, () => picked!)
    }
    if (loadError && hasRememberedFolder()) throw Error(loadError)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = name
    document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 30000)
    return true
  } catch (error) {
    const { ElMessage } = await import('./download-dialog')
    ElMessage.error(error instanceof Error ? error.message : '文件未保存，请重试。')
    return false
  }
}
