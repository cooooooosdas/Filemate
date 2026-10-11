import { shallowRef } from 'vue'

export const pageLoadFailure = shallowRef<{ path: string } | null>(null)
export const navigationPending = shallowRef<string | null>(null)
