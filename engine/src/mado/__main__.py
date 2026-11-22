"""Runs the command line for `python -m mado` and the bundled mado-engine.exe."""

from mado.cli import app

if __name__ == "__main__":
    app(prog_name="mado")
