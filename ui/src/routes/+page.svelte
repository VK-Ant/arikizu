<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Status } from '$lib/api';

  let status: Status | null = null;
  let error = '';
  let loading = true;

  async function refresh() {
    try {
      status = await api.status();
      error = '';
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    refresh();
    const id = setInterval(refresh, 2000);
    return () => clearInterval(id);
  });
</script>

<main>
  <header>
    <h1>Overview</h1>
    <p class="tag">Edge-first, offline-first, responsible-AI runtime</p>
  </header>

  <section class="card">
    <h2>Runtime</h2>
    {#if loading}
      <p class="muted">loading...</p>
    {:else if error}
      <p class="error">could not reach the runtime: {error}</p>
      <p class="muted">Is <code>arikizu run</code> running on 127.0.0.1:7000?</p>
    {:else if status}
      <dl>
        <dt>Pipeline</dt><dd>{status.pipeline}</dd>
        <dt>Version</dt><dd>{status.version}</dd>
        <dt>Uptime</dt><dd>{Math.floor(status.uptime_s)}s</dd>
        <dt>Platform</dt><dd>{status.device.platform}{status.device.is_jetson ? ' (Jetson)' : ''}</dd>
        <dt>CPUs / GPUs</dt><dd>{status.device.cpus} / {status.device.gpus}</dd>
        <dt>Capabilities</dt><dd>{status.capability_count}</dd>
        <dt>Audit rows</dt><dd>{status.audit_rows}</dd>
        <dt>Pending approvals</dt>
        <dd>
          {status.pending_approvals}
          {#if status.pending_approvals > 0}
            <a href="/review" class="action">review</a>
          {/if}
        </dd>
      </dl>
    {/if}
  </section>

  {#if status && status.workers.length > 0}
    <section class="card">
      <h2>Workers</h2>
      <table>
        <thead>
          <tr><th>Name</th><th>State</th><th>Capabilities</th></tr>
        </thead>
        <tbody>
          {#each status.workers as w}
            <tr>
              <td>{w.name}</td>
              <td class="state state-{w.state.toLowerCase()}">{w.state}</td>
              <td class="caps">
                {#each w.capabilities as c}
                  <code>{c}</code>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</main>

<style>
  main { max-width: 920px; margin: 0 auto; padding: 32px 24px 64px; }
  header { margin-bottom: 32px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  h2 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin: 0 0 12px;
    font-weight: 600;
  }
  .tag { color: var(--muted); margin: 4px 0 0 0; }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 16px 20px;
    margin-top: 16px;
  }
  dl { display: grid; grid-template-columns: 160px 1fr; gap: 6px 16px; margin: 0; }
  dt { color: var(--muted); font-size: 13px; }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  .state { font-family: var(--mono); font-size: 12px; }
  .state-ready { color: #2d8a4e; }
  .state-busy  { color: var(--accent); }
  .state-dead, .state-unhealthy  { color: #b84040; }
  .caps code { margin-right: 6px; font-size: 12px; }
  .muted { color: var(--muted); }
  .error { color: #b84040; }
  .action { margin-left: 8px; font-size: 13px; }
</style>
