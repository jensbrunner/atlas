<script lang="ts">
  import type { AuditFinding } from '../lib/api'
  import Modal from './Modal.svelte'

  let {
    findings,
    loading,
    error,
    onClose,
  }: {
    findings: AuditFinding[]
    loading: boolean
    error: string | null
    onClose: () => void
  } = $props()
</script>

<Modal title="Continuity audit" onClose={onClose}>
  {#if loading}
    <p class="muted">Reading the canon for contradictions…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if findings.length === 0}
    <p>No contradictions found. The audit is advisory only; it did not change any state.</p>
  {:else}
    <ul>
      {#each findings as finding}
        <li>
          <span class="badge {finding.severity}">{finding.severity}</span>
          <strong>{finding.summary}</strong>
          {#if finding.evidence}
            <p class="evidence">{finding.evidence}</p>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</Modal>

<style>
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    padding: 0.8rem 0;
    border-bottom: 1px solid var(--line);
  }

  .badge {
    display: inline-block;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.05rem 0.45rem;
    border-radius: 99px;
    border: 1px solid var(--line);
    color: var(--muted);
    margin-right: 0.45rem;
  }

  .badge.high {
    color: var(--danger);
    border-color: rgba(212, 114, 94, 0.5);
  }

  .badge.medium {
    color: var(--accent);
  }

  .evidence {
    margin: 0.4rem 0 0;
    font-size: 0.86rem;
    color: var(--muted);
    white-space: pre-wrap;
  }
</style>
