export interface CampaignMeta {
  id: string
  title: string
  genre: string
  tone: string
  premise: string
  created_at: string
  rules_profile: string
  narrator_model: string
  turn_count: number
  world_time_minutes: number
  content_boundaries: string[]
  creative_brief: string
}

export interface Attributes {
  might: number
  agility: number
  insight: number
  presence: number
}

export interface Track {
  current: number
  max: number
}

export interface Character {
  id: string
  name: string
  concept: string
  description: string
  attributes: Attributes
  skills: Record<string, number>
  health: Track
  stress: Track
  supplies: number
  currency: number
  conditions: string[]
}

export interface InventoryItem {
  id: string
  name: string
  quantity: number
  tags: string[]
  description: string
}

export interface Location {
  id: string
  name: string
  description: string
  player_known: boolean
  tags: string[]
}

export interface Faction {
  id: string
  name: string
}

export interface GmFaction extends Faction {
  stance: string
  goal: string
  resources: Record<string, number>
  player_known: boolean
}

export interface Clock {
  id: string
  name: string
  segments: number
  filled: number
  trigger: string
  visibility: string
}

export interface Fact {
  id: string
  text: string
  tags: string[]
}

export interface NPC {
  id: string
  name: string
  location: string
  description: string
}

export interface Roll {
  label: string
  attribute: string
  skill: string
  attribute_value: number
  skill_value: number
  bonus: number
  dice: number[]
  modifier: number
  difficulty: number
  total: number
  outcome: string
}

export interface TurnView {
  turn: number
  kind: string
  action: string
  narration: string
  world_time: number
  rolls: Roll[]
}

export interface WorldView {
  situation: string
  current_location: string
  location: Location | null
  locations: Location[]
  factions: Faction[]
  clocks: Clock[]
}

export interface PlayerView {
  campaign: CampaignMeta & { world_time: string; time_of_day: string }
  character: Character
  inventory: InventoryItem[]
  world: WorldView
  npcs: NPC[]
  facts: Fact[]
  journal: string
  turns: TurnView[]
  narration: string
}

export interface TurnResult {
  turn: number
  narration: string
  rolls: Roll[]
  changes: string[]
  usage: { input_tokens: number; output_tokens: number; estimated_usd: number }
  world_turn_requested: boolean
  world_turn_ran: boolean
  player: PlayerView
}

export interface UsageTotals {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_usd: number
  turns: number
  billable_turns: number
  priced_turns: number
  average_tokens_per_turn: number
}

export interface UsageTurn {
  turn: number
  kind: string
  action: string
  model: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_usd: number
  priced: boolean
  pricing_source: string
  world_time: number
}

export interface ModelPrice {
  model: string
  input_per_million: number
  output_per_million: number
  provider: string
  source: string
  note: string
  known: boolean
}

export interface UsageTracking {
  provider: string
  live: boolean
  models: {
    campaign: string
    narrator: string
    world: string
    auditor: string
  }
  input_usd_per_million: number
  output_usd_per_million: number
  session_usd_limit: number
  pricing_updated: string
  pricing_sources: Record<string, string>
}

export interface CampaignUsage {
  campaign: {
    id: string
    title: string
    turn_count: number
    world_time: string
  }
  totals: UsageTotals
  models: string[]
  model_prices: ModelPrice[]
  turns: UsageTurn[]
  tracking: UsageTracking
}

export interface AuditFinding {
  severity: string
  summary: string
  evidence: string
}

export interface CreateCampaignBody {
  title?: string
  prompt?: string
  genre?: string
  tone?: string
  character?: string
}

export interface GmView {
  gm: {
    campaign_notes: string
    character_notes: string
    world_notes: string
    world_gm_blocks: string
    facts: Array<Fact & { visibility: string; revealed_at_turn: number | null }>
    clocks: Clock[]
    npcs: Array<{
      id: string
      sheet: Record<string, unknown>
      notes: string
      gm_blocks: string
    }>
    locations: Location[]
    factions: GmFaction[]
    turns: TurnView[]
    journal_raw: string
  }
}

export interface CanonFact extends Fact {
  visibility: string
  revealed_at_turn: number | null
}

export interface CanonTurn {
  turn: number
  kind: string
  action: string
  narration: string
  world_time_before: number
  world_time_after: number
  model: string
  usage: { input_tokens: number; output_tokens: number; estimated_usd: number }
  rolls: Roll[]
  changes: string[]
  narrative_lens: string
}

export interface CanonNPC {
  id: string
  sheet: Record<string, unknown>
  notes: string
  gm_blocks: string
}

export interface CanonView {
  campaign: CampaignMeta & { world_time: string; time_of_day: string }
  counts: {
    npcs: number
    locations: number
    factions: number
    clocks: number
    facts: number
    turns: number
  }
  notes: {
    campaign: string
    character: string
    world: string
  }
  character: Character
  inventory: InventoryItem[]
  world: {
    situation: string
    current_location: string
    locations: Location[]
    factions: GmFaction[]
    clocks: Clock[]
    facts: CanonFact[]
  }
  npcs: CanonNPC[]
  journal: string
  turns: CanonTurn[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      // keep the status message
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function listCampaigns(): Promise<{ campaigns: CampaignMeta[] }> {
  return request('/campaigns')
}

export function createCampaign(body: CreateCampaignBody): Promise<{
  campaign: CampaignMeta
  player: PlayerView
}> {
  return request('/campaigns', { method: 'POST', body: JSON.stringify(body) })
}

export function getPlayer(campaignId: string): Promise<PlayerView> {
  return request(`/campaigns/${campaignId}/player`)
}

export function getGm(campaignId: string): Promise<GmView> {
  return request(`/campaigns/${campaignId}/gm`)
}

export function getCanon(campaignId: string): Promise<CanonView> {
  return request(`/campaigns/${campaignId}/canon`)
}

export interface TurnStreamEvent {
  type: 'status' | 'tool' | 'done' | 'error'
  stage?: 'reading' | 'thinking' | 'repairing' | 'saving' | 'world'
  name?: string
  result?: TurnResult
  message?: string
  code?: string
}

export async function playTurnStream(
  campaignId: string,
  action: string,
  onEvent: (event: TurnStreamEvent) => void,
): Promise<TurnResult> {
  const response = await fetch(`/api/campaigns/${campaignId}/turns/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ action }),
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      // keep the status message
    }
    throw new Error(message)
  }
  if (!response.body) throw new Error('This browser cannot stream the turn')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: TurnResult | null = null

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const payload = chunk
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('\n')
        if (payload) {
          const event = JSON.parse(payload) as TurnStreamEvent
          onEvent(event)
          if (event.type === 'error') {
            throw new Error(event.message || 'The turn failed')
          }
          if (event.type === 'done' && event.result) {
            result = event.result
          }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }

  if (!result) throw new Error('The turn stream ended without a result')
  return result
}

export function worldTurn(campaignId: string, reason: string): Promise<{ player: PlayerView }> {
  return request(`/campaigns/${campaignId}/world-turn`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function auditCampaign(campaignId: string): Promise<{ findings: AuditFinding[] }> {
  return request(`/campaigns/${campaignId}/audit`, { method: 'POST' })
}

export function getUsage(campaignId: string): Promise<CampaignUsage> {
  return request(`/campaigns/${campaignId}/usage`)
}

export function deleteCampaign(campaignId: string): Promise<{ deleted: string }> {
  return request(`/campaigns/${campaignId}`, { method: 'DELETE' })
}
