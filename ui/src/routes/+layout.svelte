<script lang="ts">
  import { page } from '$app/stores';
  const links = [
    { href: '/', label: 'Overview' },
    { href: '/pipelines', label: 'Pipelines' },
    { href: '/review', label: 'Review queue' },
    { href: '/models', label: 'Models' },
    { href: '/audit', label: 'Audit' },
    { href: '/events', label: 'Events' },
  ];
  $: current = $page.url.pathname;
</script>

<style>
  :global(:root) {
    --bg: #fafaf7;
    --fg: #1a1a1a;
    --muted: #6b6b6b;
    --accent: #c75c2a;
    --card: #ffffff;
    --border: #e5e5e2;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    --sans: -apple-system, system-ui, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme='light'])) {
      --bg: #15150f;
      --fg: #f0f0ec;
      --muted: #9b9b96;
      --accent: #e07a4a;
      --card: #1f1f18;
      --border: #2a2a22;
      color-scheme: dark;
    }
  }
  :global(:root[data-theme='dark']) {
    --bg: #15150f;
    --fg: #f0f0ec;
    --muted: #9b9b96;
    --accent: #e07a4a;
    --card: #1f1f18;
    --border: #2a2a22;
    color-scheme: dark;
  }
  :global(html, body) {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
  }
  :global(a) { color: var(--accent); text-decoration: none; }
  :global(a:hover) { text-decoration: underline; }
  :global(code) {
    font-family: var(--mono);
    font-size: 13px;
    background: var(--card);
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid var(--border);
  }
  :global(button) {
    font: inherit;
    background: var(--card);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 12px;
    cursor: pointer;
  }
  :global(button:hover) { border-color: var(--accent); }
  :global(button.primary) {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  :global(button.danger) {
    background: #b84040;
    color: white;
    border-color: #b84040;
  }
  :global(table) {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  :global(th, td) {
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  :global(th) { color: var(--muted); font-weight: 500; }

  nav {
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    gap: 20px;
    align-items: center;
    flex-wrap: wrap;
  }
  .brand {
    font-weight: 600;
    font-size: 16px;
    margin-right: 12px;
    color: var(--fg);
  }
  .brand:hover { text-decoration: none; }
  .nav-link {
    color: var(--muted);
    font-size: 13px;
  }
  .nav-link.active { color: var(--fg); font-weight: 500; }
</style>

<nav>
  <a class="brand" href="/">Arikizu</a>
  {#each links as l}
    <a class="nav-link" class:active={current === l.href} href={l.href}>{l.label}</a>
  {/each}
</nav>

<slot />
