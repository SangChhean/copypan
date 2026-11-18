import { describe, it, expect } from 'vitest'
import {
  extractApiError,
  formatDailyUsageText,
  dailyUsageLevelClass,
  safeInternalPath,
} from './qa4Api.js'

describe('qa4Api auth helpers', () => {
  it('extractApiError_detail_shapes', () => {
    expect(extractApiError({ detail: '用户名或密码错误' })).toBe('用户名或密码错误')
    expect(extractApiError({ detail: { message: '邀请码无效或已使用' } })).toBe(
      '邀请码无效或已使用',
    )
    expect(extractApiError({ message: '登录失败' })).toBe('登录失败')
    expect(extractApiError({}, 'fallback')).toBe('fallback')
  })

  it('formatDailyUsageText_and_level', () => {
    expect(formatDailyUsageText(1, 30)).toBe('今日 1/30')
    expect(formatDailyUsageText(0, 0)).toBe('')
    expect(dailyUsageLevelClass(30, 30)).toBe('qa-daily-usage--danger')
    expect(dailyUsageLevelClass(24, 30)).toBe('qa-daily-usage--warn')
    expect(dailyUsageLevelClass(3, 30)).toBe('')
  })

  it('safeInternalPath', () => {
    expect(safeInternalPath('/admin')).toBe('/admin')
    expect(safeInternalPath('https://evil')).toBe('/')
    expect(safeInternalPath('//evil')).toBe('/')
  })
})
