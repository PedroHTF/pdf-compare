"""Monta o texto da Release no GitHub a partir do CHANGELOG.md.

Uso:  python -m tools.release_notes 0.3.0 notes/RELEASE.md

Pega a seção `## [versão]` do CHANGELOG.md e, dentro dela, os resumos
`### Resumo` (português) e `### Summary` (inglês), e preenche o modelo
.github/release-template.md (passos de download + o que mudou). Sem um dos
resumos, usa a seção inteira da versão no lugar dele.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
TEMPLATE = ROOT / ".github" / "release-template.md"


def version_section(changelog: str, version: str) -> str:
    """Texto da seção `## [versão]` (sem o título); vazio se não existir."""
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    return match.group(1).strip() if match else ""


def subsection(section: str, title: str) -> str:
    """Texto da subseção `### título` dentro da seção da versão; vazio se não existir."""
    match = re.search(rf"^### {re.escape(title)}[ \t]*\n(.*?)(?=^### |\Z)", section, re.M | re.S)
    return match.group(1).strip() if match else ""


def build_notes(version: str, changelog: str, template: str) -> str:
    section = version_section(changelog, version)
    resumo = subsection(section, "Resumo") or section or "—"
    summary = subsection(section, "Summary") or section or "—"
    return (template.replace("{version}", version)
            .replace("{resumo}", resumo)
            .replace("{summary}", summary)).strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    version, out = argv[1].lstrip("vV"), Path(argv[2])
    changelog = CHANGELOG.read_text(encoding="utf-8")
    if not version_section(changelog, version):
        print(f"Aviso: CHANGELOG.md não tem a seção ## [{version}]", file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_notes(version, changelog, TEMPLATE.read_text(encoding="utf-8")), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
