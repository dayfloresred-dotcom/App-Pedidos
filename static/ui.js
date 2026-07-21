/* Micro-UX global: toasts, confirmaciones y estados de carga.
   Requiere bootstrap.bundle (ya cargado en base.html). */
(function () {
  // CSRF: todos los fetch mutantes same-origin llevan el token del <meta>
  // (el server rechaza POST sin token; ver CSRFProtect en app.py).
  const _fetch = window.fetch;
  window.fetch = function (url, opts) {
    opts = opts || {};
    const metodo = (opts.method || 'GET').toUpperCase();
    const esLocal = typeof url === 'string' && (url.startsWith('/') || url.startsWith(location.origin));
    if (esLocal && metodo !== 'GET' && metodo !== 'HEAD') {
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) opts.headers = Object.assign({}, opts.headers, {'X-CSRFToken': meta.content});
    }
    return _fetch.call(this, url, opts);
  };

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

  // Menu de opciones (varios botones). Resuelve con el 'valor' elegido o null.
  window.elegir = function (mensaje, opciones, titulo) {
    return new Promise((resolve) => {
      const viejo = document.getElementById('modal-elegir-app');
      if (viejo) viejo.remove();
      const div = document.createElement('div');
      div.id = 'modal-elegir-app';
      div.innerHTML =
        '<div class="modal fade" tabindex="-1">' +
        '  <div class="modal-dialog modal-dialog-centered">' +
        '    <div class="modal-content">' +
        '      <div class="modal-body">' +
        '        <div class="conf-titulo"></div>' +
        '        <div class="conf-msg"></div>' +
        '      </div>' +
        '      <div class="modal-footer border-0 pt-0 flex-wrap gap-1"></div>' +
        '    </div>' +
        '  </div>' +
        '</div>';
      document.body.appendChild(div);
      const modalEl = div.querySelector('.modal');
      modalEl.querySelector('.conf-titulo').textContent = titulo || 'Elegí una acción';
      modalEl.querySelector('.conf-msg').textContent = mensaje || '';
      const footer = modalEl.querySelector('.modal-footer');
      let elegido = null;
      const volver = document.createElement('button');
      volver.type = 'button'; volver.className = 'btn btn-suave btn-sm';
      volver.textContent = 'Volver'; volver.setAttribute('data-bs-dismiss', 'modal');
      footer.appendChild(volver);
      (opciones || []).forEach((o) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'btn btn-sm ' + (o.clase || 'btn-brand');
        b.textContent = o.label;
        b.addEventListener('click', () => { elegido = o.valor; m.hide(); });
        footer.appendChild(b);
      });
      const m = new bootstrap.Modal(modalEl);
      modalEl.addEventListener('hidden.bs.modal', () => { div.remove(); resolve(elegido); });
      m.show();
    });
  };
})();
