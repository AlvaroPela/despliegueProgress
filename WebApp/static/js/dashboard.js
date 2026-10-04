/* Inicio: gráfico de actividad y estado del entorno */
(function () {
    graficoBarras(document.getElementById('grafico'), leerDatos('datos-serie'));

    const ul = document.getElementById('listaEntorno');
    const resumen = document.getElementById('resumenEntorno');
    async function cargarEntorno() {
        ul.innerHTML = '<li class="text-muted"><span class="spinner-border spinner-border-sm"></span> Verificando...</li>';
        resumen.innerHTML = '';
        try {
            const data = await api('/api/entorno');
            pintarEntorno(ul, data.checks);
            const n = (nivel) => data.checks.filter((c) => c.nivel === nivel).length;
            resumen.innerHTML = [['ok', 'ok', n('ok')], ['warn', 'warn', n('warn')], ['bad', 'error', n('error')]]
                .filter(([, , k]) => k).map(([tono, , k]) => `<span style="background:var(--${tono}-bg);color:var(--${tono})">${k}</span>`).join('');
        } catch (e) { ul.innerHTML = `<li class="text-danger">${escapeHtml(e.message)}</li>`; }
    }
    document.getElementById('btnRecargarEntorno').addEventListener('click', cargarEntorno);
    cargarEntorno();
})();
