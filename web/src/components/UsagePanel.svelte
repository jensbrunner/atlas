<script lang="ts">
  import { onMount } from 'svelte'
  import { getUsage, type CampaignUsage } from '../lib/api'
  import Modal from './Modal.svelte'

  let { campaignId, onClose }: { campaignId: string; onClose: () => void } = $props()

  let usage = $state<CampaignUsage | null>(null)
  let error = $state<string | null>(null)

  const number = new Intl.NumberFormat()

  const turns = $derived(usage ? [...usage.turns].reverse() : [])

  onMount(async () => {
    try {
      usage = await getUsage(campaignId)
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    }
  })

  function fmt(value: number): string {
    return number.format(value)
  }

  function money(value: number): string {
    return value > 0 ? `$${value.toFixed(4)}` : '—'
  }

  function rate(value: number): string {
    return `$${Number(value.toFixed(4))}/M`
  }

  function kind(kind: string): string {
    if (kind === 'opening') return 'Opening'
    if (kind === 'world') return 'World'
    return 'Turn'
  }
</script>

<Modal title="Token usage" onClose={onClose}>
  {#if error}
    <p class="error">{error}</p>
  {:else if !usage}
    <p class="muted">Reading the campaign ledger…</p>
  {:else}
    <section class="intro">
      <div>
        <h3>{usage.campaign.title}</h3>
        <p class="muted">
          {usage.campaign.world_time} · {usage.totals.turns} recorded turns
          {#if usage.totals.billable_turns !== usage.totals.turns}
            · {usage.totals.billable_turns} billable
          {/if}
          {#if usage.totals.priced_turns !== usage.totals.billable_turns}
            · {usage.totals.priced_turns} priced
          {/if}
        </p>
      </div>
      <span class="badge {usage.tracking.live ? 'live' : 'offline'}">
        {usage.tracking.live ? 'live' : 'offline'}
      </span>
    </section>

    <section class="cards">
      <div class="card total">
        <span class="label">Total tokens</span>
        <strong>{fmt(usage.totals.total_tokens)}</strong>
      </div>
      <div class="card">
        <span class="label">Input</span>
        <strong>{fmt(usage.totals.input_tokens)}</strong>
      </div>
      <div class="card">
        <span class="label">Output</span>
        <strong>{fmt(usage.totals.output_tokens)}</strong>
      </div>
      <div class="card">
        <span class="label">Average / turn</span>
        <strong>{fmt(usage.totals.average_tokens_per_turn)}</strong>
      </div>
      <div class="card">
        <span class="label">Estimated cost</span>
        <strong>{money(usage.totals.estimated_usd)}</strong>
      </div>
    </section>

    <section class="info">
      <div class="row">
        <span class="label">Provider</span>
        <span>{usage.tracking.provider}</span>
      </div>
      <div class="row">
        <span class="label">Narrator model</span>
        <span>{usage.tracking.models.narrator}</span>
      </div>
      <div class="row">
        <span class="label">Campaign / world / audit</span>
        <span>
          {usage.tracking.models.campaign} · {usage.tracking.models.world} ·
          {usage.tracking.models.auditor}
        </span>
      </div>
      <div class="row">
        <span class="label">Pricing</span>
        <span>
          Built-in list prices checked {usage.tracking.pricing_updated}. Unknown
          model IDs fall back to {rate(usage.tracking.input_usd_per_million)} input ·
          {rate(usage.tracking.output_usd_per_million)} output.
        </span>
      </div>
    </section>

    {#if usage.model_prices.length}
      <section class="prices">
        <h4>Models used</h4>
        {#each usage.model_prices as price (price.model)}
          <div class="price">
            <strong>{price.model}</strong>
            <span class="faint"> · {price.provider}</span>
            <span class="muted">
              · {rate(price.input_per_million)} input ·
              {rate(price.output_per_million)} output
            </span>
            {#if !price.known}
              <span class="badge fallback">fallback</span>
            {/if}
            {#if price.note}
              <div class="price-note">{price.note}</div>
            {/if}
          </div>
        {/each}
        <div class="sources">
          Sources:
          {#each Object.entries(usage.tracking.pricing_sources) as [provider, url]}
            <a href={url} target="_blank" rel="noreferrer">{provider}</a>
          {/each}
        </div>
      </section>
    {/if}

    <p class="note">
      Input counts the GM packet and every tool round-trip. Output counts tool calls
      and narration. Costs use the built-in list-price table for known models;
      unknown model IDs use the configured fallback rates.
    </p>

    {#if turns.length}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Turn</th>
              <th>Type</th>
              <th>Model</th>
              <th class="num">Input</th>
              <th class="num">Output</th>
              <th class="num">Total</th>
              <th class="num">Cost</th>
            </tr>
          </thead>
          <tbody>
            {#each turns as turn, index (`${turn.turn}-${turn.kind}-${index}`)}
              <tr>
                <td class="num">{turn.turn}</td>
                <td>{kind(turn.kind)}</td>
                <td class="model">{turn.model || '—'}</td>
                <td class="num">{fmt(turn.input_tokens)}</td>
                <td class="num">{fmt(turn.output_tokens)}</td>
                <td class="num strong">{fmt(turn.total_tokens)}</td>
                <td class="num">{turn.priced ? money(turn.estimated_usd) : '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="muted">No turns have been recorded yet.</p>
    {/if}
  {/if}
</Modal>

<style>
  .intro {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 1.2rem;
  }

  h3 {
    margin: 0 0 0.2rem;
    font-size: 1.25rem;
  }

  .intro p {
    margin: 0;
    font-size: 0.85rem;
  }

  .badge {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border: 1px solid var(--line);
    border-radius: 99px;
    padding: 0.15rem 0.55rem;
    color: var(--muted);
  }

  .badge.live {
    color: var(--good);
    border-color: rgba(127, 176, 131, 0.45);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 0.6rem;
    margin-bottom: 1.2rem;
  }

  .card {
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 0.7rem 0.8rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .card.total {
    border-color: var(--accent-soft);
  }

  .card strong {
    font-family: var(--serif);
    font-size: 1.25rem;
  }

  .card.total strong {
    color: var(--accent);
  }

  .label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  .info {
    display: grid;
    gap: 0.25rem;
    padding: 0.8rem 0;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
    margin-bottom: 0.9rem;
    font-size: 0.86rem;
  }

  .row {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 0.8rem;
  }

  .note {
    font-size: 0.82rem;
    color: var(--muted);
    line-height: 1.55;
    margin: 0 0 1rem;
  }

  .prices {
    margin: 0 0 1rem;
    padding: 0.7rem 0;
    border-top: 1px solid var(--line);
  }

  .prices h4 {
    margin: 0 0 0.5rem;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  .price {
    font-size: 0.82rem;
    padding: 0.2rem 0;
  }

  .price-note {
    color: var(--faint);
    font-size: 0.76rem;
    margin-left: 0.2rem;
  }

  .badge.fallback {
    color: var(--danger);
    border-color: rgba(212, 114, 94, 0.45);
    margin-left: 0.3rem;
    font-size: 0.6rem;
  }

  .sources {
    margin-top: 0.5rem;
    font-size: 0.72rem;
    color: var(--faint);
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  .sources a {
    color: var(--muted);
  }

  .table-wrap {
    overflow: auto;
    border: 1px solid var(--line);
    border-radius: 8px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }

  th {
    position: sticky;
    top: 0;
    background: var(--panel-2);
    text-align: left;
    font-weight: 500;
    color: var(--muted);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.5rem 0.6rem;
    white-space: nowrap;
  }

  td {
    padding: 0.45rem 0.6rem;
    border-top: 1px solid var(--line);
    white-space: nowrap;
  }

  .num {
    text-align: right;
    font-family: var(--mono);
  }

  .strong {
    color: var(--accent);
  }

  .model {
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--muted);
  }

  @media (max-width: 620px) {
    .row {
      grid-template-columns: 1fr;
      gap: 0.1rem;
    }

    .info {
      font-size: 0.8rem;
    }
  }
</style>
