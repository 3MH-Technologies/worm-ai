/**
 * Type definitions mirroring the FastAPI Pydantic models.
 * Keep these in sync with apps/api/app/models/*.py
 */

export type Role = 'user' | 'moderator' | 'developer' | 'admin' | 'superadmin'
export type Status = 'pending' | 'approved' | 'rejected' | 'suspended'
export type Provider = 'internal' | 'custom'
export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'
export type CanvasType = 'document' | 'code' | 'markdown' | 'project' | 'research'
export type MemoryKind = 'long_term' | 'context' | 'session' | 'preference'

export interface PublicUser {
  id: string
  username: string
  email: string
  role: Role
  status: Status
  avatar?: string | null
  createdAt?: string
  lastLogin?: string | null
}

export interface AuthResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  user: PublicUser
}

export interface ModelRecord {
  id: string
  name: string
  provider: Provider
  endpoint?: string | null
  temperature: number
  maxTokens: number
  topP: number
  systemPromptId?: string | null
  systemPromptName?: string | null
  enabled: boolean
  description?: string | null
  displayName?: string | null
  avatar?: string | null
  tags: string[]
  createdAt: string
  updatedAt: string
  hasApiKey: boolean
}

export interface AgentModelRecord {
  id: string
  name: string
  description?: string | null
  provider: string
  enabled: boolean
  configured: boolean
}

export interface ConversationRecord {
  id: string
  userId: string
  title: string
  modelId?: string | null
  mode?: 'chat' | 'agent' | string
  folderId?: string | null
  favorite: boolean
  shared: boolean
  messageCount: number
  lastMessageAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface MessageRecord {
  id: string
  conversationId: string
  role: MessageRole
  content: string
  tokens?: number | null
  model?: string | null
  metadata: Record<string, any>
  reaction?: string | null
  parentId?: string | null
  createdAt: string
  editedAt?: string | null
}

export interface ConversationWithMessages extends ConversationRecord {
  messages: MessageRecord[]
}

export interface SystemPromptSummary {
  id: string
  name: string
  description?: string | null
}

export interface SystemPromptVersion {
  version: number
  content: string
  changelog?: string | null
  createdAt: string
}

export interface SystemPromptRecord {
  id: string
  name: string
  description?: string | null
  tags: string[]
  active: boolean
  currentVersion: number
  versions: SystemPromptVersion[]
  createdAt: string
  updatedAt: string
}

export interface CanvasRecord {
  id: string
  ownerId: string
  title: string
  type: CanvasType
  content: string
  metadata: Record<string, any>
  conversationId?: string | null
  currentVersion: number
  createdAt: string
  updatedAt: string
}

export interface CanvasVersion {
  version: number
  content: string
  commitMessage?: string | null
  authorId: string
  createdAt: string
}

export interface FolderRecord {
  id: string
  userId: string
  name: string
  color?: string | null
  icon?: string | null
  conversationCount: number
}

export interface NotificationRecord {
  id: string
  title: string
  body: string
  read: boolean
  createdAt: string
  kind: 'info' | 'warning' | 'success' | 'error'
}

export interface WebSearchResult {
  title: string
  url: string
  snippet: string
  content?: string | null
  score: number
  favicon?: string | null
  publishedAt?: string | null
}

export interface WebSearchResponse {
  query: string
  results: WebSearchResult[]
  provider: string
  took_ms: number
}

export interface ResearchSource {
  title: string
  url: string
  snippet: string
  content?: string | null
  score: number
  favicon?: string | null
  publishedAt?: string | null
}

export interface ResearchReport {
  id: string
  query: string
  summary: string
  report: string
  sources: ResearchSource[]
  citations: number[]
  modelId?: string | null
  canvasId?: string | null
  createdAt: string
}

export interface MemoryRecord {
  id: string
  userId: string
  kind: MemoryKind
  content: string
  weight: number
  source?: string | null
  createdAt: string
  lastUsedAt?: string | null
}

export interface AuditLogRecord {
  id: string
  actorId: string
  actorUsername?: string | null
  action: string
  resource: string
  ipAddress?: string | null
  userAgent?: string | null
  timestamp: string
}

export interface SearchHit {
  kind: 'conversation' | 'message' | 'user' | 'model' | 'canvas' | 'memory'
  id: string
  title: string
  snippet: string
  score: number
  extra: Record<string, any>
}

export interface SearchResponse {
  query: string
  hits: SearchHit[]
  took_ms: number
}

export interface UserListOut {
  items: PublicUser[]
  total: number
  page: number
  size: number
}

export interface SessionRecord {
  id: string
  kind: 'session' | 'device'
  userAgent?: string | null
  ip?: string | null
  firstSeen?: string | null
  lastSeen?: string | null
  revoked: boolean
  current: boolean
  fingerprint?: string | null
}

export interface AttachmentRecord {
  id: string
  kind: 'image' | 'file'
  mimeType: string
  size: number
  originalName: string
  url: string
  createdAt: string
}

export interface ErrorEvent {
  id: string
  kind: string
  message: string
  path?: string | null
  method?: string | null
  status?: number | null
  actorId?: string | null
  createdAt: string
}

export interface AdminStats {
  totalUsers: number
  pendingUsers: number
  activeUsers24h: number
  totalConversations: number
  totalMessages: number
  totalTokens: number
  tokensToday: number
  messagesToday: number
  activeModels: number
  errorRate: number
  revenue: number
  generatedAt: string
  recentRegistrations: PublicUser[]
  recentAudit: AuditLogRecord[]
  recentErrors: ErrorEvent[]
}
