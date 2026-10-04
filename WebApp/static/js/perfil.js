/* Perfil: credenciales de base de datos */
(function () {
    document.getElementById('formBD').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.submitter; btn.disabled = true;
        try {
            await api('/api/credenciales/bd', { method: 'POST', json: {
                db_user: document.getElementById('db_user').value, db_pass: document.getElementById('db_pass').value } });
            toast('Credenciales guardadas de forma segura'); setTimeout(() => location.reload(), 700);
        } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
    });
})();
