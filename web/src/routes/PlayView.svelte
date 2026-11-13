<script lang="ts">
  import { onMount } from 'svelte'
  import {
    auditCampaign,
    getPlayer,
    getWorldStatus,
    playTurnStream,
    worldTurn,
    type AuditFinding,
    type PlayerView,
    type TurnStreamEvent,
  } from '../lib/api'
  import ActionComposer from '../components/ActionComposer.svelte'
  import AuditPanel from '../components/AuditPanel.svelte'
  import CanonPanel from '../components/CanonPanel.svelte'
  import CharacterPanel from '../components/CharacterPanel.svelte'
  import ClocksPanel from '../components/ClocksPanel.svelte'
  import GmPanel from '../components/GmPanel.svelte'
  import InventoryPanel from '../components/InventoryPanel.svelte'
  import JournalPanel from '../components/JournalPanel.svelte'
  import NarrationPane from '../components/NarrationPane.svelte'
  import UsagePanel from '../components/UsagePanel.svelte'
  import WorldPanel from '../components/WorldPanel.svelte'

  let { campaignId, onBack }: { campaignId: string; onBack: () => void } = $props()

  type Tab = 'character' | 'inventory' | 'world' | 'clocks' | 'journal'

  let view = $state<PlayerView | null>(null)
  let error = $state<string | null>(null)
  let pending = $state(false)
  let status = $state('')
  let worldPending = $state(false)
  let worldBackground = $state(false)
  let lastTurnSeconds = $state<number | null>(null)
  let worldPollToken = 0
  let tab = $state<Tab>('character')
  let gmOpen = $state(false)
  let canonOpen = $state(false)
  let usageOpen = $state(false)
  let auditOpen = $state(false)
  let auditLoading = $state(false)
  let auditError = $state<string | null>(null)
  let auditFindings = $state<AuditFinding[]>([])

  const tabs: Array<[Tab, string]> = [
    ['character', 'Character'],
    ['inventory', 'Inventory'],
    ['world', 'World'],
    ['clocks', 'Clocks'],
    ['journal', 'Journal'],
  ]

  onMount(async () => {
    try {
      view = await getPlayer(campaignId)
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    }
  })

  function streamLabel(event: TurnStreamEvent): string {
    if (event.type === 'tool') {
      switch (event.name) {
        case 'roll':
          return 'Rolling the dice…'
        case 'patch_inventory':
          return 'Updating what you carry…'
        case 'patch_character':
          return 'Taking stock of the consequences…'
        case 'patch_clock':
        case 'create_clock':
          return 'The pressure shifts…'
        case 'advance_time':
          return 'Letting time pass…'
        case 'update_npc':
        case 'create_npc':
          return 'Someone in the world moves…'
        case 'update_faction':
        case 'reveal_faction':
          return 'A faction makes its move…'
        case 'record_fact':
        case 'reveal_fact':
          return 'Remembering what matters…'
        case 'create_location':
        case 'reveal_location':
        case 'set_scene':
          return 'The scene opens…'
        case 'append_journal':
          return 'Writing the journal…'
        case 'request_world_turn':
          return 'The world stirs…'
        default:
          return 'The world is moving…'
      }
    }
    switch (event.stage) {
      case 'reading':
        return 'Reading the scene…'
      case 'thinking':
        return 'Weighing what happens next…'
      case 'repairing':
        return 'Keeping a secret hidden…'
      case 'saving':
        return 'Settling the turn…'
      case 'world':
        return 'The world moves offscreen…'
      default:
        return 'The world is considering its answer…'
    }
  }

  async function send(action: string) {
    worldPollToken += 1
    worldBackground = false
    pending = true
    status = 'Reading the scene…'
    error = null
    try {
      const result = await playTurnStream(campaignId, action, (event) => {
        status = streamLabel(event)
      })
      view = result.player
      lastTurnSeconds = result.duration_seconds
      if (result.world_turn_queued) {
        void followWorldTurn()
      }
      return true
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
      return false
    } finally {
      pending = false
      status = ''
    }
  }

  /**
   * The world turn is queued after the player turn is committed. Poll until it
   * lands, then refresh the panels without making the reader wait for prose.
   */
  async function followWorldTurn() {
    const token = worldPollToken
    worldBackground = true
    try {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await wait(1_200)
        if (token !== worldPollToken) return
        const current = await getWorldStatus(campaignId)
        if (!current.pending) {
          if (token === worldPollToken) view = await getPlayer(campaignId)
          return
        }
      }
    } catch (exc) {
      if (token === worldPollToken) {
        error = exc instanceof Error ? exc.message : String(exc)
      }
    } finally {
      if (token === worldPollToken) worldBackground = false
    }
  }

  function wait(milliseconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, milliseconds))
  }

  async function advanceWorld() {
    worldPending = true
    error = null
    try {
      const result = await worldTurn(campaignId, 'the player takes stock while time passes')
      view = result.player
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    } finally {
      worldPending = false
    }
  }

  async function runAudit() {
    auditOpen = true
    auditLoading = true
    auditError = null
    auditFindings = []
    try {
      const result = await auditCampaign(campaignId)
      auditFindings = result.findings
    } catch (exc) {
      auditError = exc instanceof Error ? exc.message : String(exc)
    } finally {
      auditLoading = false
    }
  }
