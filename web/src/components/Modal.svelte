<script lang="ts">
  import type { Snippet } from 'svelte'

  let {
    title,
    onClose,
    wide = false,
    children,
  }: {
    title: string
    onClose: () => void
    wide?: boolean
    children: Snippet
  } = $props()
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === 'Escape') onClose()
  }}
/>

<div
  class="overlay"
  role="presentation"
  onclick={(event) => {
    if (event.target === event.currentTarget) onClose()
  }}
>
  <div
    class="modal"
    class:wide
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
  >
    <header>
      <h2>{title}</h2>
      <button class="ghost" onclick={onClose}>Close</button>
    </header>
    <div class="body">
      {@render children()}
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(8, 7, 6, 0.72);
    backdrop-filter: blur(3px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 50;
  }

  .modal {
    width: min(860px, 100%);
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    box-shadow: 0 30px 80px rgba(0, 0, 0, 0.5);
  }

  .modal.wide {
    width: min(1120px, 100%);
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.3rem;
    border-bottom: 1px solid var(--line);
  }

  h2 {
    margin: 0;
    font-size: 1.1rem;
  }

  .body {
    overflow-y: auto;
    padding: 1.3rem;
  }
</style>
