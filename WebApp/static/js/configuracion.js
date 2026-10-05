/* Ajustes: guardar configuración, Client Secret y correo de prueba (Microsoft Graph) */
(function () {
    const form = document.getElementById('formAjustes');
    const barra = document.getElementById('saveBar');
    const estado = barra.querySelector('.estado');
    const marcarSucio = (sucio) => {
        barra.classList.toggle('sucio', sucio);
        estado.innerHTML = sucio ? '<i class="bi bi-dot"></i>Tienes cambios sin guardar' : 'Los cambios aplican al siguiente despliegue.';
    };
    form.addEventListener('input', (e) => { if (!e.target.closest('[data-no-guardar]')) marcarSucio(true); });
    window.addEventListener('beforeunload', (e) => { if (barra.classList.contains('sucio')) e.preventDefault(); });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const json = Object.fromEntries([...new FormData(form)].filter(([k]) => k !== 'smtp_secret'));
        json.restringir_usuarios = document.getElementById('restringir_usuarios').checked;
        const btn = document.getElementById('btnGuardar'); btn.disabled = true;
        try { await api('/api/configuracion', { method: 'POST', json }); toast('Configuración guardada'); marcarSucio(false); }
        catch (err) { toast(err.message, 'error'); }
        finally { btn.disabled = false; }
    });

    /* Mantener la pestaña activa en la URL (#correo, #servidores...) */
    document.querySelectorAll('[data-bs-toggle="pill"]').forEach((b) =>
        b.addEventListener('shown.bs.tab', () => history.replaceState(null, '', '#' + b.dataset.bsTarget.slice(4).toLowerCase())));
    const hash = location.hash.slice(1);
    const inicial = hash && document.querySelector(`[data-bs-target="#tab${hash.charAt(0).toUpperCase()}${hash.slice(1)}"]`);
    if (inicial) bootstrap.Tab.getOrCreateInstance(inicial).show();

    document.getElementById('btnSecret').addEventListener('click', async () => {
        try {
            await api('/api/smtp/secret', { method: 'POST', json: { secret: document.getElementById('smtp_secret').value } });
            toast('Secret guardado cifrado'); setTimeout(() => location.reload(), 700);
        } catch (err) { toast(err.message, 'error'); }
    });
    document.getElementById('btnProbar').addEventListener('click', async (ev) => {
        const b = ev.currentTarget, html = b.innerHTML;
        b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Enviando...';
        try { const r = await api('/api/smtp/probar', { method: 'POST', json: {} }); Alerta.fire({ icon: 'success', title: 'Conexión correcta', text: r.message }); }
        catch (err) { Alerta.fire({ icon: 'error', title: 'Falló la prueba', text: err.message }); }
        finally { b.disabled = false; b.innerHTML = html; }
    });
})();

/* ---------- Listas editables (destinatarios y rutinas especiales) ---------- */
(function () {
    const validar = {
        correo: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Correo no válido.',
        rutina: (v) => /\.(p|w)$/i.test(v) || 'Debe ser un programa .p o .w',
    };
    document.querySelectorAll('[data-lista]').forEach((caja) => {
        const oculto = caja.querySelector('textarea');
        const ul = caja.querySelector('[data-items]');
        const nuevo = caja.querySelector('[data-nuevo]');
        let items = oculto.value.split('\n').map((x) => x.trim()).filter(Boolean);

        function pintar() {
            ul.innerHTML = items.length ? items.map((v, i) => `<li class="chip-item"><span>${escapeHtml(v)}</span>
                <button type="button" data-quitar="${i}" aria-label="Quitar ${escapeHtml(v)}"><i class="bi bi-x-lg"></i></button></li>`).join('')
                : `<li class="chip-vacio">${escapeHtml(caja.dataset.vacio)}</li>`;
        }
        function guardar() {
            oculto.value = items.join('\n');
            oculto.dispatchEvent(new Event('input', { bubbles: true }));  // marca "cambios sin guardar"
            pintar();
        }
        function agregar() {
            const valores = nuevo.value.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);
            for (const v of valores) {
                const ok = validar[caja.dataset.tipo]?.(v);
                if (ok !== true) return toast(`${v}: ${ok}`, 'warn');
                if (items.some((x) => x.toLowerCase() === v.toLowerCase())) return toast(`${v} ya está en la lista.`, 'warn');
                items.push(v);
            }
            nuevo.value = '';
            guardar();
        }
        caja.querySelector('[data-agregar]').addEventListener('click', agregar);
        nuevo.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); agregar(); } });
        ul.addEventListener('click', (e) => {
            const b = e.target.closest('[data-quitar]');
            if (b) { items.splice(+b.dataset.quitar, 1); guardar(); }
        });
        pintar();
    });
})();

