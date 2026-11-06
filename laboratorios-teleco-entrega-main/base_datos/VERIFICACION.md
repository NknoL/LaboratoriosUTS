# Pruebas de la copia de entrega

Fecha de revision: 6 de octubre de 2026.

La copia se importo en una base temporal de MariaDB para comprobar que se
pudiera restaurar. La base original del computador no se modifico.

## Datos encontrados al importar

| Dato | Cantidad |
| --- | ---: |
| Administradores activos | 1 (`admin`) |
| Otros usuarios | 0 |
| Reservas | 0 |
| Laboratorios | 6 |
| Materias | 91 |
| Semestres | 2 |
| Clases fijas | 76 |
| Franjas | 802 |
| Relaciones entre materias y laboratorios | 28 |

## Que se reviso

- `admin` conserva su clave como hash, no como texto. Su perfil no tiene
  contactos y al entrar pide cambiar la clave.
- Las tablas de sesiones, avisos, intentos de acceso e historiales quedaron vacias.
- Las migraciones y las comprobaciones de Django pasaron en la base restaurada.
- Se conservo la columna que evita repetir correos registrados.
- Pasaron las 70 pruebas automatizadas y la revision de codigo no reporto errores.
- Los archivos preparados para Git no incluian `.env`, la clave de Django,
  la contrasena del correo ni la conexion real a la base.
- El comprobante SHA256 coincidio con el SQL incluido en Git.

Al terminar se eliminaron las bases temporales de las pruebas.
El SQL conserva el hash de `admin`: mantenerlo privado y cambiar esa clave
en la instalacion definitiva.

## Que falta probar

Estas pruebas fueron locales. Falta revisar la importacion con la version de
MySQL/MariaDB del servidor, instalar Nginx y Gunicorn, configurar HTTPS y
comprobar los servicios y los correos desde alli.

Antes de dar acceso a los estudiantes, seguir las comprobaciones de
[ENTREGA_AL_DOCENTE.md](../ENTREGA_AL_DOCENTE.md).
