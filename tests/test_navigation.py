from app.model.session import DocumentSession
from app.services.navigation import NavigationController
from app.services.search import Hit


def _nav(*sessions):
    nav = NavigationController()
    nav.set_sessions(list(sessions))
    return nav


def _open(make_pdf, name, pages):
    return DocumentSession.open(make_pdf(name, pages))


def test_step_moves_all_documents_together(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 3), _open(make_pdf, "b.pdf", 3))
    nav.step(+1)
    assert (nav.page_for(0), nav.page_for(1)) == (1, 1)
    nav.step(-1)
    assert (nav.page_for(0), nav.page_for(1)) == (0, 0)
    assert nav.at_start


def test_position_is_clamped_and_short_document_ends(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 2), _open(make_pdf, "b.pdf", 4))
    nav.go_to(100)
    assert nav.at_end
    assert nav.page_for(0) is None      # A já terminou
    assert nav.page_for(1) == 3
    nav.step(-10)
    assert nav.current == 0


def test_step_pane_moves_only_that_document_and_keeps_alignment(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 5), _open(make_pdf, "b.pdf", 5))
    nav.step_pane(1, +2)
    assert (nav.page_for(0), nav.page_for(1)) == (0, 2)
    nav.step(+1)                         # depois, avançam juntos mantendo a diferença
    assert (nav.page_for(0), nav.page_for(1)) == (1, 3)
    assert not nav.is_aligned


def test_step_pane_from_blank_area_goes_to_nearest_page(make_pdf):
    a, b = _open(make_pdf, "a.pdf", 5), _open(make_pdf, "b.pdf", 5)
    nav = _nav(a, b)
    b.offset = 3                         # B começa 3 posições depois
    assert nav.page_for(1) is None
    nav.step_pane(1, +1)
    assert nav.page_for(1) == 0
    assert nav.current == 0              # os outros não se movem


def test_go_first_reaches_document_shifted_backwards(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 3), _open(make_pdf, "b.pdf", 3))
    nav.step_pane(0, +2)                 # A adiantado em 2 páginas
    nav.go_first()
    assert nav.page_for(0) == 0
    assert nav.page_for(1) is None       # B ainda não começou nessa posição


def test_show_page_clamps_to_document(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 3), _open(make_pdf, "b.pdf", 3))
    nav.show_page(0, 99)
    assert nav.page_for(0) == 2


def test_realign_resets_offsets_to_first_visible_page(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 5), _open(make_pdf, "b.pdf", 5))
    nav.step(+1)
    nav.step_pane(1, +2)
    nav.realign()
    assert nav.is_aligned
    assert (nav.page_for(0), nav.page_for(1)) == (1, 1)


def _hits(*pages):
    return [Hit(page=p, rects=((0, 0, 1, 1),)) for p in pages]


def test_step_hit_cycles_within_one_document(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 5), _open(make_pdf, "b.pdf", 5))
    nav.set_hits([[], _hits(1, 3, 3)])
    pages = []
    for _ in range(4):
        assert nav.step_hit(1, +1)
        pages.append((nav.page_for(1), nav.hit_index[1]))
    assert pages == [(1, 0), (3, 1), (3, 2), (1, 0)]
    assert nav.page_for(0) == 0          # o outro PDF não se move
    assert nav.step_hit(0, +1) is False  # sem ocorrências


def test_step_hit_restarts_from_shown_page_after_manual_move(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 6))
    nav.set_hits([_hits(0, 2, 4)])
    nav.step_hit(0, +1)                  # vai para a página 0
    nav.go_to(3)                         # usuário avança manualmente
    nav.step_hit(0, +1)
    assert nav.page_for(0) == 4
    nav.go_to(3)
    nav.step_hit(0, -1)
    assert nav.page_for(0) == 2


def test_step_hit_all_moves_each_document_to_its_own_hit(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 5), _open(make_pdf, "b.pdf", 5), _open(make_pdf, "c.pdf", 5))
    nav.set_hits([_hits(2), _hits(4), []])
    assert nav.step_hit_all(+1)
    assert (nav.page_for(0), nav.page_for(1), nav.page_for(2)) == (2, 4, 0)
    assert nav.total_hits == 2


def test_page_hits_groups_by_page(make_pdf):
    nav = _nav(_open(make_pdf, "a.pdf", 5))
    nav.set_hits([_hits(1, 1, 3)])
    assert len(nav.page_hits(0, 1)) == 2
    assert nav.page_hits(0, 2) == []
    assert nav.page_hits(0, None) == []
