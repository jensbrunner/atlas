<script lang="ts">
  import type { CampaignMeta } from '../lib/api'

  let {
    campaigns,
    onSelect,
    onCreate,
    onDelete,
  }: {
    campaigns: CampaignMeta[]
    onSelect: (id: string) => void
    onCreate: () => void
    onDelete: (id: string) => void
  } = $props()

  function time(minutes: number): string {
    const day = Math.floor(minutes / 1440) + 1
    const hour = Math.floor((minutes % 1440) / 60)
    return `Day ${day} · ${String(hour).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
  }
</script>

<section class="home">
  <header>
    <div>
      <div class="eyebrow">Local-first solo roleplay</div>
      <h1>ATLAS</h1>
      <p class="muted">
        An AI narrator runs the world. The harness keeps the books.
      </p>
    </div>
    <button class="primary" onclick={onCreate}>New campaign</button>
  </header>

  {#if campaigns.length === 0}
    <div class="empty">
      <h2>No campaigns yet</h2>
      <p class="muted">
        Start one with a prompt. The narrator invents the place, the people, and the
        pressure, then opens the scene.
      </p>
      <button class="primary" onclick={onCreate}>Start a campaign</button>
    </div>
  {:else}
    <div class="grid">
      {#each campaigns as campaign (campaign.id)}
        <div class="card-wrap">
          <a
            class="card"
            href={`#${campaign.id}`}
            onclick={(event) => {
              event.preventDefault()
              onSelect(campaign.id)
            }}
          >
            <h3>{campaign.title}</h3>
            <p class="premise muted">{campaign.premise || 'No premise recorded.'}</p>
            <div class="meta">
              <span>{time(campaign.world_time_minutes)}</span>
              <span>turn {campaign.turn_count}</span>
              {#if campaign.genre}<span>{campaign.genre}</span>{/if}
            </div>
          </a>
          <button
            class="delete ghost"
            title="Delete campaign"
            aria-label={`Delete ${campaign.title}`}
            onclick={() => onDelete(campaign.id)}
          >
            Delete
          </button>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .home {
    max-width: 980px;
    margin: 0 auto;
    padding: 4rem 2rem;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 2rem;
    margin-bottom: 3rem;
  }

  .eyebrow {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--accent);
  }

  h1 {
    font-size: 3.4rem;
    margin: 0.1rem 0 0.4rem;
    letter-spacing: 0.14em;
  }

  h1 + p {
    margin: 0;
  }

  .empty {
    border: 1px dashed var(--line);
    border-radius: 12px;
    padding: 3rem;
    text-align: center;
  }

  .empty h2 {
    margin-top: 0;
  }

  .empty p {
    max-width: 460px;
    margin: 0 auto 1.5rem;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }

  .card {
    text-align: left;
    padding: 1.2rem;
    background: var(--panel);
    border: 1px solid transparent;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    min-height: 170px;
    color: inherit;
    text-decoration: none;
    cursor: pointer;
    transition: border-color 120ms ease;
    flex: 1;
  }

  .card-wrap {
    position: relative;
    display: flex;
  }

  .delete {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.45rem;
    opacity: 0;
    background: rgba(18, 16, 14, 0.86);
  }

  .card-wrap:hover .delete,
  .delete:focus-visible {
    opacity: 1;
  }

  @media (hover: none) {
    .delete {
      opacity: 1;
    }
  }

  .card:hover {
    border-color: var(--accent-soft);
  }

  .card h3 {
    margin: 0;
    font-size: 1.2rem;
  }

  .premise {
    margin: 0;
    font-size: 0.88rem;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .meta {
    margin-top: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--faint);
  }
</style>
