export interface OrgAddress {
  country: string
  state: string
  city: string
}

export interface AdminUserProfile {
  user_id: string
  name: string
  email: string
  role: string
  active: boolean
}

export interface AdminOrgProfile {
  org_id: string
  name: string
  currency: string
  address: OrgAddress | null
  active: boolean
}

export interface LoginPayload {
  password: string
}

export interface LoginResponse {
  user: AdminUserProfile
  org: AdminOrgProfile
}

export interface MeResponse {
  user: AdminUserProfile
  org: AdminOrgProfile
}

export interface WsTicketResponse {
  ticket: string
  expires_in: number
}
