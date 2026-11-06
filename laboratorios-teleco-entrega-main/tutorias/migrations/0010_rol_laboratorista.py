from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tutorias", "0009_gestion_franjas")]

    operations = [
        migrations.AlterField(
            model_name="perfilusuario",
            name="rol",
            field=models.CharField(
                choices=[
                    ("COORDINADOR", "Coordinador"),
                    ("ESTUDIANTE", "Estudiante"),
                    ("LABORATORISTA", "Laboratorista"),
                ],
                default="ESTUDIANTE",
                max_length=20,
            ),
        ),
    ]
