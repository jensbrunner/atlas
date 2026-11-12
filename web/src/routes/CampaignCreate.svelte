<script lang="ts">
  import type { CreateCampaignBody } from '../lib/api'

  let {
    pending,
    error,
    onCreate,
    onCancel,
  }: {
    pending: boolean
    error: string | null
    onCreate: (body: CreateCampaignBody) => Promise<void>
    onCancel: () => void
  } = $props()

  let prompt = $state('')
  let title = $state('')
  let genre = $state('')
  let tone = $state('')
  let character = $state('')

  async function submit(event: SubmitEvent) {
    event.preventDefault()
    if (pending || !prompt.trim()) return
    await onCreate({
      prompt: prompt.trim(),
      title: title.trim(),
      genre: genre.trim(),
      tone: tone.trim(),
      character: character.trim(),
    })
  }
</script>

<section class="create">
  <button class="ghost back" onclick={onCancel}>← Back</button>
  <h1>Start a campaign</h1>
  <p class="muted">
    Describe the situation you want to be dropped into. The narrator will build the
    place, the people, their secrets, and the pressure already in motion.
  </p>

  <form onsubmit={submit}>
    <label>
      <span>Premise</span>
      <textarea
        bind:value={prompt}
        rows="4"
        placeholder="Describe the situation you want to play"
        disabled={pending}
      ></textarea>
    </label>

    <label>
      <span>Character concept (optional)</span>
      <input
        bind:value={character}
        placeholder="Optional"
        disabled={pending}
      />
    </label>

    <div class="row">
      <label>
        <span>Title (optional)</span>
        <input bind:value={title} placeholder="Let the narrator decide" disabled={pending} />
      </label>
      <label>
        <span>Genre (optional)</span>
        <input bind:value={genre} placeholder="Optional" disabled={pending} />
      </label>
      <label>
        <span>Tone (optional)</span>
        <input bind:value={tone} placeholder="Optional" disabled={pending} />
      </label>
    </div>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    <div class="actions">
      <button class="primary" type="submit" disabled={pending || !prompt.trim()}>
        {pending ? 'The narrator is building the world…' : 'Create campaign'}
      </button>
      {#if pending}
        <span class="muted">This can take a little while on a live model.</span>
      {/if}
    </div>
  </form>
</section>

<style>
  .create {
    max-width: 760px;
    margin: 0 auto;
    padding: 3rem 2rem 5rem;
  }

  .back {
    margin-bottom: 1.5rem;
    padding-left: 0;
  }

  h1 {
    margin: 0 0 0.4rem;
    font-size: 2.4rem;
  }

  h1 + p {
    margin: 0 0 2rem;
    max-width: 620px;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  label > span {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--muted);
  }

  .row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.8rem;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 0.5rem;
  }

  @media (max-width: 700px) {
    .row {
      grid-template-columns: 1fr;
    }
  }
</style>
