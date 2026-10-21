import type { AudioBinding } from './interviewAudio'

export interface LocalVideoTake {
  id: string
  binding: AudioBinding
  blob: Blob
  duration: number
  hasAudio: boolean
  partial: boolean
  issue: string | null
}
export interface VideoItem extends LocalVideoTake { url: string; attemptId: string | null }
