document.querySelectorAll("[data-password-inputs]").forEach(notice => {
    const inputs = notice.dataset.passwordInputs.split(" ").map(id => document.getElementById(id)).filter(Boolean);
    // Sin JavaScript el aviso permanece visible.
    notice.hidden = !inputs.includes(document.activeElement);
    inputs.forEach(input => {
        const describedBy = new Set((input.getAttribute("aria-describedby") || "").split(" ").filter(Boolean));
        describedBy.add(notice.id);
        input.setAttribute("aria-describedby", [...describedBy].join(" "));
        input.addEventListener("focus", () => { notice.hidden = false; });
    });
});

document.querySelectorAll('input[type="password"]').forEach(input => {
    const wrapper = document.createElement("div");
    wrapper.className = "password-field";
    input.before(wrapper);
    wrapper.append(input);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "password-toggle icon-button";
    toggle.setAttribute("aria-controls", input.id);
    toggle.setAttribute("aria-pressed", "false");
    toggle.setAttribute("aria-label", "Mostrar contraseña");
    toggle.title = "Mostrar contraseña";
    toggle.innerHTML = '<i data-lucide="eye" aria-hidden="true"></i>';
    wrapper.append(toggle);
    toggle.addEventListener("click", () => {
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        toggle.setAttribute("aria-pressed", String(visible));
        toggle.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
        toggle.title = visible ? "Ocultar contraseña" : "Mostrar contraseña";
        toggle.innerHTML = visible ? '<i data-lucide="eye-off"></i>' : '<i data-lucide="eye"></i>';
        if (window.lucide) window.lucide.createIcons({attrs: {"aria-hidden": "true"}});
    });
});
if (window.lucide) window.lucide.createIcons({attrs: {"aria-hidden": "true"}});
const menu = document.getElementById("menu-toggle");
if (menu) {
    menu.addEventListener("click", () => {
        const expanded = document.getElementById("sidebar").classList.toggle("open");
        menu.setAttribute("aria-expanded", String(expanded));
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape") {
            document.getElementById("sidebar").classList.remove("open");
            menu.setAttribute("aria-expanded", "false");
        }
    });
}
document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
});
