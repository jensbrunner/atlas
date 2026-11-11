<script lang="ts">
  import { onMount } from 'svelte'
  import {
    createCampaign,
    listCampaigns,
    type CampaignMeta,
    type CreateCampaignBody,
  } from './lib/api'
  import CampaignCreate from './routes/CampaignCreate.svelte'
  import PlayView from './routes/PlayView.svelte'
  import CampaignList from './components/CampaignList.svelte'

  let campaigns = $state<CampaignMeta[]>([])
  let activeId = $state<string | null>(null)
  let creating = $state(false)
  let loading = $state(true)
  let createPending = $state(false)
  let error = $state<string | null>(null)

  async function refresh() {
    try {
      const result = await listCampaigns()
      campaigns = result.campaigns
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    } finally {
      loading = false
    }
  }

  async function create(body: CreateCampaignBody) {
    createPending = true
    error = null
    try {
      const result = await createCampaign(body)
      campaigns = [result.campaign, ...campaigns]
      activeId = result.campaign.id
      creating = false
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    } finally {
      createPending = false
    }
  }

  function back() {
    activeId = null
    void refresh()
  }

  onMount(() => {
    void refresh()
  })
</script>

{#if activeId}
  <PlayView campaignId={activeId} onBack={back} />
{:else if creating}
  <CampaignCreate
    pending={createPending}
    error={error}
    onCreate={create}
    onCancel={() => {
      creating = false
      error = null
    }}
  />
{:else if loading}
  <div class="loading muted">Loading campaigns…</div>
{:else}
  {@render list()}
{/if}

{#snippet list()}
  <CampaignList
    {campaigns}
    onSelect={(id) => (activeId = id)}
    onCreate={() => {
      error = null
      creating = true
    }}
  />
  {#if error}
    <p class="error global">{error}</p>
  {/if}
{/snippet}

<style>
  .loading {
    display: grid;
    place-items: center;
    height: 100%;
  }

  .global {
    text-align: center;
    padding: 1rem;
  }
</style>
