/* Historial: búsqueda y filtro por estado en el cliente */
(function () {
    const filas = [...document.querySelectorAll('#tabla tbody tr')];
    const vacio = document.getElementById('vacio');
    const texto = document.getElementById('filtroTexto');
    const botones = [...document.querySelectorAll('#filtroEstado button')];
    let estado = '';

    function filtrar() {
        const q = texto.value.trim().toLowerCase();
        let visibles = 0;
        filas.forEach((f) => {
            const coincideEstado = !estado || (estado === 'version' ? f.dataset.version === 'pendiente' : f.dataset.clase === estado);
            const ok = (!q || f.dataset.texto.includes(q)) && coincideEstado;
            f.classList.toggle('d-none', !ok);
            if (ok) visibles++;
        });
        document.getElementById('contador').textContent = `${visibles} de ${filas.length} registros`;
        vacio.classList.toggle('d-none', visibles > 0);
    }
    botones.forEach((b) => b.addEventListener('click', () => {
        botones.forEach((x) => x.classList.toggle('active', x === b));
        estado = b.dataset.estado;
        filtrar();
    }));
    texto.addEventListener('input', filtrar);
    document.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-log]');
        if (b) verLog(b.dataset.log, b.dataset.titulo);
        const ev = e.target.closest('[data-ver-evidencia]');
        if (ev) verEvidencia(ev.dataset.verEvidencia, ev.dataset.caso, +ev.dataset.cantidad, ev.dataset.detalle);
        const v = e.target.closest('[data-confirmar-version]');
        if (v && await confirmarVersionEscala(v.dataset.confirmarVersion, v.dataset.caso, JSON.parse(v.dataset.versiones))) {
            setTimeout(() => location.reload(), 600);
        }
    });
    /* ?filtro=version abre directamente los pendientes (enlace desde Inicio) */
    const inicial = new URLSearchParams(location.search).get('filtro');
    botones.find((b) => inicial && b.dataset.estado === inicial)?.click();
    filtrar();
})();