/* ---------- Servidores: hostname, IP y ping de cada destino ---------- */
(function () {
    const tarjetas = [...document.querySelectorAll('[data-servidores]')];
    const ESTADO = {
        pendiente: ['pend', 'bi-three-dots', 'Verificando...'],
        ok: ['ok', 'bi-check-lg', 'Responde al ping'],
        sinping: ['error', 'bi-x-lg', 'No responde al ping'],
        sindns: ['warn', 'bi-question-lg', 'El nombre no se puede resolver'],
        nuevo: ['pend', 'bi-dash', 'Sin verificar'],
    };

    tarjetas.forEach((card) => {
        const oculto = card.querySelector('textarea');
        const tbody = card.querySelector('[data-filas]');
        const nuevo = card.querySelector('[data-nuevo]');
        const filtro = card.querySelector('[data-filtro]');
        const esDG = card.dataset.servidores === 'servidores_dg';
        let filas = oculto.value.split('\n').map((x) => x.trim()).filter(Boolean).map((entrada) => ({ entrada, estado: 'nuevo' }));

        const estadoDe = (info) => (!info.resuelto ? 'sindns' : info.ping ? 'ok' : 'sinping');

        function pintar() {
            const q = filtro.value.trim().toLowerCase();
            const visibles = filas.map((f, i) => [f, i]).filter(([f]) => !q || [f.entrada, f.hostname, f.ip].join(' ').toLowerCase().includes(q));
            tbody.innerHTML = visibles.map(([f, i]) => {
                const [tono, icono, texto] = ESTADO[f.estado];
                return `<tr>
                    <td><span class="dot ${tono}" title="${texto}"><i class="bi ${icono}"></i></span></td>
                    <td class="mono fw-semibold">${escapeHtml(f.entrada)}</td>
                    <td>${f.hostname ? escapeHtml(f.hostname) : '<span class="text-muted">—</span>'}</td>
                    <td class="mono">${f.ip ? escapeHtml(f.ip) : '<span class="text-muted">—</span>'}</td>
                    <td class="text-end"><button type="button" class="btn btn-sm btn-ghost text-danger" data-quitar="${i}" aria-label="Quitar ${escapeHtml(f.entrada)}"><i class="bi bi-trash"></i></button></td>
                </tr>`;
            }).join('') || `<tr><td colspan="5" class="text-center text-muted py-4">${filas.length ? 'Ningún servidor coincide con el filtro.' : 'No hay servidores registrados.'}</td></tr>`;
            card.querySelector('[data-contador]').textContent = filas.length;
            const verificados = filas.filter((f) => !['nuevo', 'pendiente'].includes(f.estado));
            card.querySelector('[data-resumen]').textContent = verificados.length
                ? `${filas.filter((f) => f.estado === 'ok').length} de ${filas.length} responden` : '';
        }
        function sincronizar() {
            oculto.value = filas.map((f) => f.entrada).join('\n');
            oculto.dispatchEvent(new Event('input', { bubbles: true }));
        }

        async function verificar() {
            if (!filas.length) return;
            const btn = card.querySelector('[data-verificar]');
            btn.disabled = true;
            filas.forEach((f) => { f.estado = 'pendiente'; });
            pintar();
            try {
                const { servidores } = await api('/api/servidores/estado', { method: 'POST', json: { entradas: filas.map((f) => f.entrada) } });
                servidores.forEach((info, i) => Object.assign(filas[i], info, { estado: estadoDe(info) }));
            } catch (e) {
                toast(e.message, 'error');
                filas.forEach((f) => { f.estado = 'nuevo'; });
            }
            btn.disabled = false;
            pintar();
        }

        async function agregar() {
            let entrada = nuevo.value.trim().replace(/\\+$/, '');
            if (!entrada) return;
            if (esDG && !entrada.startsWith('\\\\')) return toast('Para Dirección General escribe la ruta UNC completa, ej: \\\\SRVDG01\\d$\\Escala', 'warn');
            if (filas.some((f) => f.entrada.toLowerCase() === entrada.toLowerCase())) return toast('Ese servidor ya está en la lista.', 'warn');
            const btn = card.querySelector('[data-agregar]');
            btn.disabled = true;
            try {
                const { servidor } = await api('/api/servidores/resolver', { method: 'POST', json: { entrada } });
                const repetido = servidor.ip && filas.find((f) => f.ip === servidor.ip);
                if (repetido) toast(`Atención: ${servidor.ip} ya está registrado como ${repetido.entrada}.`, 'warn');
                filas.push({ ...servidor, estado: estadoDe(servidor) });
                if (!servidor.resuelto) toast(`${entrada} no se pudo resolver por DNS; se agregó igualmente.`, 'warn');
                else toast(`${entrada} agregado (${servidor.hostname || servidor.ip}).`);
                nuevo.value = '';
                sincronizar();
                pintar();
            } catch (e) { toast(e.message, 'error'); }
            btn.disabled = false;
        }

        card.querySelector('[data-agregar]').addEventListener('click', agregar);
        nuevo.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); agregar(); } });
        card.querySelector('[data-verificar]').addEventListener('click', verificar);
        filtro.addEventListener('input', pintar);
        filtro.addEventListener('keydown', (e) => { if (e.key === 'Enter') e.preventDefault(); });
        tbody.addEventListener('click', (e) => {
            const b = e.target.closest('[data-quitar]');
            if (!b) return;
            const [f] = filas.splice(+b.dataset.quitar, 1);
            toast(`${f.entrada} quitado. Guarda los cambios para confirmarlo.`, 'warn');
            sincronizar();
            pintar();
        });
        card.verificar = verificar;
        pintar();
    });

    /* La primera vez que se abre la pestaña se verifican todos los servidores */
    const pestana = document.querySelector('[data-bs-target="#tabServidores"]');
    let verificado = false;
    const alAbrir = () => { if (!verificado) { verificado = true; tarjetas.forEach((c) => c.verificar()); } };
    pestana?.addEventListener('shown.bs.tab', alAbrir);
    if (document.getElementById('tabServidores')?.classList.contains('active')) alAbrir();
})();
