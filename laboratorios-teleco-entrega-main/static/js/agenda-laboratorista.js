(() => {
    const contenido = document.getElementById("agenda-contenido");
    const boton = document.getElementById("actualizar-agenda");
    const estado = document.getElementById("estado-agenda");
    if (!contenido || contenido.dataset.invalid) return;

    // Usa los filtros de la consulta mostrada, no los cambios aun sin consultar.
    const url = new URL(contenido.dataset.url, window.location.origin);
    url.search = window.location.search;
    let enCurso = false;
    let accesoVigente = true;
    let ultimaRespuesta = contenido.innerHTML.trim();
    boton.hidden = false;

    async function actualizar() {
        if (enCurso || !accesoVigente || document.hidden) return;
        enCurso = true;
        boton.disabled = true;
        const controlador = new AbortController();
        const limite = window.setTimeout(() => controlador.abort(), 12000);
        try {
            const respuesta = await fetch(url, {
                signal: controlador.signal,
                credentials: "same-origin",
                cache: "no-store",
                headers: {Accept: "application/json"},
            });
            if (respuesta.redirected || [401, 403].includes(respuesta.status)) {
                accesoVigente = false;
                contenido.replaceChildren();
                estado.textContent = "Tu acceso cambió o la sesión terminó. Vuelve a ingresar al aplicativo.";
                return;
            }
            if (!respuesta.ok) throw new Error("No se pudo consultar la agenda.");
            const datos = await respuesta.json();
            if (typeof datos.html !== "string") throw new Error("Respuesta no válida.");
            if (datos.html.trim() !== ultimaRespuesta) {
                const abiertos = [...contenido.querySelectorAll("details[open]")].map(item => item.id);
                const activo = document.activeElement;
                const enfocado = activo?.tagName === "SUMMARY" ? activo.parentElement.id : null;
                contenido.innerHTML = datos.html;
                abiertos.forEach(id => { const item = document.getElementById(id); if (item) item.open = true; });
                if (enfocado) document.getElementById(enfocado)?.querySelector("summary")?.focus({preventScroll: true});
                ultimaRespuesta = datos.html.trim();
            }
            estado.textContent = `Actualizada a las ${datos.actualizado}`;
            estado.classList.remove("text-danger");
        } catch {
            estado.textContent = "No se pudo actualizar. Los datos mostrados pueden haber cambiado; intenta nuevamente.";
            estado.classList.add("text-danger");
        } finally {
            window.clearTimeout(limite);
            enCurso = false;
            boton.disabled = !accesoVigente;
        }
    }

    boton.addEventListener("click", actualizar);
    window.setInterval(actualizar, 30000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) actualizar(); });
    window.addEventListener("pageshow", actualizar);
})();
