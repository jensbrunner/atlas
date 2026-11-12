<script lang="ts">
  let {
    pending,
    onSend,
  }: { pending: boolean; onSend: (action: string) => Promise<void> } = $props()

  let action = $state('')
  let input = $state<HTMLTextAreaElement | null>(null)

  async function submit() {
    const text = action.trim()
    if (!text || pending) return
    action = ''
    await onSend(text)
    input?.focus()
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }
</script>

<div class="composer">
  <textarea
    bind:this={input}
    bind:value={action}
    onkeydown={keydown}
    rows="2"
    placeholder="What do you do?"
    disabled={pending}
    aria-label="Player action"
  ></textarea>
  <button class="primary send" onclick={submit} disabled={pending || !action.trim()}>
    {pending ? '…' : 'Act'}
  </button>
</div>

<style>
  .composer {
    display: flex;
    gap: 0.6rem;
    align-items: flex-end;
    padding: 0.9rem clamp(1rem, 4vw, 3.5rem) 1.2rem;
    border-top: 1px solid var(--line);
    background: linear-gradient(to top, rgba(18, 16, 14, 0.98), rgba(18, 16, 14, 0.8));
  }

  textarea {
    flex: 1;
    min-height: 54px;
    max-height: 180px;
    font-family: var(--serif);
    font-size: 1.02rem;
  }

  .send {
    height: 44px;
    min-width: 76px;
  }
</style>
