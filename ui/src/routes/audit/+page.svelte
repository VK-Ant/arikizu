<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AuditRow } from '$lib/api';

  let rows: AuditRow[] = [];
  let error = '';
  let kind = '';
  let limit = 100;

  async function refresh() {
    try {
      rows = await api.audit(limit, kind || undefined);
      error = '';
    } catch (e) {
      error = (e as Error).message;
    }
  }

  onMount(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  });
</script>

<main>
  <h1>Audit log</h1>
  <p class="tag">
    Append-only record of every feedback event, pipeline run, and policy
    denial. SQLite-backed; survives restarts.
  </p>

  <div class="filters">
    kind prefix:
    <input bind:value={kind} placeholder="feedback." on:change={refresh} />
    limit:
    <input type="number" bind:value={limit} on:change={refresh} />
    <button on:click={refresh}>refresh</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if rows.length === 0}
    <section class="card muted">No matching rows.</section>
  {:else}
    <section class="card">
      <table>
        <thead>
          <tr><th>#</th><th>Timestamp</th><th>Kind</th><th>Actor</th><th>Subject</th><th>Payload</th></tr>
        </thead>
        <tbody>
          {#each rows as r}
            <tr>
              <td class="n">{r.id}</td>
              <td class="ts">{new Date(r.ts).toLocaleString()}</td>
              <td><code>{r.kind}</code></td>
              <td class="muted">{r.actor ?? ''}</td>
              <td class="muted"><code>{r.subject ?? ''}</code></td>
              <td class="payload"><code>{JSON.stringify(r.payload)}</code></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</main>

<style>
  main { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  .tag { color: var(--muted); margin: 4px 0 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; margin-top: 16px; overflow-x: auto; }
  .filters { color: var(--muted); margin-bottom: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .filters input {
    font: inherit;
    background: var(--card);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 8px;
  }
  .n { color: var(--muted); font-variant-numeric: tabular-nums; }
  .ts { color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
  .payload { font-size: 11px; max-width: 400px; overflow-x: auto; }
  .muted { color: var(--muted); }
  .error { color: #b84040; }
</style>
