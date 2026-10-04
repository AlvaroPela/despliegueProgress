/* Utilidades comunes de la interfaz */
(function () {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

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
        Swal.fire({ title: 'Cargando log...', didOpen: () => Swal.showLoading(), allowOutsideClick: false });
        let texto;
        try { texto = await api(`/api/log/${id}`); }
        catch (e) { return Swal.fire({ icon: 'info', title: 'Sin log', text: e.message, confirmButtonColor: '#4d8a2a' }); }
        const html = escapeHtml(texto).split('\n').map((l) => {
            const cls = l.includes('[ERROR]') ? 'l-error' : l.includes('[WARN]') ? 'l-warn' : l.includes('[DEBUG]') ? 'l-debug' : '';
            return cls ? `<span class="${cls}">${l}</span>` : l;
        }).join('\n');
        const r = await Swal.fire({
            title: titulo || `Log del despliegue #${id}`, width: '70rem', showCloseButton: true,
            html: `<pre class="terminal text-start">${html}</pre>`,
            showDenyButton: true, denyButtonText: '<i class="bi bi-download"></i> Descargar',
            confirmButtonText: '<i class="bi bi-clipboard"></i> Copiar', confirmButtonColor: '#4d8a2a',
            didOpen: () => { const t = Swal.getHtmlContainer().querySelector('.terminal'); t.scrollTop = t.scrollHeight; },
        });
        if (r.isConfirmed) { navigator.clipboard?.writeText(texto); toast('Log copiado al portapapeles'); }
        if (r.isDenied) {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([texto], { type: 'text/plain' }));
            a.download = `despliegue_${id}.log`; a.click();
        }
    };

    /* ---- Solicitud de credenciales de BD cuando faltan ---- */
    window.pedirCredencialesBD = async function () {
        const r = await Swal.fire({
            title: 'Credenciales de base de datos', icon: 'warning', allowOutsideClick: false, allowEscapeKey: false,
            html: '<p class="text-muted small">Se guardarán cifradas (DPAPI) en el perfil de Windows del usuario que ejecuta el servicio.</p>' +
                  '<input id="sw-u" class="swal2-input" placeholder="Usuario de BD" autocomplete="off">' +
                  '<input id="sw-p" type="password" class="swal2-input" placeholder="Contraseña de BD" autocomplete="new-password">',
            confirmButtonText: 'Guardar', confirmButtonColor: '#4d8a2a', showCancelButton: true, cancelButtonText: 'Más tarde',
            preConfirm: async () => {
                const u = document.getElementById('sw-u').value.trim(), p = document.getElementById('sw-p').value;
                if (!u || !p) { Swal.showValidationMessage('Ambos campos son obligatorios'); return false; }
                try { await api('/api/credenciales/bd', { method: 'POST', json: { db_user: u, db_pass: p } }); return true; }
                catch (e) { Swal.showValidationMessage(e.message); return false; }
            },
        });
        if (r.isConfirmed) { toast('Credenciales guardadas'); setTimeout(() => location.reload(), 700); }
    };

    document.addEventListener('DOMContentLoaded', () => {
        if (document.body.dataset.dbFaltan === '1') pedirCredencialesBD();
    });
})();
