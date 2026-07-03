/* Micro-UX global: toasts, confirmaciones y estados de carga.
   Requiere bootstrap.bundle (ya cargado en base.html). */
(function () {
  function contenedor() {
    let c = document.getElementById('toast-wrap');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-wrap';
      document.body.appendChild(c);
    }
    return c;
  }

  window.toast = function (mensaje, tipo) {
    tipo = tipo || 'info';
    const el = document.createElement('div');
    el.className = 'toast-app toast-' + tipo;
    const ic = tipo === 'exito' ? '✓' : (tipo === 'error' ? '✕' : 'ℹ');
    const icon = document.createElement('span');
    icon.className = 'toast-ic';
    icon.textContent = ic;
    const txt = document.createElement('span');
    txt.textContent = mensaje;
    el.appendChild(icon); el.appendChild(txt);
    contenedor().appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 3500);
  };

  window.confirmar = function (mensaje, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      const viejo = document.getElementById('modal-confirmar-app');
      if (viejo) viejo.remove();
      const div = document.createElement('div');
      div.id = 'modal-confirmar-app';
      div.innerHTML =
        '<div class="modal fade" tabindex="-1">' +
        '  <div class="modal-dialog modal-dialog-centered">' +
        '    <div class="modal-content">' +
        '      <div class="modal-body">' +
        '        <div class="conf-titulo"></div>' +
        '        <div class="conf-msg"></div>' +
        '      </div>' +
        '      <div class="modal-footer border-0 pt-0">' +
        '        <button type="button" class="btn btn-suave btn-sm" data-bs-dismiss="modal">Volver</button>' +
        '        <button type="button" class="btn btn-sm conf-ok"></button>' +
        '      </div>' +
        '    </div>' +
        '  </div>' +
        '</div>';
      document.body.appendChild(div);
      const modalEl = div.querySelector('.modal');
      modalEl.querySelector('.conf-titulo').textContent = opts.titulo || 'Confirmar acción';
      modalEl.querySelector('.conf-msg').textContent = mensaje;
      const ok = modalEl.querySelector('.conf-ok');
      ok.textContent = opts.accion || 'Confirmar';
      ok.classList.add(opts.peligro === false ? 'btn-brand' : 'btn-peligro');
      let confirmado = false;
      const m = new bootstrap.Modal(modalEl);
      ok.addEventListener('click', () => { confirmado = true; m.hide(); });
      modalEl.addEventListener('hidden.bs.modal', () => { div.remove(); resolve(confirmado); });
      m.show();
    });
  };

  window.setLoading = function (btn, estado) {
    if (!btn) return;
    if (estado) {
      btn.dataset.htmlOriginal = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>' +
        btn.textContent.trim();
    } else {
      btn.disabled = false;
      if (btn.dataset.htmlOriginal) btn.innerHTML = btn.dataset.htmlOriginal;
    }
  };
})();
