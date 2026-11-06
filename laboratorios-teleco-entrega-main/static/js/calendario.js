(() => {
    const root = document.getElementById("semester-calendar");
    if (!root) return;
    const config = JSON.parse(document.getElementById("calendar-config").textContent);
    const message = document.getElementById("calendar-message");
    const dialog = document.getElementById("calendar-detail");
    const mobile = window.matchMedia("(max-width: 600px)");
    const calendar = new FullCalendar.Calendar(root, {
        initialView: mobile.matches ? "listWeek" : "timeGridWeek",
        initialDate: config.fecha, locale: "es", firstDay: 1, timeZone: "UTC",
        validRange: {start: config.inicio, end: config.fin},
        headerToolbar: {left: "prev,next today", center: "title", right: "timeGridWeek,dayGridMonth,listWeek"},
        buttonText: {today: "Hoy", week: "Semana", month: "Mes", list: "Agenda"},
        buttonHints: {prev: "Anterior", next: "Siguiente", today: "Hoy"},
        allDaySlot: false, slotMinTime: "06:00:00", slotMaxTime: "22:00:00", scrollTime: "09:00:00",
        height: mobile.matches ? "auto" : 760, expandRows: true, nowIndicator: false,
        slotDuration: "00:45:00", slotLabelFormat: {hour: "2-digit", minute: "2-digit", hour12: false},
        eventTimeFormat: {hour: "2-digit", minute: "2-digit", hour12: false},
        noEventsText: "No hay horarios registrados en esta semana.",
        events: config.url,
        loading: busy => { message.textContent = busy ? "Consultando horarios…" : ""; },
        eventSourceFailure: () => { message.textContent = "No se pudieron cargar los horarios. Recarga la página para reintentar."; },
        eventClick: info => {
            info.jsEvent.preventDefault();
            const event = info.event;
            const isSlot = Boolean(event.extendedProps.editar);
            document.getElementById("event-heading").textContent = isSlot ? "Franja de préstamo" : "Clase fija";
            document.getElementById("event-time").textContent = event.extendedProps.horario;
            document.getElementById("event-summary").textContent = event.extendedProps.detalle || event.title;
            document.getElementById("event-reason").textContent = event.extendedProps.motivo || "";
            document.getElementById("event-edit").href = event.extendedProps.editar || event.url;
            const reservations = document.getElementById("event-reservations");
            reservations.href = event.url;
            reservations.hidden = !isSlot;
            dialog.showModal();
        },
    });
    calendar.render();
    mobile.addEventListener("change", event => {
        calendar.changeView(event.matches ? "listWeek" : "timeGridWeek");
        calendar.setOption("height", event.matches ? "auto" : 760);
    });
    setInterval(() => { if (!document.hidden && !dialog.open) calendar.refetchEvents(); }, 60000);
})();
