import { authApi } from '@/services/api'

export const mobileAuth = {
  oauthUrl: () => authApi.wecomOauthUrl('mobile', '/m/'),
  wecomLogin: (code: string) => authApi.wecomLogin(code, 'mobile'),
  passwordLogin: (username: string, password: string) =>
    authApi.login(username, password, 'employee', 'mobile'),
}
