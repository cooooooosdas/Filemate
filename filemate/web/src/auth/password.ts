export function newPasswordError(value: string): string {
  const length = [...value].length
  if (length < 9 || length > 128) return '密码需为 9–128 个字符'
  if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) return '密码需同时包含字母和数字，符号可选'
  return ''
}
