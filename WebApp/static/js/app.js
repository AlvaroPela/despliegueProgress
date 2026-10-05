/* Utilidades comunes de la interfaz (cargado en todas las páginas) */
(function () {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const VERDE = '#4d8a2a';

    /* Diálogos con los colores de la marca */
    window.Alerta = Swal.mixin({ confirmButtonColor: VERDE, cancelButtonColor: '#6b7668', denyButtonColor: '#33601a' });

    /* Datos que el servidor inyecta como <script type="application/json" id="..."> */
    window.leerDatos = (id) => JSON.parse(document.getElementById(id)?.textContent || 'null');

    window.api = async function (url, opts = {}) {
        const init = { method: opts.method || 'GET', headers: { 'X-CSRF-Token': csrf }, credentials: 'same-origin' };
        if (opts.json !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(opts.json);
        } else if (opts.form) {
            init.body = opts.form;
        }
        let resp;
        try { resp = await fetch(url, init); }
        catch (e) { throw new Error('No hay conexión con el servidor.'); }
        if (resp.status === 401) { window.location = '/'; throw new Error('Sesión expirada.'); }
        const tipo = resp.headers.get('content-type') || '';
        const data = tipo.includes('json') ? await resp.json() : await resp.text();
        if (!resp.ok || (data && data.status === 'error')) {
            throw new Error((data && data.message) || `Error ${resp.status}`);
        }
        return data;
    };

    window.toast = function (mensaje, tipo = 'ok') {
        const icono = { ok: 'check-circle-fill', error: 'x-octagon-fill', warn: 'exclamation-triangle-fill' }[tipo] || 'info-circle-fill';
        const el = document.createElement('div');
        el.className = `toast-lite ${tipo}`;
        el.innerHTML = `<i class="bi bi-${icono}"></i><span></span>`;
        el.querySelector('span').textContent = mensaje;
        document.getElementById('toasts').appendChild(el);
        setTimeout(() => el.remove(), 4500);
    };

    window.escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    /* ---- Visor de log técnico (reutilizado por Historial y Nuevo Despliegue) ---- */
    window.verLog = async function (id, titulo) {
        Alerta.fire({ title: 'Cargando log...', didOpen: () => Swal.showLoading(), allowOutsideClick: false });
        let texto;
        try { texto = await api(`/api/log/${id}`); }
        catch (e) { return Alerta.fire({ icon: 'info', title: 'Sin log', text: e.message }); }
        const html = escapeHtml(texto).split('\n').map((l) => {
            const cls = l.includes('[ERROR]') ? 'l-error' : l.includes('[WARN]') ? 'l-warn' : l.includes('[DEBUG]') ? 'l-debug' : '';
            return cls ? `<span class="${cls}">${l}</span>` : l;
        }).join('\n');
        const r = await Alerta.fire({
            title: titulo || `Log del despliegue #${id}`, width: '70rem', showCloseButton: true,
            html: `<pre class="terminal text-start">${html}</pre>`,
            showDenyButton: true, denyButtonText: '<i class="bi bi-download"></i> Descargar',
            confirmButtonText: '<i class="bi bi-clipboard"></i> Copiar',
            didOpen: () => { const t = Swal.getHtmlContainer().querySelector('.terminal'); t.scrollTop = t.scrollHeight; },
        });
        if (r.isConfirmed) { navigator.clipboard?.writeText(texto); toast('Log copiado al portapapeles'); }
        if (r.isDenied) {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([texto], { type: 'text/plain' }));
            a.download = `despliegue_${id}.log`; a.click();
        }
    };

    /* ---- Pantallazos: se reducen en el navegador para que quepan en el correo (Graph admite ~3 MB) ---- */
    const MAX_TOTAL = 2_800_000, MAX_LADO = 1800;
    async function prepararImagen(archivo) {
        if (!archivo.type.startsWith('image/')) throw new Error(`${archivo.name || 'El archivo'} no es una imagen.`);
        if (archivo.type === 'image/png' && archivo.size <= 700_000) return archivo;  // texto nítido: se deja en PNG
        const img = await createImageBitmap(archivo);
        const escala = Math.min(1, MAX_LADO / Math.max(img.width, img.height));
        const canvas = Object.assign(document.createElement('canvas'), { width: Math.round(img.width * escala), height: Math.round(img.height * escala) });
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((ok) => canvas.toBlob(ok, 'image/jpeg', 0.86));
        return new File([blob], 'pantallazo.jpg', { type: 'image/jpeg' });
    }

    /* ---- Confirmación manual de versiones en Escala (Historial y Nuevo despliegue) ---- */
    window.confirmarVersionEscala = async function (id, caso, versiones) {
        const filas = versiones.map((v, i) => `<label class="ver-check">
                <input type="checkbox" class="form-check-input" data-v="${i}">
                <span class="flex-grow-1 text-start fw-semibold">${escapeHtml(v.programa)}</span>
                <span class="badge-status ${v.version === 'No especificada' ? 'fallo' : 'exito'}">v${escapeHtml(v.version)}</span>
            </label>`).join('');
        let imagenes = [];
        let alPegar = null;
        const r = await Alerta.fire({
            title: 'Versiones en Escala', icon: 'question', width: '40rem', showCancelButton: true,
            confirmButtonText: '<i class="bi bi-check2-all"></i> Confirmar', cancelButtonText: 'Más tarde',
            html: `<p class="small text-muted mb-2">Caso <b>${escapeHtml(caso)}</b>. Marca cada programa cuando hayas registrado su versión en Escala.</p>
                   <div class="ver-lista">${filas || '<div class="text-muted small">Sin detalle de programas.</div>'}</div>
                   <div class="text-start fw-semibold small mt-3 mb-1">Pantallazo de la versión actualizada</div>
                   <label class="pegar-zona" tabindex="0">
                       <input type="file" accept="image/png,image/jpeg" multiple hidden data-archivo>
                       <i class="bi bi-clipboard-plus"></i>
                       <span><b>Pega con Ctrl+V</b>, arrastra la imagen o haz clic para elegirla</span>
                   </label>
                   <div class="pegar-miniaturas" data-miniaturas></div>
                   <p class="small text-muted mt-2 mb-0">Se adjunta en el correo de confirmación y queda guardado en el historial.</p>`,
            didOpen: (popup) => {
                const zona = popup.querySelector('.pegar-zona');
                const mini = popup.querySelector('[data-miniaturas]');
                const pintar = () => {
                    mini.innerHTML = imagenes.map((f, i) => `<figure><img src="${URL.createObjectURL(f)}" alt="Pantallazo ${i + 1}">
                        <button type="button" data-quitar-img="${i}" aria-label="Quitar"><i class="bi bi-x-lg"></i></button></figure>`).join('');
                };
                const agregar = async (archivos) => {
                    for (const a of archivos) {
                        if (imagenes.length >= 5) { Swal.showValidationMessage('Máximo 5 pantallazos.'); break; }
                        try { imagenes.push(await prepararImagen(a)); Swal.resetValidationMessage(); }
                        catch (e) { Swal.showValidationMessage(e.message); }
                    }
                    pintar();
                };
                alPegar = (e) => {
                    const archivos = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
                    if (archivos.length) { e.preventDefault(); agregar(archivos); }
                };
                document.addEventListener('paste', alPegar);
                popup.querySelector('[data-archivo]').addEventListener('change', (e) => { agregar([...e.target.files]); e.target.value = ''; });
                zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('drag'); });
                zona.addEventListener('dragleave', () => zona.classList.remove('drag'));
                zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('drag'); agregar([...e.dataTransfer.files]); });
                mini.addEventListener('click', (e) => {
                    const b = e.target.closest('[data-quitar-img]');
                    if (b) { imagenes.splice(+b.dataset.quitarImg, 1); pintar(); }
                });
            },
            willClose: () => document.removeEventListener('paste', alPegar),
            preConfirm: async () => {
                const checks = [...Swal.getHtmlContainer().querySelectorAll('[data-v]')];
                if (checks.some((c) => !c.checked)) { Swal.showValidationMessage('Marca todos los programas para confirmar.'); return false; }
                if (!imagenes.length) { Swal.showValidationMessage('Pega o adjunta el pantallazo de la versión actualizada en Escala.'); return false; }
                if (imagenes.reduce((t, f) => t + f.size, 0) > MAX_TOTAL) { Swal.showValidationMessage('Los pantallazos superan 2,8 MB; quita alguno.'); return false; }
                const fd = new FormData();
                imagenes.forEach((f, i) => fd.append('evidencia', f, `pantallazo_${i + 1}.${f.type === 'image/png' ? 'png' : 'jpg'}`));
                try { return await api(`/api/despliegues/${id}/version-escala`, { method: 'POST', form: fd }); }
                catch (e) { Swal.showValidationMessage(e.message); return false; }
            },
        });
        if (r.isConfirmed) {
            const c = r.value.correo;
            if (c && !c.ok) Alerta.fire({ icon: 'warning', title: 'Correo no enviado', text: c.mensaje });
            else toast('Versiones confirmadas. ' + (c ? c.mensaje : ''));
        }
        return r.isConfirmed ? r.value : null;
    };

    /* ---- Ver los pantallazos guardados de una confirmación ---- */
    window.verEvidencia = function (id, caso, cantidad, detalle) {
        const imgs = Array.from({ length: cantidad }, (_, i) =>
            `<a href="/api/despliegues/${id}/evidencia/${i + 1}" target="_blank" rel="noopener"><img class="evidencia-img" src="/api/despliegues/${id}/evidencia/${i + 1}" alt="Pantallazo ${i + 1}"></a>`).join('');
        Alerta.fire({ title: `Versión confirmada · Caso ${escapeHtml(caso)}`, width: '60rem', showCloseButton: true, confirmButtonText: 'Cerrar',
            html: `<p class="small text-muted">${escapeHtml(detalle)}</p>${imgs || '<p class="text-muted">Sin pantallazos.</p>'}` });
    };

    /* ---- Gráficos (Chart.js) con estilo común ---- */
    window.COLORES = { ok: VERDE, bad: '#e05a5a', paleta: [VERDE, '#e05a5a', '#e0a21a', '#3b82c4', '#8a6bbf', '#8c9a86', '#2e9c9c'] };
    window.estiloGraficos = function () {
        Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
        Chart.defaults.color = '#6b7668';
    };
    window.graficoBarras = function (canvas, serie) {
        estiloGraficos();
        return new Chart(canvas, {
            type: 'bar',
            data: { labels: serie.labels, datasets: [
                { label: 'Exitosos', data: serie.exito, backgroundColor: COLORES.ok, borderRadius: 6, maxBarThickness: 34 },
                { label: 'Con fallos', data: serie.fallo, backgroundColor: COLORES.bad, borderRadius: 6, maxBarThickness: 34 },
            ] },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#eef1ec' } } },
                plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } },
            },
        });
    };

    /* ---- Lista de verificaciones del entorno (Inicio y Nuevo despliegue) ---- */
    window.pintarEntorno = function (ul, checks) {
        const iconos = { ok: 'bi-check-lg', warn: 'bi-exclamation-lg', error: 'bi-x-lg' };
        ul.innerHTML = checks.map((c) => `<li><span class="dot ${c.nivel}"><i class="bi ${iconos[c.nivel]}"></i></span>
            <div><b>${escapeHtml(c.label)}</b><small>${escapeHtml(c.detalle)}</small></div></li>`).join('');
    };

    /* ---- Menú lateral en móvil ---- */
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-nav-toggle]')) document.body.classList.toggle('nav-open');
        else if (e.target.closest('[data-nav-close]')) document.body.classList.remove('nav-open');
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') document.body.classList.remove('nav-open'); });
})();
