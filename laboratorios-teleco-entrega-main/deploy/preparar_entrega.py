"""Empaqueta solamente fuentes y documentacion; no modifica la carpeta de trabajo."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARPETAS = ("tutorias", "tutorias_uts", "templates", "static", "deploy", "docs")
ARCHIVOS = ("manage.py", "requirements.txt", "README.md", ".env.example")
EXTENSIONES = {
    ".py",
    ".html",
    ".css",
    ".js",
    ".png",
    ".svg",
    ".woff",
    ".woff2",
    ".ico",
    ".txt",
    ".md",
    ".docx",
    ".conf",
    ".service",
    ".timer",
    ".sh",
    ".example",
}


def seleccion():
    rutas = [ROOT / nombre for nombre in ARCHIVOS]
    for carpeta in CARPETAS:
        for path in (ROOT / carpeta).rglob("*"):
            relativa = path.relative_to(ROOT)
            if any(
                parte.startswith(".") or parte in {"__pycache__", "venv", "node_modules"}
                for parte in relativa.parts
            ):
                continue
            if path.is_file() and (
                path.suffix in EXTENSIONES or path.name.upper().startswith("LICENSE")
            ):
                rutas.append(path)
    for path in sorted(set(rutas)):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("La entrega no admite enlaces fuera de la carpeta de trabajo.")
        if not path.is_file():
            raise FileNotFoundError(path.name)
        yield path


def main():
    destino = ROOT / "dist"
    destino.mkdir(exist_ok=True)
    final = destino / "laboratorios-entrega.tar.gz"
    temporal = destino / "laboratorios-entrega.tar.gz.part"
    manifiesto = {}
    try:
        with tarfile.open(temporal, "w:gz") as paquete:
            for path in seleccion():
                nombre = path.relative_to(ROOT).as_posix()
                contenido = path.read_bytes()
                if path.suffix in {".sh", ".service", ".timer", ".conf"}:
                    contenido = contenido.replace(b"\r\n", b"\n")
                manifiesto[nombre] = hashlib.sha256(contenido).hexdigest()
                info = tarfile.TarInfo(nombre)
                info.size = len(contenido)
                info.mode = 0o644
                paquete.addfile(info, io.BytesIO(contenido))
            datos = json.dumps(manifiesto, indent=2, ensure_ascii=True).encode()
            info = tarfile.TarInfo("MANIFIESTO_SHA256.json")
            info.size = len(datos)
            info.mode = 0o644
            paquete.addfile(info, io.BytesIO(datos))
        with tarfile.open(temporal, "r:gz") as paquete:
            for nombre, esperado in manifiesto.items():
                with paquete.extractfile(nombre) as entrada:
                    assert hashlib.sha256(entrada.read()).hexdigest() == esperado
        temporal.replace(final)
    finally:
        temporal.unlink(missing_ok=True)
    suma = hashlib.sha256(final.read_bytes()).hexdigest()
    final.with_suffix(".gz.sha256").write_text(f"{suma}  {final.name}\n", encoding="ascii")
    print(f"Entrega verificada: {final}")
    print(f"Archivos incluidos: {len(manifiesto)}. Sin .env privado, bases, respaldos ni venv.")


if __name__ == "__main__":
    main()
