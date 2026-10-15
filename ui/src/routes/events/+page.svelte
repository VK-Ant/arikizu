<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { openEventStream, type AppEvent } from '$lib/api';

  let events: AppEvent[] = [];
  let close: () => void = () => {};
  let paused = false;

  onMount(() => {
    close = openEventStream((e) => {
      if (paused) return;
      events = [e, ...events].slice(0, 200);
    });
  });

  onDestroy(() => close());
</script>

<main>
  <h1>Events</h1>
  <p class="tag">
    Live WebSocket tail of the local event bus. Workers emit here, the
    pipeline executor emits here, the supervisor republishes worker events.
  </p>

  <div class="controls">
    <button on:click={() => (paused = !paused)}>{paused ? 'resume' : 'pause'}</button>
    <button on:click={() => (events = [])}>clear</button>
    <span class="muted">{events.length} / 200</span>
  </div>

  <section class="card">
    {#if events.length === 0}
      <p class="muted">Waiting for events...</p>
    {:else}
      <table>
        <thead>
          <tr><th>Time</th><th>Source</th><th>Subject</th><th>Payload</th></tr>
        </thead>
        <tbody>
          {#each events as e}
            <tr>
              <td class="ts">{new Date(e.timestamp).toLocaleTimeString()}</td>
              <td>{e.source}</td>
              <td><code>{e.subject}</code></td>
              <td class="payload"><code>{JSON.stringify(e.payload)}</code></td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
</main>

<style>
  main { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  .tag { color: var(--muted); margin: 4px 0 24px; }
  .controls { margin-bottom: 12px; display: flex; gap: 8px; align-items: center; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; overflow-x: auto; }
  .ts { font-variant-numeric: tabular-nums; color: var(--muted); white-space: nowrap; }
  .payload { font-size: 11px; max-width: 500px; overflow-x: auto; }
  .muted { color: var(--muted); }
</style>
