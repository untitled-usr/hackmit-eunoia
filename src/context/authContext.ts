import { createContext } from 'react'
import type { AuthUser } from '../lib/midAuth'

export type AuthContextValue = {
  user: AuthUser | null
  loading: boolean
  loginOpen: boolean
  openLoginModal: () => void
  closeLoginModal: () => void
  login: (identifier: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (p: {
    username: string
    email: string
    password: string
    displayName: string
  }) => Promise<void>
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
