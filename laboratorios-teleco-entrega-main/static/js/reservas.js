(() => {
    const root = document.getElementById("availability");
    if (!root || !root.dataset.date || !root.dataset.subject) return;
    const list = document.getElementById("slot-list");
    const status = document.getElementById("availability-status");
    const message = document.getElementById("booking-message");
    const dialog = document.getElementById("booking-dialog");
    const confirm = document.getElementById("booking-confirm");
    const nodes = new Map();
    let selection = null;
    let refreshing = false;
    let submitting = false;
    let slots = new Map();
    let filtersChanged = false;

    document.getElementById("availability-filter").addEventListener("change", () => {
        filtersChanged = document.getElementById("materia").value !== root.dataset.subject ||
            document.getElementById("id_fecha").value !== root.dataset.date;
        dialog.close();
        list.hidden = filtersChanged;
        if (filtersChanged) status.textContent = "Consulta las franjas para la nueva selección.";
        else refresh();
    });

    function showMessage(text, success = false) {
        message.textContent = text;
        message.className = "alert " + (success ? "alert-success" : "alert-danger");
        message.hidden = false;
    }

    function updateSlots(items) {
        slots = new Map(items.map(item => [item.id, item]));
        for (const [id, node] of nodes) {
            if (!slots.has(id)) {
                node.remove();
                nodes.delete(id);
            }
        }
        list.querySelector(".empty-state")?.remove();
        for (const item of items) {
            let node = nodes.get(item.id);
            if (!node) {
                node = document.createElement("article");
                node.className = "slot";
                node.innerHTML = '<h3></h3><p class="slot-count"></p><progress></progress><p class="slot-reason"></p><button type="button" class="btn btn-primary"></button>';
                node.querySelector("button").addEventListener("click", () => {
                    selection = slots.get(item.id);
                    document.getElementById("booking-summary").textContent =
                        document.getElementById("materia").selectedOptions[0].textContent + " · " +
                        root.dataset.date.split("-").reverse().join("/") + " · " +
                        selection.inicio + " - " + selection.fin;
                    dialog.showModal();
                    confirm.disabled = false;
                });
                nodes.set(item.id, node);
                list.append(node);
            }
            node.classList.toggle("full", !item.reservable);
            node.querySelector("h3").textContent = item.inicio + " - " + item.fin;
            node.querySelector(".slot-count").textContent = item.disponibles + " de " + item.capacidad + " cupos disponibles";
            const progress = node.querySelector("progress");
            progress.max = item.capacidad;
            progress.value = item.ocupados;
            progress.setAttribute("aria-label", item.ocupados + " cupos ocupados");
            node.querySelector(".slot-reason").textContent = item.reservada ? (item.estado_solicitud === "CONFIRMADA" ? "Tu préstamo está confirmado." : "Solicitud pendiente de aprobación. Tu cupo está apartado.") :
                item.motivo || (!item.permitida ? "Solo estudiantes con datos completos pueden reservar." : "Disponible para práctica");
            const button = node.querySelector("button");
            button.disabled = !item.reservable || item.reservada || !item.permitida;
            button.textContent = item.reservada ? (item.estado_solicitud === "CONFIRMADA" ? "Confirmada" : "Pendiente") : item.reservable ? "Solicitar préstamo" : "No disponible";
        }
        if (!items.length) {
            const empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "No hay franjas publicadas para esta fecha. Consulta otro día.";
            list.append(empty);
        }
    }

    async function refresh() {
        if (refreshing || document.hidden || filtersChanged) return;
        refreshing = true;
        try {
            const params = new URLSearchParams({fecha: root.dataset.date, materia: root.dataset.subject});
            const response = await fetch(root.dataset.url + "?" + params, {
                cache: "no-store", headers: {Accept: "application/json"}, signal: AbortSignal.timeout(12000),
            });
            if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) throw new Error();
            const data = await response.json();
            if (filtersChanged) return;
            updateSlots(data.franjas);
            status.textContent = "Cupos actualizados · " + data.actualizado;
        } catch {
            status.textContent = "Sin conexión. Reintentando actualización…";
            nodes.forEach(node => { node.querySelector("button").disabled = true; });
        } finally {
            refreshing = false;
        }
    }

    document.getElementById("booking-back").addEventListener("click", () => dialog.close());
    confirm.addEventListener("click", async () => {
        if (!selection || submitting || filtersChanged) return;
        submitting = true;
        confirm.disabled = true;
        confirm.textContent = "Enviando…";
        const body = new FormData(document.getElementById("booking-form"));
        body.set("franja", selection.id);
        body.set("materia", root.dataset.subject);
        body.set("fecha", root.dataset.date);
        try {
            const response = await fetch(root.dataset.confirmUrl, {method: "POST", body, headers: {Accept: "application/json"}});
            const data = await response.json();
            dialog.close();
            if (!response.ok) {
                showMessage(data.error || "No fue posible confirmar la reserva.");
            } else {
                showMessage(data.mensaje, true);
                const link = document.createElement("a");
                link.href = data.url;
                link.textContent = " Ver mis reservas";
                message.append(link);
            }
        } catch {
            dialog.close();
            showMessage("No se recibió la confirmación. Revisa Mis reservas antes de intentar de nuevo.");
        } finally {
            submitting = false;
            confirm.disabled = false;
            confirm.textContent = "Enviar solicitud";
            await refresh();
        }
    });
    refresh();
    setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
