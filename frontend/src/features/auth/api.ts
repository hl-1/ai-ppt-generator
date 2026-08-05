import { request } from '@/api/client'

export interface UserPublic {
  id: string
  email: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserPublic
}

export interface Credentials {
  email: string
  password: string
}

export function register(payload: Credentials) {
  return request<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function login(payload: Credentials) {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchCurrentUser() {
  return request<UserPublic>('/auth/me')
}
