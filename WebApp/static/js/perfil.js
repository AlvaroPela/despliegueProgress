/* Perfil: credenciales de cada base de datos (datos y seguimiento) */
(function () {
    document.querySelectorAll('.form-bd').forEach((form) => form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.submitter; btn.disabled = true;
        const datos = Object.fromEntries(new FormData(form));
        try {
            await api('/api/credenciales/bd', { method: 'POST', json: { base: form.dataset.base, ...datos } });
            toast('Credenciales guardadas de forma segura'); setTimeout(() => location.reload(), 700);
        } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
    }));
})();
