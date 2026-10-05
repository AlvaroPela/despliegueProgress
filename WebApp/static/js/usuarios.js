/* Usuarios: alta, cambio de rol/estado y eliminación */
(function () {
    const recargar = () => setTimeout(() => location.reload(), 500);

    /* ---------- Alta con búsqueda en el Directorio Activo ---------- */
    const $ = (id) => document.getElementById(id);
    const buscar = $('buscarAD'), lista = $('resultadosAD'), estado = $('estadoAD'), guardar = $('btnGuardarUsuario');
    let elegido = null, resultados = [], espera = null, consulta = 0, manual = false;

    function reiniciar() {
        elegido = null; resultados = []; manual = false;
        buscar.value = ''; $('nuevoNombre').value = '';
        lista.classList.add('d-none'); $('fichaAD').classList.add('d-none'); $('manualAD').classList.add('d-none');
        estado.textContent = 'Escribe al menos 2 letras; se consulta el Directorio Activo.';
        estado.className = 'form-hint';
        guardar.disabled = true;
    }
    $('modalUsuario').addEventListener('show.bs.modal', reiniciar);
    $('modalUsuario').addEventListener('shown.bs.modal', () => buscar.focus());

    function elegir(u) {
        elegido = u;
        lista.classList.add('d-none');
        $('fichaInicial').textContent = (u.nombre || u.usuario)[0];
        $('fichaNombre').textContent = u.nombre;
        [['fichaUsuario', u.usuario], ['fichaCorreo', u.correo], ['fichaCargo', u.cargo], ['fichaArea', u.area]]
            .forEach(([id, v]) => { $(id).textContent = v || '—'; });
        $('fichaAD').classList.remove('d-none');
        estado.textContent = u.activo ? 'Usuario encontrado en el Directorio Activo.' : 'Atención: la cuenta está deshabilitada en el Directorio Activo.';
        estado.className = 'form-hint ' + (u.activo ? 'text-success' : 'text-danger');
        guardar.disabled = false;
    }
    $('fichaQuitar').addEventListener('click', () => { const q = buscar.value; reiniciar(); buscar.value = q; buscar.focus(); });

    async function consultarAD() {
        const q = buscar.value.trim();
        if (q.length < 2) { lista.classList.add('d-none'); return; }
        const n = ++consulta;
        estado.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Buscando en el Directorio Activo...';
        estado.className = 'form-hint';
        try {
            const r = await api(`/api/ad/buscar?q=${encodeURIComponent(q)}`);
            if (n !== consulta) return;  // llegó una respuesta más reciente
            resultados = r.resultados;
            lista.innerHTML = resultados.map((u, i) => `<li><button type="button" data-i="${i}" ${u.registrado ? 'disabled' : ''}>
                <span class="avatar">${escapeHtml((u.nombre || u.usuario)[0])}</span>
                <span class="flex-grow-1"><b>${escapeHtml(u.nombre)}</b>
                    <span class="meta d-block">${escapeHtml(u.usuario)}${u.correo ? ' · ' + escapeHtml(u.correo) : ''}${u.cargo ? ' · ' + escapeHtml(u.cargo) : ''}</span></span>
                ${u.registrado ? '<span class="badge-role">Ya registrado</span>' : !u.activo ? '<span class="badge-status fallo">Deshabilitado</span>' : ''}
            </button></li>`).join('');
            lista.classList.toggle('d-none', !resultados.length);
            estado.textContent = resultados.length ? `${resultados.length} resultado(s). Selecciona el usuario.` : 'No se encontraron usuarios con ese criterio.';
        } catch (e) {
            if (n !== consulta) return;
            lista.classList.add('d-none');
            estado.textContent = e.message;
            estado.className = 'form-hint text-danger';
            manual = true;
            $('manualAD').classList.remove('d-none');
            guardar.disabled = false;
        }
    }
    buscar.addEventListener('input', () => {
        if (elegido) { elegido = null; $('fichaAD').classList.add('d-none'); guardar.disabled = !manual; }
        clearTimeout(espera); espera = setTimeout(consultarAD, 350);
    });
    buscar.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); clearTimeout(espera); consultarAD(); } });
    $('btnBuscarAD').addEventListener('click', consultarAD);
    lista.addEventListener('click', (e) => { const b = e.target.closest('[data-i]'); if (b) elegir(resultados[+b.dataset.i]); });

    $('formUsuario').addEventListener('submit', async (e) => {
        e.preventDefault();
        const rol = $('nuevoRol').value;
        const datos = elegido
            ? { usuario: elegido.usuario, nombre: elegido.nombre, correo: elegido.correo, cargo: elegido.cargo, area: elegido.area, rol }
            : { usuario: buscar.value.trim(), nombre: $('nuevoNombre').value.trim(), rol };
        if (!datos.usuario) return toast('Escribe el usuario de red.', 'warn');
        try { await api('/api/usuarios', { method: 'POST', json: datos }); toast(`${datos.nombre || datos.usuario} agregado`); recargar(); }
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
