<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type PendingAction } from '$lib/api';

  let pending: PendingAction[] = [];
  let approver = 'operator';
  let error = '';
  let busy = '';

  async function refresh() {
    try {
      pending = await api.pending();
      error = '';
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function approve(id: string) {
    busy = id;
    await api.approve(id, approver);
    busy = '';
    await refresh();
  }

  async function reject(id: string) {
    const reason = prompt('reason:');
    if (!reason) return;
    busy = id;
    await api.reject(id, approver, reason);
    busy = '';
    await refresh();
  }

  onMount(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  });
</script>

<main>
  <h1>Review queue</h1>
  <p class="tag">Pipeline stages waiting for a human. Approve releases, reject stops the run.</p>

  <div class="approver">
    approver: <input bind:value={approver} />
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if pending.length === 0}
    <section class="card muted">No pending approvals.</section>
  {:else}
    <section class="card">
      <table>
        <thead>
          <tr>
            <th>Pipeline</th>
            <th>Stage</th>
            <th>Role</th>
            <th>Severity</th>
            <th>Triggered</th>
            <th>Expires</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each pending as p}
            <tr>
              <td>{p.pipeline}</td>
              <td>{p.stage}</td>
              <td>{p.approver_role}</td>
              <td>{p.severity}</td>
              <td class="muted">{new Date(p.triggered_at).toLocaleString()}</td>
              <td class="muted">{new Date(p.expires_at).toLocaleString()}</td>
              <td>
                <button class="primary" disabled={busy === p.action_id} on:click={() => approve(p.action_id)}>Approve</button>
                <button class="danger" disabled={busy === p.action_id} on:click={() => reject(p.action_id)}>Reject</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</main>

<style>
  main { max-width: 1024px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }
  .tag { color: var(--muted); margin: 4px 0 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; margin-top: 16px; }
  .approver { color: var(--muted); margin-bottom: 12px; }
  .approver input {
    font: inherit;
    background: var(--card);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 8px;
    margin-left: 8px;
  }
  .muted { color: var(--muted); }
  .error { color: #b84040; }
</style>
