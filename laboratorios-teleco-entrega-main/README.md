# Reservas de laboratorios - Telecomunicaciones UTS

Proyecto para que los estudiantes soliciten un laboratorio y el coordinador
pueda aprobar o rechazar cada solicitud. Funciona de forma independiente;
no esta conectado con los sistemas de la UTS.

Esta hecho con Python, Django 5.2, MySQL/MariaDB y Bootstrap.

## Que se puede hacer

- Registrar estudiantes con correo institucional, cedula, programa y semestre.
- Consultar laboratorios, materias, horarios y cupos.
- Solicitar prestamos entre las 9:00 a. m. y las 6:00 p. m.
- Aprobar o rechazar solicitudes desde la cuenta del coordinador.
- Consultar los prestamos aprobados desde la cuenta del laboratorista.
- Crear laboratorios, materias y semestres, y ajustar las clases fijas.
- Generar franjas disponibles sin cruzarlas con las clases.
- Consultar el calendario, los reportes y recibir avisos de nuevas solicitudes.

La recuperacion de contrasena por correo esta desactivada. El coordinador puede
generar una clave temporal que el estudiante debe cambiar al ingresar.

## Carpetas

| Carpeta | Contenido |
| --- | --- |
| `tutorias/` | Reservas, usuarios, formularios, pruebas y migraciones. |
| `tutorias_uts/` | Configuracion de Django. |
| `templates/` | Paginas y plantillas de correo. |
| `static/` | Estilos, JavaScript, logo y librerias. |
| `deploy/` | Archivos para instalar y mantener el sistema en Linux. |
| `base_datos/` | Copia inicial de la base y pasos para importarla. |

Las carpetas `tutorias` y `tutorias_uts` conservan el nombre inicial del proyecto.
No hace falta cambiarlas para usar el sistema de laboratorios.

## Abrirlo en Windows

Se necesita Python 3.12 o 3.13 y MySQL/MariaDB compatible con Django 5.2.
Abrir la carpeta en VS Code y usar su terminal de PowerShell.

Si es la primera instalacion:

```powershell
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Con Python 3.12, cambiar `-3.13` por `-3.12`.

El archivo `.env` guarda la conexion a la base y los datos del correo.
Si ya esta configurado, no hay que reemplazarlo por `.env.example`.

En otro equipo, importar primero `base_datos/laboratorios_inicial.sql` en una
base vacia y colocar su conexion en `.env`. Los pasos estan en
[base_datos/README.md](base_datos/README.md).

Para iniciar:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abrir http://127.0.0.1:8000/. Para procesar los avisos por correo,
dejar abierta otra terminal con:

```powershell
.\venv\Scripts\python.exe manage.py procesar_notificaciones
```

Si se empieza sin importar el SQL, crear el administrador con
`manage.py createsuperuser`. No hay una contrasena predeterminada.
Revisar la programacion antes de permitir reservas.

## Acceso del laboratorista

El coordinador entra a **Laboratoristas > Crear cuenta**, completa el nombre,
usuario, correo y una contrasena temporal. Debe entregar esos datos de forma
privada. El laboratorista usa la misma pagina de ingreso y cambia la clave
en su primer acceso (la temporal vence en 24 horas por defecto).

Su pantalla **Prestamos aprobados** muestra los horarios del dia, agrupados
por laboratorio. Puede consultar otra fecha, filtrar un laboratorio y abrir
el listado de estudiantes para ver sus datos, materia y aprobacion.
La agenda se actualiza cada 30 segundos mientras esta visible; tambien tiene
un boton para actualizar. Las cancelaciones dejan de aparecer.
Los estados Proxima, En curso y Finalizada dependen de la hora programada;
no registran que la puerta se haya abierto fisicamente.

El laboratorista solo consulta. El coordinador conserva la aprobacion y puede
editar, deshabilitar o restablecer el acceso desde **Laboratoristas**.
No se permite elegir este rol en el registro publico de estudiantes.

## Entrega al profesor

- [Instalacion en el servidor](ENTREGA_AL_DOCENTE.md).
- [Importacion de la base](base_datos/README.md).
- [Pruebas realizadas](base_datos/VERIFICACION.md).

Git no incluye `.env`, `.django-secret-key`, `venv`, caches ni respaldos
privados. Esos archivos siguen en el equipo local; no se borran al subir el
proyecto. El `.env` se entrega al profesor por un medio privado.

Mantener el repositorio privado: el SQL incluye la contrasena protegida de
`admin` (su hash), que debe cambiarse al instalarlo. No importar esa copia
sobre una base que ya tenga datos reales.

Falta instalar y probar el sistema en el servidor definitivo. `runserver`
es solo para uso local. Las licencias de las librerias estan en
`static/vendor`; el uso del logo UTS debe contar con autorizacion.
