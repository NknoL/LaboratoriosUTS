import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations

# Asociación inicial sugerida; coordinación puede ajustarla desde la aplicación.
LABORATORIOS = ["Telecomunicaciones", "Radiocomunicaciones", "Cisco", "IoT", "Telemática"]
MATERIAS = [
    ("TGST103", "Medios de Transmisión", "TEC", 1, [1, 2]),
    ("TGST104", "Lógica y Algoritmos", "TEC", 1, [4]),
    ("TGST203", "Análisis de Circuitos Eléctricos I", "TEC", 2, [1]),
    ("TGST204", "Laboratorio de Medidas y Circuitos Eléctricos", "TEC", 2, [1]),
    ("TGST205", "Telemática I", "TEC", 2, [3, 5]),
    ("TGST206", "Programación", "TEC", 2, [4]),
    ("TGST302", "Análisis de Circuitos Eléctricos II", "TEC", 3, [1]),
    ("TGST303", "Electrónica I", "TEC", 3, [1, 4]),
    ("TGST304", "Telemática II", "TEC", 3, [3, 5]),
    ("TGST402", "Comunicaciones Análogas", "TEC", 4, [1, 2]),
    ("TGST403", "Laboratorio de Comunicaciones Análogas", "TEC", 4, [2]),
    ("TGST404", "Electrónica II", "TEC", 4, [1, 4]),
    ("TGST405", "Laboratorio de Electrónica", "TEC", 4, [4]),
    ("TGST406", "Telemática III", "TEC", 4, [3, 5]),
    ("TGST501", "Programación WEB", "TEC", 5, [4, 5]),
    ("TGST502", "Comunicaciones Digitales I", "TEC", 5, [1, 2]),
    ("TGST503", "Electrónica Digital", "TEC", 5, [4]),
    ("TGST504", "Laboratorio de Electrónica Digital", "TEC", 5, [4]),
    ("TGST603", "Comunicaciones Digitales II", "TEC", 6, [1, 2]),
    ("TGST604", "Laboratorio de Comunicaciones Digitales", "TEC", 6, [1, 2]),
    ("TGST605", "Conmutación Digital", "TEC", 6, [1, 3]),
    ("INGTEL702", "Linux", "ING", 7, [5]),
    ("INGTEL802", "Señales y Sistemas", "ING", 8, [1, 2]),
    ("INGTEL803", "Bases de Datos", "ING", 8, [4, 5]),
    ("INGTEL804", "Administración de Redes", "ING", 8, [3, 5]),
    ("INGTEL805", "Servicios bajo Linux", "ING", 8, [5]),
    ("INGTEL901", "Comunicaciones Inalámbricas", "ING", 9, [2, 4]),
    ("INGTEL906", "Telefonía IP", "ING", 9, [3]),
    ("INGTEL1001", "Laboratorio de Comunicaciones Inalámbricas", "ING", 10, [2]),
    ("INGTEL1002", "Comunicaciones Avanzadas", "ING", 10, [1, 2]),
    ("INGTEL1003", "Programación de Dispositivos Móviles", "ING", 10, [4]),
    ("INGTEL1004", "Redes de Banda Ancha", "ING", 10, [1, 3]),
    ("INGTEL1005", "Seguridad en Redes", "ING", 10, [3, 5]),
]


def preparar_catalogo(apps, schema_editor):
    alias = schema_editor.connection.alias
    Materia = apps.get_model("tutorias", "Materia")
    Lab = apps.get_model("tutorias", "Laboratorio")
    Clase = apps.get_model("tutorias", "HorarioClase")
    Archivo = apps.get_model("tutorias", "ArchivoMigracion")
    codigos = [fila[0] for fila in MATERIAS]
    generales = Materia.objects.using(alias).exclude(codigo__in=codigos)
    clases = Clase.objects.using(alias).filter(materia__in=generales)
    Archivo.objects.using(alias).create(
        origen="ClasesNoTecnicas",
        datos=json.loads(json.dumps(list(clases.values()), cls=DjangoJSONEncoder)),
    )
    clases.delete()
    generales.update(tecnica=False, activa=False)
    labs = {}
    for numero, nombre in enumerate(LABORATORIOS, 1):
        lab = Lab.objects.using(alias).filter(nombre=f"Laboratorio {numero}").first()
        if lab:
            lab.nombre = f"Lab {numero}: {nombre}"
            lab.save(using=alias)
        else:
            lab, _ = Lab.objects.using(alias).get_or_create(
                nombre=f"Lab {numero}: {nombre}", defaults={"capacidad": 20}
            )
        labs[numero] = lab
    for codigo, nombre, nivel, semestre, numeros in MATERIAS:
        materia, _ = Materia.objects.using(alias).get_or_create(
            codigo=codigo,
            defaults={"nombre": nombre, "nivel": nivel, "semestre": semestre, "tecnica": True},
        )
        for numero in numeros:
            labs[numero].materias.add(materia)
    # Las clases técnicas existentes se conservan con su laboratorio real.
    for clase in Clase.objects.using(alias).all():
        clase.laboratorio.materias.add(clase.materia)


class Migration(migrations.Migration):
    dependencies = [("tutorias", "0002_archivomigracion_and_more")]
    operations = [migrations.RunPython(preparar_catalogo)]
