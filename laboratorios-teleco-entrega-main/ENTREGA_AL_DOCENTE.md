# Guia para el profesor 

El repositorio trae el codigo, los archivos para Linux y una copia de la base
con los laboratorios, materias, semestres y horarios. Solo incluye la cuenta
`admin`; no tiene estudiantes ni reservas de prueba.

El aplicativo se ha probado en el computador local. Aun falta instalarlo y
probarlo en el servidor. Esta guia explica lo que queda por hacer.

## 1. Revisar el servidor

Confirmar la version de Linux, Python y MySQL/MariaDB,
el acceso SSH, los permisos para instalar servicios, la carpeta del proyecto,
el dominio, HTTPS y la salida para enviar correo.

Los comandos son para Ubuntu/Debian con `sudo` y Python 3.12 o 3.13.
Los servicios de `deploy/` esperan el codigo en `/srv/laboratorios` y un
usuario llamado `laboratorios`. El encargado debe crear ese usuario y dejar
el codigo en esa ruta, o adaptar los archivos a sus rutas. El servicio necesita
leer el codigo, no modificarlo.

phpMyAdmin administra la base, pero no ejecuta Django. Se incluyen archivos
para Gunicorn y Nginx. Si ya hay Apache, revisar la instalacion sin afectar
las otras paginas del servidor.

## 2. Descargar el proyecto e importar la base

Con una cuenta que tenga acceso al repositorio privado:

```bash
git clone https://github.com/Caicedo1011/laboratorios-teleco-entrega.git
cd laboratorios-teleco-entrega
sudo apt update
sudo apt install python3-venv python3-dev build-essential \
  pkg-config default-libmysqlclient-dev
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt \
  -c deploy/constraints-produccion.txt
venv/bin/python -m pip check
```

Importar `base_datos/laboratorios_inicial.sql` en una base vacia, siguiendo
[estos pasos](base_datos/README.md). Probar la importacion con la version del
servidor antes de continuar.

No conectar Django como `root`. Usar una cuenta para leer y escribir datos
y otra para ejecutar las migraciones, con permisos limitados a esta base.
No abrir el puerto de MySQL a Internet.

## 3. Pasar la configuracion y conservar el correo

El `.env` falta entregar

- `.env`: configuracion real del computador. No reemplazarla por el ejemplo.
- `.env.example`: referencia sin claves para una instalacion local.
- `deploy/laboratorios.env.example`: referencia para Linux.
- `/etc/laboratorios/laboratorios.env`: archivo que leeran los servicios en Linux.

Con el usuario `laboratorios` ya creado, preparar el archivo del servidor:

```bash
sudo install -d -o root -g laboratorios -m 0750 /etc/laboratorios
sudo install -o root -g laboratorios -m 0640 \
  deploy/laboratorios.env.example /etc/laboratorios/laboratorios.env
sudoedit /etc/laboratorios/laboratorios.env
```

No repetir el segundo comando si el archivo ya esta configurado: lo reemplaza.
Completar la conexion `DATABASE_URL`, el dominio en `DJANGO_ALLOWED_HOSTS`
y `UTS_SITIO_URL`, y una `DJANGO_SECRET_KEY` nueva.
Mantener `DJANGO_ENV=production` y `DJANGO_HTTPS=1`.

Los valores `UTS_EMAIL_*` corresponden a la cuenta que envia.
`UTS_NOTIFICAR_CORREOS` es el destinatario. El campo `UTS_EMAIL_FROM` debe
ser el remitente autenticado o un alias autorizado, no el destinatario.
Cambiar cualquier clave que se haya compartido en capturas antes de publicar.

Para generar la clave de Django en una terminal privada:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Guardar el resultado en el archivo del servidor, no en GitHub. Es una clave
distinta de la de `admin`. En `DATABASE_URL`, codificar los caracteres
especiales de la contrasena para una URL. Revisar tambien las variables del
servidor: tienen prioridad sobre el archivo indicado por `UTS_ENV_FILE`.

## 4. Preparar Django y el administrador

Crear `/etc/laboratorios/migraciones.env` como copia de la configuracion,
accesible solo para `root`, y cambiar su conexion por la del usuario de
migraciones. No usar esa cuenta en el servicio web.

Con el proyecto ya instalado en `/srv/laboratorios`, ejecutar desde esa carpeta:

```bash
sudo env UTS_ENV_FILE=/etc/laboratorios/migraciones.env \
  venv/bin/python manage.py migrate --plan
sudo env UTS_ENV_FILE=/etc/laboratorios/migraciones.env \
  venv/bin/python manage.py migrate --noinput
sudo env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py collectstatic --noinput
sudo -u laboratorios env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py changepassword admin
sudo -u laboratorios env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py verificar_publicacion --produccion
```

La copia conserva la clave de `admin` del momento de la exportacion.
`changepassword admin` permite cambiarla: la terminal la pide despues, no
se escribe al lado del comando. La web tambien pedira completar el cambio
obligatorio al ingresar. Compartir la clave inicial solo por un medio privado.
No cargar datos de ejemplo ni usar `migrate --fake` sobre la base importada.

## 5. Iniciar la pagina y los avisos

