/* Informes: gráficos mensual y por estado */
(function () {
    graficoBarras(document.getElementById('gMes'), leerDatos('datos-mensual'));
    const estados = leerDatos('datos-estados');
    new Chart(document.getElementById('gEstado'), {
        type: 'doughnut',
        data: { labels: estados.map((e) => e[0]), datasets: [{ data: estados.map((e) => e[1]), backgroundColor: COLORES.paleta, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '64%',
            plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } } },
    });
})();
