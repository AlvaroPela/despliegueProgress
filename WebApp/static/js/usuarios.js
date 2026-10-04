/* Usuarios: alta, cambio de rol/estado y eliminación */
(function () {
    const recargar = () => setTimeout(() => location.reload(), 500);

    document.getElementById('formUsuario').addEventListener('submit', async (e) => {
        e.preventDefault();
        const datos = Object.fromEntries(new FormData(e.target));
        try { await api('/api/usuarios', { method: 'POST', json: datos }); toast('Usuario agregado'); recargar(); }
        catch (err) { toast(err.message, 'error'); }
    });

    document.addEventListener('change', async (e) => {
        const el = e.target.closest('[data-accion]'); if (!el) return;
        const cuerpo = el.dataset.accion === 'rol' ? { rol: el.value } : { estado: el.checked ? 'Activo' : 'Inactivo' };
        try {
            await api(`/api/usuarios/${el.dataset.id}`, { method: 'PUT', json: cuerpo });
            toast('Cambios guardados');
            if (el.dataset.accion === 'estado') el.closest('td').querySelector('label').textContent = cuerpo.estado;
        } catch (err) { toast(err.message, 'error'); recargar(); }
    });

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-accion="eliminar"]'); if (!btn) return;
        const r = await Alerta.fire({ title: `¿Eliminar a ${btn.dataset.nombre}?`, text: 'Perderá el acceso al sistema.', icon: 'warning',
            showCancelButton: true, confirmButtonText: 'Sí, eliminar', confirmButtonColor: '#c62828', cancelButtonText: 'Cancelar' });
        if (!r.isConfirmed) return;
        try { await api(`/api/usuarios/${btn.dataset.id}`, { method: 'DELETE' }); toast('Usuario eliminado'); recargar(); }
        catch (err) { toast(err.message, 'error'); }
    });
})();
