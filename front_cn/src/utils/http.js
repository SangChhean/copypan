import axios from 'axios'
import { getToken } from './auth.js'

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

export default http
