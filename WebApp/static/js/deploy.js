/* Pantalla "Nuevo despliegue": validación, confirmación de versiones y seguimiento en vivo */
(function () {
    const $ = (id) => document.getElementById(id);
    const form = $('deployForm');
    let regId = null, timer = null, runModal = null;

    const destinoSel = () => form.querySelector('input[name=destino]:checked');
    const destinoTxt = () => destinoSel()?.nextElementSibling.querySelector('b').textContent || '';

    /* ---------- Resumen en vivo ---------- */
    function resumen() {
        $('resCaso').textContent = $('caso').value.trim() || '—';
        $('resPrin').textContent = $('archivos_prin').files.length;
        $('resInc').textContent = $('archivos_inc').files.length;
        $('resDestino').textContent = destinoTxt() || '—';
    }
    form.addEventListener('input', resumen);
    form.addEventListener('change', resumen);

    /* ---------- Zonas de carga ---------- */
    function chips(input) {
        const zona = input.closest('.dropzone');
        $(zona.dataset.target).innerHTML = [...input.files].map((f) => `<span class="file-chip">${escapeHtml(f.name)}</span>`).join('');
        zona.classList.toggle('tiene', input.files.length > 0);
    }
    document.querySelectorAll('.dropzone input[type=file]').forEach((input) => {
        const zona = input.closest('.dropzone');
        input.addEventListener('change', () => chips(input));
        ['dragenter', 'dragover'].forEach((ev) => input.addEventListener(ev, () => zona.classList.add('drag')));
        ['dragleave', 'drop'].forEach((ev) => input.addEventListener(ev, () => zona.classList.remove('drag')));
    });

    /* ---------- Marcha blanca ---------- */
    form.querySelectorAll('input[name=destino]').forEach((r) =>
        r.addEventListener('change', () => $('mbSection').classList.toggle('d-none', destinoSel()?.value !== '4')));
    $('actualizarChk').addEventListener('change', (e) => {
        $('actualizar').value = e.target.checked ? 'S' : 'N';
        $('rutaSection').classList.toggle('d-none', !e.target.checked);
    });

    /* ---------- Estado del entorno ---------- */
    async function validarEntorno() {
        const btn = $('btnSubmit');
        try {
            const data = await api('/api/entorno');
            pintarEntorno($('listaEntorno'), data.checks);
            if (data.listo) {
                btn.disabled = !!document.getElementById('avisoEnCurso');
                $('btnText').textContent = 'Iniciar despliegue';
                btn.firstElementChild.className = 'bi bi-rocket-takeoff me-1';
                const avisos = data.checks.filter((c) => c.nivel === 'warn').length;
                $('entornoAviso').textContent = avisos ? `${avisos} advertencia(s) en el entorno; puedes continuar.` : 'Entorno listo.';
            } else {
                btn.firstElementChild.className = 'bi bi-exclamation-octagon me-1';
                $('btnText').textContent = 'Entorno incompleto';
                $('entornoAviso').innerHTML = '<span class="text-danger">Corrige los puntos marcados en rojo para continuar.</span>';
            }
        } catch (e) {
            $('btnText').textContent = 'No se pudo verificar el entorno';
            $('listaEntorno').innerHTML = `<li class="text-danger">${escapeHtml(e.message)}</li>`;
        }
    }
    validarEntorno();

    /* ---------- Envío ---------- */
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const caso = $('caso').value.trim();
        const prin = $('archivos_prin').files;
        if (!/^[\w\-]{1,40}$/.test(caso)) return toast('Ingresa un número de caso válido (letras, números, guion).', 'warn');
        if (!prin.length) return toast('Debes seleccionar al menos un programa .p o .w', 'warn');
        if (!destinoSel()) return toast('Selecciona el destino del despliegue.', 'warn');
        if (destinoSel().value === '4' && !$('ips').value.trim()) return toast('Indica los servidores (IP o hostname) de la marcha blanca.', 'warn');

        // 1) Versiones detectadas en los programas
        const fd = new FormData();
        [...prin].forEach((f) => fd.append('archivos_prin', f));
        let versiones;
        try { versiones = (await api('/api/check_versions', { method: 'POST', form: fd })).versiones; }
        catch (err) { return toast(err.message, 'error'); }

        const filas = versiones.map((v) => `<tr><td class="text-start fw-semibold">${escapeHtml(v.archivo)}</td>
            <td class="text-end"><span class="badge text-bg-success">v${escapeHtml(v.version)}</span></td></tr>`).join('');
        const r = await Alerta.fire({
            title: 'Confirma el despliegue', icon: 'question', showCancelButton: true,
            confirmButtonText: '<i class="bi bi-rocket-takeoff"></i> Desplegar', cancelButtonText: 'Cancelar', width: '34rem',
            html: `<div class="text-start small mb-2">Caso <b>${escapeHtml(caso)}</b> → <b>${escapeHtml(destinoTxt())}</b></div>
                   <div style="max-height:260px;overflow:auto" class="border rounded-3"><table class="table table-sm mb-0">
                   <thead><tr><th class="text-start">Programa</th><th class="text-end">Versión detectada</th></tr></thead><tbody>${filas}</tbody></table></div>
                   <div class="small text-muted mt-2">Revisa que las versiones correspondan a lo que vas a publicar.</div>`,
        });
        if (!r.isConfirmed) return;

        // 2) Lanzar
        const btn = $('btnSubmit'); btn.disabled = true;
        try {
            const resp = await api('/desplegar', { method: 'POST', form: new FormData(form) });
            regId = resp.id;
            abrirModal(caso);
        } catch (err) {
            toast(err.message, 'error'); btn.disabled = false;
        }
    });

    /* ---------- Seguimiento ---------- */
    function abrirModal(caso) {
        runModal = runModal || new bootstrap.Modal($('runModal'));
        $('runCaso').textContent = `Caso ${caso}`;
        $('runHead').className = 'run-head px-4 py-3 d-flex align-items-center justify-content-between';
        $('runTitulo').innerHTML = '<i class="bi bi-rocket-takeoff me-2"></i>Despliegue en ejecución';
        $('runPie').classList.add('d-none');
        for (let i = 1; i <= 4; i++) $('step' + i).className = 'step';
        runModal.show();
        clearInterval(timer);
        timer = setInterval(consultar, 1000);
    }

    const reloj = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

    async function consultar() {
        let d;
        try { d = await api(`/api/progreso/${regId}`); } catch (e) { return; }
        $('runPaso').textContent = d.step_name;
        $('runDetalle').textContent = d.details || '';
        $('runReloj').textContent = reloj(d.elapsed || 0);
        const terminado = d.status !== 'running';
        $('runBarra').style.width = (terminado && d.status !== 'error' ? 100 : Math.max(5, (d.step - 1) * 25 + 8)) + '%';

        for (let i = 1; i <= 4; i++) {
            const el = $('step' + i);
            if (d.step >= 5 || i < d.step) el.className = 'step done';
            else if (i === d.step) el.className = 'step ' + (d.status === 'error' ? 'error' : 'active');
            else el.className = 'step';
            const num = el.querySelector('.num');
            num.innerHTML = el.classList.contains('active') ? '<i class="bi bi-arrow-repeat"></i>' : el.classList.contains('error') ? '<i class="bi bi-x-lg"></i>' : i;
        }
        if (!terminado) return;

        clearInterval(timer);
        $('runPie').classList.remove('d-none');
        const head = $('runHead');
        if (d.status === 'error') {
            head.classList.add('is-error');
            $('runTitulo').innerHTML = '<i class="bi bi-x-octagon me-2"></i>El despliegue falló';
        } else if (d.status === 'warning') {
            head.classList.add('is-warning');
            $('runTitulo').innerHTML = '<i class="bi bi-exclamation-triangle me-2"></i>Finalizó con advertencias';
        } else {
            $('runTitulo').innerHTML = '<i class="bi bi-check2-circle me-2"></i>Despliegue completado';
        }
        $('btnSubmit').disabled = false;
    }

    $('btnVerLog').addEventListener('click', () => verLog(regId));
})();
