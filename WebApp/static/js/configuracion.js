/* Ajustes: guardar configuración, secret SMTP y prueba OAuth */
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
        b.disabled = true; b.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Probando...';
        try { const r = await api('/api/smtp/probar', { method: 'POST', json: {} }); Alerta.fire({ icon: 'success', title: 'Conexión correcta', text: r.message }); }
        catch (err) { Alerta.fire({ icon: 'error', title: 'Falló la prueba', text: err.message }); }
        finally { b.disabled = false; b.innerHTML = html; }
    });
})();
