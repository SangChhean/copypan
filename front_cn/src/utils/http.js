import axios from 'axios'
import { abortOnUnauthorized, getToken, isUnauthorizedExcluded } from './auth.js'

const http = axios.create({
  timeout: 120000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && !isUnauthorizedExcluded(error.config?.url)) {
      // 登录失效：统一处理并让调用方挂起，原因见 abortOnUnauthorized 的注释
      return abortOnUnauthorized()
    }
    return Promise.reject(error)
  },
)

export default http
