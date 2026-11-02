/** Consume the public error contract; tolerate raw transport errors at adapters. */
export function readHttpStatus(error: unknown): number | undefined {
  const value = error as { status?: unknown; response?: { status?: unknown } } | null
  const status = value?.status ?? value?.response?.status
  return typeof status === 'number' && Number.isInteger(status) && status >= 100 && status <= 599 ? status : undefined
}
