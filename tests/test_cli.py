"""Pruebas del CLI que no necesitan IA."""
from loopeable.cli import main
from loopeable.verificar import detectar_pruebas


def _proyecto(tmp_path, extra=""):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"x\"\n")  # para que haya algo que detectar
    (tmp_path / "loopeable.toml").write_text('objetivo = "algo"\n' + extra)
    return tmp_path


def test_pruebas_muestra_las_de_hecho_si_estan_configuradas(tmp_path, capsys):
    r = _proyecto(tmp_path, '[hecho]\npruebas = ["make check"]\n')
    main(["-C", str(r), "pruebas"])
    salida = capsys.readouterr()
    assert salida.out == "make check\n"          # lo mismo que usará una corrida, y nada más en stdout
    assert "cargo test" not in salida.out
    assert "[hecho] pruebas" in salida.err      # el origen va a stderr


def test_pruebas_sin_hecho_pruebas_muestra_lo_detectado(tmp_path, capsys):
    r = _proyecto(tmp_path)
    main(["-C", str(r), "pruebas"])
    assert capsys.readouterr().out == "\n".join(detectar_pruebas(r)) + "\n"


def test_pruebas_sin_loopeable_toml_muestra_lo_detectado(tmp_path, capsys):
    (tmp_path / "Cargo.toml").write_text("")
    main(["-C", str(tmp_path), "pruebas"])
    assert capsys.readouterr().out == "\n".join(detectar_pruebas(tmp_path)) + "\n"
