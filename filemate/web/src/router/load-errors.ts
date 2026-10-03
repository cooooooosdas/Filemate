import { shallowRef } from 'vue'

export const pageLoadFailure = shallowRef<{ path: string } | null>(null)
