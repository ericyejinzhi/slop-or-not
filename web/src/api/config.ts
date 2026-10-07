import { get } from './client'
import type { AppConfig } from './types'

export function getAppConfig(): Promise<AppConfig> {
  return get<AppConfig>('/config')
}
