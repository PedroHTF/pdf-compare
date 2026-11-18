"""PDFs protegidos por senha: modelo e fluxo na interface."""

import fitz
import pytest

from app.model.session import DocumentSession, PasswordRequired, WrongPassword
from app.services.search import search_index
from app.services.text_index import DocumentIndex


@pytest.fixture
def locked(make_pdf):
    return make_pdf("secreto.pdf", texts=["Contrato confidencial", "Anexo"], user_pw="segredo", owner_pw="dono")


# --- modelo -----------------------------------------------------------------
def test_locked_pdf_requires_password(locked):
    with pytest.raises(PasswordRequired):
        DocumentSession.open(locked)


def test_wrong_password_is_rejected(locked):
    with pytest.raises(WrongPassword):
        DocumentSession.open(locked, password="errada")


def test_correct_password_opens_and_text_is_searchable(locked):
    session = DocumentSession.open(locked, password="segredo")
    assert session.encrypted and session.page_count == 2
    index = DocumentIndex.build(session.doc)
    assert len(search_index(index, "confidencial")) == 1
    session.close()


def test_owner_password_also_opens(locked):
    session = DocumentSession.open(locked, password="dono")
    assert session.page_count == 2
    session.close()


def test_permissions_only_pdf_opens_without_asking(make_pdf):
    path = make_pdf("restrito.pdf", texts=["texto"], owner_pw="dono")
    probe = fitz.open(str(path))
    assert "AES" in (probe.metadata.get("encryption") or "")   # está criptografado...
    probe.close()
    session = DocumentSession.open(path)
    assert session.page_count == 1 and not session.encrypted
    session.close()


# --- interface --------------------------------------------------------------
def _answers(window, *answers):
    """Simula o que o usuário digita na janela de senha (None = cancelar)."""
    calls = []
    queue = list(answers)

    def ask(name, attempt):
        calls.append((name, attempt))
        return queue.pop(0)

    window._ask_password = ask
    return calls


def test_ui_opens_with_correct_password(window, locked, make_pdf):
    calls = _answers(window, "segredo")
    window.add_files([make_pdf("aberto.pdf", 1), locked])
    assert [s.name for s in window.sessions] == ["aberto.pdf", "secreto.pdf"]
    assert calls == [("secreto.pdf", 1)]
    assert window.notifications == []
    assert "senha" in window.panes[1].name_label.toolTip()


def test_ui_retries_after_wrong_password(window, locked):
    calls = _answers(window, "errada", "segredo")
    window.add_files([locked])
    assert len(window.sessions) == 1
    assert [a for _, a in calls] == [1, 2]


def test_ui_cancel_skips_only_that_file(window, locked, make_pdf):
    _answers(window, None)
    window.add_files([locked, make_pdf("aberto.pdf", 1)])
    assert [s.name for s in window.sessions] == ["aberto.pdf"]
    assert window.notifications == []           # cancelar não é erro: só aviso na barra de status
    assert "secreto.pdf" in window.statusBar().currentMessage()


def test_ui_gives_up_after_three_wrong_passwords(window, locked):
    calls = _answers(window, "a", "b", "c")
    window.add_files([locked])
    assert window.sessions == []
    assert len(calls) == 3
    kind, _title, text = window.notifications[0]
    assert kind == "warning" and "Senha incorreta" in text


def test_password_is_not_saved_in_settings(window, locked):
    _answers(window, "segredo")
    window.add_files([locked])
    window.close()
    window.settings.sync()
    stored = " ".join(str(window.settings.value(k)) for k in window.settings.allKeys())
    assert "segredo" not in stored
