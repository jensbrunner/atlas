<script lang="ts">
  import type { InventoryItem } from '../lib/api'

  let { inventory }: { inventory: InventoryItem[] } = $props()
</script>

<section class="panel">
  <h3>Inventory</h3>
  {#if inventory.length === 0}
    <p class="muted">Nothing carried.</p>
  {:else}
    <ul>
      {#each inventory as item (item.id)}
        <li>
          <span class="name">{item.name}</span>
          <span class="qty">×{item.quantity}</span>
          {#if item.tags?.length}
            <span class="tags">{item.tags.join(' · ')}</span>
          {/if}
          {#if item.description}
            <span class="desc muted">{item.description}</span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  h3 {
    margin: 0 0 0.9rem;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  li {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.1rem 0.6rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--line);
  }

  li:last-child {
    border-bottom: none;
  }

  .name {
    font-family: var(--serif);
  }

  .qty {
    font-family: var(--mono);
    color: var(--accent);
  }

  .tags {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--faint);
  }

  .desc {
    grid-column: 1 / -1;
    font-size: 0.82rem;
  }
</style>
