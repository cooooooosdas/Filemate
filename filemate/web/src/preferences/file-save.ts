export function safeDownloadName(value: string): string {
  const clean = value.replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, '_').trim().replace(/[. ]+$/, '')
  if (!clean || clean === '.' || clean === '..') return 'FileMate-export.txt'
  if (clean.length <= 180) return clean
  const extension = clean.match(/\.[a-z0-9]{1,10}$/i)?.[0] || ''
  return clean.slice(0, 180 - extension.length) + extension
}

interface WritableFile { write(data: Blob): Promise<void>; close(): Promise<void>; abort?(): Promise<void> }
interface PickedFile { createWritable(): Promise<WritableFile> }
export async function writePickedFile(blob: Blob, filename: string, picker: (name: string) => Promise<PickedFile>): Promise<boolean> {
  let stream: WritableFile | undefined
  try {
    const handle = await picker(safeDownloadName(filename))
    stream = await handle.createWritable()
    await stream.write(blob)
    await stream.close()
    return true
  } catch (error) {
    if (stream) await stream.abort?.().catch(() => {})
    if (!stream && error instanceof Error && error.name === 'AbortError') return false
    throw error
  }
}
