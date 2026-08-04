(function () {
  const path = (location.pathname || "/").replace(/\/+$/, "") || "/";

  function isActive(href) {
    const clean = href.replace(/\/+$/, "") || "/";
    if (clean === "/") return path === "/" || path === "";
    return path === clean || path.startsWith(clean + "/");
  }

  function mountNav() {
    const host = document.getElementById("site-nav");
    if (!host) return;
    const links = [
      { href: "/", label: "Início" },
      { href: "/calculadora/", label: "Calculadora" },
      { href: "/radar/", label: "Radar" },
      { href: "/agenda/", label: "Agenda" },
      { href: "/metodo/", label: "Método" },
      { href: "/liquidez/", label: "Liquidez" },
      { href: "/mundo/", label: "Mundo" },
    ];
    host.innerHTML = `
      <a class="brand" href="/">Div<em>metric</em></a>
      <div class="links">
        ${links
          .map((l) => `<a href="${l.href}" class="${isActive(l.href) ? "active" : ""}">${l.label}</a>`)
          .join("")}
        <a href="https://velumetric.pages.dev/" rel="noopener">Velumetric</a>
      </div>
    `;
  }

  window.DivmetricSite = {
    mountNav,
    async loadJSON(url) {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`Falha ao carregar ${url}`);
      return res.json();
    },
    projectFutureValue(principal, monthly, months, annualPct) {
      const r = Number(annualPct) / 100 / 12;
      let balance = Number(principal) || 0;
      const m = Math.max(0, Number(months) || 0);
      const contrib = Number(monthly) || 0;
      for (let i = 0; i < m; i += 1) {
        balance = balance * (1 + r) + contrib;
      }
      return balance;
    },
    fmtBRL(v) {
      return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    },
  };

  document.addEventListener("DOMContentLoaded", mountNav);
})();
