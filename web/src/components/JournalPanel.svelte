<script lang="ts">
  let { journal }: { journal: string } = $props()
</script>

<section class="panel">
  <h3>Journal</h3>
  {#if journal.trim()}
    <div class="journal">{journal}</div>
  {:else}
    <p class="muted">The journal is still empty.</p>
  {/if}
</section>

<style>
  h3 {
    margin: 0 0 0.9rem;
  }

  .journal {
    font-family: var(--serif);
    font-size: 0.92rem;
    line-height: 1.7;
    white-space: pre-wrap;
    color: #d8cdbd;
  }
</style>