</script>

<div class="play">
  <header class="topbar">
    <div class="identity">
      <button class="ghost back" onclick={onBack} aria-label="Back to campaigns">←</button>
      <div>
        <h1>{view?.campaign.title ?? 'Campaign'}</h1>
        <div class="meta muted">
          {#if view}
            {view.campaign.time_of_day} · {view.campaign.world_time} · turn {view.campaign.turn_count}
            {#if view.world.location}· {view.world.location.name}{/if}
            {#if lastTurnSeconds !== null}· {lastTurnSeconds.toFixed(1)}s{/if}
            {#if worldBackground}· the world moves offscreen…{/if}
          {/if}
        </div>
      </div>
    </div>
    <div class="controls">
      <button
        onclick={advanceWorld}
        disabled={worldPending || pending || worldBackground}
        title="Force an offscreen world turn. The world also advances automatically every few turns."
      >
        {worldPending ? 'World is moving…' : 'World now'}
      </button>
      <button onclick={() => (canonOpen = true)} title="View all backing campaign data">
        Canon
      </button>
      <button onclick={() => (usageOpen = true)}>Usage</button>
      <button onclick={runAudit} disabled={pending}>Audit</button>
      <button onclick={() => (gmOpen = true)}>GM view</button>
    </div>
  </header>

  {#if error}
    <div class="banner">
      <span class="error">{error}</span>
      <button class="ghost" onclick={() => (error = null)}>Dismiss</button>
    </div>
  {/if}

  {#if view}
    <div class="layout">
      <main>
        <NarrationPane {view} {pending} {status} />
        <ActionComposer {pending} onSend={send} />
      </main>

      <aside>
        <nav class="tabs">
          {#each tabs as [id, label]}
            <button class:active={tab === id} onclick={() => (tab = id)}>{label}</button>
          {/each}
        </nav>
        <div class="panel-body">
          {#if tab === 'character'}
            <CharacterPanel character={view.character} />
          {:else if tab === 'inventory'}
            <InventoryPanel inventory={view.inventory} />
          {:else if tab === 'world'}
            <WorldPanel world={view.world} npcs={view.npcs} facts={view.facts} />
          {:else if tab === 'clocks'}
            <ClocksPanel clocks={view.world.clocks} />
          {:else}
            <JournalPanel journal={view.journal} />
          {/if}
        </div>
      </aside>
    </div>
  {:else}
    <div class="loading muted">Opening the campaign…</div>
  {/if}
</div>

{#if gmOpen && view}
  <GmPanel campaignId={campaignId} onClose={() => (gmOpen = false)} />
{/if}

{#if canonOpen}
  <CanonPanel campaignId={campaignId} onClose={() => (canonOpen = false)} />
{/if}

{#if usageOpen}
  <UsagePanel campaignId={campaignId} onClose={() => (usageOpen = false)} />
{/if}

{#if auditOpen}
  <AuditPanel
    findings={auditFindings}
    loading={auditLoading}
    error={auditError}
    onClose={() => (auditOpen = false)}
  />
{/if}

<style>
  .play {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.85rem 1.4rem;
    border-bottom: 1px solid var(--line);
    background: rgba(18, 16, 14, 0.9);
    backdrop-filter: blur(8px);
  }

  .identity {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
  }

  .back {
    font-size: 1.1rem;
    padding: 0.3rem 0.6rem;
  }

  h1 {
    margin: 0;
    font-size: 1.15rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .meta {
    font-size: 0.76rem;
    margin-top: 0.1rem;
  }

  .controls {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .controls button {
    font-size: 0.8rem;
    padding: 0.4rem 0.7rem;
  }

  .banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 1.4rem;
    border-bottom: 1px solid rgba(212, 114, 94, 0.35);
    background: rgba(212, 114, 94, 0.08);
    font-size: 0.88rem;
  }

  .layout {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 370px;
  }

  main {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
  }

  aside {
    border-left: 1px solid var(--line);
    background: var(--panel);
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .tabs {
    display: flex;
    overflow-x: auto;
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }

  .tabs button {
    flex: 1;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.7rem 0.3rem;
    white-space: nowrap;
  }

  .tabs button.active {
    color: var(--ink);
    border-bottom-color: var(--accent);
  }

  .panel-body {
    overflow-y: auto;
    padding: 1.2rem 1.1rem;
  }

  .loading {
    display: grid;
    place-items: center;
    height: 100%;
  }

  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: minmax(0, 1fr) auto;
    }

    aside {
      border-left: none;
      border-top: 1px solid var(--line);
      max-height: 42vh;
    }
  }
</style>
