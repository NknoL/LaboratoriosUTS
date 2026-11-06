(() => {
    const root = document.getElementById("reservation-history");
    if (!root) return;
    const message = document.getElementById("reservation-updates");
    let loading = false;
    let disconnected = false;
    let signedOut = false;
    async function refresh() {
        if (document.hidden || loading || signedOut) return;
        loading = true;
        try {
            const response = await fetch(root.dataset.url, {cache: "no-store", signal: AbortSignal.timeout(12000)});
            if (response.redirected) {
                signedOut = true;
                message.textContent = "Tu sesión terminó. Recarga la página para iniciar sesión.";
                return;
            }
            if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) throw new Error();
            const data = await response.json();
            if (disconnected) message.textContent = "Conexión restablecida. Estados actualizados.";
            disconnected = false;
            for (const item of data.reservas) {
                const row = root.querySelector('[data-reservation="' + item.id + '"]');
                if (!row) continue;
                const badge = row.querySelector(".status");
                badge.textContent = item.etiqueta;
                badge.className = "status state-" + item.estado;
                row.querySelector(".decision-reason").textContent = item.motivo;
                if (!item.activa) row.querySelector("form")?.remove();
                if (row.dataset.state !== item.estado) message.textContent = "Se actualizó el estado de tus solicitudes.";
                row.dataset.state = item.estado;
            }
        } catch {
            disconnected = true;
            message.textContent = "No se pudo actualizar el estado. Reintentando…";
        } finally { loading = false; }
    }
    setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
