# Base de datos para instalar el proyecto

## Que archivo se usa

- `laboratorios_inicial.sql`: es la base que se importa en phpMyAdmin.
- `laboratorios_inicial.sql.sha256`: comprueba que el SQL no cambio. No se
  importa ni se convierte en SQL cambiandole el nombre.
- `VERIFICACION.md`: resultados de las pruebas de esta copia.

El SQL trae las tablas, laboratorios, materias, semestres, clases y franjas.
Tambien incluye los permisos y el registro de migraciones de Django.
Solo conserva `admin`, sin datos de contacto, y pide cambiar la clave al entrar.

No lleva estudiantes, reservas, sesiones, avisos pendientes ni historiales
personales. Tampoco incluye las cuentas de MySQL ni la clave del correo.

Guarda el hash de la contrasena de `admin`, no la clave en texto.
Mantener el repositorio privado y cambiar esa clave al instalarlo.

## Importar con phpMyAdmin

1. Crear una base nueva y vacia con juego de caracteres `utf8mb4`. Para una
   prueba local puede llamarse `laboratorios_prueba_entrega`.
2. Seleccionarla en el panel izquierdo y abrir Importar.
3. Elegir `laboratorios_inicial.sql`, dejar el formato SQL y pulsar Importar.
4. Si aparece un error, guardar el mensaje y revisarlo antes de continuar.
5. Colocar la conexion de esa base en la configuracion del aplicativo y ejecutar
   `manage.py migrate` con el Python del entorno virtual.
6. Entrar con `admin`, cambiar la clave y revisar la programacion.

**No importar sobre la base que ya funciona en el computador ni sobre una base
con datos reales. El archivo contiene instrucciones que recrean las tablas.**

Para cambiar la clave desde la terminal, usar `manage.py changepassword admin`.
La clave se escribe cuando la terminal la pida, no dentro del comando.

## Importar desde Linux

Desde la carpeta del proyecto, con la base vacia ya creada:

```bash
sha256sum -c base_datos/laboratorios_inicial.sql.sha256
mariadb --host=127.0.0.1 --user=USUARIO_MIGRADOR --password \
  --default-character-set=utf8mb4 laboratorios \
  < base_datos/laboratorios_inicial.sql
```

Cambiar usuario y nombre de base por los del servidor. `--password` pide la
clave sin dejarla escrita en el comando. No usar `--force` para saltar errores.

La copia se genero con MariaDB 13.0.2. Hay que probarla con la version del
servidor porque puede haber diferencias con otras versiones de MariaDB o MySQL.
No hacer reemplazos generales en el SQL para intentar quitar un error.

## Volver a generar la copia

Solo hace falta si cambia la programacion antes de entregar.
Detener temporalmente el servidor local para evitar cambios durante la copia.
En PowerShell, desde la carpeta del proyecto:

```powershell
.\venv\Scripts\python.exe manage.py exportar_entrega --confirmar-copia-admin `
  --cliente 'C:\Program Files\MariaDB 13.0\bin\mariadb-dump.exe'
```

El comando genera el SQL y su comprobante sin borrar ni modificar la base
original. Copia la programacion y prepara el perfil de `admin` sin contactos.
No permite las claves conocidas de demostracion.

Esta copia es para la primera instalacion, no para respaldar el sistema en uso.
Cuando haya datos reales, guardar los respaldos aparte y fuera de GitHub.