Revisar primero las rutas y permisos de los archivos de `deploy/`:

```bash
sudo install -m 0644 deploy/laboratorios.service \
  deploy/laboratorios-notificaciones.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now laboratorios laboratorios-notificaciones
sudo systemctl status laboratorios laboratorios-notificaciones --no-pager
```

Completar el dominio, firewall, Nginx y certificado. Los archivos
`nginx-laboratorios-bootstrap.conf`, `nginx-laboratorios.conf` y
`nginx-laboratorios-limits.conf` sirven de base.
No activar HTTPS antes de tener el certificado ni usar `runserver` en produccion.
Gunicorn, MySQL y phpMyAdmin no deben quedar expuestos directamente a Internet.
Si se usa otro proxy, revisar sus cabeceras IP y HTTPS.

Configurar tambien los servicios y temporizadores `laboratorios-respaldo`
y `laboratorios-comprobacion`. El primero necesita una cuenta de respaldo.
El segundo registra fallas, pero no envia alarmas por si solo.
Acordar quien revisara esos registros y cuanto tiempo se guardaran las copias.

## 6. Probar antes de compartir el enlace

1. Entrar con el administrador y una cuenta de estudiante de prueba.
2. Comprobar los permisos y el bloqueo tras cinco intentos fallidos por cuenta e IP.
3. Revisar todos los calendarios y el horario de prestamos de 9:00 a. m. a 6:00 p. m.
4. Probar cupos, bloqueo por clases, solicitud pendiente, aprobacion y rechazo.
5. Confirmar que lleguen los avisos y que la cola continue tras un reinicio.
6. Abrir desde otra red, revisar HTTPS, estilos y que DEBUG este desactivado.
7. Probar un respaldo y restaurarlo en una base aparte.

Para revisar problemas:

```bash
sudo -u laboratorios env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py comprobar_operacion
sudo -u laboratorios env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py diagnosticar_correo --conectar
sudo journalctl -u laboratorios -u laboratorios-notificaciones -n 60 --no-pager
```

`diagnosticar_correo --conectar` no envia mensajes.
`probar_notificaciones` si envia un aviso; comunicarlo al destinatario antes
de hacer la prueba.

## 7. Dejar el proyecto a cargo del profesor

Agregar al profesor al repositorio privado y, cuando corresponda, transferirle
la propiedad desde Settings > General > Danger Zone > Transfer ownership.
Confirmar su usuario antes; el profesor debe aceptar la transferencia.
Despues puede retirar los colaboradores que ya no necesiten acceso.
No compartir contrasenas de GitHub.

El servidor, el correo, el dominio y los respaldos se entregan aparte.
Transferir GitHub no transfiere esas cuentas.

Para futuras actualizaciones: probar los cambios aparte, hacer un respaldo,
aplicarlos durante mantenimiento, ejecutar migraciones y `collectstatic`,
y reiniciar los servicios cuando corresponda.
No volver a importar la base inicial cuando ya haya datos reales.

## 8. Actualizar para habilitar el laboratorista

Si el servidor ya esta funcionando, conservar su base y su archivo de
configuracion. Este cambio no necesita volver a importar el SQL ni cambiar
los datos del correo. La migracion `0010_rol_laboratorista` agrega el rol
al modelo existente, sin borrar usuarios ni reservas.

Hacer primero un respaldo y comprobar que termino correctamente. Ejecutar
desde la cuenta que administra el codigo, durante mantenimiento. Estos
comandos usan las rutas y servicios de esta guia; adaptarlos si se instalaron
con otros nombres:

```bash
cd /srv/laboratorios
git status --short
git pull --ff-only origin main
sudo env UTS_ENV_FILE=/etc/laboratorios/migraciones.env \
  venv/bin/python manage.py migrate --plan
sudo env UTS_ENV_FILE=/etc/laboratorios/migraciones.env \
  venv/bin/python manage.py migrate --noinput
sudo env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py collectstatic --noinput
sudo -u laboratorios env UTS_ENV_FILE=/etc/laboratorios/laboratorios.env \
  venv/bin/python manage.py check
sudo systemctl restart laboratorios laboratorios-notificaciones
sudo systemctl status laboratorios laboratorios-notificaciones --no-pager
```

Si Git muestra modificaciones locales o rechaza el avance, revisarlas antes
de continuar; no forzar la descarga ni borrar la configuracion del servidor.
El cambio no agrega dependencias nuevas.

Entrar como coordinador y crear la cuenta en **Laboratoristas > Crear cuenta**.
Entregar el usuario y la clave temporal por un medio privado. El laboratorista
ingresa por la misma pagina, cambia su clave y llega a **Prestamos aprobados**.

Probar una solicitud pendiente: no debe aparecer en esa agenda. Aprobarla
como coordinador y comprobar que aparece al actualizar o dentro de 30 segundos.
Revisar el nombre, laboratorio, horario, materia y quien la aprobo. Cancelarla
y comprobar que desaparece. Verificar tambien que un estudiante no pueda
entrar a `/laboratorista/` y que el laboratorista no pueda aprobar solicitudes.

Si aun no se ha instalado el servidor, seguir los pasos anteriores de
instalacion: `migrate` incluira automaticamente esta nueva migracion.
