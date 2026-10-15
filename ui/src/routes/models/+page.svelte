<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Capability } from '$lib/api';

  let caps: Capability[] = [];
  let runtime: any = null;
  let error = '';
  let workerCaps: Record<string, Capability[]> = {};
  let busy: Record<string, boolean> = {};

  async function refresh() {
    try {
      caps = await api.capabilities();
      caps.sort((a, b) => a.name.localeCompare(b.name));
      workerCaps = {};
      for (const c of caps) (workerCaps[c.worker] ??= []).push(c);

      const r = await fetch('/api/v1/runtime');
      runtime = r.ok ? await r.json() : null;
      error = '';
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function switchModel(worker: string, modelPath: string) {
    busy[worker] = true;
    try {
      const r = await fetch(`/api/v1/call/${worker}/switch_model`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ payload: { model_path: modelPath } }),
      });
      const body = await r.json();
      if (!body.ok) alert('switch failed: ' + (body.error ?? JSON.stringify(body)));
    } catch (e) {
      alert('switch error: ' + (e as Error).message);
    } finally {
      busy[worker] = false;
      await refresh();
    }
  }

  onMount(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  });
</script>

<main>
  <h1>Models and runtimes</h1>
  <p class="tag">
    Each worker reports what model it loaded, which runtime handled it, and
    what else is on disk. Pick a different file to swap models at runtime
    (no restart).
  </p>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if runtime?.device}
    <section class="card compact">
      <h2>Device</h2>
      <dl>
        <dt>Platform</dt><dd>{runtime.device.platform}{runtime.device.is_jetson ? ' (Jetson)' : ''}</dd>
        <dt>CPUs / GPUs</dt><dd>{runtime.device.cpus} / {runtime.device.gpus}</dd>
        <dt>Memory</dt><dd>{runtime.device.total_memory_mb} MB</dd>
      </dl>
    </section>
  {/if}

  {#if runtime?.workers && Object.keys(runtime.workers).length > 0}
    {#each Object.entries(runtime.workers) as [worker, info]}
      <section class="card">
        <h2>{worker}</h2>
        {#if (info as any).error}
          <p class="error">{(info as any).error}</p>
        {:else}
          <dl>
            <dt>Picked backend</dt>
            <dd>
              {#if (info as any).picked_backend}
                <span class="pill pill-ok">{(info as any).picked_backend}</span>
              {:else}
                <span class="pill pill-off">none</span>
              {/if}
            </dd>
            <dt>Available runtimes</dt>
            <dd>
              {#if ((info as any).available ?? []).length === 0}
                <span class="muted">none installed; see docs/MODEL_OPTIMIZATION.md</span>
              {:else}
                {#each (info as any).available as b}
                  <code class="runtime">{b}</code>
                {/each}
              {/if}
            </dd>
            <dt>Model loaded</dt>
            <dd>
              {#if (info as any).model_path}
                <code>{(info as any).model_path}</code>
              {:else}
                <span class="muted">no model loaded (placeholder handlers)</span>
              {/if}
            </dd>
            <dt>Models dir</dt>
            <dd class="muted"><code>{(info as any).models_dir ?? 'n/a'}</code></dd>
          </dl>

          {#if (info as any).available_models && (info as any).available_models.length > 0}
            <div class="switch-row">
              <label>Switch model:</label>
              <select on:change={(e) => switchModel(worker, (e.target as HTMLSelectElement).value)} disabled={busy[worker]}>
                <option value="">pick a file...</option>
                {#each (info as any).available_models as path}
                  <option value={path}>{path}</option>
                {/each}
              </select>
              {#if busy[worker]}<span class="muted">reloading...</span>{/if}
            </div>
          {/if}
        {/if}
      </section>
    {/each}
  {/if}

  <h2 style="margin-top: 32px">Registered capabilities</h2>
  {#each Object.entries(workerCaps) as [worker, items]}
    <section class="card">
      <h3>{worker}</h3>
      <table>
        <thead>
          <tr><th>Capability</th><th>Timeout</th><th>Priority</th></tr>
        </thead>
        <tbody>
          {#each items as c}
            <tr>
              <td><code>{c.name}</code></td>
              <td>{c.timeout_ms} ms</td>
              <td>{c.priority}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/each}
</main>

<style>
  main { max-width: 920px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0 0 12px; }
  h3 { font-size: 14px; margin: 0 0 10px; font-family: var(--mono); }
  .tag { color: var(--muted); margin: 4px 0 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; margin-top: 16px; }
  .card.compact { padding: 12px 20px; }
  dl { display: grid; grid-template-columns: 160px 1fr; gap: 6px 16px; margin: 0; }
  dt { color: var(--muted); font-size: 13px; }
  dd { margin: 0; font-size: 13px; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-family: var(--mono); border: 1px solid var(--border); }
  .pill-ok { color: #2d8a4e; border-color: #2d8a4e; }
  .pill-off { color: var(--muted); }
  .runtime { margin-right: 6px; font-size: 11px; }
  .muted { color: var(--muted); }
  .error { color: #b84040; }
  .switch-row { margin-top: 14px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; }
  .switch-row select {
    font: inherit; background: var(--bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; min-width: 260px;
  }
</style>
