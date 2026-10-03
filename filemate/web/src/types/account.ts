export interface AccountUser {
  account_id: string
  email: string
  display_name: string
  created_at: string
}
export interface AccountState { user: AccountUser | null; enabled: boolean; expired: boolean }
export interface RegisterAccount {
  email: string; display_name: string; password: string; keep_guest_data: boolean; remember: boolean
}
