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
            const ok = (!q || f.dataset.texto.includes(q)) && (!estado || f.dataset.clase === estado);
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
    document.addEventListener('click', (e) => {
        const b = e.target.closest('[data-log]');
        if (b) verLog(b.dataset.log, b.dataset.titulo);
    });
    filtrar();
})();
