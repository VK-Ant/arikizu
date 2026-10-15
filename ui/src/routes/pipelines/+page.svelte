<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';

  let config: any = null;
  let error = '';
  let running = false;
  let lastRun: any = null;
  let runError = '';

  onMount(async () => {
    try {
      config = await api.pipelineConfig();
    } catch (e) {
      error = (e as Error).message;
    }
  });

  async function run() {
    running = true;
    runError = '';
    try {
      lastRun = await api.runPipeline();
    } catch (e) {
      runError = (e as Error).message;
    } finally {
      running = false;
    }
  }
</script>

<main>
  <h1>Pipelines</h1>
  <p class="tag">arikizu.yaml, running against the current capability registry.</p>

  {#if error}
    <p class="error">{error}</p>
  {:else if config}
    <section class="card">
      <h2>{config.name}</h2>
      <table>
        <thead>
          <tr><th>#</th><th>Stage</th><th>Capability</th><th>Approve</th></tr>
        </thead>
        <tbody>
          {#each config.pipeline as stage, i}
            <tr>
              <td class="n">{i + 1}</td>
              <td>{stage.name}</td>
              <td><code>{stage.capability}</code></td>
              <td class="muted">{stage.approver_role ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>

      <div class="actions">
        <button class="primary" disabled={running} on:click={run}>
          {running ? 'running...' : 'Run pipeline'}
        </button>
      </div>
    </section>

    {#if lastRun}
      <section class="card">
        <h2>Last run</h2>
        <pre>{JSON.stringify(lastRun, null, 2)}</pre>
      </section>
    {/if}
    {#if runError}
      <p class="error">{runError}</p>
    {/if}
  {/if}
</main>

<style>
  main { max-width: 920px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0 0 12px; }
  .tag { color: var(--muted); margin: 4px 0 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; margin-top: 16px; }
  .actions { margin-top: 16px; }
  .n { color: var(--muted); font-variant-numeric: tabular-nums; width: 24px; }
  .muted { color: var(--muted); }
  .error { color: #b84040; }
  pre {
    font-family: var(--mono);
    font-size: 12px;
    background: var(--bg);
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
  }
</style>
